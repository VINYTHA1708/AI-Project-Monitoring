# ProjectScope — AI-Based Student Project Monitoring and Review Automation

ProjectScope is an enterprise-grade, full-stack platform designed to automate student project monitoring, deliverable submissions, faculty reviews, document validation, GitHub collaboration tracking, and evidence-grounded AI project analysis.

The platform provides a centralized environment for students and faculty to manage academic project activities, monitor progress, evaluate submissions, and generate AI-assisted insights while keeping final academic decisions under faculty control.

---

## 1. System Architecture

### Backend

- Python 3.12
- FastAPI
- SQLAlchemy 2.x
- PostgreSQL for persistent storage
- SQLite for isolated automated tests
- Argon2id password hashing
- JWT-based authentication
- OTP-based email verification

### Frontend

- React 19
- Vite
- Vanilla CSS design system
- Responsive glassmorphism interface
- Accessible semantic layouts
- Role-based student, faculty, and administrative views

### AI and Analytics Services

**1. Rule-Based Document Completeness Analysis**

- Heading detection and structural validation.
- Required-section identification.
- Document completeness assessment.
- Missing-section detection with rationale-based feedback.
- Independent analysis of supported deliverables.

**2. GitHub Collaboration Insights**

- GitHub repository inspection.
- Commit frequency analysis.
- Contributor statistics.
- Student identity matching with `verified`, `probable`, and `unmatched` classifications.
- Repository activity insights for faculty review.

**3. LLM-Based Project Synthesis**

- Provider-agnostic LLM integration.
- Supports Groq (Llama 3.3) and Google Gemini.
- Evidence-grounded project summaries.
- Identification of potential project risks.
- Faculty review questions.
- Advisory recommendations with explicit academic decision-support disclaimers.

---

## 2. Core Platform Features

### Student Module

- Student registration and authentication.
- OTP-based email verification.
- Project access and progress monitoring.
- Weekly deliverable submissions.
- Upload of project reports, presentations, and SRS documents.
- Submission history and status tracking.
- Faculty marks and feedback notifications.
- AI-generated project analysis and document feedback.

### Faculty Module

- Faculty registration with administrative approval.
- Project supervision and assignment.
- Access to assigned student projects.
- Review of student deliverables.
- Submission evaluation and rubric-based scoring.
- Marks and feedback management.
- Automated student notifications when marks or feedback are updated.
- Access to document analysis, GitHub insights, and AI-generated project summaries.

### Multi-Faculty Submission Notifications

ProjectScope supports automated email notifications to all eligible faculty members assigned to a project.

When a student submits a deliverable:

1. The backend identifies all faculty members assigned to the relevant project.
2. Only approved faculty accounts are considered.
3. Invalid and duplicate email addresses are excluded.
4. The submitting student's email address is excluded from the faculty recipient list.
5. A notification payload containing submission and project details is sent to the configured n8n webhook.
6. The n8n workflow processes the recipient list and sends individual email notifications to the eligible faculty members.

The implementation retains compatibility with the legacy single-faculty notification payload.

### Student Marks and Feedback Notifications

When faculty members create or update marks or feedback:

1. The backend identifies the relevant student.
2. A notification event is generated when marks or feedback change.
3. The configured marks-update webhook receives the notification.
4. The n8n workflow sends an email to the student.

The submission notification and marks-update notification workflows use separate webhook configurations.

### Workflow Automation

ProjectScope uses n8n for external email notification automation.

- Student submission alerts to assigned faculty.
- Marks and feedback update alerts to students.
- Separate webhook configurations for each notification type.
- Best-effort notification delivery without blocking the underlying database transaction.
- Webhook authentication using the configured shared secret.
- Notification event identifiers for event tracking.

WhatsApp notifications are not part of the current implementation.

---

## 3. Prerequisites (Windows)

- Python 3.12 or later (64-bit).
- Node.js 18 or later (Node.js 20+ LTS recommended).
- PostgreSQL 14 or later.
- Git 2.30 or later.
- PowerShell 5.1 or PowerShell 7+.
- n8n account for external email notification workflows.
- Groq or Gemini API credentials for LLM-based synthesis.

