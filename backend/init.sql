-- =============================================================
-- SprintSight — Initial Schema
-- Runs automatically on first `docker compose up`
-- Safe to re-run: all statements use IF NOT EXISTS / ON CONFLICT
-- =============================================================

-- =============================================================
-- EXTENSIONS
-- =============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector for LLM embeddings

-- =============================================================
-- 1. USERS & AUTHENTICATION
-- =============================================================
CREATE TABLE IF NOT EXISTS users (
    user_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name     VARCHAR(100) NOT NULL,
    -- Using CHECK instead of ENUM: easier to add roles later without migrations
    role          VARCHAR(20)  NOT NULL CHECK (role IN ('instructor', 'student', 'admin')),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login    TIMESTAMP
);

-- Fast lookups by email on every login request
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- =============================================================
-- REFRESH TOKENS
-- Stores hashed JWT refresh tokens so sessions can be revoked
-- =============================================================
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_id   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    issued_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP   NOT NULL,
    revoked    BOOLEAN     NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id   ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);

-- =============================================================
-- SEED DATA
-- Default accounts for local development
-- Password for all accounts: changeme123
-- Hash generated with: bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12))
-- =============================================================
INSERT INTO users (email, password_hash, full_name, role) VALUES
    ('admin@sprintsight.dev',
     '$2b$12$eImiTXuWVxfM37uY4JANjQ==',
     'System Admin',
     'admin'),
    ('instructor@sprintsight.dev',
     '$2b$12$eImiTXuWVxfM37uY4JANjQ==',
     'Dr. Sample Instructor',
     'instructor'),
    ('student@sprintsight.dev',
     '$2b$12$eImiTXuWVxfM37uY4JANjQ==',
     'Sample Student',
     'student')
ON CONFLICT (email) DO NOTHING;    -- safe to re-run, won't duplicate rows