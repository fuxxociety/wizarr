# PostgreSQL Fork - Quick Reference

> This is a PostgreSQL fork of Wizarr that uses PostgreSQL v17 instead of SQLite, with integrated Stripe Sync Engine support.

## What's Different?

- 🐘 **PostgreSQL v17** instead of SQLite
- 💳 **Stripe Sync Engine** for payment/subscription tracking
- 📊 **Schema Separation**: Wizarr uses `public` schema, Stripe uses `stripe` schema
- 🚀 **Optimized Performance**: Connection pooling, indexes, and proper constraints
- 📦 **Docker-based**: Everything runs in containers with automatic initialization

## Quick Start

```bash
# 1. Clone and configure
git clone <your-fork-url>
cd wizarr
cp .env.example .env
# Edit .env with your Stripe API keys

# 2. Start everything
docker-compose up -d

# 3. Access Wizarr
open http://localhost:5690
```

That's it! The database will be automatically initialized on first run.

## What Gets Started?

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL | 5432 | Shared database for both services |
| Wizarr | 5690 | Main application (uses `public` schema) |
| Stripe Sync | 3000 | Syncs Stripe data (uses `stripe` schema) |

## Important Files

| File | Purpose |
|------|---------|
| [POSTGRES_MIGRATION.md](POSTGRES_MIGRATION.md) | Complete migration guide and documentation |
| [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md) | Quick reference of all changes made |
| [.env.example](.env.example) | Environment variable template |
| [docker-compose.yml](docker-compose.yml) | Service orchestration |
| [docker-entrypoint-initdb.d/](docker-entrypoint-initdb.d/) | Database initialization scripts |

## Common Commands

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f wizarr        # Wizarr logs
docker-compose logs -f postgres      # Database logs
docker-compose logs -f stripe-sync   # Stripe Sync logs

# Stop services
docker-compose down

# Reset everything (⚠️ deletes all data)
docker-compose down -v
docker-compose up -d

# Database access
docker-compose exec postgres psql -U postgres -d postgres

# Backup database
docker-compose exec postgres pg_dump -U postgres -d postgres > backup.sql

# Restore database
cat backup.sql | docker-compose exec -T postgres psql -U postgres -d postgres
```

## Database Schemas

### Wizarr Schema (`public`)
```sql
-- 22 tables including:
- users, invitations, media_servers
- activity_session, audit_log
- wizard_steps, admin_accounts
- ... and more
```

### Stripe Schema (`stripe`)
```sql
-- Auto-created by Stripe Sync Engine:
- customers, subscriptions, invoices
- products, prices, payment_methods
- ... and more
```

## Requirements

- Docker & Docker Compose
- Stripe API keys (for Stripe Sync Engine)

## Upgrading from SQLite Wizarr

See [POSTGRES_MIGRATION.md](POSTGRES_MIGRATION.md) for detailed migration instructions.

**TL;DR**: Fresh start recommended. Export settings, start PostgreSQL fork, reimport settings.

## Troubleshooting

### Services won't start
```bash
# Check status
docker-compose ps

# Check logs
docker-compose logs

# Restart
docker-compose restart
```

### Database connection errors
```bash
# Verify PostgreSQL is healthy
docker-compose ps postgres

# Check if schemas exist
docker-compose exec postgres psql -U postgres -c "\dn"

# Check if tables exist
docker-compose exec postgres psql -U postgres -d postgres -c "SET search_path TO public; \dt"
```

### Stripe Sync not working
- Check that `.env` has valid `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`
- Restart stripe-sync: `docker-compose restart stripe-sync`
- Check logs: `docker-compose logs stripe-sync`

## Performance

The PostgreSQL setup is optimized for production use:

- ✅ Connection pooling (10 base + 20 overflow)
- ✅ 23 indexes on activity/audit tables
- ✅ Proper foreign key constraints with CASCADE
- ✅ Health checks on all services
- ✅ Automatic connection pre-ping and recycling

## Support

1. **General Wizarr issues**: See main Wizarr repository
2. **PostgreSQL migration issues**: Check [POSTGRES_MIGRATION.md](POSTGRES_MIGRATION.md)
3. **Stripe Sync issues**: See [Stripe Sync Engine docs](https://github.com/supabase-community/stripe-sync-engine)

## Contributing

This is a fork focused on PostgreSQL support. Contributions welcome for:
- PostgreSQL-specific optimizations
- Migration improvements
- Stripe integration enhancements
- Documentation improvements

## License

Same license as the original Wizarr project.

---

**Need more details?** Read the complete [POSTGRES_MIGRATION.md](POSTGRES_MIGRATION.md) guide.
