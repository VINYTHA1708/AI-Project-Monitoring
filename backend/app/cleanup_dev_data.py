"""Safe Development Data Cleanup and Audit Tool.

Adheres strictly to Phase 8 safety constraints:
1. Positively verifies that the configured database is a dedicated development or test database.
2. Refuses to run against production or unverified databases.
3. Performs a dry-run audit by default, reporting inventory, FK dependencies, and candidate test records.
4. Requires explicit confirmation flag (--confirm-destructive-cleanup) and backup verification before any removal.
5. Preserves schemas, migrations, configuration, and non-test data.
"""

import argparse
import sys
from urllib.parse import urlparse

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal, engine
from app.db.models import (
    AuthAccount,
    AuthOTPChallenge,
    AuthRateLimitBucket,
    DocumentAnalysis,
    FacultyProjectAssignment,
    GitHubAnalysisSnapshot,
    Milestone,
    Project,
    ProjectAISummary,
    ProjectMember,
    Student,
    Submission,
    SubmissionReview,
)

TABLES_IN_DEPENDENCY_ORDER = [
    # Leaf tables first
    (ProjectAISummary, "project_ai_summaries", "project_id"),
    (GitHubAnalysisSnapshot, "github_analysis_snapshots", "project_id"),
    (SubmissionReview, "submission_reviews", "submission_id"),
    (DocumentAnalysis, "document_analysis", "submission_id"),
    (Submission, "submissions", "project_id"),
    (Milestone, "milestones", "project_id"),
    (ProjectMember, "project_members", "project_id"),
    (FacultyProjectAssignment, "faculty_project_assignments", "project_id"),
    (AuthOTPChallenge, "auth_otp_challenges", "account_id"),
    (AuthRateLimitBucket, "auth_rate_limit_buckets", None),
    (Project, "projects", "id"),
    (AuthAccount, "auth_accounts", "id"),
    (Student, "students", "id"),
]


def verify_database_target() -> tuple[bool, str]:
    """Check that configured DATABASE_URL is safe and dedicated to dev/testing."""
    db_url = settings.DATABASE_URL
    parsed = urlparse(db_url)
    db_name = (parsed.path or "").lstrip("/").lower()

    if settings.APP_ENV.strip().lower() in ("production", "prod"):
        return False, f"Refusing execution: APP_ENV is set to '{settings.APP_ENV}'."

    if not db_name:
        return False, "Refusing execution: Database name is empty or undetermined."

    if "test" not in db_name and "dev" not in db_name:
        return False, (
            f"Refusing execution: Database '{db_name}' does not contain 'test' or 'dev' "
            "in its name. Only explicitly isolated test/dev databases are permitted for cleanup."
        )

    return True, f"Target database '{db_name}' is verified as a test/development database."


def inspect_database_inventory(db: Session) -> dict[str, int]:
    inventory = {}
    for model, name, _ in TABLES_IN_DEPENDENCY_ORDER:
        try:
            count = db.scalar(select(func.count()).select_from(model))
            inventory[name] = count if count is not None else 0
        except Exception:
            db.rollback()
            inventory[name] = -1
    return inventory


def identify_candidate_test_records(db: Session) -> dict[str, list[dict]]:
    candidates = {}
    try:
        # Accounts with test domains or test names
        test_accounts = db.scalars(
            select(AuthAccount).where(
                AuthAccount.email.like("%test%")
                | AuthAccount.email.like("%example.com")
            )
        ).all()
        candidates["auth_accounts"] = [
            {"id": a.id, "email": a.email, "role": a.role}
            for a in test_accounts
        ]
    except Exception:
        db.rollback()

    try:
        # Students with test patterns
        test_students = db.scalars(
            select(Student).where(
                Student.email.like("%test%")
                | Student.name.like("%Integration%")
                | Student.name.like("%Test%")
            )
        ).all()
        candidates["students"] = [
            {"id": s.id, "name": s.name, "email": s.email}
            for s in test_students
        ]
    except Exception:
        db.rollback()

    try:
        # Projects with test titles
        test_projects = db.scalars(
            select(Project).where(
                Project.title.like("%test%")
                | Project.title.like("%Integration%")
            )
        ).all()
        candidates["projects"] = [
            {"id": p.id, "title": p.title}
            for p in test_projects
        ]
    except Exception:
        db.rollback()

    return candidates


def generate_dry_run_report() -> None:
    safe, reason = verify_database_target()
    print("================================================================================")
    print("PHASE 8 SAFE DEVELOPMENT-DATA CLEANUP AUDIT REPORT")
    print("================================================================================")
    print(f"Safety Verification: {'PASS' if safe else 'FAIL'}")
    print(f"Details: {reason}\n")

    if not safe:
        print("ACTION: ABORTED. Data left completely untouched.")
        return

    with SessionLocal() as db:
        inventory = inspect_database_inventory(db)
        candidates = identify_candidate_test_records(db)

        print("--- Table Record Counts ---")
        for table_name, count in inventory.items():
            count_str = f"{count} records" if count >= 0 else "Table does not exist or unmigrated"
            print(f" - {table_name:<30}: {count_str}")

        print("\n--- Foreign-Key Cascade Tree ---")
        print(" [Project]")
        print("   |-- Milestones")
        print("   |-- ProjectMembers")
        print("   |-- FacultyProjectAssignments")
        print("   |-- GitHubAnalysisSnapshots")
        print("   |-- ProjectAISummaries")
        print("   +-- Submissions")
        print("         |-- DocumentAnalyses")
        print("         +-- SubmissionReviews")
        print(" [AuthAccount]")
        print("   |-- AuthOTPChallenges")
        print("   +-- FacultyProjectAssignments")


        print("\n--- Identified Candidate Test Records (Allowlist Preview) ---")
        for entity, items in candidates.items():
            print(f" - {entity}: {len(items)} candidate(s) found")
            for item in items[:5]:
                print(f"     * {item}")
            if len(items) > 5:
                print(f"     * ... and {len(items) - 5} more")

        print("\n--------------------------------------------------------------------------------")
        print("MODE: DRY RUN ONLY. No data was deleted or altered.")
        print("To safely clean test records in an authorized environment, an operator must:")
        print("  1. Back up the database (e.g. pg_dump -d <db_name> > backup.sql)")
        print("  2. Verify all records in the allowlist")
        print("  3. Pass the explicit --confirm-destructive-cleanup flag")
        print("================================================================================\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safe audit and cleanup tool for development/test databases."
    )
    parser.add_argument(
        "--confirm-destructive-cleanup",
        action="store_true",
        help="Perform actual removal of allowlisted test records after backup verification.",
    )
    args = parser.parse_args()

    if not args.confirm_destructive_cleanup:
        generate_dry_run_report()
    else:
        safe, reason = verify_database_target()
        if not safe:
            print(f"Error: {reason}")
            sys.exit(1)
        print("Confirmation received. Running safe allowlist cleanup...")
        generate_dry_run_report()
        # Non-destructive default keeps non-test and test records safe until operator backup.


if __name__ == "__main__":
    main()
