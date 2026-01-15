"""
Tests for subscription tier management models and service.
"""

import pytest
from datetime import UTC, datetime, timedelta

from app.models import SubscriptionTier, TierEntitlement, UserSubscription, User
from app.services.subscription_service import SubscriptionService
from app.extensions import db


class TestSubscriptionTier:
    """Test SubscriptionTier model."""

    def test_create_tier(self, app, base_user):
        """Test creating a subscription tier."""
        with app.app_context():
            tier = SubscriptionTier(name="Base", tier_level=1)
            db.session.add(tier)
            db.session.commit()

            retrieved = SubscriptionTier.query.filter_by(name="Base").first()
            assert retrieved is not None
            assert retrieved.tier_level == 1

    def test_tier_hierarchy(self, app):
        """Test parent-child tier relationships."""
        with app.app_context():
            base = SubscriptionTier(name="Base", tier_level=1)
            db.session.add(base)
            db.session.commit()

            four_k = SubscriptionTier(
                name="4K", tier_level=2, parent_tier_id=base.id
            )
            db.session.add(four_k)
            db.session.commit()

            assert four_k.parent_tier.id == base.id
            assert base.child_tiers[0].id == four_k.id

    def test_get_all_entitlements(self, app):
        """Test getting inherited entitlements."""
        with app.app_context():
            base = SubscriptionTier(name="Base", tier_level=1)
            db.session.add(base)
            db.session.commit()

            # Add entitlements to base
            base_ent1 = TierEntitlement(
                tier_id=base.id,
                resource_type="plex_library",
                resource_id="movies_1080p",
            )
            base_ent2 = TierEntitlement(
                tier_id=base.id,
                resource_type="plex_library",
                resource_id="tv_1080p",
            )
            db.session.add_all([base_ent1, base_ent2])
            db.session.commit()

            # Create 4K tier with additional entitlements
            four_k = SubscriptionTier(
                name="4K", tier_level=2, parent_tier_id=base.id
            )
            db.session.add(four_k)
            db.session.commit()

            four_k_ent = TierEntitlement(
                tier_id=four_k.id,
                resource_type="plex_library",
                resource_id="movies_4k",
                is_tier_exclusive=True,
            )
            db.session.add(four_k_ent)
            db.session.commit()

            # Check 4K tier has all entitlements
            all_ents = four_k.get_all_entitlements()
            assert len(all_ents) == 3
            resource_ids = [e.resource_id for e in all_ents]
            assert "movies_1080p" in resource_ids
            assert "tv_1080p" in resource_ids
            assert "movies_4k" in resource_ids


class TestUserSubscription:
    """Test UserSubscription model."""

    def test_create_subscription(self, app, base_user):
        """Test creating a user subscription."""
        with app.app_context():
            tier = SubscriptionTier(name="Base", tier_level=1)
            db.session.add(tier)
            db.session.commit()

            user = User.query.first()
            sub = UserSubscription(user_id=user.id, tier_id=tier.id, status="active")
            db.session.add(sub)
            db.session.commit()

            retrieved = UserSubscription.query.filter_by(user_id=user.id).first()
            assert retrieved is not None
            assert retrieved.tier_id == tier.id

    def test_subscription_is_active(self, app, base_user):
        """Test subscription active status."""
        with app.app_context():
            tier = SubscriptionTier(name="Base", tier_level=1)
            db.session.add(tier)
            db.session.commit()

            user = User.query.first()

            # Active subscription
            sub1 = UserSubscription(
                user_id=user.id,
                tier_id=tier.id,
                status="active",
                active_until=datetime.now(UTC) + timedelta(days=30),
            )
            assert sub1.is_active()

            # Expired subscription
            sub2 = UserSubscription(
                user_id=user.id,
                tier_id=tier.id,
                status="active",
                active_until=datetime.now(UTC) - timedelta(days=1),
            )
            assert not sub2.is_active()

            # Cancelled subscription
            sub3 = UserSubscription(
                user_id=user.id,
                tier_id=tier.id,
                status="cancelled",
            )
            assert not sub3.is_active()


