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

-- This must exist in courses table
ALTER TABLE courses 
    ADD CONSTRAINT uq_courses_id_offering UNIQUE (course_id, code, term, year);

-- course_students FK references that exact constraint
CREATE TABLE IF NOT EXISTS course_students (
    course_id   UUID NOT NULL,
    user_id     UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    code        VARCHAR(20) NOT NULL,
    term        VARCHAR(20) NOT NULL,
    year        INTEGER     NOT NULL,
    enrolled_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (course_id, user_id),
    FOREIGN KEY (course_id, code, term, year)
        REFERENCES courses(course_id, code, term, year) ON DELETE CASCADE
);

-- UNIQUE CONSTRAINT: Prevents a student from enrolling in multiple sections of the same course offering
CREATE UNIQUE INDEX IF NOT EXISTS uq_student_single_section_per_course
    ON course_students(user_id, code, term, year);

CREATE TABLE IF NOT EXISTS projects (
    project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_name VARCHAR(150) NOT NULL,
    team_name VARCHAR(255) NOT NULL,
    description TEXT,
    course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    github_repo_url VARCHAR(255),
    local_repo_path VARCHAR(255),
    jira_email VARCHAR(255) NOT NULL,
    jira_domain VARCHAR(255),
    jira_project_key VARCHAR(50),
    jira_api_token_encrypted TEXT,
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(btrim(team_name)) > 0)
);

-- Schema migration/backfill logic
ALTER TABLE projects ADD COLUMN IF NOT EXISTS github_repo_url VARCHAR(255);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS local_repo_path VARCHAR(255);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS team_name VARCHAR(255);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_email VARCHAR(255);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_domain VARCHAR(255);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_project_key VARCHAR(50);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_api_token_encrypted TEXT;

-- Indexing and uniqueness
CREATE INDEX IF NOT EXISTS idx_projects_course_id ON projects(course_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_course_team_name
    ON projects(course_id, lower(team_name));

-- Ensure (project_id, course_id) is uniquely identifiable in projects
ALTER TABLE projects 
    ADD CONSTRAINT uq_projects_id_course UNIQUE (project_id, course_id);

-- Update project_members table schema
CREATE TABLE IF NOT EXISTS project_members (
    project_id UUID NOT NULL,
    course_id  UUID NOT NULL,
    user_id    UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, user_id),
    -- Verifies project belongs to the expected course
    FOREIGN KEY (project_id, course_id) 
        REFERENCES projects(project_id, course_id) ON DELETE CASCADE
);

-- UNIQUE CONSTRAINT: Prevents a student from joining more than 1 project in the same course
CREATE UNIQUE INDEX IF NOT EXISTS uq_student_single_project_per_course
    ON project_members(user_id, course_id);

