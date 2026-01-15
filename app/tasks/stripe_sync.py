"""Background tasks for Stripe Sync Engine backfill operations."""

import logging


def stripe_backfill(app=None):
    """Trigger a backfill operation on the embedded Stripe Sync Engine.

    This task uses the embedded StripeSync service to synchronize all Stripe data
    into the PostgreSQL 'stripe' schema.

    Args:
        app: Flask application instance. If None, will try to get from current context.
    """
    if app is None:
        from flask import current_app

        try:
            app = current_app._get_current_object()  # type: ignore
        except RuntimeError:
            logging.error(
                "stripe_backfill called outside application context and no app provided"
            )
            return

    with app.app_context():
        try:
            from app.models import Settings
            from app.services.stripe_service import StripeService

            # Check if Stripe is connected
            stripe_connected_setting = Settings.query.filter_by(
                key="stripe_connected"
            ).first()

            if not stripe_connected_setting or stripe_connected_setting.value not in ["True", "true", "1"]:
                logging.info(
                    "Stripe backfill skipped - not connected to Stripe"
                )
                return

            # Check if Stripe service is configured
            if not StripeService.is_configured():
                logging.info(
                    "Stripe backfill skipped - service not configured"
                )
                return

            # Get the StripeSync instance
            sync_engine = StripeService.get_instance()

            if not sync_engine:
                logging.warning(
                    "❌ Stripe backfill failed - sync engine not initialized"
                )
                return

            # Trigger backfill operation - sync all Stripe objects
            result = sync_engine.sync_backfill({'object': 'all'})

            logging.info(
                "💳 Stripe backfill completed successfully: %s", result
            )

        except Exception as e:
            logging.error("❌ Unexpected error during Stripe backfill: %s", e, exc_info=True)
