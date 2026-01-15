"""Routes for Stripe settings management."""

import json
import os

import requests
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import _
from flask_login import login_required

from app.extensions import db
from app.forms.stripe import StripeSettingsForm
from app.models import Settings
from app.services.stripe_service import StripeService

stripe_settings_bp = Blueprint("stripe_settings", __name__, url_prefix="/settings")


def get_stripe_account_info(api_key: str, timeout: float = 5.0):
    """Test Stripe API connection and retrieve account information.

    Args:
        api_key: Stripe secret key
        timeout: Request timeout in seconds

    Returns:
        dict with account_id and account_name, or None if connection failed
    """
    try:
        resp = requests.get(
            "https://api.stripe.com/v1/account",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        acct = resp.json()
        company = acct.get("company", {})
        return {
            "account_id": acct.get("id"),
            "account_name": company.get("name") if company else None,
        }
    except requests.RequestException:
        return None


@stripe_settings_bp.route("/stripe/test-connection", methods=["POST"])
@login_required
def test_stripe_connection():
    """API endpoint to test Stripe connection and get account info."""
    data = request.get_json()
    api_key = data.get("api_key", "").strip()

    if not api_key:
        return jsonify({"success": False, "error": "API key required"}), 400

    account_info = get_stripe_account_info(api_key)

    if account_info:
        return jsonify({"success": True, "account": account_info}), 200
    else:
        return jsonify({"success": False, "error": "Failed to connect to Stripe"}), 400


@stripe_settings_bp.route("/stripe/connect", methods=["POST"])
@login_required
def connect_stripe():
    """Connect to Stripe and enable backfill service."""
    data = request.get_json()
    api_key = data.get("api_key", "").strip()
    publishable_key = data.get("publishable_key", "").strip()
    account_id = data.get("account_id", "")
    account_name = data.get("account_name", "")

    if not api_key:
        return jsonify({"success": False, "error": "API key required"}), 400

    try:
        # Save connection settings
        settings_to_save = {
            "stripe_connected": True,
            "stripe_secret_key": api_key,
            "stripe_account_id": account_id,
            "stripe_account_name": account_name or account_id,
        }

        # Also save publishable key if provided
        if publishable_key:
            settings_to_save["stripe_publishable_key"] = publishable_key

        for key, value in settings_to_save.items():
            if isinstance(value, bool):
                value = str(value)

            setting = Settings.query.filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                setting = Settings(key=key, value=value)
                db.session.add(setting)

        db.session.commit()

        # Reinitialize StripeService
        from flask import current_app
        StripeService.reset()
        StripeService.initialize(current_app)

        return jsonify({"success": True}), 200

    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


@stripe_settings_bp.route("/stripe/disconnect", methods=["POST"])
@login_required
def disconnect_stripe():
    """Disconnect from Stripe and disable backfill service."""
    try:
        # Update connection status
        setting = Settings.query.filter_by(key="stripe_connected").first()
        if setting:
            setting.value = "False"
            db.session.commit()

        # Reset StripeService
        StripeService.reset()

        return jsonify({"success": True}), 200

    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


@stripe_settings_bp.route("/stripe/webhooks", methods=["POST"])
@login_required
def save_webhooks():
    """Save webhook endpoint configurations."""
    data = request.get_json()
    webhooks = data.get("webhooks", [])

    if len(webhooks) > 5:
        return jsonify({"success": False, "error": "Maximum 5 webhooks allowed"}), 400

    try:
        # Save webhooks as JSON
        webhooks_json = json.dumps(webhooks)

        setting = Settings.query.filter_by(key="stripe_webhooks").first()
        if setting:
            setting.value = webhooks_json
        else:
            setting = Settings(key="stripe_webhooks", value=webhooks_json)
            db.session.add(setting)

        db.session.commit()
        return jsonify({"success": True}), 200

    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


def _load_stripe_settings() -> dict:
    """Load Stripe settings from database.

    Returns:
        dict: Dictionary of Stripe settings
    """
    settings = {s.key: s.value for s in Settings.query.all()}

    # Load Stripe connection settings
    result = {
        "stripe_connected": settings.get("stripe_connected") in ["True", "true", "1", True],
        "stripe_secret_key": settings.get("stripe_secret_key", ""),
        "stripe_account_id": settings.get("stripe_account_id", ""),
        "stripe_account_name": settings.get("stripe_account_name", ""),
    }

    # Load webhook endpoints (stored as JSON array)
    webhooks_json = settings.get("stripe_webhooks", "[]")
    try:
        result["webhooks"] = json.loads(webhooks_json)
    except (json.JSONDecodeError, TypeError):
        result["webhooks"] = []

    return result


def _save_stripe_settings(data: dict) -> None:
    """Save Stripe settings to database.

    Args:
        data: Dictionary of settings to save
    """
    try:
        for key, value in data.items():
            # Only save Stripe-related settings
            if not key.startswith("stripe_"):
                continue

            # Convert boolean to string for storage
            if isinstance(value, bool):
                value = str(value)

            # Skip empty values for optional fields (but not False boolean)
            if value is None or value == "":
                continue

            setting = Settings.query.filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                setting = Settings(key=key, value=value)
                db.session.add(setting)

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


@stripe_settings_bp.route("/stripe", methods=["GET"])
@login_required
def stripe_settings():
    """Display Stripe settings page."""
    stripe_settings_data = _load_stripe_settings()

    if request.headers.get("HX-Request"):
        return render_template(
            "settings/stripe.html",
            stripe_settings=stripe_settings_data,
        )

    return redirect(url_for("settings.page"))
