from typing import List, Dict, Any, Optional, Callable, Union
from datetime import datetime
import stripe

from .database.postgres import PostgresClient
from .types import StripeSyncConfig, Sync, SyncBackfill, SyncBackfillParams
from .schemas import (
    charge_schema,
    checkout_session_schema,
    checkout_session_line_item_schema,
    credit_note_schema,
    customer_schema,
    customer_deleted_schema,
    dispute_schema,
    invoice_schema,
    plan_schema,
    price_schema,
    product_schema,
    payment_intent_schema,
    payment_methods_schema,
    setup_intents_schema,
    tax_id_schema,
    subscription_item_schema,
    subscription_schedule_schema,
    subscription_schema,
    early_fraud_warning_schema,
    review_schema,
    refund_schema,
    active_entitlement_schema,
    feature_schema,
    invoice_payment_schema,
)


def get_unique_ids(entries: List[Dict[str, Any]], key: str) -> List[str]:
    """Extract unique IDs from a list of entries.

    Args:
        entries: List of entity dictionaries
        key: Key to extract IDs from

    Returns:
        List of unique IDs as strings
    """
    unique_set = set()
    for entry in entries:
        value = entry.get(key)
        if value:
            unique_set.add(str(value))
    return list(unique_set)


def chunk_array(array: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split an array into chunks.

    Args:
        array: Array to split
        chunk_size: Size of each chunk

    Returns:
        List of chunks
    """
    result = []
    for i in range(0, len(array), chunk_size):
        result.append(array[i:i + chunk_size])
    return result


DEFAULT_SCHEMA = 'stripe'


class StripeSync:
    """Main class for syncing Stripe data to PostgreSQL."""

    def __init__(self, config: StripeSyncConfig):
        """Initialize StripeSync.

        Args:
            config: Configuration for Stripe and PostgreSQL
        """
        self.config = config
        self.config.schema = config.schema or DEFAULT_SCHEMA

        # Initialize Stripe client
        stripe.api_key = config.stripe_secret_key
        if config.stripe_api_version:
            stripe.api_version = config.stripe_api_version
        stripe.set_app_info('Stripe Postgres Sync')

        if config.logger:
            config.logger.info(
                f'StripeSync initialized with auto_expand_lists={config.auto_expand_lists}, '
                f'stripe_api_version={config.stripe_api_version}'
            )

        # Initialize PostgreSQL client
        pool_config = config.pool_config or {}
        pool_config['application_name'] = 'stripe-sync-engine'

        if config.database_url:
            pool_config['connection_string'] = config.database_url

        if config.max_postgres_connections:
            pool_config['max'] = config.max_postgres_connections

        if pool_config.get('max') is None:
            pool_config['max'] = 10

        self.postgres_client = PostgresClient({
            'schema': self.config.schema,
            'pool_config': pool_config
        })

    def process_webhook(
        self,
        payload: Union[bytes, str],
        signature: Optional[str]
    ) -> None:
        """Process a Stripe webhook event.

        Args:
            payload: Webhook payload
            signature: Stripe signature for verification
        """
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            self.config.stripe_webhook_secret
        )

        return self.process_event(event)

    def process_event(self, event: stripe.Event) -> None:
        """Process a Stripe event.

        Args:
            event: Stripe event object
        """
        event_type = event['type']

        # Charge events
        if event_type in [
            'charge.captured', 'charge.expired', 'charge.failed',
            'charge.pending', 'charge.refunded', 'charge.succeeded', 'charge.updated'
        ]:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.Charge.retrieve(id),
                lambda charge: charge.get('status') in ['failed', 'succeeded']
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for charge {entity['id']}"
                )

            self._upsert_charges(
                [entity],
                False,
                self._get_sync_timestamp(event, refetched)
            )

        # Customer deleted
        elif event_type == 'customer.deleted':
            customer = {
                'id': event['data']['object']['id'],
                'object': 'customer',
                'deleted': True
            }

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for customer {customer['id']}"
                )

            self._upsert_customers([customer], self._get_sync_timestamp(event, False))

        # Checkout session events
        elif event_type in [
            'checkout.session.async_payment_failed',
            'checkout.session.async_payment_succeeded',
            'checkout.session.completed',
            'checkout.session.expired'
        ]:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.checkout.Session.retrieve(id)
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for checkout session {entity['id']}"
                )

            self._upsert_checkout_sessions(
                [entity],
                False,
                self._get_sync_timestamp(event, refetched)
            )

        # Customer events
        elif event_type in ['customer.created', 'customer.updated']:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.Customer.retrieve(id),
                lambda customer: customer.get('deleted') == True
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for customer {entity['id']}"
                )

            self._upsert_customers([entity], self._get_sync_timestamp(event, refetched))

        # Subscription events
        elif event_type in [
            'customer.subscription.created', 'customer.subscription.deleted',
            'customer.subscription.paused', 'customer.subscription.pending_update_applied',
            'customer.subscription.pending_update_expired', 'customer.subscription.trial_will_end',
            'customer.subscription.resumed', 'customer.subscription.updated'
        ]:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.Subscription.retrieve(id),
                lambda sub: sub.get('status') in ['canceled', 'incomplete_expired']
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for subscription {entity['id']}"
                )

            self._upsert_subscriptions(
                [entity],
                False,
                self._get_sync_timestamp(event, refetched)
            )

        # Tax ID events
        elif event_type in ['customer.tax_id.updated', 'customer.tax_id.created']:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.TaxId.retrieve(id)
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for taxId {entity['id']}"
                )

            self._upsert_tax_ids([entity], False, self._get_sync_timestamp(event, refetched))

        elif event_type == 'customer.tax_id.deleted':
            tax_id = event['data']['object']

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for taxId {tax_id['id']}"
                )

            self._delete_tax_id(tax_id['id'])

        # Invoice events
        elif event_type in [
            'invoice.created', 'invoice.deleted', 'invoice.finalized',
            'invoice.finalization_failed', 'invoice.paid', 'invoice.payment_action_required',
            'invoice.payment_failed', 'invoice.payment_succeeded', 'invoice.upcoming',
            'invoice.sent', 'invoice.voided', 'invoice.marked_uncollectible', 'invoice.updated'
        ]:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.Invoice.retrieve(id),
                lambda inv: inv.get('status') == 'void'
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for invoice {entity['id']}"
                )

            self._upsert_invoices([entity], False, self._get_sync_timestamp(event, refetched))

        # Product events
        elif event_type in ['product.created', 'product.updated']:
            try:
                entity, refetched = self._fetch_or_use_webhook_data(
                    event['data']['object'],
                    lambda id: stripe.Product.retrieve(id)
                )

                if self.config.logger:
                    self.config.logger.info(
                        f"Received webhook {event['id']}: {event_type} for product {entity['id']}"
                    )

                self._upsert_products([entity], self._get_sync_timestamp(event, refetched))
            except stripe.error.InvalidRequestError as err:
                if err.code == 'resource_missing':
                    self._delete_product(event['data']['object']['id'])
                else:
                    raise

        elif event_type == 'product.deleted':
            product = event['data']['object']

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for product {product['id']}"
                )

            self._delete_product(product['id'])

        # Price events
        elif event_type in ['price.created', 'price.updated']:
            try:
                entity, refetched = self._fetch_or_use_webhook_data(
                    event['data']['object'],
                    lambda id: stripe.Price.retrieve(id)
                )

                if self.config.logger:
                    self.config.logger.info(
                        f"Received webhook {event['id']}: {event_type} for price {entity['id']}"
                    )

                self._upsert_prices([entity], False, self._get_sync_timestamp(event, refetched))
            except stripe.error.InvalidRequestError as err:
                if err.code == 'resource_missing':
                    self._delete_price(event['data']['object']['id'])
                else:
                    raise

        elif event_type == 'price.deleted':
            price = event['data']['object']

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for price {price['id']}"
                )

            self._delete_price(price['id'])

        # Plan events
        elif event_type in ['plan.created', 'plan.updated']:
            try:
                entity, refetched = self._fetch_or_use_webhook_data(
                    event['data']['object'],
                    lambda id: stripe.Plan.retrieve(id)
                )

                if self.config.logger:
                    self.config.logger.info(
                        f"Received webhook {event['id']}: {event_type} for plan {entity['id']}"
                    )

                self._upsert_plans([entity], False, self._get_sync_timestamp(event, refetched))
            except stripe.error.InvalidRequestError as err:
                if err.code == 'resource_missing':
                    self._delete_plan(event['data']['object']['id'])
                else:
                    raise

        elif event_type == 'plan.deleted':
            plan = event['data']['object']

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for plan {plan['id']}"
                )

            self._delete_plan(plan['id'])

        # Setup intent events
        elif event_type in [
            'setup_intent.canceled', 'setup_intent.created',
            'setup_intent.requires_action', 'setup_intent.setup_failed', 'setup_intent.succeeded'
        ]:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.SetupIntent.retrieve(id),
                lambda si: si.get('status') in ['canceled', 'succeeded']
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for setupIntent {entity['id']}"
                )

            self._upsert_setup_intents(
                [entity],
                False,
                self._get_sync_timestamp(event, refetched)
            )

        # Subscription schedule events
        elif event_type in [
            'subscription_schedule.aborted', 'subscription_schedule.canceled',
            'subscription_schedule.completed', 'subscription_schedule.created',
            'subscription_schedule.expiring', 'subscription_schedule.released',
            'subscription_schedule.updated'
        ]:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.SubscriptionSchedule.retrieve(id),
                lambda ss: ss.get('status') in ['canceled', 'completed']
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for subscriptionSchedule {entity['id']}"
                )

            self._upsert_subscription_schedules(
                [entity],
                False,
                self._get_sync_timestamp(event, refetched)
            )

        # Payment method events
        elif event_type in [
            'payment_method.attached', 'payment_method.automatically_updated',
            'payment_method.detached', 'payment_method.updated'
        ]:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.PaymentMethod.retrieve(id)
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for paymentMethod {entity['id']}"
                )

            self._upsert_payment_methods(
                [entity],
                False,
                self._get_sync_timestamp(event, refetched)
            )

        # Dispute events
        elif event_type in [
            'charge.dispute.created', 'charge.dispute.funds_reinstated',
            'charge.dispute.funds_withdrawn', 'charge.dispute.updated', 'charge.dispute.closed'
        ]:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.Dispute.retrieve(id),
                lambda d: d.get('status') in ['won', 'lost']
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for dispute {entity['id']}"
                )

            self._upsert_disputes([entity], False, self._get_sync_timestamp(event, refetched))

        # Payment intent events
        elif event_type in [
            'payment_intent.amount_capturable_updated', 'payment_intent.canceled',
            'payment_intent.created', 'payment_intent.partially_funded',
            'payment_intent.payment_failed', 'payment_intent.processing',
            'payment_intent.requires_action', 'payment_intent.succeeded'
        ]:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.PaymentIntent.retrieve(id),
                lambda pi: pi.get('status') in ['canceled', 'succeeded']
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for paymentIntent {entity['id']}"
                )

            self._upsert_payment_intents(
                [entity],
                False,
                self._get_sync_timestamp(event, refetched)
            )

        # Credit note events
        elif event_type in ['credit_note.created', 'credit_note.updated', 'credit_note.voided']:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.CreditNote.retrieve(id),
                lambda cn: cn.get('status') == 'void'
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for creditNote {entity['id']}"
                )

            self._upsert_credit_notes(
                [entity],
                False,
                self._get_sync_timestamp(event, refetched)
            )

        # Early fraud warning events
        elif event_type in ['radar.early_fraud_warning.created', 'radar.early_fraud_warning.updated']:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.radar.EarlyFraudWarning.retrieve(id)
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for earlyFraudWarning {entity['id']}"
                )

            self._upsert_early_fraud_warning(
                [entity],
                False,
                self._get_sync_timestamp(event, refetched)
            )

        # Refund events
        elif event_type in ['refund.created', 'refund.failed', 'refund.updated', 'charge.refund.updated']:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.Refund.retrieve(id)
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for refund {entity['id']}"
                )

            self._upsert_refunds([entity], False, self._get_sync_timestamp(event, refetched))

        # Review events
        elif event_type in ['review.closed', 'review.opened']:
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.Review.retrieve(id)
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for review {entity['id']}"
                )

            self._upsert_reviews([entity], False, self._get_sync_timestamp(event, refetched))

        # Entitlements events
        elif event_type == 'entitlements.active_entitlement_summary.updated':
            summary = event['data']['object']
            entitlements = summary['entitlements']
            refetched = False

            if self.config.revalidate_objects_via_stripe_api and \
               'entitlements' in self.config.revalidate_objects_via_stripe_api:
                result = stripe.entitlements.ActiveEntitlement.list(customer=summary['customer'])
                entitlements = result
                refetched = True

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for customer {summary['customer']}"
                )

            self._delete_removed_active_entitlements(
                summary['customer'],
                [e['id'] for e in entitlements['data']]
            )
            self._upsert_active_entitlements(
                summary['customer'],
                entitlements['data'],
                False,
                self._get_sync_timestamp(event, refetched)
            )

        # Invoice payment events
        elif event_type == 'invoice_payment.paid':
            entity, refetched = self._fetch_or_use_webhook_data(
                event['data']['object'],
                lambda id: stripe.InvoicePayment.retrieve(id)
            )

            if self.config.logger:
                self.config.logger.info(
                    f"Received webhook {event['id']}: {event_type} for invoicePayment {entity['id']}"
                )

            self._upsert_invoice_payments(
                [entity],
                False,
                self._get_sync_timestamp(event, refetched)
            )

        else:
            raise Exception('Unhandled webhook event')

    def _get_sync_timestamp(self, event: stripe.Event, refetched: bool) -> str:
        """Get sync timestamp for an event.

        Args:
            event: Stripe event
            refetched: Whether the entity was refetched from Stripe

        Returns:
            ISO timestamp string
        """
        if refetched:
            return datetime.utcnow().isoformat()
        return datetime.fromtimestamp(event['created']).isoformat()

    def _should_refetch_entity(self, entity: Dict[str, Any]) -> bool:
        """Check if an entity should be refetched from Stripe.

        Args:
            entity: Entity object

        Returns:
            True if entity should be refetched
        """
        if not self.config.revalidate_objects_via_stripe_api:
            return False
        return entity.get('object') in self.config.revalidate_objects_via_stripe_api

    def _fetch_or_use_webhook_data(
        self,
        entity: Dict[str, Any],
        fetch_fn: Callable[[str], Any],
        entity_in_final_state: Optional[Callable[[Dict[str, Any]], bool]] = None
    ) -> tuple[Dict[str, Any], bool]:
        """Fetch entity from Stripe or use webhook data.

        Args:
            entity: Entity from webhook
            fetch_fn: Function to fetch entity from Stripe
            entity_in_final_state: Function to check if entity is in final state

        Returns:
            Tuple of (entity, refetched)
        """
        if not entity.get('id'):
            return (entity, False)

        # Optimization: avoid re-fetching if in final state
        if entity_in_final_state and entity_in_final_state(entity):
            return (entity, False)

        if self._should_refetch_entity(entity):
            fetched_entity = fetch_fn(entity['id'])
            return (fetched_entity, True)

        return (entity, False)

    def sync_single_entity(self, stripe_id: str) -> None:
        """Sync a single Stripe entity by ID.

        Args:
            stripe_id: Stripe entity ID (e.g., cus_xxx, prod_xxx)
        """
        if stripe_id.startswith('cus_'):
            customer = stripe.Customer.retrieve(stripe_id)
            if customer and not customer.get('deleted'):
                self._upsert_customers([customer])

        elif stripe_id.startswith('in_'):
            invoice = stripe.Invoice.retrieve(stripe_id)
            self._upsert_invoices([invoice])

        elif stripe_id.startswith('price_'):
            price = stripe.Price.retrieve(stripe_id)
            self._upsert_prices([price])

        elif stripe_id.startswith('prod_'):
            product = stripe.Product.retrieve(stripe_id)
            self._upsert_products([product])

        elif stripe_id.startswith('sub_'):
            subscription = stripe.Subscription.retrieve(stripe_id)
            self._upsert_subscriptions([subscription])

        elif stripe_id.startswith('seti_'):
            setup_intent = stripe.SetupIntent.retrieve(stripe_id)
            self._upsert_setup_intents([setup_intent])

        elif stripe_id.startswith('pm_'):
            payment_method = stripe.PaymentMethod.retrieve(stripe_id)
            self._upsert_payment_methods([payment_method])

        elif stripe_id.startswith('dp_') or stripe_id.startswith('du_'):
            dispute = stripe.Dispute.retrieve(stripe_id)
            self._upsert_disputes([dispute])

        elif stripe_id.startswith('ch_'):
            charge = stripe.Charge.retrieve(stripe_id)
            self._upsert_charges([charge], True)

        elif stripe_id.startswith('pi_'):
            payment_intent = stripe.PaymentIntent.retrieve(stripe_id)
            self._upsert_payment_intents([payment_intent])

        elif stripe_id.startswith('txi_'):
            tax_id = stripe.TaxId.retrieve(stripe_id)
            self._upsert_tax_ids([tax_id])

        elif stripe_id.startswith('cn_'):
            credit_note = stripe.CreditNote.retrieve(stripe_id)
            self._upsert_credit_notes([credit_note])

        elif stripe_id.startswith('issfr_'):
            early_fraud_warning = stripe.radar.EarlyFraudWarning.retrieve(stripe_id)
            self._upsert_early_fraud_warning([early_fraud_warning])

        elif stripe_id.startswith('prv_'):
            review = stripe.Review.retrieve(stripe_id)
            self._upsert_reviews([review])

        elif stripe_id.startswith('re_'):
            refund = stripe.Refund.retrieve(stripe_id)
            self._upsert_refunds([refund])

        elif stripe_id.startswith('inpay_'):
            invoice_payment = stripe.InvoicePayment.retrieve(stripe_id)
            self._upsert_invoice_payments([invoice_payment])

        elif stripe_id.startswith('feat_'):
            feature = stripe.entitlements.Feature.retrieve(stripe_id)
            self._upsert_features([feature])

        elif stripe_id.startswith('cs_'):
            checkout_session = stripe.checkout.Session.retrieve(stripe_id)
            self._upsert_checkout_sessions([checkout_session])

    def sync_backfill(self, params: Optional[SyncBackfillParams] = None) -> SyncBackfill:
        """Backfill all Stripe data.

        Args:
            params: Optional parameters for backfill

        Returns:
            SyncBackfill object with results
        """
        obj = params.get('object') if params else None

        products = None
        prices = None
        customers = None
        checkout_sessions = None
        subscriptions = None
        subscription_schedules = None
        invoices = None
        setup_intents = None
        payment_methods = None
        disputes = None
        charges = None
        payment_intents = None
        plans = None
        tax_ids = None
        credit_notes = None
        early_fraud_warnings = None
        refunds = None

        if obj == 'all':
            products = self.sync_products(params)
            prices = self.sync_prices(params)
            plans = self.sync_plans(params)
            customers = self.sync_customers(params)
            subscriptions = self.sync_subscriptions(params)
            subscription_schedules = self.sync_subscription_schedules(params)
            invoices = self.sync_invoices(params)
            charges = self.sync_charges(params)
            setup_intents = self.sync_setup_intents(params)
            payment_methods = self.sync_payment_methods(params)
            payment_intents = self.sync_payment_intents(params)
            tax_ids = self.sync_tax_ids(params)
            credit_notes = self.sync_credit_notes(params)
            disputes = self.sync_disputes(params)
            early_fraud_warnings = self.sync_early_fraud_warnings(params)
            refunds = self.sync_refunds(params)
            checkout_sessions = self.sync_checkout_sessions(params)
        elif obj == 'customer':
            customers = self.sync_customers(params)
        elif obj == 'invoice':
            invoices = self.sync_invoices(params)
        elif obj == 'price':
            prices = self.sync_prices(params)
        elif obj == 'product':
            products = self.sync_products(params)
        elif obj == 'subscription':
            subscriptions = self.sync_subscriptions(params)
        elif obj == 'subscription_schedules':
            subscription_schedules = self.sync_subscription_schedules(params)
        elif obj == 'setup_intent':
            setup_intents = self.sync_setup_intents(params)
        elif obj == 'payment_method':
            payment_methods = self.sync_payment_methods(params)
        elif obj == 'dispute':
            disputes = self.sync_disputes(params)
        elif obj == 'charge':
            charges = self.sync_charges(params)
        elif obj == 'payment_intent':
            payment_intents = self.sync_payment_intents(params)
        elif obj == 'plan':
            plans = self.sync_plans(params)
        elif obj == 'tax_id':
            tax_ids = self.sync_tax_ids(params)
        elif obj == 'credit_note':
            credit_notes = self.sync_credit_notes(params)
        elif obj == 'early_fraud_warning':
            early_fraud_warnings = self.sync_early_fraud_warnings(params)
        elif obj == 'refund':
            refunds = self.sync_refunds(params)
        elif obj == 'checkout_sessions':
            checkout_sessions = self.sync_checkout_sessions(params)

        return {
            'products': products,
            'prices': prices,
            'customers': customers,
            'checkout_sessions': checkout_sessions,
            'subscriptions': subscriptions,
            'subscription_schedules': subscription_schedules,
            'invoices': invoices,
            'setup_intents': setup_intents,
            'payment_methods': payment_methods,
            'disputes': disputes,
            'charges': charges,
            'payment_intents': payment_intents,
            'plans': plans,
            'tax_ids': tax_ids,
            'credit_notes': credit_notes,
            'early_fraud_warnings': early_fraud_warnings,
            'refunds': refunds,
        }

    def sync_products(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync products from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing products')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.Product.list(**params),
            lambda products: self._upsert_products(products)
        )

    def sync_prices(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync prices from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing prices')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.Price.list(**params),
            lambda prices: self._upsert_prices(
                prices,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_plans(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync plans from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing plans')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.Plan.list(**params),
            lambda plans: self._upsert_plans(
                plans,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_customers(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync customers from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing customers')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.Customer.list(**params),
            lambda items: self._upsert_customers(items)
        )

    def sync_subscriptions(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync subscriptions from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing subscriptions')

        params = {'status': 'all', 'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.Subscription.list(**params),
            lambda items: self._upsert_subscriptions(
                items,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_subscription_schedules(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync subscription schedules from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing subscription schedules')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.SubscriptionSchedule.list(**params),
            lambda items: self._upsert_subscription_schedules(
                items,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_invoices(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync invoices from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing invoices')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.Invoice.list(**params),
            lambda items: self._upsert_invoices(
                items,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_charges(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync charges from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing charges')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.Charge.list(**params),
            lambda items: self._upsert_charges(
                items,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_setup_intents(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync setup intents from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing setup_intents')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.SetupIntent.list(**params),
            lambda items: self._upsert_setup_intents(
                items,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_payment_intents(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync payment intents from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing payment_intents')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.PaymentIntent.list(**params),
            lambda items: self._upsert_payment_intents(
                items,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_tax_ids(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync tax IDs from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing tax_ids')

        params = {'limit': 100}

        return self._fetch_and_upsert(
            lambda: stripe.TaxId.list(**params),
            lambda items: self._upsert_tax_ids(
                items,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_payment_methods(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync payment methods from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing payment method')

        # Get all customer IDs from database
        query = f'SELECT id FROM "{self.config.schema}"."customers" WHERE deleted <> true;'
        result = self.postgres_client.query(query, [])
        customer_ids = [row['id'] for row in result['rows']]

        if self.config.logger:
            self.config.logger.info(f'Getting payment methods for {len(customer_ids)} customers')

        synced = 0

        # Process in chunks of 10
        for customer_id_chunk in chunk_array(customer_ids, 10):
            chunk_results = []
            for customer_id in customer_id_chunk:
                sync_result = self._fetch_and_upsert(
                    lambda cid=customer_id: stripe.PaymentMethod.list(
                        limit=100,
                        customer=cid
                    ),
                    lambda items: self._upsert_payment_methods(
                        items,
                        sync_params.get('backfill_related_entities') if sync_params else None
                    )
                )
                chunk_results.append(sync_result)

            for result in chunk_results:
                synced += result['synced']

        return {'synced': synced}

    def sync_disputes(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync disputes from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.Dispute.list(**params),
            lambda items: self._upsert_disputes(
                items,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_early_fraud_warnings(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync early fraud warnings from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing early fraud warnings')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.radar.EarlyFraudWarning.list(**params),
            lambda items: self._upsert_early_fraud_warning(
                items,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_refunds(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync refunds from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing refunds')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.Refund.list(**params),
            lambda items: self._upsert_refunds(
                items,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def sync_credit_notes(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync credit notes from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing credit notes')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.CreditNote.list(**params),
            lambda credit_notes: self._upsert_credit_notes(credit_notes)
        )

    def sync_features(self, sync_params: Optional[Dict[str, Any]] = None) -> Sync:
        """Sync features from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing features')

        params = {'limit': 100}
        if sync_params and sync_params.get('pagination'):
            params.update(sync_params['pagination'])

        return self._fetch_and_upsert(
            lambda: stripe.entitlements.Feature.list(**params),
            lambda features: self._upsert_features(features)
        )

    def sync_entitlements(self, customer_id: str, sync_params: Optional[Dict[str, Any]] = None) -> Sync:
        """Sync entitlements for a customer from Stripe.

        Args:
            customer_id: Customer ID
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing entitlements')

        params = {'customer': customer_id, 'limit': 100}
        if sync_params and sync_params.get('pagination'):
            params.update(sync_params['pagination'])

        return self._fetch_and_upsert(
            lambda: stripe.entitlements.ActiveEntitlement.list(**params),
            lambda entitlements: self._upsert_active_entitlements(customer_id, entitlements)
        )

    def sync_checkout_sessions(self, sync_params: Optional[SyncBackfillParams] = None) -> Sync:
        """Sync checkout sessions from Stripe.

        Args:
            sync_params: Optional sync parameters

        Returns:
            Sync result
        """
        if self.config.logger:
            self.config.logger.info('Syncing checkout sessions')

        params = {'limit': 100}
        if sync_params and sync_params.get('created'):
            params['created'] = sync_params['created']

        return self._fetch_and_upsert(
            lambda: stripe.checkout.Session.list(**params),
            lambda items: self._upsert_checkout_sessions(
                items,
                sync_params.get('backfill_related_entities') if sync_params else None
            )
        )

    def _fetch_and_upsert(
        self,
        fetch: Callable[[], Any],
        upsert: Callable[[List[Any]], Any]
    ) -> Sync:
        """Fetch items from Stripe and upsert to database.

        Args:
            fetch: Function to fetch items from Stripe
            upsert: Function to upsert items to database

        Returns:
            Sync result
        """
        chunk_size = 250
        chunk = []
        synced = 0

        if self.config.logger:
            self.config.logger.info('Fetching items to sync from Stripe')

        # Fetch items from Stripe
        stripe_list = fetch()
        for item in stripe_list.auto_paging_iter():
            chunk.append(item)
            synced += 1
            if synced % 1000 == 0 and self.config.logger:
                self.config.logger.info(f'Synced {synced} items')

            if len(chunk) >= chunk_size:
                upsert(chunk)
                chunk = []

        if len(chunk) > 0:
            upsert(chunk)

        if self.config.logger:
            self.config.logger.info(f'Upserted {synced} items')

        return {'synced': synced}

    def _upsert_charges(
        self,
        charges: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert charges to database.

        Args:
            charges: List of charges
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted charges
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_customers(get_unique_ids(charges, 'customer'))
            self._backfill_invoices(get_unique_ids(charges, 'invoice'))

        self._expand_entity(
            charges,
            'refunds',
            lambda id: stripe.Refund.list(charge=id, limit=100)
        )

        return self.postgres_client.upsert_many_with_timestamp_protection(
            charges,
            'charges',
            charge_schema,
            sync_timestamp
        )

    def _backfill_charges(self, charge_ids: List[str]) -> None:
        """Backfill missing charges.

        Args:
            charge_ids: List of charge IDs
        """
        missing_ids = self.postgres_client.find_missing_entries('charges', charge_ids)
        charges = self._fetch_missing_entities(missing_ids, lambda id: stripe.Charge.retrieve(id))
        self._upsert_charges(charges)

    def _backfill_payment_intents(self, payment_intent_ids: List[str]) -> None:
        """Backfill missing payment intents.

        Args:
            payment_intent_ids: List of payment intent IDs
        """
        missing_ids = self.postgres_client.find_missing_entries('payment_intents', payment_intent_ids)
        payment_intents = self._fetch_missing_entities(
            missing_ids,
            lambda id: stripe.PaymentIntent.retrieve(id)
        )
        self._upsert_payment_intents(payment_intents)

    def _upsert_credit_notes(
        self,
        credit_notes: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert credit notes to database.

        Args:
            credit_notes: List of credit notes
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted credit notes
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_customers(get_unique_ids(credit_notes, 'customer'))
            self._backfill_invoices(get_unique_ids(credit_notes, 'invoice'))

        self._expand_entity(
            credit_notes,
            'lines',
            lambda id: stripe.CreditNote.list_line_items(id, limit=100)
        )

        return self.postgres_client.upsert_many_with_timestamp_protection(
            credit_notes,
            'credit_notes',
            credit_note_schema,
            sync_timestamp
        )

    def _upsert_checkout_sessions(
        self,
        checkout_sessions: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert checkout sessions to database.

        Args:
            checkout_sessions: List of checkout sessions
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted checkout sessions
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_customers(get_unique_ids(checkout_sessions, 'customer'))
            self._backfill_subscriptions(get_unique_ids(checkout_sessions, 'subscription'))
            self._backfill_payment_intents(get_unique_ids(checkout_sessions, 'payment_intent'))
            self._backfill_invoices(get_unique_ids(checkout_sessions, 'invoice'))

        # Upsert checkout sessions first
        rows = self.postgres_client.upsert_many_with_timestamp_protection(
            checkout_sessions,
            'checkout_sessions',
            checkout_session_schema,
            sync_timestamp
        )

        self._fill_checkout_sessions_line_items(
            [cs['id'] for cs in checkout_sessions],
            sync_timestamp
        )

        return rows

    def _upsert_early_fraud_warning(
        self,
        early_fraud_warnings: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert early fraud warnings to database.

        Args:
            early_fraud_warnings: List of early fraud warnings
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted early fraud warnings
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_payment_intents(get_unique_ids(early_fraud_warnings, 'payment_intent'))
            self._backfill_charges(get_unique_ids(early_fraud_warnings, 'charge'))

        return self.postgres_client.upsert_many_with_timestamp_protection(
            early_fraud_warnings,
            'early_fraud_warnings',
            early_fraud_warning_schema,
            sync_timestamp
        )

    def _upsert_refunds(
        self,
        refunds: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert refunds to database.

        Args:
            refunds: List of refunds
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted refunds
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_payment_intents(get_unique_ids(refunds, 'payment_intent'))
            self._backfill_charges(get_unique_ids(refunds, 'charge'))

        return self.postgres_client.upsert_many_with_timestamp_protection(
            refunds,
            'refunds',
            refund_schema,
            sync_timestamp
        )

    def _upsert_reviews(
        self,
        reviews: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert reviews to database.

        Args:
            reviews: List of reviews
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted reviews
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_payment_intents(get_unique_ids(reviews, 'payment_intent'))
            self._backfill_charges(get_unique_ids(reviews, 'charge'))

        return self.postgres_client.upsert_many_with_timestamp_protection(
            reviews,
            'reviews',
            review_schema,
            sync_timestamp
        )

    def _upsert_customers(
        self,
        customers: List[Any],
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert customers to database.

        Args:
            customers: List of customers
            sync_timestamp: Sync timestamp

        Returns:
            Upserted customers
        """
        deleted_customers = [c for c in customers if c.get('deleted')]
        non_deleted_customers = [c for c in customers if not c.get('deleted')]

        self.postgres_client.upsert_many_with_timestamp_protection(
            non_deleted_customers,
            'customers',
            customer_schema,
            sync_timestamp
        )
        self.postgres_client.upsert_many_with_timestamp_protection(
            deleted_customers,
            'customers',
            customer_deleted_schema,
            sync_timestamp
        )

        return customers

    def _backfill_customers(self, customer_ids: List[str]) -> None:
        """Backfill missing customers.

        Args:
            customer_ids: List of customer IDs
        """
        missing_ids = self.postgres_client.find_missing_entries('customers', customer_ids)
        try:
            customers = self._fetch_missing_entities(
                missing_ids,
                lambda id: stripe.Customer.retrieve(id)
            )
            self._upsert_customers(customers)
        except Exception as err:
            if self.config.logger:
                self.config.logger.error(f'Failed to backfill: {err}')
            raise

    def _upsert_disputes(
        self,
        disputes: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert disputes to database.

        Args:
            disputes: List of disputes
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted disputes
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_charges(get_unique_ids(disputes, 'charge'))

        return self.postgres_client.upsert_many_with_timestamp_protection(
            disputes,
            'disputes',
            dispute_schema,
            sync_timestamp
        )

    def _upsert_invoices(
        self,
        invoices: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert invoices to database.

        Args:
            invoices: List of invoices
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted invoices
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_customers(get_unique_ids(invoices, 'customer'))
            self._backfill_subscriptions(get_unique_ids(invoices, 'subscription'))

        self._expand_entity(
            invoices,
            'lines',
            lambda id: stripe.Invoice.list_line_items(id, limit=100)
        )

        return self.postgres_client.upsert_many_with_timestamp_protection(
            invoices,
            'invoices',
            invoice_schema,
            sync_timestamp
        )

    def _backfill_invoices(self, invoice_ids: List[str]) -> None:
        """Backfill missing invoices.

        Args:
            invoice_ids: List of invoice IDs
        """
        missing_ids = self.postgres_client.find_missing_entries('invoices', invoice_ids)
        invoices = self._fetch_missing_entities(missing_ids, lambda id: stripe.Invoice.retrieve(id))
        self._upsert_invoices(invoices)

    def _backfill_prices(self, price_ids: List[str]) -> None:
        """Backfill missing prices.

        Args:
            price_ids: List of price IDs
        """
        missing_ids = self.postgres_client.find_missing_entries('prices', price_ids)
        prices = self._fetch_missing_entities(missing_ids, lambda id: stripe.Price.retrieve(id))
        self._upsert_prices(prices)

    def _upsert_invoice_payments(
        self,
        invoice_payments: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert invoice payments to database.

        Args:
            invoice_payments: List of invoice payments
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted invoice payments
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            invoice_ids = get_unique_ids(invoice_payments, 'invoice')
            payment_intent_ids = []
            charge_ids = []

            for invoice_payment in invoice_payments:
                payment = invoice_payment.get('payment', {})
                if isinstance(payment, dict):
                    if payment.get('type') == 'payment_intent' and payment.get('payment_intent'):
                        payment_intent_ids.append(str(payment['payment_intent']))
                    elif payment.get('type') == 'charge' and payment.get('charge'):
                        charge_ids.append(str(payment['charge']))

            self._backfill_invoices(invoice_ids)
            self._backfill_payment_intents(list(set(payment_intent_ids)))
            self._backfill_charges(list(set(charge_ids)))

        return self.postgres_client.upsert_many_with_timestamp_protection(
            invoice_payments,
            'invoice_payments',
            invoice_payment_schema,
            sync_timestamp
        )

    def _upsert_plans(
        self,
        plans: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert plans to database.

        Args:
            plans: List of plans
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted plans
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_products(get_unique_ids(plans, 'product'))

        return self.postgres_client.upsert_many_with_timestamp_protection(
            plans,
            'plans',
            plan_schema,
            sync_timestamp
        )

    def _delete_plan(self, id: str) -> bool:
        """Delete a plan from database.

        Args:
            id: Plan ID

        Returns:
            True if deleted
        """
        return self.postgres_client.delete('plans', id)

    def _upsert_prices(
        self,
        prices: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert prices to database.

        Args:
            prices: List of prices
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted prices
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_products(get_unique_ids(prices, 'product'))

        return self.postgres_client.upsert_many_with_timestamp_protection(
            prices,
            'prices',
            price_schema,
            sync_timestamp
        )

    def _delete_price(self, id: str) -> bool:
        """Delete a price from database.

        Args:
            id: Price ID

        Returns:
            True if deleted
        """
        return self.postgres_client.delete('prices', id)

    def _upsert_products(
        self,
        products: List[Any],
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert products to database.

        Args:
            products: List of products
            sync_timestamp: Sync timestamp

        Returns:
            Upserted products
        """
        return self.postgres_client.upsert_many_with_timestamp_protection(
            products,
            'products',
            product_schema,
            sync_timestamp
        )

    def _delete_product(self, id: str) -> bool:
        """Delete a product from database.

        Args:
            id: Product ID

        Returns:
            True if deleted
        """
        return self.postgres_client.delete('products', id)

    def _backfill_products(self, product_ids: List[str]) -> None:
        """Backfill missing products.

        Args:
            product_ids: List of product IDs
        """
        missing_ids = self.postgres_client.find_missing_entries('products', product_ids)
        products = self._fetch_missing_entities(missing_ids, lambda id: stripe.Product.retrieve(id))
        self._upsert_products(products)

    def _upsert_payment_intents(
        self,
        payment_intents: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert payment intents to database.

        Args:
            payment_intents: List of payment intents
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted payment intents
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_customers(get_unique_ids(payment_intents, 'customer'))
            self._backfill_invoices(get_unique_ids(payment_intents, 'invoice'))

        return self.postgres_client.upsert_many_with_timestamp_protection(
            payment_intents,
            'payment_intents',
            payment_intent_schema,
            sync_timestamp
        )

    def _upsert_payment_methods(
        self,
        payment_methods: List[Any],
        backfill_related_entities: Optional[bool] = False,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert payment methods to database.

        Args:
            payment_methods: List of payment methods
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted payment methods
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_customers(get_unique_ids(payment_methods, 'customer'))

        return self.postgres_client.upsert_many_with_timestamp_protection(
            payment_methods,
            'payment_methods',
            payment_methods_schema,
            sync_timestamp
        )

    def _upsert_setup_intents(
        self,
        setup_intents: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert setup intents to database.

        Args:
            setup_intents: List of setup intents
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted setup intents
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_customers(get_unique_ids(setup_intents, 'customer'))

        return self.postgres_client.upsert_many_with_timestamp_protection(
            setup_intents,
            'setup_intents',
            setup_intents_schema,
            sync_timestamp
        )

    def _upsert_tax_ids(
        self,
        tax_ids: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert tax IDs to database.

        Args:
            tax_ids: List of tax IDs
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted tax IDs
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_customers(get_unique_ids(tax_ids, 'customer'))

        return self.postgres_client.upsert_many_with_timestamp_protection(
            tax_ids,
            'tax_ids',
            tax_id_schema,
            sync_timestamp
        )

    def _delete_tax_id(self, id: str) -> bool:
        """Delete a tax ID from database.

        Args:
            id: Tax ID

        Returns:
            True if deleted
        """
        return self.postgres_client.delete('tax_ids', id)

    def _upsert_subscription_items(
        self,
        subscription_items: List[Any],
        sync_timestamp: Optional[str] = None
    ) -> None:
        """Upsert subscription items to database.

        Args:
            subscription_items: List of subscription items
            sync_timestamp: Sync timestamp
        """
        modified_items = []
        for item in subscription_items:
            # Modify price object to string id
            price_id = item['price']['id'] if isinstance(item.get('price'), dict) else item.get('price')
            deleted = item.get('deleted', False)
            quantity = item.get('quantity')

            modified_items.append({
                **item,
                'price': str(price_id),
                'deleted': deleted,
                'quantity': quantity
            })

        self.postgres_client.upsert_many_with_timestamp_protection(
            modified_items,
            'subscription_items',
            subscription_item_schema,
            sync_timestamp
        )

    def _fill_checkout_sessions_line_items(
        self,
        checkout_session_ids: List[str],
        sync_timestamp: Optional[str] = None
    ) -> None:
        """Fill checkout session line items.

        Args:
            checkout_session_ids: List of checkout session IDs
            sync_timestamp: Sync timestamp
        """
        for checkout_session_id in checkout_session_ids:
            line_items = []

            # Fetch all line items
            line_items_list = stripe.checkout.Session.list_line_items(checkout_session_id, limit=100)
            for line_item in line_items_list.auto_paging_iter():
                line_items.append(line_item)

            self._upsert_checkout_session_line_items(line_items, checkout_session_id, sync_timestamp)

    def _upsert_checkout_session_line_items(
        self,
        line_items: List[Any],
        checkout_session_id: str,
        sync_timestamp: Optional[str] = None
    ) -> None:
        """Upsert checkout session line items to database.

        Args:
            line_items: List of line items
            checkout_session_id: Checkout session ID
            sync_timestamp: Sync timestamp
        """
        # Backfill prices needed for line items
        price_ids = []
        for item in line_items:
            price = item.get('price')
            if isinstance(price, dict) and price.get('id'):
                price_ids.append(str(price['id']))
            elif price:
                price_ids.append(str(price))

        self._backfill_prices([pid for pid in price_ids if pid])

        modified_items = []
        for item in line_items:
            # Extract price ID
            price = item.get('price')
            if isinstance(price, dict) and price.get('id'):
                price_id = str(price['id'])
            elif price:
                price_id = str(price)
            else:
                price_id = None

            modified_items.append({
                **item,
                'price': price_id,
                'checkout_session': checkout_session_id
            })

        self.postgres_client.upsert_many_with_timestamp_protection(
            modified_items,
            'checkout_session_line_items',
            checkout_session_line_item_schema,
            sync_timestamp
        )

    def _mark_deleted_subscription_items(
        self,
        subscription_id: str,
        current_sub_item_ids: List[str]
    ) -> Dict[str, int]:
        """Mark subscription items as deleted.

        Args:
            subscription_id: Subscription ID
            current_sub_item_ids: Current subscription item IDs

        Returns:
            Dict with rowCount
        """
        query = f'''
            SELECT id FROM "{self.config.schema}"."subscription_items"
            WHERE subscription = %s AND deleted = false;
        '''
        result = self.postgres_client.query(query, [subscription_id])
        rows = result['rows']

        deleted_ids = [row['id'] for row in rows if row['id'] not in current_sub_item_ids]

        if len(deleted_ids) > 0:
            update_query = f'''
                UPDATE "{self.config.schema}"."subscription_items"
                SET deleted = true WHERE id = ANY(%s::text[]);
            '''
            result = self.postgres_client.query(update_query, [deleted_ids])
            return {'rowCount': result.get('rowCount', 0)}
        else:
            return {'rowCount': 0}

    def _upsert_subscription_schedules(
        self,
        subscription_schedules: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert subscription schedules to database.

        Args:
            subscription_schedules: List of subscription schedules
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted subscription schedules
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            customer_ids = get_unique_ids(subscription_schedules, 'customer')
            self._backfill_customers(customer_ids)

        rows = self.postgres_client.upsert_many_with_timestamp_protection(
            subscription_schedules,
            'subscription_schedules',
            subscription_schedule_schema,
            sync_timestamp
        )

        return rows

    def _upsert_subscriptions(
        self,
        subscriptions: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert subscriptions to database.

        Args:
            subscriptions: List of subscriptions
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted subscriptions
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            customer_ids = get_unique_ids(subscriptions, 'customer')
            self._backfill_customers(customer_ids)

        self._expand_entity(
            subscriptions,
            'items',
            lambda id: stripe.SubscriptionItem.list(subscription=id, limit=100)
        )

        rows = self.postgres_client.upsert_many_with_timestamp_protection(
            subscriptions,
            'subscriptions',
            subscription_schema,
            sync_timestamp
        )

        # Upsert subscription items
        all_subscription_items = []
        for subscription in subscriptions:
            items_data = subscription.get('items', {})
            if isinstance(items_data, dict) and 'data' in items_data:
                all_subscription_items.extend(items_data['data'])

        self._upsert_subscription_items(all_subscription_items, sync_timestamp)

        # Mark deleted subscription items
        for subscription in subscriptions:
            items_data = subscription.get('items', {})
            if isinstance(items_data, dict) and 'data' in items_data:
                subscription_items = items_data['data']
            else:
                subscription_items = []

            sub_item_ids = [item['id'] for item in subscription_items]
            self._mark_deleted_subscription_items(subscription['id'], sub_item_ids)

        return rows

    def _delete_removed_active_entitlements(
        self,
        customer_id: str,
        current_active_entitlement_ids: List[str]
    ) -> Dict[str, int]:
        """Delete removed active entitlements.

        Args:
            customer_id: Customer ID
            current_active_entitlement_ids: Current active entitlement IDs

        Returns:
            Dict with rowCount
        """
        query = f'''
            DELETE FROM "{self.config.schema}"."active_entitlements"
            WHERE customer = %s AND id <> ALL(%s::text[]);
        '''
        result = self.postgres_client.query(query, [customer_id, current_active_entitlement_ids])
        return {'rowCount': result.get('rowCount', 0)}

    def _upsert_features(
        self,
        features: List[Any],
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert features to database.

        Args:
            features: List of features
            sync_timestamp: Sync timestamp

        Returns:
            Upserted features
        """
        return self.postgres_client.upsert_many_with_timestamp_protection(
            features,
            'features',
            feature_schema,
            sync_timestamp
        )

    def _backfill_features(self, feature_ids: List[str]) -> None:
        """Backfill missing features.

        Args:
            feature_ids: List of feature IDs
        """
        missing_ids = self.postgres_client.find_missing_entries('features', feature_ids)
        try:
            features = self._fetch_missing_entities(
                missing_ids,
                lambda id: stripe.entitlements.Feature.retrieve(id)
            )
            self._upsert_features(features)
        except Exception as err:
            if self.config.logger:
                self.config.logger.error(f'Failed to backfill features: {err}')
            raise

    def _upsert_active_entitlements(
        self,
        customer_id: str,
        active_entitlements: List[Any],
        backfill_related_entities: Optional[bool] = None,
        sync_timestamp: Optional[str] = None
    ) -> List[Any]:
        """Upsert active entitlements to database.

        Args:
            customer_id: Customer ID
            active_entitlements: List of active entitlements
            backfill_related_entities: Whether to backfill related entities
            sync_timestamp: Sync timestamp

        Returns:
            Upserted active entitlements
        """
        if backfill_related_entities if backfill_related_entities is not None else self.config.backfill_related_entities:
            self._backfill_customers(get_unique_ids(active_entitlements, 'customer'))
            self._backfill_features(get_unique_ids(active_entitlements, 'feature'))

        entitlements = []
        for entitlement in active_entitlements:
            feature = entitlement.get('feature')
            feature_id = feature if isinstance(feature, str) else feature.get('id')

            entitlements.append({
                'id': entitlement['id'],
                'object': entitlement['object'],
                'feature': feature_id,
                'customer': customer_id,
                'livemode': entitlement['livemode'],
                'lookup_key': entitlement.get('lookup_key')
            })

        return self.postgres_client.upsert_many_with_timestamp_protection(
            entitlements,
            'active_entitlements',
            active_entitlement_schema,
            sync_timestamp
        )

    def _backfill_subscriptions(self, subscription_ids: List[str]) -> None:
        """Backfill missing subscriptions.

        Args:
            subscription_ids: List of subscription IDs
        """
        missing_ids = self.postgres_client.find_missing_entries('subscriptions', subscription_ids)
        subscriptions = self._fetch_missing_entities(
            missing_ids,
            lambda id: stripe.Subscription.retrieve(id)
        )
        self._upsert_subscriptions(subscriptions)

    def _backfill_subscription_schedules(self, subscription_schedule_ids: List[str]) -> None:
        """Backfill missing subscription schedules.

        Args:
            subscription_schedule_ids: List of subscription schedule IDs
        """
        missing_ids = self.postgres_client.find_missing_entries(
            'subscription_schedules',
            subscription_schedule_ids
        )
        subscription_schedules = self._fetch_missing_entities(
            missing_ids,
            lambda id: stripe.SubscriptionSchedule.retrieve(id)
        )
        self._upsert_subscription_schedules(subscription_schedules)

    def _expand_entity(
        self,
        entities: List[Any],
        property: str,
        list_fn: Callable[[str], Any]
    ) -> None:
        """Expand entity property by fetching all data.

        Args:
            entities: List of entities
            property: Property to expand
            list_fn: Function to list items
        """
        if not self.config.auto_expand_lists:
            return

        for entity in entities:
            prop_value = entity.get(property)
            if isinstance(prop_value, dict) and prop_value.get('has_more'):
                all_data = []
                stripe_list = list_fn(entity['id'])
                for item in stripe_list.auto_paging_iter():
                    all_data.append(item)

                entity[property] = {
                    **prop_value,
                    'data': all_data,
                    'has_more': False
                }

    def _fetch_missing_entities(
        self,
        ids: List[str],
        fetch: Callable[[str], Any]
    ) -> List[Any]:
        """Fetch missing entities from Stripe.

        Args:
            ids: List of entity IDs
            fetch: Function to fetch entity

        Returns:
            List of entities
        """
        if not ids:
            return []

        entities = []
        for id in ids:
            entity = fetch(id)
            entities.append(entity)

        return entities

    def close(self) -> None:
        """Close database connection."""
        self.postgres_client.close()

    def __aenter__(self):
        """Async context manager entry."""
        return self

    def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.close()
