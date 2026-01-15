"""
Subscription service for managing user subscriptions and entitlements.
"""

from datetime import UTC, datetime
from typing import Optional

from app.extensions import db
from app.models import SubscriptionTier, TierEntitlement, User, UserSubscription


class SubscriptionService:
    """Service for managing subscriptions and entitlements."""

    @staticmethod
    def create_subscription(
        user_id: int,
        tier_id: int,
        stripe_subscription_id: Optional[str] = None,
        active_from: Optional[datetime] = None,
        active_until: Optional[datetime] = None,
    ) -> UserSubscription:
        """
        Create a new subscription for a user.

        Args:
            user_id: The user ID
            tier_id: The subscription tier ID
            stripe_subscription_id: Optional Stripe subscription ID
            active_from: When the subscription starts (defaults to now)
            active_until: When the subscription ends (optional)

        Returns:
            The created UserSubscription object

        Raises:
            ValueError: If user or tier doesn't exist
        """
        user = User.query.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        tier = SubscriptionTier.query.get(tier_id)
        if not tier:
            raise ValueError(f"SubscriptionTier {tier_id} not found")

        # Cancel any existing active subscriptions for this user
        existing = UserSubscription.query.filter_by(
            user_id=user_id, status="active"
        ).all()
        for sub in existing:
            sub.status = "cancelled"

        subscription = UserSubscription(
            user_id=user_id,
            tier_id=tier_id,
            stripe_subscription_id=stripe_subscription_id,
            active_from=active_from or datetime.now(UTC),
            active_until=active_until,
            status="active",
        )
        db.session.add(subscription)
        db.session.commit()
        return subscription

    @staticmethod
    def get_user_subscriptions(user_id: int, include_inactive: bool = False) -> list[UserSubscription]:
        """Get all subscriptions for a user."""
        query = UserSubscription.query.filter_by(user_id=user_id)
        if not include_inactive:
            query = query.filter_by(status="active")
        return query.all()

    @staticmethod
    def get_active_subscription(user_id: int) -> Optional[UserSubscription]:
        """Get the currently active subscription for a user."""
        now = datetime.now(UTC)
        subscription = UserSubscription.query.filter(
            UserSubscription.user_id == user_id,
            UserSubscription.status == "active",
            UserSubscription.active_from <= now,
            db.or_(
                UserSubscription.active_until.is_(None),
                UserSubscription.active_until > now,
            ),
        ).first()
        return subscription

    @staticmethod
    def get_user_entitlements(user_id: int) -> list[TierEntitlement]:
        """
        Get all entitlements for a user based on their active subscription.

        Returns:
            List of TierEntitlement objects, including inherited ones from parent tiers
        """
        subscription = SubscriptionService.get_active_subscription(user_id)
        if not subscription:
            return []
        return subscription.tier.get_all_entitlements()

    @staticmethod
    def user_has_library_access(user_id: int, library_key: str) -> bool:
        """Check if a user has access to a specific library."""
        entitlements = SubscriptionService.get_user_entitlements(user_id)
        return any(
            ent.resource_type == "plex_library" and ent.resource_id == library_key
            for ent in entitlements
        )

    @staticmethod
    def cancel_subscription(subscription_id: int) -> UserSubscription:
        """Cancel a subscription."""
        subscription = UserSubscription.query.get(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")
        subscription.status = "cancelled"
        db.session.commit()
        return subscription

    @staticmethod
    def expire_subscription(subscription_id: int) -> UserSubscription:
        """Mark a subscription as expired."""
        subscription = UserSubscription.query.get(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")
        subscription.status = "expired"
        db.session.commit()
        return subscription

    @staticmethod
    def update_from_stripe(stripe_subscription_id: str, status: str) -> Optional[UserSubscription]:
        """
        Update a subscription based on Stripe webhook data.

        Args:
            stripe_subscription_id: The Stripe subscription ID
            status: The status from Stripe ('active', 'past_due', 'canceled', 'unpaid')

        Returns:
            The updated UserSubscription or None if not found
        """
        subscription = UserSubscription.query.filter_by(
            stripe_subscription_id=stripe_subscription_id
        ).first()
        if not subscription:
            return None

        # Map Stripe status to our status
        if status == "active":
            subscription.status = "active"
        elif status in ("past_due", "unpaid"):
            subscription.status = "suspended"
        elif status == "canceled":
            subscription.status = "cancelled"

        db.session.commit()
        return subscription