CREATE INDEX IF NOT EXISTS idx_course_instructors_user_id ON course_instructors(user_id);
CREATE INDEX IF NOT EXISTS idx_course_students_user_id ON course_students(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_course_id ON projects(course_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_github_repo_url ON projects(github_repo_url);
CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_jira_email ON projects(jira_email);
CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_jira_api_token ON projects(jira_api_token_encrypted);

CREATE TABLE IF NOT EXISTS project_documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    uploader_id UUID NOT NULL REFERENCES users(user_id),
    filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    byte_size BIGINT NOT NULL CHECK (byte_size > 0),
    checksum VARCHAR(64) NOT NULL,
    storage_bucket VARCHAR(255) NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_project_documents_project_id ON project_documents(project_id);

CREATE TABLE IF NOT EXISTS jira_ingestion_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    sprint_id VARCHAR(100) NOT NULL,
    jira_project_key VARCHAR(50) NOT NULL,
    jql TEXT NOT NULL,
    raw_bucket VARCHAR(255) NOT NULL,
    raw_object_key TEXT NOT NULL UNIQUE,
    issue_count INTEGER NOT NULL CHECK (issue_count >= 0),
    captured_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ,
    processing_status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (processing_status IN ('pending', 'completed', 'failed')),
    normalization_version VARCHAR(50),
    processing_error TEXT,
    cleaned_snapshot JSONB CHECK (cleaned_snapshot IS NULL OR jsonb_typeof(cleaned_snapshot) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_jira_runs_project_sprint_captured
    ON jira_ingestion_runs(project_id, sprint_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS manual_text (
    manual_text_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    sprint_id VARCHAR(100) NOT NULL,
    expectations_text TEXT NOT NULL CHECK (length(btrim(expectations_text)) BETWEEN 1 AND 5000),
    updated_by UUID NOT NULL REFERENCES users(user_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (course_id, project_id, sprint_id),
    FOREIGN KEY (project_id, course_id) REFERENCES projects(project_id, course_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assessment_override (
    override_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL,
    project_id UUID NOT NULL,
    sprint_id VARCHAR(100) NOT NULL,
    requirements_score NUMERIC(5, 2) NOT NULL CHECK (requirements_score BETWEEN 0 AND 100),
    code_quality_score NUMERIC(5, 2) NOT NULL CHECK (code_quality_score BETWEEN 0 AND 100),
    testing_score NUMERIC(5, 2) NOT NULL CHECK (testing_score BETWEEN 0 AND 100),
    documentation_score NUMERIC(5, 2) NOT NULL CHECK (documentation_score BETWEEN 0 AND 100),
    collaboration_score NUMERIC(5, 2) NOT NULL CHECK (collaboration_score BETWEEN 0 AND 100),
    total_score NUMERIC(5, 2) GENERATED ALWAYS AS (
        (requirements_score + code_quality_score + testing_score + documentation_score + collaboration_score) / 5.0
    ) STORED,
    graded_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (course_id, project_id, sprint_id),
    FOREIGN KEY (project_id, course_id)
        REFERENCES projects(project_id, course_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_assessment_override_project_sprint
    ON assessment_override(project_id, sprint_id);

CREATE TABLE IF NOT EXISTS assessment_reports (
    report_id UUID PRIMARY KEY,
    model_name VARCHAR(255) NOT NULL,
    mode VARCHAR(255) NOT NULL,
    course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    sprint_id VARCHAR(100) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rubric_weights JSONB NOT NULL,
    team_score JSONB NOT NULL,
    individual_scores JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    rubric_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    strengths JSONB NOT NULL DEFAULT '[]'::jsonb,
    weaknesses JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_assessment_reports_course_project_sprint
    ON assessment_reports(course_id, project_id, sprint_id, generated_at DESC);

-- Per-course rubric dimension weights, set by faculty; falls back to the
-- backend's hardcoded equal-weight default when a course has no row here.
CREATE TABLE IF NOT EXISTS rubric_weight_configs (
    course_id UUID PRIMARY KEY REFERENCES courses(course_id) ON DELETE CASCADE,
    weights JSONB NOT NULL,
    updated_by UUID NOT NULL REFERENCES users(user_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================
-- 3. LOCAL GIT INGESTION EVIDENCE
-- One run represents one project/sprint ingestion and is replaced
-- transactionally when the same project/sprint is ingested again.
-- =============================================================
CREATE TABLE IF NOT EXISTS ingestion_runs (
    ingestion_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    sprint_id VARCHAR(100) NOT NULL,
    local_repo_path VARCHAR(255) NOT NULL,
    head_sha VARCHAR(64),
    commit_frequency DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (commit_frequency >= 0),
    code_churn INTEGER NOT NULL DEFAULT 0 CHECK (code_churn >= 0),
    pr_turnaround_hours DOUBLE PRECISION,
    assigned_story_points INTEGER,
    completion_percent DOUBLE PRECISION,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, sprint_id)
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_project_sprint
    ON ingestion_runs(project_id, sprint_id);

CREATE TABLE IF NOT EXISTS ingestion_commits (
    ingestion_commit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_run_id UUID NOT NULL REFERENCES ingestion_runs(ingestion_run_id) ON DELETE CASCADE,
    sha VARCHAR(64) NOT NULL,
    author VARCHAR(255) NOT NULL,
    author_email VARCHAR(255),
    student_id UUID REFERENCES users(user_id),
    message TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    lines_added INTEGER NOT NULL DEFAULT 0 CHECK (lines_added >= 0),
    lines_deleted INTEGER NOT NULL DEFAULT 0 CHECK (lines_deleted >= 0),
    files_changed JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (ingestion_run_id, sha),
    CHECK (jsonb_typeof(files_changed) = 'array')
);

ALTER TABLE ingestion_commits
    ADD COLUMN IF NOT EXISTS author_email VARCHAR(255);

ALTER TABLE ingestion_commits
    ADD COLUMN IF NOT EXISTS student_id UUID REFERENCES users(user_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_commits_sha ON ingestion_commits(sha);
CREATE INDEX IF NOT EXISTS idx_ingestion_commits_run ON ingestion_commits(ingestion_run_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_commits_author_email ON ingestion_commits(author_email);
CREATE INDEX IF NOT EXISTS idx_ingestion_commits_student_id ON ingestion_commits(student_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_commits_run_timestamp_sha
    ON ingestion_commits(ingestion_run_id, timestamp, sha);