-- =========================================================================
-- Wizarr Database Schema - PostgreSQL Initialization Script
-- =========================================================================
-- This script creates the complete database schema for Wizarr
-- Generated from migration history up to revision: eecad7c18ac3
-- Compatible with PostgreSQL 12+
-- =========================================================================

-- Enable foreign key constraint enforcement
SET client_min_messages = WARNING;

-- =========================================================================
-- Core Tables
-- =========================================================================

-- Settings table - Key-value configuration storage
CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR NOT NULL UNIQUE,
    value VARCHAR
);

-- Notification providers table
CREATE TABLE IF NOT EXISTS notification (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    type VARCHAR NOT NULL,
    url VARCHAR NOT NULL,
    username VARCHAR,
    password VARCHAR,
    channel_id INTEGER,
    notification_events VARCHAR NOT NULL DEFAULT 'user_joined,update_available'
);

-- Identity table - Represents a unique user identity across servers
CREATE TABLE IF NOT EXISTS identity (
    id SERIAL PRIMARY KEY,
    primary_email VARCHAR,
    primary_username VARCHAR,
    nickname VARCHAR,
    created_at TIMESTAMP NOT NULL
);

-- Admin account table - Administrator accounts for Wizarr
CREATE TABLE IF NOT EXISTS admin_account (
    id SERIAL PRIMARY KEY,
    username VARCHAR NOT NULL UNIQUE,
    password_hash VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL
);

-- WebAuthn credentials table - For passwordless authentication
CREATE TABLE IF NOT EXISTS webauthn_credential (
    id SERIAL PRIMARY KEY,
    admin_account_id INTEGER NOT NULL,
    credential_id BYTEA NOT NULL UNIQUE,
    public_key BYTEA NOT NULL,
    sign_count INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_used_at TIMESTAMP,
    FOREIGN KEY (admin_account_id) REFERENCES admin_account(id) ON DELETE CASCADE
);

-- API keys table - For API authentication
CREATE TABLE IF NOT EXISTS api_key (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    key_hash VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL,
    last_used_at TIMESTAMP,
    created_by_id INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL,
    FOREIGN KEY (created_by_id) REFERENCES admin_account(id) ON DELETE CASCADE
);

-- =========================================================================
-- Media Server Tables
-- =========================================================================

-- Media server table - Plex, Jellyfin, Emby servers
CREATE TABLE IF NOT EXISTS media_server (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    server_type VARCHAR NOT NULL,
    url VARCHAR NOT NULL,
    api_key VARCHAR,
    external_url VARCHAR,
    allow_downloads BOOLEAN NOT NULL DEFAULT FALSE,
    allow_live_tv BOOLEAN NOT NULL DEFAULT FALSE,
    allow_mobile_uploads BOOLEAN NOT NULL DEFAULT FALSE,
    verified BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL
);

-- Library table - Media libraries on servers
CREATE TABLE IF NOT EXISTS library (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    server_id INTEGER,
    FOREIGN KEY (server_id) REFERENCES media_server(id) ON DELETE CASCADE,
    UNIQUE (external_id, server_id)
);

-- =========================================================================
-- User Tables
-- =========================================================================

-- User table - Media server users created through invitations
CREATE TABLE IF NOT EXISTS "user" (
    id SERIAL PRIMARY KEY,
    token VARCHAR NOT NULL,
    username VARCHAR NOT NULL,
    email VARCHAR,
    code VARCHAR NOT NULL,
    photo VARCHAR,
    expires TIMESTAMP,
    server_id INTEGER,
    identity_id INTEGER,
    notes TEXT,
    library_access_json TEXT,
    raw_policies_json TEXT,
    allow_downloads BOOLEAN,
    allow_live_tv BOOLEAN,
    allow_camera_upload BOOLEAN,
    accessible_libraries TEXT,
    is_admin BOOLEAN,
    is_disabled BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (server_id) REFERENCES media_server(id) ON DELETE CASCADE,
    FOREIGN KEY (identity_id) REFERENCES identity(id) ON DELETE SET NULL
);

-- Password reset token table
CREATE TABLE IF NOT EXISTS password_reset_token (
    id SERIAL PRIMARY KEY,
    code VARCHAR NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN NOT NULL,
    used_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE
);

