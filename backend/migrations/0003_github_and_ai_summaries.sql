-- Phase 6 & Phase 7: Additive persistent GitHub analysis snapshots and AI project summaries.
-- Apply only to the intended database after explicit operator authorization.
BEGIN;

CREATE TABLE github_analysis_snapshots (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    repo_url VARCHAR(500) NOT NULL,
    total_commits INTEGER NOT NULL DEFAULT 0,
    contributor_stats JSONB,
    recent_activity JSONB,
    limitations_disclaimer TEXT,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_github_analysis_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX ix_github_analysis_project
    ON github_analysis_snapshots (project_id);
CREATE INDEX ix_github_analysis_analyzed_at
    ON github_analysis_snapshots (analyzed_at);

CREATE TABLE project_ai_summaries (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    provider VARCHAR(50) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    summary_text TEXT NOT NULL,
    key_points JSONB,
    risks JSONB,
    recommended_next_steps JSONB,
    review_questions JSONB,
    evidence_sources JSONB,
    advisory_disclaimer TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_project_ai_summaries_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX ix_project_ai_summaries_project
    ON project_ai_summaries (project_id);
CREATE INDEX ix_project_ai_summaries_created_at
    ON project_ai_summaries (created_at);

COMMIT;
