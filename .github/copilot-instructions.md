# Wizarr AI Agent Instructions

This guide helps AI agents become productive contributors to Wizarr, a multi-server media invitation and management system.

## Big Picture Architecture

**Wizarr** is a **Flask + HTMX** application managing user invitations across multiple media servers (Plex, Jellyfin, Emby, AudiobookShelf, Komga, Kavita, Romm) with:
- **Clean Architecture**: Dependencies flow downward only (Presentation → Application → Domain → Infrastructure)
- **Multi-server invitations**: Users can accept invites for multiple servers in one flow
- **Two-phase wizard**: Pre-invite (before account creation) and post-invite (after account creation) steps
- **Activity monitoring & analytics**: Real-time dashboard and historical analysis
- **Subscription tiers & payment**: Stripe integration with tiered feature access

### Core Layers

1. **Presentation**: Flask blueprints (`app/blueprints/*/`), HTMX templates, REST API
2. **Application**: Services (`app/services/*/`), invitation flow orchestration, business logic
3. **Domain**: Models (`app/models.py`), activity events, value objects
4. **Infrastructure**: Database (SQLAlchemy), media server clients, external APIs

### Key Integration Points

- **Wizard Flow** ([WIZARD_ARCHITECTURE.md](../WIZARD_ARCHITECTURE.md)): `/pre-wizard/` → join form → `/post-wizard/` → completion
- **Invitation Manager**: Coordinates multi-server user creation, library assignment, expiry validation
- **Media Clients**: Pluggable per-server clients (Plex, Jellyfin, etc.) via `@register_media_client()` decorator
- **Activity Service**: Facade pattern coordinating analytics, ingestion, maintenance, queries
- **Subscription System**: Ties feature access (Discord, SSO, request systems) to user tiers

## Critical Workflows

### Running the Application

```bash
# Development
python run.py                    # Runs with DevelopmentConfig

# With environment variables
FLASK_ENV=development python run.py

# Using Gunicorn (production)
gunicorn -c gunicorn.conf.py run:app
```

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_api_restx.py

# With output
pytest -s tests/test_invitation_flow.py

# For E2E tests (uses playwright)
pytest tests/test_final_integration.py --playwright
```

### Database Migrations

```bash
# Upgrade to latest
flask db upgrade

# Create migration from model changes
flask db migrate -m "description"

# See migration history
flask db current
```

### Key Configuration Files

- `pyproject.toml`: Dependencies, project metadata
- `app/config.py`: Flask config (development vs production)
- `pytest.ini`: Test configuration
- `gunicorn.conf.py`: Production WSGI settings

## Project-Specific Conventions & Patterns

### Blueprint Organization

Each media server type and feature gets a **blueprint** in `app/blueprints/`. Example patterns:

```python
# app/blueprints/wizard/routes.py
from flask import Blueprint, render_template, request
from app.extensions import htmx

wizard_bp = Blueprint("wizard", __name__, url_prefix="/wizard")

@wizard_bp.route("/pre-wizard/<int:idx>")
def pre_wizard(idx: int = 0):
    # Wizard routes return _content.html for HTMX swaps, frame.html for initial load
    if not request.headers.get("HX-Request"):
        page = "wizard/frame.html"
    else:
        page = "wizard/_content.html"
    return render_template(page, body_html=html, ...)
```

**Don't break these patterns:**
- HTMX requests return content-only templates (`_content.html`)
- Initial loads return full frames (`frame.html`)
- All blueprints registered in `app/blueprints/__init__.py`

### Service Layer with Dependency Injection

Services are **constructor-injected** and never access global state directly:

```python
# ✅ GOOD: Constructor injection
class InvitationService:
    def __init__(self, db: SQLAlchemy, config: Config):
        self.db = db
        self.config = config

    def process_invitation(self, code: str) -> dict:
        # Business logic here, returns DTO
        return {"status": "created", "user_id": 123}

# ❌ AVOID: Global state access
from app.models import User
class BadService:
    def process(self):
        User.query.all()  # ← Direct ORM access, hard to test
```

### Media Client Registration

Media server clients use a **plugin pattern**:

```python
# app/services/media/plex.py
@register_media_client("plex")
class PlexClient(RestApiMixin):
    def libraries(self) -> dict[str, str]:
        # Returns DTO, never ORM objects
        return {"library_id": "library_name"}

    def create_user(self, username: str, password: str) -> str:
        # Returns user ID only
        return user_id
```

**Key rule**: Media clients must:
- Implement `RestApiMixin` for shared HTTP utilities
- Return DTOs (dicts), never ORM models
- Handle authentication separately per server type
- Be registered with `@register_media_client("name")`

### HTMX + Flask Pattern

The **"Five Line Rule"**: Flask routes should render templates, not contain logic:

```python
# ✅ GOOD: Logic in service, template in route
@users_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id: int):
    user_dto = UserService().get_user_details(user_id)
    return render_template("user_detail.html", user=user_dto)

# ❌ AVOID: Business logic in route
@users_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id: int):
    user = User.query.get(user_id)
    user.last_login = datetime.now()
    db.session.commit()
    return render_template("user_detail.html", ...)
