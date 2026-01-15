-- =========================================================================
-- Migration: Add Subscription Tier Management (2026-01)
-- =========================================================================
-- This migration adds support for subscription tiers with entitlements

SET search_path TO public;

-- Create subscription_tier table
CREATE TABLE IF NOT EXISTS subscription_tier (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    tier_level INTEGER NOT NULL UNIQUE,
    stripe_product_id VARCHAR(255),
    parent_tier_id INTEGER REFERENCES subscription_tier(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create tier_entitlement table
CREATE TABLE IF NOT EXISTS tier_entitlement (
    id SERIAL PRIMARY KEY,
    tier_id INTEGER NOT NULL REFERENCES subscription_tier(id) ON DELETE CASCADE,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(255) NOT NULL,
    is_tier_exclusive BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tier_id, resource_type, resource_id)
);

-- Create user_subscription table
CREATE TABLE IF NOT EXISTS user_subscription (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    tier_id INTEGER NOT NULL REFERENCES subscription_tier(id) ON DELETE RESTRICT,
    stripe_subscription_id VARCHAR(255),
    active_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active_until TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_subscription_tier_level ON subscription_tier(tier_level);
CREATE INDEX idx_subscription_tier_parent ON subscription_tier(parent_tier_id);
CREATE INDEX idx_tier_entitlement_tier ON tier_entitlement(tier_id);
CREATE INDEX idx_tier_entitlement_resource ON tier_entitlement(resource_type, resource_id);
CREATE INDEX idx_user_subscription_user ON user_subscription(user_id);
CREATE INDEX idx_user_subscription_tier ON user_subscription(tier_id);
CREATE INDEX idx_user_subscription_status ON user_subscription(status);
CREATE INDEX idx_user_subscription_active ON user_subscription(active_from, active_until);
