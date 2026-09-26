-- Runs once, on first start of an empty postgres_data volume.
-- Schema itself will be managed by migrations from the backend; only
-- extensions live here.
CREATE EXTENSION IF NOT EXISTS citext;    -- case-insensitive email for FR-01 accounts
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_bytes for tokens
