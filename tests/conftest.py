import os
import re
from collections.abc import Iterator

import pytest
from dotenv import load_dotenv
from httpx import Response

load_dotenv()

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("TEST_DATABASE_URL is not set. Tests must use a separate test database.")
if TEST_DATABASE_URL == os.getenv("DATABASE_URL"):
    raise RuntimeError("TEST_DATABASE_URL must be different from DATABASE_URL.")

# Point the app at the test database before the app is imported, so tests never touch real data.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402

TEST_PASSWORD = "correct-horse-123"


@pytest.fixture
def client() -> Iterator[TestClient]:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


def get_csrf_token(client: TestClient, path: str) -> str:
    page = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match is not None
    return match.group(1)


def register(client: TestClient, email: str, password: str = TEST_PASSWORD) -> Response:
    csrf_token = get_csrf_token(client, "/register")
    form = {"email": email, "password": password, "csrf_token": csrf_token}
    return client.post("/register", data=form)


def login(client: TestClient, email: str, password: str = TEST_PASSWORD) -> Response:
    csrf_token = get_csrf_token(client, "/login")
    form = {"email": email, "password": password, "csrf_token": csrf_token}
    return client.post("/login", data=form)


def logout(client: TestClient) -> Response:
    csrf_token = get_csrf_token(client, "/login")
    return client.post("/logout", data={"csrf_token": csrf_token})


def post_form(client: TestClient, form_page: str, post_url: str, data: dict[str, str]) -> Response:
    form = {**data, "csrf_token": get_csrf_token(client, form_page)}
    return client.post(post_url, data=form)