-- Expired user tracking table
CREATE TABLE IF NOT EXISTS expired_user (
    id SERIAL PRIMARY KEY,
    original_user_id INTEGER NOT NULL,
    username VARCHAR NOT NULL,
    email VARCHAR,
    invitation_code VARCHAR,
    server_id INTEGER,
    expired_at TIMESTAMP NOT NULL,
    deleted_at TIMESTAMP NOT NULL,
    FOREIGN KEY (server_id) REFERENCES media_server(id) ON DELETE SET NULL
);

-- =========================================================================
-- Invitation Tables
-- =========================================================================

-- Invitation table - Invitation codes for new users
CREATE TABLE IF NOT EXISTS invitation (
    id SERIAL PRIMARY KEY,
    code VARCHAR NOT NULL,
    used BOOLEAN NOT NULL,
    used_at TIMESTAMP,
    created TIMESTAMP NOT NULL,
    used_by_id INTEGER,
    expires TIMESTAMP,
    unlimited BOOLEAN,
    duration VARCHAR,
    specific_libraries VARCHAR,
    plex_allow_sync BOOLEAN,
    plex_home BOOLEAN,
    plex_allow_channels BOOLEAN,
    server_id INTEGER,
    wizard_bundle_id INTEGER,
    allow_downloads BOOLEAN,
    allow_live_tv BOOLEAN,
    allow_mobile_uploads BOOLEAN,
    max_active_sessions INTEGER,
    FOREIGN KEY (used_by_id) REFERENCES "user"(id) ON DELETE SET NULL,
    FOREIGN KEY (server_id) REFERENCES media_server(id) ON DELETE SET NULL,
    FOREIGN KEY (wizard_bundle_id) REFERENCES wizard_bundle(id) ON DELETE SET NULL
);

-- Invitation-Server association table (many-to-many)
CREATE TABLE IF NOT EXISTS invitation_server (
    invite_id INTEGER NOT NULL,
    server_id INTEGER NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    used_at TIMESTAMP,
    expires TIMESTAMP,
    PRIMARY KEY (invite_id, server_id),
    FOREIGN KEY (invite_id) REFERENCES invitation(id) ON DELETE CASCADE,
    FOREIGN KEY (server_id) REFERENCES media_server(id) ON DELETE CASCADE
);

-- Invitation-Library association table (many-to-many)
CREATE TABLE IF NOT EXISTS invite_library (
    invite_id INTEGER NOT NULL,
    library_id INTEGER NOT NULL,
    PRIMARY KEY (invite_id, library_id),
    FOREIGN KEY (invite_id) REFERENCES invitation(id) ON DELETE CASCADE,
    FOREIGN KEY (library_id) REFERENCES library(id) ON DELETE CASCADE
);