```

### Model Relationships & Association Tables

Wizarr uses association tables for many-to-many relationships with metadata:

```python
# Track which users used which invitations (with timestamp + server info)
invitation_users = db.Table(
    "invitation_user",
    db.Column("invite_id", db.Integer, db.ForeignKey("invitation.id"), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("used_at", db.DateTime, default=datetime.now),
    db.Column("server_id", db.Integer, db.ForeignKey("media_server.id"), nullable=True),
)
```

**Pattern**: Use association tables for:
- Tracking **when** relationships occur (timestamps)
- Adding **metadata** to relationships (server_id, status flags)
- Enabling **independent usage** per server (multi-server invitations)

### Testing: Mock API Pattern

Tests use a **mock state manager** to simulate media server responses:

```python
from tests.conftest import setup_mock_servers

def test_user_creation(client):
    setup_mock_servers()

    # Mock API will track this call
    response = client.post("/api/users", json={"username": "test"})

    # Verify mock state
    mock_state = get_mock_state()
    assert len(mock_state.users) == 1
```

**Key patterns**:
- Use `@patch('app.services.media.service.get_client_for_media_server')` to mock clients
- Check mock state after operations: `get_mock_state().users`, `get_mock_state().errors`
- Create realistic data using model factories before testing

### Database Schema: Multi-Server Invitations

Key association table for multi-server support:

```python
invitation_servers = db.Table(
    "invitation_server",
    db.Column("invite_id", db.Integer, db.ForeignKey("invitation.id"), primary_key=True),
    db.Column("server_id", db.Integer, db.ForeignKey("media_server.id"), primary_key=True),
    db.Column("used", db.Boolean, default=False),  # ← Per-server usage tracking
    db.Column("expires", db.DateTime, nullable=True),  # ← Per-server expiry
)
```

**Pattern**: Users create accounts independently on each server when using multi-server invitations.

## Essential Knowledge Files

| File | Purpose |
|------|---------|
| [WIZARD_ARCHITECTURE.md](../WIZARD_ARCHITECTURE.md) | Two-phase wizard, HTMX flow, template pattern, phase-aware routing |
| [tests/README.md](../tests/README.md) | Test structure, mock API pattern, test categories, best practices |
| [app/__init__.py](../app/__init__.py) | App factory, blueprint registration, extension initialization |
| [app/extensions.py](../app/extensions.py) | Flask extensions: DB, API (Flask-RESTX), HTMX, Babel, Session, Login |
| [app/services/invitation_manager.py](../app/services/invitation_manager.py) | Core: multi-server invitation processing, user creation, expiry |
| [app/services/media/](../app/services/media/) | Media client implementations (plex.py, jellyfin.py, etc.) |
| [app/blueprints/wizard/routes.py](../app/blueprints/wizard/routes.py) | Wizard routes: phase-aware rendering, HTMX handling |
| [app/blueprints/api/](../app/blueprints/api/) | REST API endpoints with Flask-RESTX (OpenAPI auto-docs at `/api/docs/`) |
| [app/templates/wizard/](../app/templates/wizard/) | Wizard templates: frame.html (full), steps.html (chrome), _content.html (HTMX swap) |

## Cross-Component Communication

### Data Flow Example: Creating a User from Invite

```
1. User visits /invite/<code> (public blueprint)
   ↓
2. join_form() route validates invite, renders join form
   ↓
3. User submits form → POST /invite/<code>/join
   ↓
4. InvitationManager.process_invitation()
   ├─ Validates expiry, usage, server access
   ├─ Gets media client for each server
   ├─ Client.create_user(username, password) → returns user_id
   ├─ Records account in local DB (User model)
   └─ Returns DTO with success status
   ↓
5. Route redirects to /post-wizard (if configured)
   ↓
6. post_wizard() renders post-invite steps
   ↓
7. User completes wizard → /wizard/complete → success page
```

### API Documentation

- **Interactive**: `http://localhost:5000/api/docs/` (Swagger UI)
- **OpenAPI Spec**: `http://localhost:5000/api/swagger.json`
- **Auto-generated**: Flask-RESTX automatically documents all routes with `@api.marshal_with()`, `@api.expect()`

## Common Pitfalls to Avoid

1. **Importing ORM models in services**: Return DTOs, not `User`/`Invitation` objects
2. **Skipping HTMX request detection**: Always check `request.headers.get("HX-Request")`
3. **Global state in tests**: Use `setup_mock_servers()` to reset between tests
4. **Blocking operations in routes**: Use `@scheduler.scheduled_job()` for background tasks
5. **Per-server assumptions**: Remember multi-server invitations exist—check `invitation.servers` relationship
6. **Missing error handling**: Services should validate input, return meaningful errors
7. **Upward imports**: Never import from presentation layer in domain/infrastructure layers

## Specialized AI Agents

The project includes pre-configured agent personalities in `.claude/agents/`:

- **backend-logic-specialist.md**: Flask routes, database operations, service architecture
- **integration-orchestrator.md**: Cross-layer integration, component coordination, merge conflicts
- **htmx-frontend-specialist.md**: Template logic, JavaScript, HTMX interactions
- **qa-test-automation.md**: Test design, mocking, E2E test automation
- **tailwind-ui-stylist.md**: CSS, Tailwind components, UI polish

These agent profiles provide specialized expertise—use them when working on their respective domains!
