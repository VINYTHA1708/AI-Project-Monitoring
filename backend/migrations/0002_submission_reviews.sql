-- Phase 4: Additive persistent faculty reviews and scoring.
-- Apply only to the intended database after explicit operator authorization.
BEGIN;

CREATE TABLE submission_reviews (
    id SERIAL PRIMARY KEY,
    submission_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    faculty_account_id INTEGER NOT NULL,
    score NUMERIC(5, 2) NOT NULL,
    feedback TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_submission_reviews_submission
        FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE,
    CONSTRAINT fk_submission_reviews_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT fk_submission_reviews_faculty
        FOREIGN KEY (faculty_account_id) REFERENCES auth_accounts(id) ON DELETE CASCADE,
    CONSTRAINT ck_submission_reviews_score_range
        CHECK (score >= 0.0 AND score <= 100.0),
    CONSTRAINT ck_submission_reviews_feedback_not_empty
        CHECK (trim(feedback) <> ''),
    CONSTRAINT uq_submission_reviews_submission_faculty
        UNIQUE (submission_id, faculty_account_id)
);

CREATE INDEX ix_submission_reviews_project
    ON submission_reviews (project_id);
CREATE INDEX ix_submission_reviews_submission
    ON submission_reviews (submission_id);
CREATE INDEX ix_submission_reviews_faculty
    ON submission_reviews (faculty_account_id);

COMMIT;
