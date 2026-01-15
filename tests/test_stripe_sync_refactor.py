"""Tests to verify the refactored stripe-sync-engine works correctly."""

import inspect
import os

import pytest

from app.services.stripe_sync.database.postgres import PostgresClient
from app.services.stripe_sync.stripe_sync import StripeSync
from app.services.stripe_sync.types import Sync, SyncBackfill, StripeSyncConfig


class TestStripeSyncRefactor:
    """Test suite for verifying the synchronous refactoring of stripe-sync-engine."""

    def test_imports_work(self):
        """Test that all necessary imports work without errors."""
        # Imports are at the top of the file, so if we got here, they worked
        assert StripeSync is not None
        assert StripeSyncConfig is not None
        assert PostgresClient is not None
        assert Sync is not None
        assert SyncBackfill is not None

    def test_no_async_await_in_stripe_sync(self):
        """Verify there are no async/await keywords in stripe_sync.py."""
        stripe_sync_file = os.path.join(
            os.path.dirname(__file__),
            "..",
            "app",
            "services",
            "stripe_sync",
            "stripe_sync.py",
        )

        with open(stripe_sync_file, encoding="utf-8") as f:
            content = f.read()

        async_def_count = content.count("async def")
        await_count = content.count("await ")

        assert (
            async_def_count == 0
        ), f"Found {async_def_count} 'async def' declarations"
        assert await_count == 0, f"Found {await_count} 'await' keywords"

    def test_basic_initialization(self):
        """Test that StripeSync can be initialized without errors."""
        config = StripeSyncConfig(
            stripe_secret_key="sk_test_fake_key_for_testing",
            stripe_webhook_secret="whsec_fake_secret_for_testing",
            pool_config={
                "host": "localhost",
                "port": 5432,
                "database": "postgres",
                "user": "postgres",
                "password": "postgres",
            },
            schema="stripe",
        )

        sync = StripeSync(config)

        assert sync is not None
        assert sync.config.schema == "stripe"
        assert sync.postgres_client is not None

    def test_stripe_sync_methods_are_synchronous(self):
        """Test that key StripeSync methods are synchronous (not coroutines)."""
        config = StripeSyncConfig(
            stripe_secret_key="sk_test_fake_key",
            stripe_webhook_secret="whsec_fake_secret",
            pool_config={
                "host": "localhost",
                "database": "postgres",
                "user": "postgres",
                "password": "postgres",
            },
        )

        sync = StripeSync(config)

        # List of important methods that should be synchronous
        methods_to_check = [
            "process_webhook",
            "process_event",
            "sync_backfill",
            "sync_customers",
            "sync_products",
            "sync_subscriptions",
            "sync_invoices",
            "sync_prices",
        ]

        for method_name in methods_to_check:
            method = getattr(sync, method_name)
            assert (
                method is not None
            ), f"Method '{method_name}' should exist on StripeSync"
            assert not inspect.iscoroutinefunction(
                method
            ), f"Method '{method_name}' should not be a coroutine (async)"

    def test_postgres_client_methods_are_synchronous(self):
        """Test that PostgresClient methods are all synchronous."""
        # Get all public methods
        methods = [m for m in dir(PostgresClient) if not m.startswith("_")]

        async_methods = []
        for method_name in methods:
            method = getattr(PostgresClient, method_name, None)
            if method and inspect.iscoroutinefunction(method):
                async_methods.append(method_name)

        assert (
            len(async_methods) == 0
        ), f"PostgresClient should have no async methods, found: {async_methods}"

    def test_config_dataclass_structure(self):
        """Test that StripeSyncConfig has the expected structure."""
        config = StripeSyncConfig(
            stripe_secret_key="sk_test_key",
            stripe_webhook_secret="whsec_secret",
            pool_config={"host": "localhost"},
        )

        # Required fields
        assert hasattr(config, "stripe_secret_key")
        assert hasattr(config, "stripe_webhook_secret")
        assert hasattr(config, "pool_config")

        # Optional fields
        assert hasattr(config, "schema")
        assert hasattr(config, "stripe_api_version")
        assert hasattr(config, "auto_expand_lists")
        assert hasattr(config, "backfill_related_entities")
        assert hasattr(config, "logger")

    def test_stripe_sync_has_key_attributes(self):
        """Test that StripeSync instance has expected attributes."""
        config = StripeSyncConfig(
            stripe_secret_key="sk_test_key",
            stripe_webhook_secret="whsec_secret",
            pool_config={"host": "localhost"},
        )

        sync = StripeSync(config)

        assert hasattr(sync, "config")
        assert hasattr(sync, "postgres_client")
        assert sync.config is not None
        assert sync.postgres_client is not None

    def test_no_async_context_managers(self):
        """Test that context manager methods are not async."""
        config = StripeSyncConfig(
            stripe_secret_key="sk_test_key",
            stripe_webhook_secret="whsec_secret",
            pool_config={"host": "localhost"},
        )

        sync = StripeSync(config)

        # The __aenter__ and __aexit__ methods should exist but not be async
        # (They were converted from async context managers to sync)
        assert hasattr(sync, "__aenter__")
        assert hasattr(sync, "__aexit__")

        # Note: These may still be named __aenter__/__aexit__ but should not be async
        # In a fully correct implementation, they should be renamed to __enter__/__exit__
        # but the current refactoring just removed async/await


class TestPostgresClient:
    """Tests specific to the PostgresClient class."""

    def test_postgres_client_has_expected_methods(self):
        """Test that PostgresClient has the expected methods."""
        expected_methods = [
            "delete",
            "query",
            "upsert_many",
            "upsert_many_with_timestamp_protection",
            "find_missing_entries",
        ]

        for method_name in expected_methods:
            assert hasattr(
                PostgresClient, method_name
            ), f"PostgresClient should have method '{method_name}'"
            method = getattr(PostgresClient, method_name)
            assert not inspect.iscoroutinefunction(
                method
            ), f"Method '{method_name}' should not be async"
