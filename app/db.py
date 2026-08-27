from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


settings = get_settings()
engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    if settings.database_url.startswith("sqlite:///"):
        db_path = settings.database_url.removeprefix("sqlite:///")
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("vm_assignments")}
    with engine.begin() as connection:
        if "template_vmid" not in columns:
            connection.execute(text("ALTER TABLE vm_assignments ADD COLUMN template_vmid INTEGER"))
        if "template_label" not in columns:
            connection.execute(text("ALTER TABLE vm_assignments ADD COLUMN template_label VARCHAR(200)"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
