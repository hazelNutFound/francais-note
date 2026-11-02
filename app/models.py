from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%d %b %Y")


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(max_length=255, unique=True)
    password_hash: str
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class Note(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    title: str = Field(max_length=200)
    content: str = Field(max_length=10000)
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(sa_type=DateTime(timezone=True))


class Vocabulary(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    french_word: str = Field(max_length=100)
    english_meaning: str = Field(max_length=300)
    next_review_date: datetime = Field(sa_type=DateTime(timezone=True))
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
