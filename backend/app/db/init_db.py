from app.db.database import engine
from app.db.models import Base


def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")
    print("Tables:", list(Base.metadata.tables.keys()))


if __name__ == "__main__":
    init_db()
