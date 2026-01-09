# PostgreSQL Migration Guide

This fork of Wizarr has been migrated from SQLite to PostgreSQL v17. This document explains the changes and how to use the new setup.

## What Changed

### Database
- **SQLite → PostgreSQL v17**: The application now uses PostgreSQL instead of SQLite
- **Unified Schema**: All SQLite migrations have been combined into a single PostgreSQL initialization script
- **Schema Separation**:
  - `public` schema: Wizarr application data
  - `stripe` schema: Stripe Sync Engine data (for payment/subscription tracking)

### Docker Compose
- **PostgreSQL Service**: Added PostgreSQL 17 container
- **Stripe Sync Engine**: Added Supabase Stripe Sync Engine container
- **Automatic Schema Initialization**: Database schemas are created automatically on first startup

### Application Configuration
- **DATABASE_URL**: Now configured via environment variable (set in docker-compose.yml)
- **Connection Pooling**: Configured for PostgreSQL with proper pool sizes
- **Backward Compatibility**: Falls back to SQLite for local development without docker

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL v17 Container                  │
│  ┌────────────────────────┐  ┌──────────────────────────┐  │
│  │   public schema        │  │    stripe schema         │  │
│  │  (Wizarr data)         │  │  (Stripe Sync data)      │  │
│  │                        │  │                          │  │
│  │  - users               │  │  - customers             │  │
│  │  - invitations         │  │  - subscriptions         │  │
│  │  - media_servers       │  │  - invoices              │  │
│  │  - activity_sessions   │  │  - products              │  │
│  │  - admin_accounts      │  │  - prices                │  │
│  │  - ... (22 tables)     │  │  - ... (auto-created)    │  │
│  └────────────────────────┘  └──────────────────────────┘  │
│           ▲                              ▲                  │
└───────────┼──────────────────────────────┼──────────────────┘
            │                              │
    ┌───────┴────────┐          ┌─────────┴──────────┐
    │  Wizarr App    │          │  Stripe Sync       │
    │  (Port 5690)   │          │  (Port 3000)       │
    └────────────────┘          └────────────────────┘
```

## Getting Started

### 1. Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and add your Stripe API keys:

```bash
STRIPE_SECRET_KEY=sk_test_your_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret_here
```

### 2. Start the Services

```bash
docker-compose up -d
```

This will:
1. Start PostgreSQL v17
2. Automatically create `public` and `stripe` schemas
3. Initialize Wizarr database schema in `public` schema
4. Start Stripe Sync Engine connected to `stripe` schema
5. Start Wizarr application connected to `public` schema

### 3. Verify Setup

Check that all services are running:

```bash
docker-compose ps
```

You should see:
- `postgres` - PostgreSQL database (port 5432)
- `stripe-sync` - Stripe Sync Engine (port 3000)
- `wizarr` - Wizarr application (port 5690)

### 4. Access Applications

- **Wizarr**: http://localhost:5690
- **Stripe Sync API**: http://localhost:3000
- **PostgreSQL**: localhost:5432 (postgres/rock-fall-death)

## Database Schema

### Wizarr Schema (public)
The Wizarr schema contains 22 tables organized into these categories:

**Core Tables:**
- `settings` - System configuration
- `notification` - Notification providers
- `identity` - User identities across servers
- `admin_account` - Administrator accounts
- `webauthn_credential` - Passwordless auth credentials
- `api_key` - API authentication keys

**Media Server Tables:**
- `media_server` - Plex/Jellyfin/Emby servers
- `library` - Media libraries

**User Tables:**
- `user` - Media server users
- `password_reset_token` - Password reset tokens
- `expired_user` - Archived expired users

**Invitation Tables:**
- `invitation` - Invitation codes
- `invitation_server` - Invite-server relationships
- `invite_library` - Invite-library relationships
- `invitation_user` - Invite-user tracking

**Wizard Tables:**
- `wizard_bundle` - Setup step collections
- `wizard_step` - Individual setup steps
- `wizard_bundle_step` - Bundle-step associations

**Integration Tables:**
- `ombi_connection` - Ombi/Overseerr connections

**Activity Monitoring Tables (Plus Feature):**
- `activity_session` - Playback tracking
- `activity_snapshot` - Playback state snapshots
- `historical_import_job` - Historical data import jobs

**Audit Tables (Plus Feature):**
- `audit_log` - Admin action audit trail

### Stripe Schema (stripe)
The Stripe schema is automatically managed by Stripe Sync Engine. Tables include:
- `customers` - Stripe customers
- `subscriptions` - Active/past subscriptions
- `invoices` - Invoice records
- `products` - Product catalog
- `prices` - Pricing information
- And more...

## Migration from SQLite (Existing Installations)

If you're migrating an existing Wizarr installation from SQLite to PostgreSQL:

### Option 1: Fresh Start (Recommended)
The easiest approach is to start fresh with PostgreSQL:

1. Back up your existing SQLite database
2. Export any critical configuration (admin credentials, media server settings, etc.)
3. Start the new PostgreSQL-based stack
4. Manually reconfigure your settings

### Option 2: Data Migration (Advanced)
For preserving existing data:

1. Use `pgloader` or similar tool to migrate SQLite → PostgreSQL
2. Manually adjust any SQLite-specific data types or constraints
3. Update the `alembic_version` table to reflect the current migration

```bash
# Example using pgloader (not included, manual setup required)
pgloader sqlite:///path/to/database.db postgresql://postgres:rock-fall-death@localhost:5432/postgres
```

**Note**: Data migration is complex and may require manual intervention. Test thoroughly before using in production.

## Development

### Local Development (Without Docker)

For local development, the application will fall back to SQLite:

```bash
# Install dependencies
uv sync

