from sqlalchemy import text

from app.db.database import engine


def test_connection():
    """Verify database connectivity with a dialect-neutral probe query.

    Uses SELECT 1 instead of the PostgreSQL-specific SELECT current_database()
    so that the smoke test works against both SQLite (for tests) and PostgreSQL
    (for development/production).  Connection metadata is read from the engine
    URL rather than from a database-specific function.
    """
    url = engine.url
    dialect = url.get_dialect().name
    # Report the database name from the URL; for SQLite this is the file path.
    database_name = str(url.database or "(none)")

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    print(f"Connected successfully. dialect={dialect} database={database_name}")


if __name__ == "__main__":
    try:
        test_connection()
    except Exception as error:
        print("Database connection failed.")
        print(f"Error: {error}")
    finally:
        engine.dispose()
