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
-- 2. COURSES, PROJECTS & PROJECT MEMBERS
-- =============================================================
CREATE TABLE IF NOT EXISTS courses (
    course_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) NOT NULL,
    name VARCHAR(150) NOT NULL,
    section VARCHAR(20) NOT NULL,
    year INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    term VARCHAR(20) NOT NULL,
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Migrate databases created before course offerings had section/term metadata.
ALTER TABLE courses ADD COLUMN IF NOT EXISTS section VARCHAR(20) NOT NULL DEFAULT '001';
ALTER TABLE courses ADD COLUMN IF NOT EXISTS year INTEGER NOT NULL DEFAULT 2000;
ALTER TABLE courses ADD COLUMN IF NOT EXISTS term VARCHAR(20) NOT NULL DEFAULT 'unknown';
ALTER TABLE courses ADD COLUMN IF NOT EXISTS created_by UUID;
UPDATE courses SET created_by = (SELECT user_id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1)
WHERE created_by IS NULL;
ALTER TABLE courses ALTER COLUMN created_by SET NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'courses_created_by_fkey') THEN
        ALTER TABLE courses ADD CONSTRAINT courses_created_by_fkey FOREIGN KEY (created_by) REFERENCES users(user_id);
    END IF;
END $$;
ALTER TABLE courses DROP CONSTRAINT IF EXISTS courses_code_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_courses_offering ON courses(code, section, year, term);

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