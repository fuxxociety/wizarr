"""
Subscription tier management routes for stripe settings.
Handles CRUD operations for subscription tiers and their entitlements.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required
from app.extensions import db
from app.models import SubscriptionTier, TierEntitlement, UserSubscription

subscription_tier_bp = Blueprint(
    "subscription_tier",
    __name__,
    url_prefix="/api/settings/subscription-tiers",
)


@subscription_tier_bp.route("", methods=["GET"])
@login_required
def get_tiers():
    """Get all subscription tiers."""
    try:
        tiers = SubscriptionTier.query.order_by(SubscriptionTier.tier_level).all()
        result = []
        for tier in tiers:
            tier_data = {
                "id": tier.id,
                "name": tier.name,
                "description": tier.description,
                "tier_level": tier.tier_level,
                "stripe_product_id": tier.stripe_product_id,
                "parent_tier_id": tier.parent_tier_id,
                "entitlements": [
                    {
                        "id": ent.id,
                        "resource_type": ent.resource_type,
                        "resource_id": ent.resource_id,
                        "is_tier_exclusive": ent.is_tier_exclusive,
                    }
                    for ent in tier.entitlements
                ],
                "all_entitlements": [
                    {
                        "id": ent.id,
                        "resource_type": ent.resource_type,
                        "resource_id": ent.resource_id,
                        "is_tier_exclusive": ent.is_tier_exclusive,
                    }
                    for ent in tier.get_all_entitlements()
                ],
            }
            result.append(tier_data)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@subscription_tier_bp.route("", methods=["POST"])
@login_required
def create_tier():
    """Create a new subscription tier."""
    try:
        data = request.get_json()
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        tier_level = data.get("tier_level")
        stripe_product_id = data.get("stripe_product_id", "").strip() or None
        parent_tier_id = data.get("parent_tier_id")

        if not name:
            return jsonify({"error": "Tier name is required"}), 400
        if tier_level is None:
            return jsonify({"error": "Tier level is required"}), 400

        # Check for duplicate tier level
        if SubscriptionTier.query.filter_by(tier_level=tier_level).first():
            return jsonify({"error": "Tier level already exists"}), 400

        # Check for duplicate name
        if SubscriptionTier.query.filter_by(name=name).first():
            return jsonify({"error": "Tier name already exists"}), 400

        # Validate parent tier if provided
        if parent_tier_id:
            parent = SubscriptionTier.query.get(parent_tier_id)
            if not parent:
                return jsonify({"error": "Parent tier not found"}), 404

        tier = SubscriptionTier(
            name=name,
            description=description,
            tier_level=tier_level,
            stripe_product_id=stripe_product_id,
            parent_tier_id=parent_tier_id,
        )
        db.session.add(tier)
        db.session.commit()

        return (
            jsonify(
                {
                    "id": tier.id,
                    "name": tier.name,
                    "tier_level": tier.tier_level,
                    "stripe_product_id": tier.stripe_product_id,
                    "parent_tier_id": tier.parent_tier_id,
                }
            ),
            201,
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@subscription_tier_bp.route("/<int:tier_id>", methods=["PUT"])
@login_required
def update_tier(tier_id):
    """Update a subscription tier."""
    try:
        tier = SubscriptionTier.query.get(tier_id)
        if not tier:
            return jsonify({"error": "Tier not found"}), 404

        data = request.get_json()
        if "name" in data:
            new_name = data["name"].strip()
            if new_name and new_name != tier.name:
                if SubscriptionTier.query.filter_by(name=new_name).first():
                    return jsonify({"error": "Tier name already exists"}), 400
                tier.name = new_name

        if "description" in data:
            tier.description = data["description"].strip()
        if "stripe_product_id" in data:
            tier.stripe_product_id = data["stripe_product_id"].strip() or None

        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@subscription_tier_bp.route("/<int:tier_id>", methods=["DELETE"])
@login_required
def delete_tier(tier_id):
    """Delete a subscription tier."""
    try:
        tier = SubscriptionTier.query.get(tier_id)
        if not tier:
            return jsonify({"error": "Tier not found"}), 404

        # Check if tier has active subscriptions
        active_subs = UserSubscription.query.filter_by(tier_id=tier_id, status="active").first()
        if active_subs:
            return jsonify(
                {"error": "Cannot delete tier with active subscriptions"}
            ), 400

        db.session.delete(tier)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@subscription_tier_bp.route("/<int:tier_id>/entitlements", methods=["POST"])
@login_required
def add_entitlement(tier_id):
    """Add an entitlement to a tier."""
    try:
        tier = SubscriptionTier.query.get(tier_id)
        if not tier:
            return jsonify({"error": "Tier not found"}), 404

        data = request.get_json()
        resource_type = data.get("resource_type", "").strip()
        resource_id = data.get("resource_id", "").strip()
        is_tier_exclusive = data.get("is_tier_exclusive", False)

        if not resource_type or not resource_id:
            return jsonify({"error": "resource_type and resource_id are required"}), 400

        # Check for duplicate
        existing = TierEntitlement.query.filter_by(
            tier_id=tier_id, resource_type=resource_type, resource_id=resource_id
        ).first()
        if existing:
            return jsonify({"error": "This entitlement already exists for this tier"}), 400

        entitlement = TierEntitlement(
            tier_id=tier_id,
            resource_type=resource_type,
            resource_id=resource_id,
            is_tier_exclusive=is_tier_exclusive,
        )
        db.session.add(entitlement)
        db.session.commit()

        return (
            jsonify(
                {
                    "id": entitlement.id,
                    "resource_type": entitlement.resource_type,
                    "resource_id": entitlement.resource_id,
                    "is_tier_exclusive": entitlement.is_tier_exclusive,
                }
            ),
            201,
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@subscription_tier_bp.route("/entitlements/<int:entitlement_id>", methods=["DELETE"])
@login_required
def remove_entitlement(entitlement_id):
    """Remove an entitlement from a tier."""
    try:
        entitlement = TierEntitlement.query.get(entitlement_id)
        if not entitlement:
            return jsonify({"error": "Entitlement not found"}), 404

        db.session.delete(entitlement)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Stripe Product Configuration Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@subscription_tier_bp.route("/stripe-config", methods=["GET"])
@login_required
def get_stripe_config():
    """
    Get the complete Stripe product configuration UI data.
    Returns Stripe products with their configured tiers and libraries.
    """
    from sqlalchemy import text

    try:
        # Fetch available libraries from the main database
        from app.models import Library, MediaServer

        libraries = (
            Library.query.with_entities(
                Library.id.label("id"),
                Library.name.label("name"),
                Library.key.label("key"),
                MediaServer.name.label("server_name"),
            )
            .outerjoin(MediaServer, Library.server_id == MediaServer.id)
            .order_by(MediaServer.name, Library.name)
            .all()
        )

        library_list = [
            {
                "id": lib.id,
                "name": lib.name,
                "key": lib.external_id,
                "server_name": lib.server_name or "Unknown",
            }
            for lib in libraries
        ]

        # Fetch Stripe products from stripe schema
        conn = db.engine.raw_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, name, active, created
                FROM stripe.products
                ORDER BY created DESC
            """)
            products = []
            for row in cursor.fetchall():
                products.append(
                    {
                        "id": row[0],
                        "name": row[1],
                        "active": row[2],
                        "created": row[3].isoformat() if row[3] else None,
                    }
                )
        finally:
            cursor.close()
            conn.close()

        # For each Stripe product, get or create associated SubscriptionTier
        config_rows = []
        for idx, product in enumerate(products):
            tier = SubscriptionTier.query.filter_by(
                stripe_product_id=product["id"]
            ).first()

            tier_data = {
                "stripe_product_id": product["id"],
                "stripe_product_name": product["name"],
                "stripe_active": product["active"],
                "tier_id": tier.id if tier else None,
                "tier_name": tier.name if tier else product["name"],
                "tier_level": tier.tier_level if tier else idx + 1,
                "parent_tier_id": tier.parent_tier_id if tier else None,
                "entitlements": (
                    [
                        {"id": ent.id, "resource_type": ent.resource_type, "resource_id": ent.resource_id}
                        for ent in tier.entitlements
                    ]
                    if tier
                    else []
                ),
            }
            config_rows.append(tier_data)

        return (
            jsonify(
                {
                    "products": config_rows,
                    "libraries": library_list,
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@subscription_tier_bp.route("/stripe-config/reorder", methods=["POST"])
@login_required
def reorder_tiers():
    """
    Reorder subscription tiers (update tier_levels based on drag order).
    Expects: { "product_ids": ["prod_123", "prod_456", ...] }
    """
    try:
        data = request.get_json()
        product_ids = data.get("product_ids", [])

        if not product_ids:
            return jsonify({"error": "product_ids required"}), 400

        # Update tier levels based on new order
        for new_level, product_id in enumerate(product_ids, start=1):
            tier = SubscriptionTier.query.filter_by(
                stripe_product_id=product_id
            ).first()
            if tier:
                tier.tier_level = new_level
                # Update parent tier if applicable
                if new_level > 1:
                    prev_product_id = product_ids[new_level - 2]
                    parent_tier = SubscriptionTier.query.filter_by(
                        stripe_product_id=prev_product_id
                    ).first()
                    tier.parent_tier_id = parent_tier.id if parent_tier else None
                else:
                    tier.parent_tier_id = None

        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@subscription_tier_bp.route("/stripe-config/update-entitlements", methods=["POST"])
@login_required
def update_tier_entitlements():
    """
    Update entitlements for a tier based on Stripe product.
    Expects: {
        "stripe_product_id": "prod_123",
        "tier_name": "Base Plan",
        "library_keys": ["movies_1080p", "tv_shows"],
        "inherit_from_previous": true
    }
    """
    try:
        data = request.get_json()
        product_id = data.get("stripe_product_id", "").strip()
        tier_name = data.get("tier_name", "").strip()
        library_keys = data.get("library_keys", [])
        inherit_from_previous = data.get("inherit_from_previous", False)

        if not product_id:
            return jsonify({"error": "stripe_product_id required"}), 400

        # Get or create tier for this product
        tier = SubscriptionTier.query.filter_by(
            stripe_product_id=product_id
        ).first()

        if not tier:
            # Create new tier
            tier_level = (
                db.session.query(db.func.max(SubscriptionTier.tier_level)).scalar() or 0
            ) + 1
            tier = SubscriptionTier(
                name=tier_name or product_id,
                tier_level=tier_level,
                stripe_product_id=product_id,
            )
            db.session.add(tier)
            db.session.flush()

        # Update parent tier if inherit_from_previous
        if inherit_from_previous and tier.tier_level > 1:
            parent_tier = SubscriptionTier.query.filter(
                SubscriptionTier.tier_level == tier.tier_level - 1
            ).first()
            tier.parent_tier_id = parent_tier.id if parent_tier else None

        # Update tier name
        if tier_name:
            tier.name = tier_name

        # Clear existing entitlements and rebuild from library_keys
        TierEntitlement.query.filter_by(tier_id=tier.id).delete()

        # Add new entitlements for each library
        for library_key in library_keys:
            entitlement = TierEntitlement(
                tier_id=tier.id,
                resource_type="plex_library",
                resource_id=library_key,
                is_tier_exclusive=False,
            )
            db.session.add(entitlement)

        db.session.commit()

        return (
            jsonify(
                {
                    "success": True,
                    "tier_id": tier.id,
                    "tier_level": tier.tier_level,
                    "entitlements_count": len(library_keys),
                }
            ),
            200,
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@subscription_tier_bp.route("/stripe-config/backfill-products", methods=["POST"])
@login_required
def backfill_stripe_products():
    """
    Manually trigger backfill of Stripe products from API.
    Only works if stripe_secret_key is configured and stripe schema exists.
    """
    try:
        from app.services.stripe_service import StripeService

        stripe_sync = StripeService.get_instance()
        if not stripe_sync:
            return (
                jsonify(
                    {
                        "error": "Stripe not configured. Please configure the Stripe API key first."
                    }
                ),
                503,
            )

        # Trigger product backfill
        stripe_sync.sync_products()

        return (
            jsonify({"success": True, "message": "Products backfilled from Stripe"}),
            200,
        )
    except Exception as e:
        return jsonify({"error": f"Backfill failed: {str(e)}"}), 500
