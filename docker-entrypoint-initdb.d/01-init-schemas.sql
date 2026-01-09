-- =========================================================================
-- Initialize Database Schemas for Wizarr and Stripe Sync Engine
-- =========================================================================
-- This script runs automatically when PostgreSQL container starts for the
-- first time. It creates the necessary schemas for both applications.
-- =========================================================================

-- Create Stripe schema for stripe-sync-engine
CREATE SCHEMA IF NOT EXISTS stripe;
COMMENT ON SCHEMA stripe IS 'Stripe Sync Engine data - synced from Stripe API';

-- Create public schema (if not exists) for Wizarr
-- Public schema exists by default but we ensure it's available
CREATE SCHEMA IF NOT EXISTS public;
COMMENT ON SCHEMA public IS 'Wizarr application data';

-- Grant privileges to postgres user (used by both services)
GRANT ALL PRIVILEGES ON SCHEMA stripe TO postgres;
GRANT ALL PRIVILEGES ON SCHEMA public TO postgres;

-- Set default privileges for future tables in stripe schema
ALTER DEFAULT PRIVILEGES IN SCHEMA stripe GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA stripe GRANT ALL ON SEQUENCES TO postgres;

-- Set default privileges for future tables in public schema
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres;

-- Note: The stripe-sync-engine will automatically create its own tables
-- in the stripe schema when it first connects. No manual table creation needed.
