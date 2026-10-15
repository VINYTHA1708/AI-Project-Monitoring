-- Migration 0006: Add original file names for uploaded student submission deliverables
BEGIN;

ALTER TABLE submissions ADD COLUMN IF NOT EXISTS report_original_name VARCHAR(500);
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS presentation_original_name VARCHAR(500);
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS srs_original_name VARCHAR(500);

COMMIT;
