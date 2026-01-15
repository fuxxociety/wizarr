"""Flask-WTF forms for Stripe sync engine settings."""

from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField
from wtforms.validators import Length, Optional, Regexp


class StripeSettingsForm(FlaskForm):
    """Form for configuring Stripe Sync Engine settings."""

    stripe_enabled = BooleanField(
        str(_l("Enable Stripe Integration")),
        default=False,
        validators=[Optional()],
    )

    stripe_backfill_enabled = BooleanField(
        str(_l("Enable Backfill Sync (runs every minute)")),
        default=False,
        validators=[Optional()],
    )

    stripe_secret_key = StringField(
        str(_l("Stripe Secret Key")),
        validators=[
            Optional(),
            Length(min=107, max=120, message="Stripe secret key must be 107-120 characters"),
            Regexp(
                r"^sk_(test|live)_[a-zA-Z0-9]{99,107}$",
                message="Invalid Stripe secret key format (must start with sk_test_ or sk_live_ followed by 99-107 characters)",
            ),
        ],
        render_kw={
            "placeholder": "sk_test_...",
            "autocomplete": "off",
            "class": "form-control",
        },
    )

    stripe_webhook_endpoint = StringField(
        str(_l("Webhook Endpoint Path")),
        validators=[
            Optional(),
            Length(max=100, message="Endpoint path must be less than 100 characters"),
            Regexp(
                r"^/[a-zA-Z0-9_\-/]*$",
                message="Endpoint must start with / and contain only alphanumeric, underscore, hyphen, or slash characters",
            ),
        ],
        default="/webhooks/stripe",
        render_kw={
            "placeholder": "/webhooks/stripe",
            "class": "form-control",
        },
    )

    stripe_webhook_secret = StringField(
        str(_l("Stripe Webhook Secret")),
        validators=[
            Optional(),
            Length(min=32, message="Webhook secret must be at least 32 characters"),
            Regexp(
                r"^whsec_[a-zA-Z0-9]+$",
                message="Invalid webhook secret format (must start with whsec_)",
            ),
        ],
        render_kw={
            "placeholder": "whsec_...",
            "autocomplete": "off",
            "class": "form-control",
        },
    )