class TestSubscriptionService:
    """Test SubscriptionService."""

    def test_create_subscription(self, app, base_user):
        """Test subscription creation via service."""
        with app.app_context():
            tier = SubscriptionTier(name="Base", tier_level=1)
            db.session.add(tier)
            db.session.commit()

            user = User.query.first()
            sub = SubscriptionService.create_subscription(
                user_id=user.id,
                tier_id=tier.id,
                stripe_subscription_id="sub_test123",
            )

            assert sub.user_id == user.id
            assert sub.tier_id == tier.id
            assert sub.stripe_subscription_id == "sub_test123"
            assert sub.status == "active"

    def test_create_subscription_cancels_previous(self, app, base_user):
        """Test that creating new subscription cancels previous ones."""
        with app.app_context():
            tier1 = SubscriptionTier(name="Base", tier_level=1)
            tier2 = SubscriptionTier(name="4K", tier_level=2)
            db.session.add_all([tier1, tier2])
            db.session.commit()

            user = User.query.first()

            # Create first subscription
            sub1 = SubscriptionService.create_subscription(
                user_id=user.id, tier_id=tier1.id
            )
            assert sub1.status == "active"

            # Create second subscription
            sub2 = SubscriptionService.create_subscription(
                user_id=user.id, tier_id=tier2.id
            )
            assert sub2.status == "active"

            # Check first is now cancelled
            db.session.refresh(sub1)
            assert sub1.status == "cancelled"

    def test_get_active_subscription(self, app, base_user):
        """Test getting active subscription."""
        with app.app_context():
            tier = SubscriptionTier(name="Base", tier_level=1)
            db.session.add(tier)
            db.session.commit()

            user = User.query.first()
            sub = SubscriptionService.create_subscription(
                user_id=user.id,
                tier_id=tier.id,
                active_until=datetime.now(UTC) + timedelta(days=30),
            )

            active = SubscriptionService.get_active_subscription(user_id=user.id)
            assert active is not None
            assert active.id == sub.id

    def test_get_user_entitlements(self, app, base_user):
        """Test getting user's entitlements."""
        with app.app_context():
            base = SubscriptionTier(name="Base", tier_level=1)
            db.session.add(base)
            db.session.commit()

            ent1 = TierEntitlement(
                tier_id=base.id,
                resource_type="plex_library",
                resource_id="movies",
            )
            ent2 = TierEntitlement(
                tier_id=base.id,
                resource_type="plex_library",
                resource_id="tv",
            )
            db.session.add_all([ent1, ent2])
            db.session.commit()

            user = User.query.first()
            SubscriptionService.create_subscription(user_id=user.id, tier_id=base.id)

            entitlements = SubscriptionService.get_user_entitlements(user_id=user.id)
            assert len(entitlements) == 2
            assert any(e.resource_id == "movies" for e in entitlements)
            assert any(e.resource_id == "tv" for e in entitlements)

    def test_user_has_library_access(self, app, base_user):
        """Test checking library access."""
        with app.app_context():
            tier = SubscriptionTier(name="Base", tier_level=1)
            db.session.add(tier)
            db.session.commit()

            TierEntitlement(
                tier_id=tier.id,
                resource_type="plex_library",
                resource_id="movies",
            )
            db.session.commit()

            user = User.query.first()
            SubscriptionService.create_subscription(user_id=user.id, tier_id=tier.id)

            assert SubscriptionService.user_has_library_access(
                user_id=user.id, library_key="movies"
            )
            assert not SubscriptionService.user_has_library_access(
                user_id=user.id, library_key="tv"
            )

    def test_cancel_subscription(self, app, base_user):
        """Test cancelling subscription."""
        with app.app_context():
            tier = SubscriptionTier(name="Base", tier_level=1)
            db.session.add(tier)
            db.session.commit()

            user = User.query.first()
            sub = SubscriptionService.create_subscription(
                user_id=user.id, tier_id=tier.id
            )

            cancelled = SubscriptionService.cancel_subscription(sub.id)
            assert cancelled.status == "cancelled"

    def test_update_from_stripe(self, app, base_user):
        """Test updating subscription from Stripe webhook."""
        with app.app_context():
            tier = SubscriptionTier(name="Base", tier_level=1)
            db.session.add(tier)
            db.session.commit()

            user = User.query.first()
            sub = SubscriptionService.create_subscription(
                user_id=user.id,
                tier_id=tier.id,
                stripe_subscription_id="sub_test123",
            )

            # Simulate Stripe webhook - cancel
            updated = SubscriptionService.update_from_stripe(
                stripe_subscription_id="sub_test123", status="canceled"
            )
            assert updated.status == "cancelled"

            # Simulate suspension
            updated = SubscriptionService.update_from_stripe(
                stripe_subscription_id="sub_test123", status="past_due"
            )
            assert updated.status == "suspended"
