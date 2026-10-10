-- Additive authentication foundation. This migration does not alter existing rows.
-- Apply only to the intended database after explicit operator authorization.
BEGIN;

CREATE TABLE auth_accounts (
    id SERIAL PRIMARY KEY,
    role VARCHAR(16) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    student_id INTEGER NULL,
    faculty_id VARCHAR(50) NULL,
    faculty_name VARCHAR(150) NULL,
    phone VARCHAR(32) NULL,
    department VARCHAR(150) NULL,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    faculty_approved BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_auth_accounts_role
        CHECK (role IN ('student', 'faculty')),
    CONSTRAINT ck_auth_accounts_email_normalized
        CHECK (email <> '' AND email = lower(trim(email))),
    CONSTRAINT ck_auth_accounts_argon2id_hash
        CHECK (password_hash LIKE '$argon2id$%'),
    CONSTRAINT ck_auth_accounts_login_attempts
        CHECK (failed_login_count >= 0),
    CONSTRAINT fk_auth_accounts_student
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE RESTRICT,
    CONSTRAINT uq_auth_accounts_student
        UNIQUE (student_id),
    CONSTRAINT ck_auth_accounts_role_profile CHECK (
        (
            role = 'student'
            AND student_id IS NOT NULL
            AND faculty_id IS NULL
            AND faculty_name IS NULL
            AND phone IS NOT NULL AND btrim(phone) <> ''
            AND department IS NOT NULL AND btrim(department) <> ''
            AND faculty_approved = FALSE
        )
        OR
        (
            role = 'faculty'
            AND student_id IS NULL
            AND faculty_id IS NOT NULL AND btrim(faculty_id) <> ''
            AND faculty_name IS NOT NULL AND btrim(faculty_name) <> ''
        )
    ),
    CONSTRAINT ck_auth_accounts_approval_state
        CHECK (NOT faculty_approved OR (role = 'faculty' AND email_verified))
);

CREATE UNIQUE INDEX uq_auth_accounts_email_lower
    ON auth_accounts (lower(email));
CREATE UNIQUE INDEX uq_auth_accounts_faculty_id
    ON auth_accounts (lower(faculty_id))
    WHERE role = 'faculty';

CREATE TABLE auth_otp_challenges (
    id UUID PRIMARY KEY,
    account_id INTEGER NOT NULL,
    purpose VARCHAR(24) NOT NULL,
    code_digest VARCHAR(64) NOT NULL,
    delivery_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    delivered_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    consumed_at TIMESTAMPTZ NULL,
    CONSTRAINT fk_auth_otp_challenges_account
        FOREIGN KEY (account_id) REFERENCES auth_accounts(id) ON DELETE CASCADE,
    CONSTRAINT ck_auth_otp_challenges_purpose
        CHECK (purpose IN ('registration', 'login')),
    CONSTRAINT ck_auth_otp_challenges_digest
        CHECK (length(code_digest) = 64),
    CONSTRAINT ck_auth_otp_challenges_digest_hex
        CHECK (code_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_auth_otp_challenges_delivery_status
        CHECK (delivery_status IN ('pending', 'delivered', 'failed', 'superseded')),
    CONSTRAINT ck_auth_otp_challenges_delivered_at
        CHECK ((delivery_status = 'delivered') = (delivered_at IS NOT NULL)),
    CONSTRAINT ck_auth_otp_challenges_pending_unconsumed
        CHECK (delivery_status <> 'pending' OR consumed_at IS NULL),
    CONSTRAINT ck_auth_otp_challenges_terminal_consumed
        CHECK (delivery_status NOT IN ('failed', 'superseded')
               OR consumed_at IS NOT NULL),
    CONSTRAINT ck_auth_otp_challenges_attempts
        CHECK (attempt_count >= 0),
    CONSTRAINT ck_auth_otp_challenges_expiry
        CHECK (expires_at > created_at),
    CONSTRAINT ck_auth_otp_challenges_consumed_time
        CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE INDEX ix_auth_otp_account_purpose_created
    ON auth_otp_challenges (account_id, purpose, created_at DESC);
CREATE UNIQUE INDEX uq_auth_otp_one_unconsumed_challenge
    ON auth_otp_challenges (account_id, purpose)
    WHERE consumed_at IS NULL;

CREATE TABLE auth_rate_limit_buckets (
    action VARCHAR(24) NOT NULL,
    scope VARCHAR(8) NOT NULL,
    subject_digest VARCHAR(64) NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    hit_count INTEGER NOT NULL,
    CONSTRAINT pk_auth_rate_limit_buckets
        PRIMARY KEY (action, scope, subject_digest, window_started_at),
    CONSTRAINT ck_auth_rate_limit_action
        CHECK (action IN ('login', 'registration', 'verify', 'resend')),
    CONSTRAINT ck_auth_rate_limit_scope
        CHECK (scope IN ('email', 'ip')),
    CONSTRAINT ck_auth_rate_limit_digest
        CHECK (length(subject_digest) = 64),
    CONSTRAINT ck_auth_rate_limit_digest_hex
        CHECK (subject_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_auth_rate_limit_hits
        CHECK (hit_count > 0),
    CONSTRAINT ck_auth_rate_limit_expiry
        CHECK (expires_at > window_started_at)
);
CREATE INDEX ix_auth_rate_limit_expiry
    ON auth_rate_limit_buckets (expires_at);

CREATE TABLE faculty_project_assignments (
    faculty_account_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_faculty_project_assignments
        PRIMARY KEY (faculty_account_id, project_id),
    CONSTRAINT fk_faculty_project_assignments_faculty
        FOREIGN KEY (faculty_account_id) REFERENCES auth_accounts(id) ON DELETE CASCADE,
    CONSTRAINT fk_faculty_project_assignments_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX ix_faculty_project_assignments_project
    ON faculty_project_assignments (project_id);

COMMIT;
