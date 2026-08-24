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
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    token_version INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login    TIMESTAMP
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;

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

-- Revoked access tokens remain invalid until their natural expiration.
CREATE TABLE IF NOT EXISTS revoked_access_tokens (
    token_id   UUID PRIMARY KEY,
    user_id    UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_revoked_access_tokens_expires_at
    ON revoked_access_tokens(expires_at);

-- =============================================================
-- SEED DATA
-- Default accounts for local development
-- Password for all accounts: changeme123
-- Hash generated with app.core.security.hash_password("changeme123")
-- =============================================================
INSERT INTO users (email, password_hash, full_name, role) VALUES
    ('admin@sprintsight.dev',
        'pbkdf2_sha256$200000$BEoJU9gfy7Rgq_MTo5W9jw==$B6ngQF8EXp93J20Dzydf6RqoTASrX8AHlV5zZ4A7jJw=',
     'System Admin',
     'admin'),
    ('instructor@sprintsight.dev',
        'pbkdf2_sha256$200000$BEoJU9gfy7Rgq_MTo5W9jw==$B6ngQF8EXp93J20Dzydf6RqoTASrX8AHlV5zZ4A7jJw=',
     'Dr. Sample Instructor',
     'instructor'),
    ('student@sprintsight.dev',
        'pbkdf2_sha256$200000$BEoJU9gfy7Rgq_MTo5W9jw==$B6ngQF8EXp93J20Dzydf6RqoTASrX8AHlV5zZ4A7jJw=',
     'Sample Student',
     'student')
ON CONFLICT (email) DO NOTHING;    -- safe to re-run, won't duplicate rows

-- =============================================================
-- 2. COURSES, PROJECTS & PROJECT MEMBERS
-- =============================================================
CREATE TABLE IF NOT EXISTS courses (
    course_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS course_instructors (
    course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    PRIMARY KEY (course_id, user_id)
);

CREATE TABLE IF NOT EXISTS projects (
    project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_name VARCHAR(150) NOT NULL,
    description TEXT,
    course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    github_repo_url VARCHAR(255),
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_members (
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_course_instructors_user_id ON course_instructors(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_course_id ON projects(course_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);