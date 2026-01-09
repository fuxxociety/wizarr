# Wizarr Database Schema Analysis

## Overview

This document provides a comprehensive analysis of the Wizarr database schema based on all migration files from `20250522_create_database.py` through `eecad7c18ac3_20251209_merge_max_sessions_and_password_reset.py`.

## Migration Timeline

### Initial Schema (20250522_create_database.py)
- Created base tables: `notification`, `settings`, `user`, `invitation`
- Established basic invitation and user management system

### Library Management (20250523 - 20250618)
- Added `library` table for media library management
- Created `invite_library` junction table for invitation-library associations
- Added live TV support with `plex_allow_channels`
- Made library IDs unique per server (composite unique constraint)

### Multi-Server Support (20250611 - 20250612)
- Added `media_server` table to support multiple Plex/Jellyfin/Emby servers
- Migrated legacy single-server settings to new multi-server architecture
- Added `identity` table to track users across multiple servers
- Made emails nullable to support varied authentication methods

### Wizard System (20250619 - 20250712)
- Added `wizard_step` table for customizable onboarding flows
- Added `wizard_bundle` and `wizard_bundle_step` for grouping steps
- Added category field to wizard steps (pre_invite vs post_invite)
- Migrated template variables in wizard markdown content

### Authentication & Security (20250705 - 20251120)
- Added `admin_account` table for admin user management
- Added `webauthn_credential` table for passwordless authentication
- Added `api_key` table for API access control
- Added `password_reset_token` table for user password resets

### Universal Settings (20250714 - 20250717)
- Consolidated server-specific toggles into universal `allow_downloads` and `allow_live_tv`
- Added `allow_mobile_uploads` for camera upload permissions
- Deprecated platform-specific columns (plex_*, jellyfin_*, emby_*)

### Connections System (20250729)
- Added `ombi_connection` table for Ombi/Overseerr integrations
- Added `expired_user` table to track deleted users
- Added per-server expiry support in `invitation_server`
- Migrated Discord/Overseerr settings from key-value to structured tables

### Invitation Improvements (20250813 - 20250814)
- Added `invitation_user` many-to-many table to track all users per invitation
- Improved invitation-server foreign key constraints with CASCADE
- Added recovery logic to link existing users to invitations via code field
- Added `max_active_sessions` to limit concurrent user sessions

### User Metadata (20250905 - 20250927)
- Added `notes` field for admin comments on users
- Added caching fields: `library_access_json`, `raw_policies_json`
- Added permission fields: `allow_downloads`, `allow_live_tv`, `allow_camera_upload`
- Added `accessible_libraries` JSON field
- Added `is_admin` and `is_disabled` flags

### Activity Monitoring (20251018 - Plus Feature)
- Added `activity_session` table for real-time playback tracking
- Added `activity_snapshot` table for detailed session states
- Added `historical_import_job` table for importing past playback data
- Added `audit_log` table for admin action tracking
- Linked activity to Wizarr users/identities for cross-server tracking

### Foreign Key Cleanup (20251027 - 20251103)
- Fixed all foreign key constraints to properly CASCADE or SET NULL
- Ensured proper cleanup when parent records are deleted
- Fixed SQLite-specific foreign key recreation issues

## Final Schema Structure

### Core Tables (13 tables)
1. **settings** - System configuration key-value pairs
2. **notification** - Notification provider configurations
3. **identity** - User identities spanning multiple servers
4. **admin_account** - Administrator accounts
5. **webauthn_credential** - Passwordless authentication credentials
6. **api_key** - API access keys
7. **media_server** - Media server configurations
8. **library** - Media libraries per server
9. **user** - Media server users
10. **password_reset_token** - Password reset tokens
11. **expired_user** - Archive of expired users
12. **invitation** - Invitation codes
13. **ombi_connection** - Ombi/Overseerr integrations

### Association Tables (4 tables)
1. **invitation_server** - Invitation ↔ Server (many-to-many)
2. **invite_library** - Invitation ↔ Library (many-to-many)
3. **invitation_user** - Invitation ↔ User (many-to-many)
4. **wizard_bundle_step** - Bundle ↔ Step (many-to-many with ordering)

### Wizard Tables (2 tables)
1. **wizard_bundle** - Step collections
2. **wizard_step** - Individual onboarding steps

