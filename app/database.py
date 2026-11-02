from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import DATABASE_URL

# pool_pre_ping replaces connections that Neon closed while the database was idle.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def create_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
