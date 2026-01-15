"""Webhook routes for external integrations (Stripe, etc.)."""

import json
import logging

import stripe
from flask import Blueprint, current_app, jsonify, request

from app.models import Settings
from app.services.stripe_service import StripeService

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


def _handle_payment_tracking(event: dict):
    """Track payment completion for invitations based on Stripe webhook events.

    Handles:
    - checkout.session.completed: Links checkout session to invitation
    - customer.subscription.created: Marks payment as complete
    - customer.subscription.updated: Updates payment status
    """
    from app.extensions import db
    from app.models import Invitation
    from datetime import datetime, UTC

    event_type = event.get("type")
    event_data = event.get("data", {}).get("object", {})

    try:
        # Handle checkout session completion
        if event_type == "checkout.session.completed":
            metadata = event_data.get("metadata", {})
            invitation_code = metadata.get("invitation_code")

            if not invitation_code:
                # Try client_reference_id as fallback
                invitation_code = event_data.get("client_reference_id")

            if invitation_code:
                invitation = Invitation.query.filter(
                    db.func.lower(Invitation.code) == invitation_code.lower()
                ).first()

                if invitation and invitation.requires_payment:
                    # Store customer and subscription IDs
                    invitation.stripe_customer_id = event_data.get("customer")
                    invitation.stripe_subscription_id = event_data.get("subscription")

                    current_app.logger.info(
                        f"Linked checkout session to invitation {invitation_code}: "
                        f"customer={invitation.stripe_customer_id}, "
                        f"subscription={invitation.stripe_subscription_id}"
                    )

                    db.session.commit()

        # Handle subscription activation
        elif event_type in ["customer.subscription.created", "customer.subscription.updated"]:
            subscription_id = event_data.get("id")
            customer_id = event_data.get("customer")
            status = event_data.get("status")

            # Only mark as complete if status is active or trialing
            if status in ["active", "trialing"] and subscription_id:
                # Find invitation by subscription ID or customer ID
                invitation = Invitation.query.filter(
                    (Invitation.stripe_subscription_id == subscription_id) |
                    (Invitation.stripe_customer_id == customer_id)
                ).first()

                if invitation and invitation.requires_payment and not invitation.payment_completed:
                    invitation.payment_completed = True
                    invitation.payment_completed_at = datetime.now(UTC)
                    invitation.stripe_subscription_id = subscription_id
                    invitation.stripe_customer_id = customer_id

                    current_app.logger.info(
                        f"Marked payment complete for invitation {invitation.code}: "
                        f"subscription={subscription_id}, status={status}"
                    )

                    db.session.commit()

        # Handle subscription cancellation/pause
        elif event_type in ["customer.subscription.deleted", "customer.subscription.paused"]:
            subscription_id = event_data.get("id")

            if subscription_id:
                invitation = Invitation.query.filter_by(
                    stripe_subscription_id=subscription_id
                ).first()

                if invitation:
                    invitation.payment_completed = False

                    current_app.logger.info(
                        f"Marked payment incomplete for invitation {invitation.code} "
                        f"due to subscription {event_type}"
                    )

                    db.session.commit()

    except Exception as e:
        current_app.logger.error(f"Error tracking payment for invitation: {e}")
        db.session.rollback()