-- Invitation-User association table (many-to-many)
CREATE TABLE IF NOT EXISTS invitation_user (
    invite_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    used_at TIMESTAMP NOT NULL,
    server_id INTEGER,
    PRIMARY KEY (invite_id, user_id),
    FOREIGN KEY (invite_id) REFERENCES invitation(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE,
    FOREIGN KEY (server_id) REFERENCES media_server(id) ON DELETE SET NULL
);

-- =========================================================================
-- Wizard/Setup Tables
-- =========================================================================

-- Wizard bundle table - Groups of setup steps
CREATE TABLE IF NOT EXISTS wizard_bundle (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    description VARCHAR
);

-- Wizard step table - Individual setup steps
CREATE TABLE IF NOT EXISTS wizard_step (
    id SERIAL PRIMARY KEY,
    server_type VARCHAR NOT NULL,
    category VARCHAR NOT NULL DEFAULT 'post_invite',
    position INTEGER NOT NULL,
    title VARCHAR,
    markdown TEXT NOT NULL,
    requires JSON,
    require_interaction BOOLEAN,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE (server_type, category, position)
);

-- Wizard bundle-step association table (many-to-many with ordering)
CREATE TABLE IF NOT EXISTS wizard_bundle_step (
    id SERIAL PRIMARY KEY,
    bundle_id INTEGER NOT NULL,
    step_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    FOREIGN KEY (bundle_id) REFERENCES wizard_bundle(id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES wizard_step(id) ON DELETE CASCADE,
    UNIQUE (bundle_id, position)
);

-- =========================================================================
-- Connection/Integration Tables
-- =========================================================================

-- Ombi/Overseerr connection table
CREATE TABLE IF NOT EXISTS ombi_connection (
    id SERIAL PRIMARY KEY,
    connection_type VARCHAR NOT NULL DEFAULT 'ombi',
    name VARCHAR NOT NULL,
    url VARCHAR,
    api_key VARCHAR,
    media_server_id INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (media_server_id) REFERENCES media_server(id) ON DELETE CASCADE
);

-- =========================================================================
-- Activity Monitoring Tables (Plus Feature)
-- =========================================================================

-- Activity session table - Tracks media playback sessions
CREATE TABLE IF NOT EXISTS activity_session (
    id SERIAL PRIMARY KEY,
    server_id INTEGER NOT NULL,
    session_id VARCHAR NOT NULL,
    user_name VARCHAR NOT NULL,
    user_id VARCHAR,
    media_title VARCHAR NOT NULL,
    media_type VARCHAR,
    media_id VARCHAR,
    series_name VARCHAR,
    season_number INTEGER,
    episode_number INTEGER,
    started_at TIMESTAMP NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    duration_ms BIGINT,
    final_position_ms BIGINT,
    progress_percent REAL,
    device_name VARCHAR,
    client_name VARCHAR,
    ip_address VARCHAR,
    platform VARCHAR,
    player_version VARCHAR,
    transcoding_info TEXT,
    session_metadata TEXT,
    artwork_url VARCHAR,
    thumbnail_url VARCHAR,
    reference_id INTEGER,
    wizarr_user_id INTEGER,
    wizarr_identity_id INTEGER,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (server_id) REFERENCES media_server(id) ON DELETE CASCADE,
    FOREIGN KEY (wizarr_user_id) REFERENCES "user"(id) ON DELETE CASCADE,
    FOREIGN KEY (wizarr_identity_id) REFERENCES identity(id) ON DELETE SET NULL
);

-- Activity snapshot table - Point-in-time details of playback sessions
CREATE TABLE IF NOT EXISTS activity_snapshot (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    position_ms BIGINT,
    state VARCHAR NOT NULL,
    transcoding_details TEXT,
    bandwidth_kbps INTEGER,
    quality VARCHAR,
    subtitle_stream VARCHAR,
    audio_stream VARCHAR,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (session_id) REFERENCES activity_session(id) ON DELETE CASCADE
);

-- Historical import job table - Background jobs for importing past data
CREATE TABLE IF NOT EXISTS historical_import_job (
    id SERIAL PRIMARY KEY,
    server_id INTEGER NOT NULL,
    days_back INTEGER NOT NULL,
    max_results INTEGER,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    total_fetched INTEGER NOT NULL DEFAULT 0,
    total_processed INTEGER NOT NULL DEFAULT 0,
    total_stored INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (server_id) REFERENCES media_server(id) ON DELETE CASCADE
);

-- =========================================================================
-- Audit Logging Tables (Plus Feature)
-- =========================================================================

-- Audit log table - Tracks admin actions and system events
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR NOT NULL,
    resource_type VARCHAR NOT NULL,
    resource_id VARCHAR,
    admin_id INTEGER,
    admin_username VARCHAR NOT NULL,
    ip_address VARCHAR,
    user_agent VARCHAR,
    endpoint VARCHAR,
    method VARCHAR,
    description TEXT NOT NULL,
    details_json TEXT,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    timestamp TIMESTAMP NOT NULL,
    duration_ms INTEGER,
    FOREIGN KEY (admin_id) REFERENCES admin_account(id) ON DELETE SET NULL
);

-- =========================================================================
-- Indexes for Performance
-- =========================================================================

-- Activity session indexes
CREATE INDEX IF NOT EXISTS ix_activity_session_server_id ON activity_session(server_id);
CREATE INDEX IF NOT EXISTS ix_activity_session_user_name ON activity_session(user_name);
CREATE INDEX IF NOT EXISTS ix_activity_session_started_at ON activity_session(started_at);
CREATE INDEX IF NOT EXISTS ix_activity_session_active ON activity_session(active);
CREATE INDEX IF NOT EXISTS ix_activity_session_media_type ON activity_session(media_type);
CREATE INDEX IF NOT EXISTS ix_activity_session_session_id ON activity_session(session_id);
CREATE INDEX IF NOT EXISTS ix_activity_session_reference_id ON activity_session(reference_id);
CREATE INDEX IF NOT EXISTS ix_activity_session_wizarr_user_id ON activity_session(wizarr_user_id);
CREATE INDEX IF NOT EXISTS ix_activity_session_wizarr_identity_id ON activity_session(wizarr_identity_id);
CREATE INDEX IF NOT EXISTS ix_activity_session_server_started ON activity_session(server_id, started_at);
CREATE INDEX IF NOT EXISTS ix_activity_session_user_started ON activity_session(user_name, started_at);

-- Activity snapshot indexes
CREATE INDEX IF NOT EXISTS ix_activity_snapshot_session_id ON activity_snapshot(session_id);
CREATE INDEX IF NOT EXISTS ix_activity_snapshot_timestamp ON activity_snapshot(timestamp);
CREATE INDEX IF NOT EXISTS ix_activity_snapshot_state ON activity_snapshot(state);
CREATE INDEX IF NOT EXISTS ix_activity_snapshot_session_timestamp ON activity_snapshot(session_id, timestamp);

-- Historical import job indexes
CREATE INDEX IF NOT EXISTS ix_historical_import_job_server_id ON historical_import_job(server_id);
CREATE INDEX IF NOT EXISTS ix_historical_import_job_status ON historical_import_job(status);
CREATE INDEX IF NOT EXISTS ix_historical_import_job_server_status ON historical_import_job(server_id, status);

-- =========================================================================
-- Forward References Fix
-- =========================================================================

-- Add missing foreign key for invitation.wizard_bundle_id
-- (This FK was added later in migration 5805136a1d16)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_invitation_wizard_bundle'
    ) THEN
        ALTER TABLE invitation
        ADD CONSTRAINT fk_invitation_wizard_bundle
        FOREIGN KEY (wizard_bundle_id)
        REFERENCES wizard_bundle(id)
        ON DELETE SET NULL;
    END IF;
