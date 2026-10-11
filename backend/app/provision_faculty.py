import argparse
import sys
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import _faculty_is_approved, normalize_email
from app.db.database import SessionLocal
from app.db.models import AuthAccount, FacultyProjectAssignment, Project


def approve_faculty(email: str, db: Optional[Session] = None) -> AuthAccount:
    """Safely approve a verified faculty account via CLI or administrative provisioning."""
    normalized_email = normalize_email(email)
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        account = db.scalar(
            select(AuthAccount).where(AuthAccount.email == normalized_email)
        )
        if account is None:
            raise ValueError(f"Account with email '{normalized_email}' not found.")
        if account.role != "faculty":
            raise ValueError(f"Account '{normalized_email}' is a {account.role}, not faculty.")
        if not account.email_verified:
            raise ValueError(f"Faculty account '{normalized_email}' must verify email before approval.")
        if not account.faculty_approved:
            account.faculty_approved = True
            db.commit()
            db.refresh(account)
        return account
    finally:
        if close_db:
            db.close()


def assign_faculty(email: str, project_id: int, db: Optional[Session] = None) -> FacultyProjectAssignment:
    normalized_email = normalize_email(email)
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        account = db.scalar(
            select(AuthAccount).where(AuthAccount.email == normalized_email)
        )
        if account is None or not _faculty_is_approved(account):
            raise ValueError("An approved, verified faculty account is required.")
        if db.get(Project, project_id) is None:
            raise ValueError("Project not found.")
        existing = db.get(
            FacultyProjectAssignment,
            (account.id, project_id),
        )
        if existing is None:
            assignment = FacultyProjectAssignment(
                faculty_account_id=account.id,
                project_id=project_id,
            )
            db.add(assignment)
            db.commit()
            return assignment
        return existing
    finally:
        if close_db:
            db.close()


def list_pending_faculty(db: Optional[Session] = None) -> list[AuthAccount]:
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        return list(
            db.scalars(
                select(AuthAccount)
                .where(
                    AuthAccount.role == "faculty",
                    AuthAccount.faculty_approved.is_(False),
                )
                .order_by(AuthAccount.created_at)
            ).all()
        )
    finally:
        if close_db:
            db.close()


def main(args: Optional[list[str]] = None) -> None:
    raw_args = args if args is not None else sys.argv[1:]
    
    # Backward-compatible fallback: python -m app.provision_faculty <email> <project_id>
    if len(raw_args) == 2 and not raw_args[0].startswith("-") and raw_args[0] not in ("approve", "assign", "list-pending"):
        email, project_id_str = raw_args
        try:
            pid = int(project_id_str)
            assign_faculty(email, pid)
            print(f"Faculty '{email}' assigned to project #{pid}.")
            return
        except ValueError:
            pass

    parser = argparse.ArgumentParser(
        description="Provision, approve, and assign faculty accounts."
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    assign_parser = subparsers.add_parser("assign", help="Assign an approved faculty member to a project")
    assign_parser.add_argument("email", help="Verified faculty email address")
    assign_parser.add_argument("project_id", type=int, help="Existing project ID")

    approve_parser = subparsers.add_parser("approve", help="Approve an email-verified faculty account")
    approve_parser.add_argument("email", help="Faculty email address")

    subparsers.add_parser("list-pending", help="List all faculty accounts pending approval")

    parsed = parser.parse_args(raw_args)
    if parsed.subcommand == "approve":
        account = approve_faculty(parsed.email)
        print(f"Faculty account '{account.email}' (ID: {account.faculty_id}) is now approved.")
    elif parsed.subcommand == "assign":
        assign_faculty(parsed.email, parsed.project_id)
        print(f"Faculty project assignment saved for '{parsed.email}' on project #{parsed.project_id}.")
    elif parsed.subcommand == "list-pending":
        pending = list_pending_faculty()
        if not pending:
            print("No faculty accounts pending approval.")
        else:
            print(f"Found {len(pending)} pending faculty account(s):")
            for acc in pending:
                print(f" - {acc.email} | Name: {acc.faculty_name} | ID: {acc.faculty_id} | Verified: {acc.email_verified}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