@webhooks_bp.route("/stripe", methods=["POST"])
def stripe_webhook():
    """Handle incoming Stripe webhook events.

    This endpoint receives webhook events from Stripe, validates the signature,
    and processes the event using the StripeSync engine.

    Returns:
        JSON response with status
    """
    try:
        # Load webhook configurations
        webhooks_setting = Settings.query.filter_by(key="stripe_webhooks").first()

        if not webhooks_setting or not webhooks_setting.value:
            current_app.logger.warning("Stripe webhook received but no webhooks configured")
            return jsonify({"error": "No webhooks configured"}), 503

        try:
            webhooks = json.loads(webhooks_setting.value)
        except (json.JSONDecodeError, TypeError):
            current_app.logger.error("Failed to parse webhook configuration")
            return jsonify({"error": "Invalid webhook configuration"}), 500

        # Find the webhook secret for /webhooks/stripe endpoint
        webhook_secret = None
        for webhook in webhooks:
            if webhook.get("endpoint") == "/webhooks/stripe":
                webhook_secret = webhook.get("secret")
                break

        if not webhook_secret:
            current_app.logger.error("No webhook secret configured for /webhooks/stripe")
            return jsonify({"error": "Webhook secret not configured"}), 500

        # Get the raw request payload (as bytes) and signature header
        payload = request.get_data()
        sig_header = request.headers.get("Stripe-Signature")

        if not sig_header:
            current_app.logger.warning("Stripe webhook missing signature header")
            return jsonify({"error": "Missing stripe-signature header"}), 400

        # Verify the webhook signature and construct the event
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except stripe.error.SignatureVerificationError as sig_error:
            # Invalid signature - return 400 so Stripe doesn't retry
            current_app.logger.error(f"Stripe webhook signature verification failed: {sig_error}")
            return jsonify({"error": "Invalid signature"}), 400
        except ValueError as value_error:
            # Invalid payload - return 400 so Stripe doesn't retry
            current_app.logger.error(f"Stripe webhook invalid payload: {value_error}")
            return jsonify({"error": "Invalid payload"}), 400

        # Get Stripe secret key for API operations
        stripe_key_setting = Settings.query.filter_by(key="stripe_secret_key").first()

        if not stripe_key_setting or not stripe_key_setting.value:
            current_app.logger.error("Stripe API key not configured - cannot process webhook")
            return jsonify({"error": "Stripe API key not configured"}), 500

        # Set Stripe API key
        stripe.api_key = stripe_key_setting.value

        # Get or create a StripeSync instance for webhook processing
        # Note: We create a temporary instance just for this webhook since webhooks
        # can work independently from the backfill service
        from app.services.stripe_sync.stripe_sync import StripeSync
        from app.services.stripe_sync.types import StripeSyncConfig
        import os
        import logging

        # Build PostgreSQL connection config
        database_url = os.getenv("DATABASE_URL")
        if database_url and database_url.startswith("postgresql://"):
            from urllib.parse import urlparse
            parsed = urlparse(database_url)
            pool_config = {
                "host": parsed.hostname or "localhost",
                "port": parsed.port or 5432,
                "database": parsed.path.lstrip("/") if parsed.path else "postgres",
                "user": parsed.username or "postgres",
                "password": parsed.password or "postgres",
            }
        else:
            pool_config = {
                "host": os.getenv("DB_HOST", "localhost"),
                "port": int(os.getenv("DB_PORT", "5432")),
                "database": os.getenv("DB_NAME", "postgres"),
                "user": os.getenv("DB_USER", "postgres"),
                "password": os.getenv("DB_PASSWORD", "postgres"),
            }

        # Create StripeSync config
        config = StripeSyncConfig(
            stripe_secret_key=stripe_key_setting.value,
            stripe_webhook_secret=webhook_secret,
            pool_config=pool_config,
            schema="stripe",
            logger=logging.getLogger("app.webhooks.stripe"),
        )

        # Create StripeSync instance and process the webhook
        sync_engine = StripeSync(config)

        try:
            # Process the webhook event - this will upsert to database
            sync_engine.process_event(event)

            # Handle invitation payment tracking for checkout and subscription events
            _handle_payment_tracking(event)

            current_app.logger.info(
                f"Stripe webhook processed successfully: {event['type']} (id: {event['id']})"
            )

            return jsonify({"received": True}), 200
        finally:
            # Clean up database connection
            if hasattr(sync_engine, 'postgres_client'):
                sync_engine.postgres_client.close()

    except Exception as exc:
        current_app.logger.exception(f"Unexpected error in Stripe webhook handler: {exc}")
        return jsonify({"error": "Internal server error"}), 500


# Dynamic webhook endpoint support
@webhooks_bp.before_app_request
def register_custom_webhook_endpoint():
    """Dynamically register custom webhook endpoint if configured.
    This allows users to configure a custom webhook path in settings.
    The custom route will point to the same stripe_webhook handler.
    """
    # Only register once
    if hasattr(webhooks_bp, "_custom_endpoint_registered"):
        return

    try:
        # Check if a custom endpoint is configured
        custom_endpoint_setting = Settings.query.filter_by(
            key="stripe_webhook_endpoint"
        ).first()

        if (
            custom_endpoint_setting
            and custom_endpoint_setting.value
            and custom_endpoint_setting.value != "/webhooks/stripe"
        ):
            custom_path = custom_endpoint_setting.value

            # Ensure it starts with /
            if not custom_path.startswith("/"):
                custom_path = f"/{custom_path}"

            # Register the custom route
            current_app.add_url_rule(
                custom_path,
                endpoint="webhooks.stripe_webhook_custom",
                view_func=stripe_webhook,
                methods=["POST"],
            )

            current_app.logger.info(f"Registered custom Stripe webhook endpoint: {custom_path}")

    except Exception as exc:
        current_app.logger.warning(f"Failed to register custom webhook endpoint: {exc}")
    finally:
        # Mark as registered to avoid repeated attempts
        webhooks_bp._custom_endpoint_registered = True
