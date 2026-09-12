import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker


# Find the backend folder
BASE_DIR = Path(__file__).resolve().parent

# Load values from backend/.env
load_dotenv(BASE_DIR / ".env")


DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")


DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )
else:
    DATABASE_URL = URL.create(
        drivername="postgresql+psycopg",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=int(DB_PORT or 5432),
        database=DB_NAME,
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


Base = declarative_base()


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()  


def get_write_db():
    """Serialize campus inventory mutations before reading state.

    The transaction-scoped PostgreSQL lock covers request, inventory, user and
    assignment changes together and releases on commit/rollback or disconnect.
    All mutation routes use this dependency; ordinary reads remain concurrent.
    """
    with SessionLocal() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(728104)'))
        try:
            yield db
        except Exception:
            db.rollback()
            raise
