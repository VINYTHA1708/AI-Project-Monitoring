# Database migrations

Authentication tables, including the shared rate-limit buckets, are managed by
`0001_auth_foundation.sql`. It adds tables, constraints, and indexes only; it
does not update, delete, or recreate existing student, project, or submission
records.

`app.db.init_db` deliberately excludes all migration-managed tables. Do not use
`init_db.py` as a substitute for this migration.

Authentication rate limits use PostgreSQL-backed buckets shared by application
workers. They key IP limits from the ASGI client's peer address and deliberately
do not trust arbitrary `X-Forwarded-For` headers. Deployments behind a reverse
proxy must configure trusted-proxy handling at the server boundary so
`request.client.host` is the actual client address; do not enable untrusted
forwarded headers.

## Required preflight before a separately authorized migration

1. Confirm the target database and PostgreSQL version with the operator. Do not
   infer the target from a local `.env`.
2. Create a fresh full backup and verify that it can be restored into a
   separate, isolated database. Do not consider a dump successful until that
   restore check is complete. Example commands, to be run only after explicit
   authorization:

   ```powershell
   pg_dump --format=custom --file .\backup-before-auth.dump $env:DATABASE_URL
   pg_restore --list .\backup-before-auth.dump
   ```

   The second command lists archive contents; it is not a substitute for the
   required isolated restore test.
3. Verify that the existing `students` and `projects` tables have the
   PostgreSQL integer primary keys referenced by this migration, and that none
   of the migration's tables, indexes, or named constraints already exist.
   Record baseline counts for existing tables if operational policy requires
   before/after comparison.
4. Apply the migration once from `backend/`, and only after the preflight and
   separate approval:

   ```powershell
   psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\migrations\0001_auth_foundation.sql
   ```

   The script uses one transaction. A statement failure should roll back the
   schema changes. The command has not been run as part of this work.
5. Verify the expected tables, foreign keys, checks, indexes, and defaults in
   `information_schema`/`pg_catalog`; compare the recorded existing-table
   counts. In particular, confirm the case-insensitive email/faculty-ID indexes,
   the digest and delivery-state checks, the one-unconsumed-OTP partial unique
   index, and the rate-limit expiry index. Verify the application can read the
   new schema before enabling authentication traffic.

   Example read-only checks, not run as part of this work:

   ```powershell
   psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -c "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema() AND table_name IN ('auth_accounts', 'auth_otp_challenges', 'auth_rate_limit_buckets', 'faculty_project_assignments') ORDER BY table_name"
   psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -c "SELECT conrelid::regclass AS table_name, conname FROM pg_constraint WHERE conrelid IN ('auth_accounts'::regclass, 'auth_otp_challenges'::regclass, 'auth_rate_limit_buckets'::regclass, 'faculty_project_assignments'::regclass) ORDER BY table_name, conname"
   psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -c "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() AND tablename IN ('auth_accounts', 'auth_otp_challenges', 'auth_rate_limit_buckets', 'faculty_project_assignments') ORDER BY tablename, indexname"
   ```

## Additive Phase Migrations

### `0002_submission_reviews.sql`
Adds the `submission_reviews` table for faculty rubric scoring and feedback, with foreign keys to `projects`, `submissions`, and `auth_accounts`.

### `0003_github_and_ai_summaries.sql`
Adds `github_analysis_snapshots` and `project_ai_summaries` tables for persistent GitHub commit snapshots and LLM advisory summaries.

### `0004_ai_summary_relevance.sql`
Adds semantic document relevance columns to `project_ai_summaries` via `ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS`:
- `document_relevance` (VARCHAR)
- `detected_document_topic` (TEXT)
- `assigned_project_topic` (TEXT)
- `relevance_explanation` (TEXT)
- `supporting_evidence` (JSONB)
- `relevant_findings` (JSONB)
- `missing_evidence` (JSONB)
- `progress_assessment` (TEXT)
- `confidence` (DOUBLE PRECISION)

### `0005_document_relevance_analyses.sql`
Adds the `document_relevance_analyses` table and multi-deliverable verification summary columns:
- Adds table `document_relevance_analyses` with foreign keys to `projects` and `submissions`, unique constraint `uq_document_relevance_submission_file_type`, and indices on `project_id` and `submission_id`.
- Adds columns to `project_ai_summaries` via `ALTER TABLE project_ai_summaries ADD COLUMN IF NOT EXISTS`:
  - `document_results` (JSONB)
  - `submission_verification_status` (VARCHAR(50))
  - `relevant_documents_count` (INTEGER DEFAULT 0 NOT NULL)
  - `partially_relevant_documents_count` (INTEGER DEFAULT 0 NOT NULL)
  - `unrelated_documents_count` (INTEGER DEFAULT 0 NOT NULL)
  - `insufficient_content_documents_count` (INTEGER DEFAULT 0 NOT NULL)

Apply with psql:
```powershell
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\migrations\0005_document_relevance_analyses.sql
```

### `0006_submission_original_filenames.sql`
Adds columns to preserve user-uploaded original filenames for submissions:
- `report_original_name` (VARCHAR(500))
- `presentation_original_name` (VARCHAR(500))
- `srs_original_name` (VARCHAR(500))

Apply with psql:
```powershell
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\migrations\0006_submission_original_filenames.sql
```

### `cleanup_dummy_submissions.sql`
Idempotent, transactional cleanup script that removes legacy dummy submission records (e.g., submissions 1 and 2 for Project 1) and test student accounts without touching genuine student submissions, reviews, or project milestones. Validates integrity constraints before and after execution.

## Recovery

If the migration fails, stop and verify that PostgreSQL rolled back the
transaction; do not retry blindly. If it completes but post-migration checks
fail, stop application writes and preserve logs. Do not rerun the migration or
drop its tables as an automatic recovery. Restore the verified backup into a
separate recovery database first, assess the target and data impact, then use a
reviewed forward migration or a separately approved restoration of the target.
Any target restore, cleanup, or data change requires its own explicit
authorization.

