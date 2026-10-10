from app.db.database import engine
from app.db.models import Base

MIGRATION_MANAGED_TABLES = {
    "auth_accounts",
    "auth_otp_challenges",
    "auth_rate_limit_buckets",
    "faculty_project_assignments",
}


def init_db():
    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name not in MIGRATION_MANAGED_TABLES
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    print("Existing application tables initialized.")
    print("Tables:", [table.name for table in tables])


if __name__ == "__main__":
    init_db()