END $$;

-- =========================================================================
-- Comments for Documentation
-- =========================================================================

COMMENT ON TABLE settings IS 'System-wide configuration key-value pairs';
COMMENT ON TABLE notification IS 'Notification provider configurations (Discord, webhook, etc.)';
COMMENT ON TABLE identity IS 'User identities that can span multiple media servers';
COMMENT ON TABLE admin_account IS 'Administrator accounts for Wizarr management';
COMMENT ON TABLE webauthn_credential IS 'WebAuthn/passkey credentials for passwordless admin login';
COMMENT ON TABLE api_key IS 'API keys for programmatic access to Wizarr';
COMMENT ON TABLE media_server IS 'Media server configurations (Plex, Jellyfin, Emby)';
COMMENT ON TABLE library IS 'Media libraries from connected servers';
COMMENT ON TABLE "user" IS 'Media server users created through invitations';
COMMENT ON TABLE password_reset_token IS 'Temporary tokens for user password resets';
COMMENT ON TABLE expired_user IS 'Archive of users who were automatically deleted after expiry';
COMMENT ON TABLE invitation IS 'Invitation codes for onboarding new users';
COMMENT ON TABLE invitation_server IS 'Associates invitations with specific media servers';
COMMENT ON TABLE invite_library IS 'Associates invitations with specific libraries';
COMMENT ON TABLE invitation_user IS 'Tracks which users were created from which invitations';
COMMENT ON TABLE wizard_bundle IS 'Collections of wizard steps for user onboarding';
COMMENT ON TABLE wizard_step IS 'Individual onboarding steps shown to new users';
COMMENT ON TABLE wizard_bundle_step IS 'Orders wizard steps within bundles';
COMMENT ON TABLE ombi_connection IS 'Connections to Ombi/Overseerr for content requests';
COMMENT ON TABLE activity_session IS 'Real-time tracking of media playback sessions';
COMMENT ON TABLE activity_snapshot IS 'Point-in-time snapshots of playback state';
COMMENT ON TABLE historical_import_job IS 'Background jobs for importing historical playback data';
COMMENT ON TABLE audit_log IS 'Audit trail of admin actions and system events';

-- =========================================================================
-- Schema Version Tracking
-- =========================================================================

-- Create a table to track the current migration version
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

-- Set the current migration version
INSERT INTO alembic_version (version_num)
VALUES ('eecad7c18ac3')
ON CONFLICT (version_num) DO NOTHING;

-- =========================================================================
-- End of Schema
-- =========================================================================