---

## 4. Quickstart and Local Setup on Windows

Open PowerShell in the repository root directory:

`AI-Project-Monitoring-cleaned-worktree`

### 4.1 Backend Setup

Navigate to the backend directory:

```powershell
cd backend
```

Create a Python virtual environment if one does not already exist:

```powershell
python -m venv .venv
```

If PowerShell restricts script execution:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Upgrade pip and install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Configure environment variables.

If `.env` does not exist:

```powershell
Copy-Item .env.example .env
```

Configure the following values in `backend/.env`:

| Variable                        | Purpose                                       |
| ------------------------------- | --------------------------------------------- |
| `DATABASE_URL`                  | PostgreSQL database connection                |
| `STUDENT_EMAIL_DOMAINS`         | Approved student email domains                |
| `FACULTY_EMAIL_ALLOWLIST`       | Approved faculty email addresses              |
| `JWT_SECRET_KEY`                | JWT signing secret                            |
| `OTP_HMAC_SECRET`               | OTP verification secret                       |
| `SMTP_USERNAME`                 | SMTP account username                         |
| `SMTP_PASSWORD`                 | SMTP password or Google App Password          |
| `SMTP_FROM_EMAIL`               | Sender email address                          |
| `LLM_PROVIDER`                  | `groq` or `gemini`                            |
| `GROQ_API_KEY`                  | Groq API key when using Groq                  |
| `GEMINI_API_KEY`                | Gemini API key when using Gemini              |
| `GITHUB_TOKEN`                  | Optional GitHub Personal Access Token         |
| `N8N_WEBHOOK_URL`               | Student submission notification webhook       |
| `N8N_MARKS_UPDATED_WEBHOOK_URL` | Student marks-update notification webhook     |
| `N8N_WEBHOOK_SECRET`            | Optional shared webhook authentication secret |

Use strong, randomly generated secrets for authentication-related variables. Never commit `.env` or expose API keys, passwords, or webhook secrets.

Verify the database connection:

```powershell
python -m app.db.test_connection
```

---

## 5. Database Initialization and Migrations

The database schema consists of SQLAlchemy-managed base tables and migration-managed additional tables.

### Step 5.1: Initialize Core Tables

From the backend directory:

```powershell
python -m app.db.init_db
```

This initializes the core entities, including:

- Students
- Projects
- Milestones
- Submissions
- Project members
- Document analysis

### Step 5.2: Apply SQL Migrations

Apply the migration files sequentially using PostgreSQL `psql` or a database management tool.

```powershell
# 1. Authentication foundation and rate-limiting tables
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\migrations\0001_auth_foundation.sql

# 2. Faculty submission reviews and rubric scoring
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\migrations\0002_submission_reviews.sql

# 3. GitHub analysis snapshots and AI synthesis records
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\migrations\0003_github_and_ai_summaries.sql

# 4. Document relevance detection and semantic evidence columns
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\migrations\0004_ai_summary_relevance.sql

# 5. Independent document relevance analyses and verification status
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f .\migrations\0005_document_relevance_analyses.sql
```

**Migration Safety:** Always verify the target database and available backups before executing migrations. Never execute development migrations against an unverified production database. Refer to `backend/migrations/README.md` for migration-specific instructions.

---

## 6. Faculty Onboarding and Project Assignment

Faculty registration follows an administrative approval workflow.

### Step 6.1: Faculty Registration

Faculty members register through the application or the registration endpoint:

`POST /auth/register/faculty`

### Step 6.2: Administrative Approval

List faculty accounts awaiting approval:

```powershell
python -m app.provision_faculty list_pending_faculty
```

Approve a faculty account:

```powershell
python -m app.provision_faculty approve_faculty --email "faculty@university.edu"
```

### Step 6.3: Assign Faculty to a Project

```powershell
python -m app.provision_faculty assign_faculty --email "faculty@university.edu" --project-id 1
```

