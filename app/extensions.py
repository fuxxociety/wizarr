import os

from flask import current_app, request, session
from flask_apscheduler import APScheduler
from flask_babel import Babel
from flask_htmx import HTMX
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_restx import Api
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy

# Instantiate extensions
db = SQLAlchemy()
babel = Babel()
sess = Session()
scheduler = APScheduler()
htmx = HTMX()
login_manager = LoginManager()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],  # No default limits
    storage_uri="memory://",
    enabled=False,  # Explicitly disabled by default
)

# Initialize Flask-RESTX API with OpenAPI configuration
# This will be initialized later with the blueprint in api_routes.py
api = Api(
    title="Wizarr API",
    version="2.2.1",
    description="Multi-server invitation manager for Plex, Jellyfin, Emby & AudiobookShelf",
    doc="/docs/",  # Swagger UI will be available at /api/docs/
    validate=True,
    ordered=True,
)

# Define API key security scheme for OpenAPI
api.authorizations = {
    "apikey": {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "API key required for all endpoints",
    }
}


# Initialize with app
def init_extensions(app):
    """Initialize Flask extensions with clean separation of concerns."""
    # Core extensions initialization
    sess.init_app(app)
    babel.init_app(app, locale_selector=_select_locale)

    # Scheduler initialization - Flask-APScheduler handles Gunicorn properly
    should_skip_scheduler = (
        "pytest" in os.getenv("_", "")
        or os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("FLASK_SKIP_SCHEDULER") == "true"
        or os.getenv("WIZARR_DISABLE_SCHEDULER", "false").lower()
        in ("true", "1", "yes")
    )

    if not should_skip_scheduler:
        # Configure Flask-APScheduler for Gunicorn compatibility
        app.config["SCHEDULER_API_ENABLED"] = False  # Disable API for security
        app.config["SCHEDULER_JOBSTORE_URL"] = app.config.get("SQLALCHEMY_DATABASE_URI")

        scheduler.init_app(app)

        # Register tasks with the scheduler
        from app.tasks.maintenance import (
            _get_expiry_check_interval,
            check_expiring,
        )
        from app.tasks.update_check import fetch_and_cache_manifest

        # Add the expiry check task to the scheduler, passing the app instance
        scheduler.add_job(
            id="check_expiring",
            func=lambda: check_expiring(app),
            trigger="interval",
            minutes=_get_expiry_check_interval(),
            replace_existing=True,
        )

        # Add the manifest fetch task to run every 24 hours
        scheduler.add_job(
            id="fetch_manifest",
            func=lambda: fetch_and_cache_manifest(app),
            trigger="interval",
            hours=24,
            replace_existing=True,
        )

        # Start the scheduler - Flask-APScheduler handles Gunicorn coordination
        try:
            if not scheduler.running:
                scheduler.start()
                app.logger.info("APScheduler started successfully")
            else:
                app.logger.info("APScheduler already running")
        except Exception as e:
            app.logger.warning(f"Failed to start APScheduler: {e}")

    # Continue with remaining extensions
    htmx.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"  # type: ignore[assignment]
    db.init_app(app)

    limiter.init_app(app)
    # Flask-RESTX API will be initialized with the blueprint

    # Always fetch manifest on startup after DB is initialized
    if not should_skip_scheduler:
        try:
            from app.tasks.update_check import fetch_and_cache_manifest

            fetch_and_cache_manifest(app)
        except Exception as e:
            app.logger.info("Initial manifest fetch failed: %s", e)


@login_manager.user_loader
def load_user(user_id):
    """Translate *user_id* from the session back into a user instance.

    Two cases are supported for backward-compatibility:

    1. ``"admin"`` – legacy constant representing the sole admin account
       backed by ``Settings`` rows.  We keep it around so existing sessions
       remain valid after upgrading.
    2. A decimal string – primary key of an ``AdminAccount`` row.
    """

    from .models import (  # imported lazily to avoid circular deps
        AdminAccount,
        AdminUser,
    )

    # ── legacy single-admin token ───────────────────────────────────────────
    if user_id == "admin":
        return AdminUser()

    # ── new multi-admin accounts ───────────────────────────────────────────
    if user_id.isdigit():
        return db.session.get(AdminAccount, int(user_id))

    return None


def _normalize_locale(code: str | None) -> str | None:
    """Normalise locale codes to the internal form, handling case and separators."""
    if not code:
        return None

    supported = current_app.config["LANGUAGES"]
    candidate = code.strip()
    if not candidate:
        return None

    candidate = candidate.replace("-", "_")
    lowered_map = {key.lower(): key for key in supported}

    if candidate.lower() in lowered_map:
        return lowered_map[candidate.lower()]

    base = candidate.split("_", 1)[0]
    return lowered_map.get(base.lower())


def _select_locale():
    supported_keys = current_app.config["LANGUAGES"].keys()
    forced = current_app.config.get("FORCE_LANGUAGE") or os.getenv("FORCE_LANGUAGE")
    if forced:
        normalised = _normalize_locale(forced)
        if normalised:
            return normalised
        current_app.logger.warning(
            "FORCE_LANGUAGE=%s ignored - unsupported locale", forced
        )

    if arg := request.args.get("lang"):
        normalised = _normalize_locale(arg)
        if normalised:
            session["lang"] = normalised
            return normalised

    if stored := session.get("lang"):
        if normalised := _normalize_locale(stored):
            if normalised != stored:
                session["lang"] = normalised
            return normalised
        session.pop("lang", None)

    if best := request.accept_languages.best_match(supported_keys):
        return best

    return current_app.config.get("BABEL_DEFAULT_LOCALE", "en")