# Run migrations (if needed)
uv run flask db upgrade

# Run the application
uv run python dev.py
```

The application will automatically use SQLite at `./database/database.db` when `DATABASE_URL` is not set.

### Using PostgreSQL Locally

To use PostgreSQL for local development:

1. Start just the PostgreSQL container:
   ```bash
   docker-compose up -d postgres
   ```

2. Set the DATABASE_URL environment variable:
   ```bash
   export DATABASE_URL=postgresql://postgres:rock-fall-death@localhost:5432/postgres
   ```

3. Run the application locally:
   ```bash
   uv run python dev.py
   ```

## Database Management

### Accessing PostgreSQL

Connect to the database using psql:

```bash
docker-compose exec postgres psql -U postgres -d postgres
```

### Viewing Wizarr Tables

```sql
\c postgres
SET search_path TO public;
\dt
```

### Viewing Stripe Tables

```sql
\c postgres
SET search_path TO stripe;
\dt
```

### Backup Database

```bash
docker-compose exec postgres pg_dump -U postgres -d postgres > backup.sql
```

### Restore Database

```bash
cat backup.sql | docker-compose exec -T postgres psql -U postgres -d postgres
```

## Troubleshooting

### PostgreSQL Connection Issues

If Wizarr can't connect to PostgreSQL:

1. Check that PostgreSQL is healthy:
   ```bash
   docker-compose ps postgres
   ```

2. Check logs:
   ```bash
   docker-compose logs postgres
   docker-compose logs wizarr
   ```

3. Verify DATABASE_URL is set correctly in docker-compose.yml

### Stripe Sync Issues

If Stripe Sync Engine isn't working:

1. Verify your Stripe API keys in `.env`
2. Check Stripe Sync logs:
   ```bash
   docker-compose logs stripe-sync
   ```

3. Verify the schema exists:
   ```bash
   docker-compose exec postgres psql -U postgres -d postgres -c "\dn"
   ```

### Schema Initialization Issues

If tables aren't created on first run:

1. Check initialization logs:
   ```bash
   docker-compose logs postgres | grep init
   ```

2. Manually verify the init scripts are mounted:
   ```bash
   docker-compose exec postgres ls -la /docker-entrypoint-initdb.d/
   ```

3. Recreate the database (will delete all data):
   ```bash
   docker-compose down -v
   docker-compose up -d
   ```

## Performance Considerations

### Connection Pooling
The application is configured with:
- Pool size: 10 connections
- Max overflow: 20 connections
- Connection pre-ping: Enabled
- Connection recycling: 1 hour

### Indexes
The schema includes optimized indexes for:
- Activity session queries (by server, user, time)
- Activity snapshots (by session, timestamp)
- Historical import jobs (by server, status)

### Monitoring

Monitor PostgreSQL performance:

```bash
# Check active connections
docker-compose exec postgres psql -U postgres -d postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Check database size
docker-compose exec postgres psql -U postgres -d postgres -c "SELECT pg_size_pretty(pg_database_size('postgres'));"

# Check table sizes
docker-compose exec postgres psql -U postgres -d postgres -c "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size FROM pg_tables WHERE schemaname IN ('public', 'stripe') ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"
```

## Files Changed

### Modified Files
- `pyproject.toml` - Added psycopg2-binary dependency
- `app/config.py` - Updated to use DATABASE_URL environment variable
- `docker-compose.yml` - Added PostgreSQL and Stripe Sync Engine services

### New Files
- `docker-entrypoint-initdb.d/01-init-schemas.sql` - Creates public and stripe schemas
- `docker-entrypoint-initdb.d/02-init-wizarr-schema.sql` - Creates all Wizarr tables
- `.env.example` - Environment variable template
- `POSTGRES_MIGRATION.md` - This documentation file

### Reference Files (Not Used at Runtime)
- `init_schema.sql` - Complete schema reference (combined migrations)
- `SCHEMA_ANALYSIS.md` - Detailed migration history analysis

## Support

For issues with:
- **Wizarr**: See the main Wizarr repository
- **PostgreSQL Migration**: Open an issue in this fork's repository
- **Stripe Sync Engine**: See [Supabase Stripe Sync Engine](https://github.com/supabase-community/stripe-sync-engine)

## License

This fork maintains the same license as the original Wizarr project.