Multiple approved faculty members can be assigned to the same project. All eligible assigned faculty members are considered for student submission notifications.

---

## 7. n8n Email Notification Configuration

ProjectScope uses two independent n8n workflows.

### Workflow 1: Student Submission Alert

**Trigger:** Student submits a project deliverable.

**Recipients:** All approved faculty members assigned to the project.

**Process:**

1. Receive the submission notification webhook.
2. Validate the required submission details.
3. Prepare and deduplicate faculty recipients.
4. Exclude the submitting student's email address.
5. Send an individual email to each eligible faculty member.
6. Return the workflow response.

### Workflow 2: Student Marks Update Email

**Trigger:** Faculty creates or updates student marks or feedback.

**Recipient:** Relevant student.

**Process:**

1. Receive the marks-update webhook.
2. Validate the notification payload.
3. Send the marks and feedback notification email.
4. Return the workflow response.

**Important:** Keep the two webhook URLs separate. Changes to the submission notification workflow should not affect the marks-update workflow.

---

## 8. Running the Backend Server

From the backend directory with the virtual environment activated:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend endpoints:

| Resource        | URL                          |
| --------------- | ---------------------------- |
| API Base URL    | http://127.0.0.1:8000        |
| Swagger UI      | http://127.0.0.1:8000/docs   |
| Health Endpoint | http://127.0.0.1:8000/health |

Keep this terminal running while using the application.

---

## 9. Frontend Setup and Execution

Open a separate PowerShell terminal in the repository root.

Navigate to the frontend:

```powershell
cd frontend
```

Install dependencies:

```powershell
npm install
```

Start the development server:

```powershell
npm run dev
```

The React application will generally be available at:

`http://localhost:5173`

Frontend API requests are configured to communicate with the FastAPI backend at:

`http://127.0.0.1:8000`

Keep both terminals running during development.

---

## 10. Running Automated Tests

ProjectScope includes backend automated tests and frontend tests.

### 10.1 Backend Tests

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -v
```

The latest reported full backend test run completed with:

- 188 passed
- 3 skipped
- 0 failed

The suite includes tests for authentication, project management, document analysis, reviews, notifications, and other backend functionality.

The multi-faculty submission notification tests cover:

- Multiple approved faculty recipients.
- Single-faculty compatibility.
- Duplicate recipient filtering.
- Project-level recipient isolation.
- Unapproved faculty exclusion.
- Student email exclusion.
- Missing or invalid faculty email addresses.
- No eligible faculty recipients.
- Webhook failures.
- Event identifiers and webhook authentication.
- n8n partial-failure and response handling.

These tests use mocked external transport where applicable. Passing automated tests does not independently establish successful live email delivery.

### 10.2 PostgreSQL Integration Tests

For PostgreSQL integration testing, create an isolated test database. Its name must contain `test`.

Example:

```sql
CREATE DATABASE ai_project_monitoring_test;
```

Set the test database connection:

```powershell
$env:AUTH_TEST_POSTGRES_URL="postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/ai_project_monitoring_test"
```

Run the backend tests:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -v
```

Never point integration tests at the production database.

### 10.3 Frontend Tests

From the frontend directory:

```powershell
npm test -- --run
```

The existing README test baseline was 2 test files and 5 tests passed. Re-run the command to confirm the current result.

### 10.4 Frontend Production Build

```powershell
npm run build
```

The optimized production bundle is generated in:

`frontend/dist/`

---

## 11. Safe Development-Data Cleanup

The backend provides a non-destructive development-data audit utility:

`backend/app/cleanup_dev_data.py`

Run a dry-run audit:

```powershell
python -m app.cleanup_dev_data
```

The utility enforces safeguards:

- `APP_ENV` cannot be `production`.
- The target database name must contain `test` or `dev`.
- Foreign-key dependency trees and record counts are displayed.
- The default operation is an audit rather than destructive cleanup.

Always inspect the output before considering any data modification.

---

## 12. External Integrations and Credentials

