# ProjectScope — AI-Based Student Project Monitoring and Review Automation

ProjectScope is an enterprise-grade full-stack platform designed to automate student project monitoring, deliverable reviews, structural document validation, GitHub collaboration tracking, and evidence-grounded AI synthesis for academic institutions.

---

## System Architecture

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x, PostgreSQL (production) / SQLite (in-memory test isolation), Argon2id password hashing, JWT bearer tokens, OTP email verification.
- **Frontend:** React 19, Vite, Vanilla CSS design system with responsive glassmorphism aesthetic, accessible semantic layout, and role-based views.
- **AI & Analytics Services:**
  - **Rule-based Document Completeness:** Heading detection, structural section checks, and rationale feedback for academic reports and SRS documents.
  - **GitHub Collaboration Insights:** Git commit frequency inspection, contributor statistics, and student identity matching (`verified`, `probable`, `unmatched`).
  - **LLM Project Synthesis:** Provider-agnostic abstraction supporting Groq (Llama 3.3) and Google Gemini with evidence grounding, risk flags, faculty review questions, and advisory disclaimers.

---

## Prerequisites (Windows)

- **Python:** 3.12+ (64-bit)
- **Node.js:** 18+ (Node 20+ LTS recommended)
- **PostgreSQL:** 14+ (Installed locally or accessible via network)
- **Git:** 2.30+
- **PowerShell:** 5.1+ or PowerShell 7+

---

## Quickstart & Local Setup on Windows

Open **PowerShell** in the repository root directory (`AI-Project-Monitoring-cleaned-worktree`):

### 1. Backend Setup

```powershell
# Navigate into backend directory
cd backend

# Create Python virtual environment
python -m venv .venv

# If script execution is restricted on Windows, bypass policy for current process:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install application dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Configure environment variables
Copy-Item .env.example .env
```

Open `backend\.env` in an editor and set your local credentials:
- `DATABASE_URL`: Connection string to your PostgreSQL development database.
- `STUDENT_EMAIL_DOMAINS`: Comma-separated list of approved student email domains (e.g., `vitstudent.ac.in,university.edu`).
- `FACULTY_EMAIL_ALLOWLIST`: Comma-separated list of approved faculty email addresses (e.g., `faculty@university.edu`).
- `JWT_SECRET_KEY` & `OTP_HMAC_SECRET`: At least 32-byte secret strings.
- `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`: Gmail account and 16-character Google App Password.
- `LLM_PROVIDER`: `groq` or `gemini`.
- `GROQ_API_KEY` or `GEMINI_API_KEY`: API key for your chosen provider.
- `GITHUB_TOKEN`: (Optional) GitHub Personal Access Token to avoid unauthenticated API rate limits.

Verify your database connection:
```powershell
python -m app.db.test_connection
```

---

### 2. Database Migrations

The database schema is organized into base tables (managed by SQLAlchemy metadata) and migration-managed tables (managed via SQL scripts).

#### Step 2A: Initialize Core Base Tables
```powershell
python -m app.db.init_db
```
This initializes core entity tables (`students`, `projects`, `milestones`, `submissions`, `project_members`, `document_analysis`).

#### Step 2B: Apply SQL Migrations to PostgreSQL
Run each migration file sequentially using `psql` (or run within pgAdmin / database client):
```powershell
# 1. Authentication foundation & rate-limiting tables
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\migrations\0001_auth_foundation.sql

# 2. Faculty submission reviews & rubric scoring
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\migrations\0002_submission_reviews.sql

# 3. GitHub analysis snapshots & AI synthesis records
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\migrations\0003_github_and_ai_summaries.sql
```

> **Note on Migration Safety:** Never execute migrations against an unverified production database. Always verify backups first as outlined in `backend/migrations/README.md`.

---

### 3. Faculty Onboarding Workflow

Faculty registration requires a two-step administrative verification flow:
1. Faculty registers through the web interface or `/auth/register/faculty`.
2. Administrator verifies and approves the faculty account via the CLI tool:

```powershell
# List pending faculty accounts awaiting approval
python -m app.provision_faculty list_pending_faculty

# Approve a registered faculty account
python -m app.provision_faculty approve_faculty --email "faculty@university.edu"

# Assign faculty supervisor to a specific project
python -m app.provision_faculty assign_faculty --email "faculty@university.edu" --project-id 1
```

---

### 4. Running Backend Server

From the `backend` directory with virtual environment activated:
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- API Base URL: `http://127.0.0.1:8000`
- Interactive Swagger UI: `http://127.0.0.1:8000/docs`
- Health Endpoint: `http://127.0.0.1:8000/health`

---

### 5. Frontend Setup

Open a separate **PowerShell** window in the repository root:

```powershell
# Navigate into frontend directory
cd frontend

# Install npm dependencies
npm install

# Start Vite development server
npm run dev
```

- The React application will be available at `http://localhost:5173`.
- API requests are routed to the FastAPI backend at `http://127.0.0.1:8000`.

---

## Running Automated Tests

### Backend Test Suite (Pytest)

From the repository root:

#### Mode A: Fast In-Memory SQLite Isolation (64 tests passed, 2 skipped)
```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -v
```

#### Mode B: Full Suite with PostgreSQL Integration Tests (All 66 tests passed)
To run the full suite including live PostgreSQL schema isolation and concurrency tests:
1. Ensure an isolated test database exists (the database name **must** contain `test`):
   ```powershell
   # Example in psql:
   # CREATE DATABASE ai_project_monitoring_test;
   ```
2. Set `AUTH_TEST_POSTGRES_URL` and run pytest:
   ```powershell
   $env:AUTH_TEST_POSTGRES_URL="postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/ai_project_monitoring_test"
   .\backend\.venv\Scripts\python.exe -m pytest backend/tests -v
   ```

### Frontend Test Suite (Vitest)

From the `frontend` directory:
```powershell
npm test -- --run
```
Expected output: 2 test files passed, 5 tests passed.

### Frontend Production Build

From the `frontend` directory:
```powershell
npm run build
```
Builds the optimized production bundle in `frontend/dist/`.

---

## Safe Development-Data Cleanup Tool

`backend/app/cleanup_dev_data.py` provides a non-destructive audit tool for inspecting test data:

```powershell
# Run safe dry-run audit (default)
python -m app.cleanup_dev_data

# The tool enforces:
# - APP_ENV cannot be production
# - Target database name must contain 'test' or 'dev'
# - Displays foreign-key dependency trees and record counts
```

---

## External Integrations & Credentials Guide

| Service | Test Mode | Real Service Requirements | Safe Fallback Behavior |
| :--- | :--- | :--- | :--- |
| **Email / OTP** | Mocked via `FakeSMTP` in tests | Valid Gmail App Password in `SMTP_PASSWORD` with `SMTP_HOST=smtp.gmail.com:587` | Raises `EmailServiceError` on invalid credentials without exposing password |
| **GitHub REST API** | Mocked via JSON fixtures in unit tests | Public repositories work without credentials; private or heavy traffic requires `GITHUB_TOKEN` | Verified against live `https://github.com/octocat/Hello-World`; handles rate limits gracefully |
| **LLM Synthesis (Groq / Gemini)** | Mocked via `MockLLMProvider` in tests | `GROQ_API_KEY` for Llama 3.3 or `GEMINI_API_KEY` for Gemini 1.5 Flash | Returns HTTP 503 with clear configuration instructions when unconfigured |

---

## Security & Academic Integrity Safeguards

1. **Role-Based Principal Derivation:** Reviewer identity (`faculty_account_id`) is strictly bound to the verified JWT principal on the server. Client input cannot spoof or alter reviewer identities.
2. **Confidentiality of Paths:** Deliverable uploads and downloads never expose internal server disk paths. Files are stored under random UUIDs with MIME/magic-byte validation.
3. **Advisory Academic Notice:** All automated document completeness scores, Git commit activity indicators, and LLM synthesis reports are explicitly stamped with mandatory **advisory decision-support disclaimers** and must never be used as automated final student marks.