### Activity/Audit Tables (3 tables - Plus Feature)
1. **activity_session** - Playback session tracking
2. **activity_snapshot** - Session state snapshots
3. **historical_import_job** - Background import jobs
4. **audit_log** - Admin action logging

## Key Relationships

### User Management Flow
```
identity (1) ←→ (many) user
user (many) ←→ (1) media_server
user (many) ←→ (many) invitation [via invitation_user]
invitation (many) ←→ (many) media_server [via invitation_server]
invitation (many) ←→ (many) library [via invite_library]
```

### Activity Tracking Flow
```
media_server (1) ←→ (many) activity_session
activity_session (1) ←→ (many) activity_snapshot
activity_session (many) ←→ (1) user [wizarr_user_id]
activity_session (many) ←→ (1) identity [wizarr_identity_id]
```

### Wizard/Onboarding Flow
```
wizard_bundle (1) ←→ (many) wizard_bundle_step (many) ←→ (1) wizard_step
invitation (many) ←→ (1) wizard_bundle
```

## Foreign Key Behaviors

### CASCADE DELETE (parent deletion removes children)
- `media_server` → `library`, `user`, `activity_session`, `historical_import_job`, `ombi_connection`
- `admin_account` → `webauthn_credential`, `api_key`
- `user` → `password_reset_token`, `activity_session`
- `invitation` → `invitation_server`, `invite_library`, `invitation_user`
- `wizard_bundle` → `wizard_bundle_step`
- `wizard_step` → `wizard_bundle_step`
- `activity_session` → `activity_snapshot`

### SET NULL (parent deletion nullifies reference)
- `user` → `invitation.used_by_id`
- `media_server` → `invitation.server_id`, `expired_user.server_id`
- `identity` → `user.identity_id`, `activity_session.wizarr_identity_id`
- `wizard_bundle` → `invitation.wizard_bundle_id`
- `admin_account` → `audit_log.admin_id`

## Data Types & PostgreSQL Equivalents

| SQLAlchemy Type | PostgreSQL Type | Notes |
|----------------|----------------|-------|
| `sa.Integer()` | `INTEGER` or `SERIAL` | SERIAL for primary keys |
| `sa.String()` | `VARCHAR` | No length limit specified |
| `sa.Text()` | `TEXT` | For long content |
| `sa.Boolean()` | `BOOLEAN` | True/False values |
| `sa.DateTime()` | `TIMESTAMP` | Without timezone |
| `sa.JSON()` | `JSON` | Native JSON support |
| `sa.LargeBinary()` | `BYTEA` | For WebAuthn keys |
| `sa.BigInteger()` | `BIGINT` | For large millisecond values |
| `sa.Float()` | `REAL` | For progress percentages |

## Indexes

### Activity Performance Indexes
- Single column: server_id, user_name, started_at, active, media_type, session_id, reference_id
- Composite: (server_id, started_at), (user_name, started_at)
- Wizarr linking: wizarr_user_id, wizarr_identity_id

### Activity Snapshot Indexes
- Single column: session_id, timestamp, state
- Composite: (session_id, timestamp)

### Historical Import Indexes
- Single column: server_id, status
- Composite: (server_id, status)

## Special Considerations

### SQLite-Specific Migrations
Many migrations included SQLite-specific code for:
- Foreign key constraint modifications (requires table recreation)
- PRAGMA commands for FK enforcement
- Batch alter table operations

### Data Migration Logic
Several migrations included data transformations:
- Migration of settings to media_server table
- Population of identity table from user emails
- Recovery of invitation-user relationships
- Consolidation of platform-specific settings

### Idempotency
The generated SQL script uses:
- `CREATE TABLE IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS`
- `ON CONFLICT DO NOTHING` for version tracking
- `DO $$ ... END $$` blocks for conditional constraints

## Usage

The generated `init_schema.sql` file can be used to:
1. Initialize a fresh PostgreSQL database
2. Compare against existing schema for validation
3. Generate documentation
4. Serve as a reference for schema understanding

To apply the schema:
```bash
psql -U username -d wizarr -f init_schema.sql
```

## Migration Version
Final migration version: `eecad7c18ac3` (2025-12-09)

This represents a merge point of two parallel migration branches:
- `080eaac6e013` (max_active_sessions feature)
- `c854ad44aad5` (password_reset_token CASCADE fix)