| Integration                  | Development/Test Mode                      | Live Requirements                                                                                                          | Fallback Behavior                                              |
| ---------------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Email and OTP                | Mocked using `FakeSMTP` in automated tests | Valid SMTP credentials and application password                                                                            | Raises a sanitized email service error                         |
| GitHub REST API              | Mocked JSON fixtures in unit tests         | Public repositories can be accessed without credentials; private repositories and heavier usage may require `GITHUB_TOKEN` | Handles API rate limits gracefully                             |
| LLM Synthesis                | Mocked using `MockLLMProvider`             | Groq or Gemini API key                                                                                                     | Returns a configuration-related service error when unavailable |
| n8n Submission Notifications | Mocked webhook transport in backend tests  | Configured submission webhook and email workflow                                                                           | Notification failure is handled as a best-effort operation     |
| n8n Marks Notifications      | Mocked webhook transport in backend tests  | Configured marks-update webhook and email workflow                                                                         | Notification failure does not undo the database update         |

### Groq and Gemini

The LLM provider is configured through:

```env
LLM_PROVIDER=groq
```

or:

```env
LLM_PROVIDER=gemini
```

Provide the corresponding API key in the environment configuration.

### GitHub

For authenticated GitHub API access:

```env
GITHUB_TOKEN=your_github_personal_access_token
```

Use an appropriately scoped token and keep it private.

---

## 13. Security and Academic Integrity Safeguards

ProjectScope incorporates the following safeguards:

1. **Role-Based Principal Derivation:** Faculty reviewer identity is derived from the verified JWT principal on the server. Client-provided input cannot spoof reviewer identities.

2. **Secure Password Storage:** Passwords are protected using Argon2id hashing.

3. **Authentication and Verification:** JWT bearer authentication and OTP-based email verification protect account access.

4. **Confidentiality of File Paths:** Deliverable uploads and downloads do not expose internal server disk paths.

5. **Secure File Handling:** Uploaded files are stored using random UUID-based identifiers and undergo MIME-type and file-signature validation.

6. **Webhook Authentication:** Configured shared secrets are used to authenticate supported n8n webhook requests.

7. **Safe Notification Processing:** Email notifications are processed as best-effort external operations without rolling back already committed submission or review changes.

8. **Advisory AI Outputs:** Document completeness scores, GitHub activity indicators, and LLM-generated project summaries are decision-support tools, not automated academic grading mechanisms.

9. **Faculty Authority:** Final academic marks, project evaluations, and student assessment decisions remain under faculty control.

---

## 14. Repository Structure

```text
AI-Project-Monitoring/
│
├── backend/
│   ├── app/
│   │   ├── api_submission_uploads.py
│   │   ├── api_reviews.py
│   │   ├── services/
│   │   │   └── n8n_notifier.py
│   │   ├── db/
│   │   ├── main.py
│   │   └── provision_faculty.py
│   │
│   ├── migrations/
│   ├── tests/
│   │   └── test_submission_faculty_notifications.py
│   │
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.js
│
├── README.md
└── .gitignore
```

_This is a representative overview; additional application modules and configuration files may be present._

---

## 15. Future Enhancements

Potential areas for further development include:

- Advanced project progress analytics.
- Improved faculty review dashboards.
- Expanded GitHub contribution insights.
- Additional document formats and structural validation rules.
- Enhanced AI evidence-grounding and explainability.
- More detailed notification delivery monitoring.
- Deployment automation and production observability.

---

## 16. Project Information

**Project Name:** ProjectScope

**Project Category:** AI-Based Academic Project Monitoring and Review Automation

**Technology Stack:** Python, FastAPI, React, PostgreSQL, SQLAlchemy, n8n, Groq, Gemini, and GitHub REST API.

**Repository:** https://github.com/VINYTHA1708/AI-Project-Monitoring

ProjectScope aims to reduce manual academic project administration through structured workflows, automated notifications, document analysis, collaboration insights, and evidence-grounded AI assistance while preserving faculty oversight and academic integrity.
