-- Phase 8: Additive persistent document relevance columns to project_ai_summaries.
-- Apply only to the intended database after explicit operator authorization.
BEGIN;

ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS document_relevance VARCHAR(40);
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS detected_document_topic TEXT;
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS assigned_project_topic TEXT;
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS relevance_explanation TEXT;
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS supporting_evidence JSONB;
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS relevant_findings JSONB;
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS missing_evidence JSONB;
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS progress_assessment TEXT;
ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION;

COMMIT;
