import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    user_required_columns = {
        "nickname": "VARCHAR(50)",
        "profile_image": "VARCHAR(500)",
        "bio": "TEXT",
        "is_admin": "BOOLEAN DEFAULT 0",
    }
    post_columns = {column["name"] for column in inspector.get_columns("posts")} if "posts" in inspector.get_table_names() else set()
    post_required_columns = {
        "view_count": "INTEGER DEFAULT 0",
        "status": "VARCHAR(20) DEFAULT 'published'",
        "anonymous_author_name": "VARCHAR(50)",
        "promotion_deadline": "DATETIME",
    }

    with engine.begin() as connection:
        for name, ddl in user_required_columns.items():
            if name not in user_columns:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
        for name, ddl in post_required_columns.items():
            if name not in post_columns:
                connection.execute(text(f"ALTER TABLE posts ADD COLUMN {name} {ddl}"))
