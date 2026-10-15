-- Phase 9: Document-Level Deliverable Relevance Verification and Persistence
-- Adds document_relevance_analyses table and document_results columns to project_ai_summaries.
BEGIN;

-- 1. Add document-level result aggregation columns to project_ai_summaries
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS document_results JSONB;
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS submission_verification_status VARCHAR(50);
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS relevant_documents_count INTEGER DEFAULT 0 NOT NULL;
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS partially_relevant_documents_count INTEGER DEFAULT 0 NOT NULL;
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS unrelated_documents_count INTEGER DEFAULT 0 NOT NULL;
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS insufficient_content_documents_count INTEGER DEFAULT 0 NOT NULL;

-- 2. Create document_relevance_analyses table for per-file deliverable verification
CREATE TABLE IF NOT EXISTS document_relevance_analyses (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    document_identifier VARCHAR(100) NOT NULL,
    file_name VARCHAR(500) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    document_title VARCHAR(500) NOT NULL DEFAULT 'Not extractable',
    document_headings JSONB,
    detected_document_topic TEXT NOT NULL,
    assigned_project_title TEXT NOT NULL,
    title_match_explanation TEXT,
    content_match_explanation TEXT,
    document_relevance VARCHAR(40) NOT NULL,
    supporting_evidence JSONB,
    conflicting_evidence JSONB,
    missing_evidence JSONB,
    recommended_action TEXT,
    confidence DOUBLE PRECISION,
    content_hash VARCHAR(64),
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_document_relevance_submission_file_type UNIQUE (submission_id, file_type)
);

CREATE INDEX IF NOT EXISTS ix_doc_relevance_project ON document_relevance_analyses(project_id);
CREATE INDEX IF NOT EXISTS ix_doc_relevance_submission ON document_relevance_analyses(submission_id);

COMMIT;
