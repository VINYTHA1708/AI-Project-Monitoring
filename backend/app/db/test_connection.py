from sqlalchemy import text

from app.db.database import engine


def test_connection():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT current_database()"))
        database_name = result.scalar_one()

        print(f"Connected successfully to: {database_name}")


if __name__ == "__main__":
    try:
        test_connection()
    except Exception as error:
        print("Database connection failed.")
        print(f"Error: {error}")
    finally:
        engine.dispose()
