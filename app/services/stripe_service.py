"""Stripe Sync Service - Singleton wrapper for StripeSync engine."""

import os
from typing import Optional

from app.extensions import db
from app.models import Settings
from app.services.stripe_sync.stripe_sync import StripeSync
from app.services.stripe_sync.types import StripeSyncConfig


class StripeService:
    """Singleton service for managing Stripe sync operations."""

    _instance: Optional[StripeSync] = None
    _initialized: bool = False

    @classmethod
    def initialize(cls, app) -> bool:
        """Initialize the Stripe sync service from database settings.

        Args:
            app: Flask application instance

        Returns:
            bool: True if initialization succeeded, False otherwise
        """
        # For multi-process scenarios (Gunicorn workers), each process needs its own instance
        # Don't rely on _initialized flag across processes - just check if we have a valid instance
        if cls._instance is not None:
            return True

        try:
            # Ensure we're in an app context for ALL database operations
            from flask import has_app_context
            import json

            if has_app_context():
                # Read ALL configuration from database with environment variable fallbacks
                stripe_secret_key = cls._get_setting(
                    "stripe_secret_key", os.getenv("STRIPE_SECRET_KEY")
                )
                stripe_webhooks_json = cls._get_setting("stripe_webhooks", os.getenv("STRIPE_WEBHOOKS"))
                stripe_webhook_secret = cls._extract_webhook_secret(stripe_webhooks_json)
                stripe_enabled = cls._get_setting("stripe_enabled", os.getenv("STRIPE_ENABLED"))
            else:
                with app.app_context():
                    # Read ALL configuration from database with environment variable fallbacks
                    stripe_secret_key = cls._get_setting(
                        "stripe_secret_key", os.getenv("STRIPE_SECRET_KEY")
                    )
                    stripe_webhooks_json = cls._get_setting("stripe_webhooks", os.getenv("STRIPE_WEBHOOKS"))
                    stripe_webhook_secret = cls._extract_webhook_secret(stripe_webhooks_json)
                    stripe_enabled = cls._get_setting("stripe_enabled", os.getenv("STRIPE_ENABLED"))
            # If critical settings are missing, skip initialization
            if not stripe_secret_key or not stripe_webhook_secret:
                app.logger.info(
                    f"Stripe service not configured (missing API keys). Secret Key: {bool(stripe_secret_key)}, Webhook Secret: {bool(stripe_webhook_secret)}"
                )
                return False

            # Check if Stripe is explicitly disabled (only if setting exists and is False)
            if stripe_enabled in ["False", "false", "0"]:
                app.logger.info("Stripe service disabled")
                return False

            # Build PostgreSQL connection config
            # Parse DATABASE_URL or use individual DB_* variables
            database_url = os.getenv("DATABASE_URL")
            if database_url and database_url.startswith("postgresql://"):
                # Parse postgresql://user:password@host:port/database
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
                # Fallback to individual environment variables
                pool_config = {
                    "host": os.getenv("DB_HOST", "localhost"),
                    "port": int(os.getenv("DB_PORT", "5432")),
                    "database": os.getenv("DB_NAME", "postgres"),
                    "user": os.getenv("DB_USER", "postgres"),
                    "password": os.getenv("DB_PASSWORD", "postgres"),
                }

            # Hard-code schema to 'stripe' as per user requirements
            schema = "stripe"

            # Create configuration
            config = StripeSyncConfig(
                stripe_secret_key=stripe_secret_key,
                stripe_webhook_secret=stripe_webhook_secret,
                pool_config=pool_config,
                schema=schema,
            )

            # Run database migrations to create stripe schema tables
            from app.services.stripe_sync.database import run_migrations_sync, MigrationConfig

            # Use DATABASE_URL if available, otherwise build from pool_config
            if database_url and database_url.startswith("postgresql://"):
                db_url = database_url
            else:
                db_url = f"postgresql://{pool_config['user']}:{pool_config['password']}@{pool_config['host']}:{pool_config['port']}/{pool_config['database']}"

            migration_config = MigrationConfig(
                database_url=db_url,
                schema=schema,
                logger=app.logger,
            )

            try:
                run_migrations_sync(migration_config)
                app.logger.info(f"Stripe database migrations completed (schema: {schema})")
            except Exception as migration_exc:
                app.logger.warning(f"Stripe migration failed: {migration_exc}")
                # Continue anyway - tables might already exist

            # Initialize the StripeSync instance
            cls._instance = StripeSync(config)
            cls._initialized = True

            app.logger.info(f"Stripe service initialized (schema: {schema})")
            return True

        except Exception as exc:
            app.logger.warning(f"Stripe service initialization failed: {exc}")
            import traceback
            app.logger.debug(traceback.format_exc())
            return False

    @classmethod
    def get_instance(cls) -> Optional[StripeSync]:
        """Get the singleton StripeSync instance.

        Returns:
            Optional[StripeSync]: The StripeSync instance if initialized, None otherwise
        """
        return cls._instance

    @classmethod
    def is_configured(cls) -> bool:
        """Check if Stripe service is configured based on database settings.

        This checks the database rather than the in-memory instance so it works
        correctly across multiple worker processes.

        Returns:
            bool: True if Stripe is connected and has valid configuration
        """
        try:
            from app.models import Settings
            from app.extensions import db

            # Query database for settings
            settings = {s.key: s.value for s in db.session.query(Settings).filter(
                Settings.key.in_(['stripe_connected', 'stripe_secret_key', 'stripe_webhooks'])
            ).all()}

            # Check if connected
            stripe_connected = settings.get('stripe_connected')
            if stripe_connected not in ['True', 'true', '1']:
                return False

            # Check if secret key is configured
            secret_key = settings.get('stripe_secret_key')
            if not secret_key:
                return False

            # Check if webhook secret is configured
            stripe_webhooks_json = settings.get('stripe_webhooks')
            webhook_secret = cls._extract_webhook_secret(stripe_webhooks_json)

            return bool(webhook_secret)

        except Exception:
            # Database not available or not initialized
            return False

    @classmethod
    def reset(cls):
        """Reset the singleton (useful for testing)."""
        cls._instance = None
        cls._initialized = False

    @staticmethod
    def _get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
        """Read a setting from the database.

        Args:
            key: Setting key to retrieve
            default: Default value if setting doesn't exist

        Returns:
            Optional[str]: Setting value or default
        """
        try:
            setting = db.session.query(Settings).filter_by(key=key).first()
            return setting.value if setting else default
        except Exception:
            # Database might not be initialized yet
            return default

    @staticmethod
    def _extract_webhook_secret(stripe_webhooks_json: Optional[str]) -> Optional[str]:
        """Extract the webhook secret from the stripe_webhooks JSON array.

        Args:
            stripe_webhooks_json: JSON string containing webhooks array

        Returns:
            Optional[str]: The webhook secret if found, None otherwise
        """
        if not stripe_webhooks_json:
            return None

        try:
            import json
            webhooks = json.loads(stripe_webhooks_json)
            if isinstance(webhooks, list) and len(webhooks) > 0:
                # Get the first webhook's secret
                return webhooks[0].get('secret')
        except (json.JSONDecodeError, TypeError, KeyError, AttributeError):
            pass

        return None
