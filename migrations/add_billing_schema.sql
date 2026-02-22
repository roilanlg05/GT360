-- Migration: add_billing_schema
-- Creates the billing schema and subscriptions table.
-- Run this manually or let psqlmodel auto-create via ensure_tables=True.

CREATE SCHEMA IF NOT EXISTS billing;

CREATE TABLE IF NOT EXISTS billing.subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL UNIQUE REFERENCES entities.organizations(id) ON DELETE CASCADE,

    -- Stripe references (null until manager subscribes)
    stripe_customer_id      VARCHAR(255),
    stripe_subscription_id  VARCHAR(255),

    -- Plan: NULL during trial (Basic-level access), then 'Basic' | 'Pro' | 'Enterprise'
    plan_type   VARCHAR(50),

    -- Status: trialing | active | past_due | canceled | unpaid
    status      VARCHAR(50) NOT NULL DEFAULT 'trialing',

    -- Free trial window
    trial_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trial_end   TIMESTAMPTZ NOT NULL,

    -- Active billing period (populated after first payment)
    current_period_start TIMESTAMPTZ,
    current_period_end   TIMESTAMPTZ,

    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_organization_id   ON billing.subscriptions(organization_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer   ON billing.subscriptions(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_sub        ON billing.subscriptions(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status            ON billing.subscriptions(status);
