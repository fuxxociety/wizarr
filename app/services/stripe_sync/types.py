from typing import Optional, List, Dict, Any, Literal, TypedDict
from dataclasses import dataclass


RevalidateEntity = Literal[
    'charge',
    'credit_note',
    'customer',
    'dispute',
    'invoice',
    'payment_intent',
    'payment_method',
    'plan',
    'price',
    'product',
    'refund',
    'review',
    'radar.early_fraud_warning',
    'setup_intent',
    'subscription',
    'subscription_schedule',
    'tax_id',
    'entitlements',
]


@dataclass
class StripeSyncConfig:
    """Configuration for StripeSync.

    Args:
        stripe_secret_key: Stripe secret key used to authenticate requests to the Stripe API
        stripe_webhook_secret: Webhook secret from Stripe to verify the signature of webhook events
        database_url: Deprecated. Use pool_config with a connection string instead
        schema: Database schema name (default: 'stripe')
        stripe_api_version: Stripe API version for the webhooks (default: '2020-08-27')
        auto_expand_lists: Fetch all list items from Stripe (not just the default 10)
        backfill_related_entities: Ensure related entities are present for foreign key integrity
        revalidate_objects_via_stripe_api: Always fetch latest entity from Stripe instead of trusting webhook payload
        max_postgres_connections: Deprecated. Use pool_config['max'] instead
        pool_config: Configuration for PostgreSQL connection pooling
        logger: Logger instance (optional)
    """
    stripe_secret_key: str
    stripe_webhook_secret: str
    pool_config: Dict[str, Any]
    database_url: Optional[str] = None
    schema: Optional[str] = None
    stripe_api_version: Optional[str] = None
    auto_expand_lists: Optional[bool] = None
    backfill_related_entities: Optional[bool] = None
    revalidate_objects_via_stripe_api: Optional[List[RevalidateEntity]] = None
    max_postgres_connections: Optional[int] = None
    logger: Optional[Any] = None


SyncObject = Literal[
    'all',
    'customer',
    'customer_with_entitlements',
    'invoice',
    'price',
    'product',
    'subscription',
    'subscription_schedules',
    'setup_intent',
    'payment_method',
    'dispute',
    'charge',
    'payment_intent',
    'plan',
    'tax_id',
    'credit_note',
    'early_fraud_warning',
    'refund',
    'checkout_sessions',
]


class Sync(TypedDict):
    """Result of a sync operation."""
    synced: int


class SyncBackfill(TypedDict, total=False):
    """Result of a backfill operation."""
    products: Sync
    prices: Sync
    plans: Sync
    customers: Sync
    subscriptions: Sync
    subscriptionSchedules: Sync
    invoices: Sync
    setupIntents: Sync
    paymentIntents: Sync
    paymentMethods: Sync
    disputes: Sync
    charges: Sync
    taxIds: Sync
    creditNotes: Sync
    earlyFraudWarnings: Sync
    refunds: Sync
    checkoutSessions: Sync


class RangeQuery(TypedDict, total=False):
    """Range query parameters for filtering by creation date."""
    gt: int  # Minimum value to filter by (exclusive)
    gte: int  # Minimum value to filter by (inclusive)
    lt: int  # Maximum value to filter by (exclusive)
    lte: int  # Maximum value to filter by (inclusive)


class SyncBackfillParams(TypedDict, total=False):
    """Parameters for backfill operations."""
    created: RangeQuery
    object: SyncObject
    backfill_related_entities: bool


class PaginationParams(TypedDict, total=False):
    """Pagination parameters for Stripe API calls."""
    starting_after: str
    ending_before: str


class SyncEntitlementsParams(TypedDict, total=False):
    """Parameters for syncing entitlements."""
    object: Literal['entitlements']
    customerId: str
    pagination: PaginationParams


class SyncFeaturesParams(TypedDict, total=False):
    """Parameters for syncing features."""
    object: Literal['features']
    pagination: PaginationParams
