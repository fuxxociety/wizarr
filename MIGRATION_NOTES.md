# Migration Implementation Notes

## Important: Handling Alembic Migrations

This PostgreSQL fork uses a **combined schema initialization approach** instead of running individual migrations. Here's what you need to know:

## How It Works

### On First Startup (Empty Database)
1. PostgreSQL container starts
2. Init scripts in `docker-entrypoint-initdb.d/` run automatically:
   - `01-init-schemas.sql` - Creates `public` and `stripe` schemas
   - `02-init-wizarr-schema.sql` - Creates all 22 tables with indexes
3. Alembic version is set to `eecad7c18ac3` (latest migration)
4. Wizarr starts and sees the database is already at the latest version
5. No migrations need to run ✅

### On Subsequent Startups
1. PostgreSQL starts with existing data
2. Init scripts are NOT run (PostgreSQL only runs them once)
3. Wizarr starts and checks migration version
4. Database is already at `eecad7c18ac3`, no action needed ✅

## About the Migrations Directory

The `migrations/` directory is **kept for reference only**. The individual migration files are no longer executed because:

1. All migrations are combined into `02-init-wizarr-schema.sql`
2. This single script represents the final state after all migrations
3. The `alembic_version` table is set to the latest version on initialization
4. SQLAlchemy/Alembic will skip all migrations since we're already "up to date"

## Future Migrations

### If You Need to Add New Tables/Columns

**Option 1: Create New Alembic Migrations (Recommended)**
```bash
# Create a new migration
uv run flask db migrate -m "add new feature"

# This will create a new migration file that:
# 1. Detects the current schema (from database)
# 2. Compares with models.py
# 3. Generates SQL to update schema

# Apply the migration
uv run flask db upgrade
```

**Option 2: Update the Init Script (For Forks)**
If you're maintaining a fork and want to keep the "combined schema" approach:

1. Make changes to `models.py`
2. Update `docker-entrypoint-initdb.d/02-init-wizarr-schema.sql` manually
3. Increment the version in the script
4. Test with fresh database: `docker-compose down -v && docker-compose up -d`

## Schema Version Tracking

The `alembic_version` table tracks which migrations have been applied:

```sql
-- Current version (set by init script)
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

INSERT INTO alembic_version (version_num)
VALUES ('eecad7c18ac3')
ON CONFLICT (version_num) DO NOTHING;
```

This tells Alembic that migration `eecad7c18ac3` (and all before it) have already been applied.

## Why This Approach?

### Benefits
- ✅ Faster startup (single script vs 45+ migrations)
- ✅ Cleaner PostgreSQL schema (proper types, not SQLite-compatible)
- ✅ Easier to review/audit complete schema
- ✅ No migration ordering issues
- ✅ Idempotent (can run multiple times safely)

### Trade-offs
- ⚠️ Can't migrate existing SQLite data automatically
- ⚠️ Individual migration history is "squashed"
- ⚠️ Must maintain init script separately

## Migration Strategy Comparison

### Approach 1: Run All Migrations (Original Wizarr)
```
Start → Run Migration 1 → Run Migration 2 → ... → Run Migration 45 → Done
```
- Works for SQLite → PostgreSQL migration
- Slow (45+ migrations)
- May have SQLite-specific syntax issues

### Approach 2: Combined Schema Init (This Fork)
```
Start → Run Combined Schema → Set Version → Done
```
- Fast (single script)
- PostgreSQL-optimized
- Clean slate only (no migration from SQLite)

## Handling Updates from Upstream Wizarr

If the original Wizarr project adds new migrations:

1. **Read the new migration** to understand what changed
2. **Update your init script** to include the new tables/columns
3. **Update the version number** in the init script
4. **Test with a fresh database** to ensure it works

Or:

1. **Keep the migrations directory** synchronized with upstream
2. **Let Alembic run new migrations** on existing databases
3. **Update init script** to match the final state (for new deployments)

## Best Practice Recommendations

### For Development
- Keep migrations directory for compatibility
- Let Alembic manage schema changes
- Test migrations before deploying

### For Production
- Use the combined init script for new deployments
- For existing deployments, run migrations normally
- Keep backups before schema changes

### For This Fork
- The init script is the source of truth for fresh installations
- Existing deployments can upgrade using normal Alembic migrations
- Document all schema changes in both places

## Testing Schema Changes

```bash
# Test with fresh database
docker-compose down -v  # Delete volumes
docker-compose up -d    # Recreate everything

# Verify tables
docker-compose exec postgres psql -U postgres -d postgres -c "SET search_path TO public; \dt"

# Check version
docker-compose exec postgres psql -U postgres -d postgres -c "SELECT * FROM alembic_version;"

# Verify Wizarr starts without errors
docker-compose logs wizarr | grep -i "error\|failed"
```

## Summary

- ✅ Init script creates complete schema on first run
- ✅ Alembic version is set to latest automatically
- ✅ No migrations need to run on startup
- ✅ Future migrations work normally
- ✅ Migrations directory kept for reference
- ⚠️ This approach is for fresh installations only
- ⚠️ Migrating from SQLite requires data migration tools

This design prioritizes simplicity and performance for new PostgreSQL deployments while maintaining compatibility with Alembic for future schema changes.
