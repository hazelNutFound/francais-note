from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, select

from app.database import engine, get_session
from app.main import app
from app.models import Vocabulary
from conftest import post_form, register


def test_missing_page_shows_html_404(client: TestClient) -> None:
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "Page not found" in response.text


def test_missing_note_shows_html_404(client: TestClient) -> None:
    register(client, "anna@example.com")
    response = client.get("/notes/99999")
    assert response.status_code == 404
    assert "Page not found" in response.text
    assert '"detail"' not in response.text


def test_invalid_id_in_path_shows_html_404(client: TestClient) -> None:
    register(client, "anna@example.com")
    response = client.get("/notes/abc")
    assert response.status_code == 404
    assert "Page not found" in response.text


def test_csrf_failure_shows_html_403(client: TestClient) -> None:
    client.get("/login")
    response = client.post("/login", data={"email": "a@b.com", "password": "x", "csrf_token": "wrong"})
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("text/html")
    assert "This form has expired or is not valid." in response.text


def test_invalid_review_rating_shows_html_400(client: TestClient) -> None:
    register(client, "anna@example.com")
    post_form(client, "/vocabulary/new", "/vocabulary/new", {"french_word": "le chat", "english_meaning": "the cat"})
    with Session(engine) as session:
        word = session.exec(select(Vocabulary)).first()
        assert word is not None
    response = post_form(client, "/review", f"/review/{word.id}", {"rating": "hard"})
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/html")
    assert "Rating must be again, good or easy" in response.text


def test_wrong_method_shows_html_405(client: TestClient) -> None:
    response = client.get("/logout")
    assert response.status_code == 405
    assert "Not allowed" in response.text


def test_server_error_shows_generic_html_500(client: TestClient) -> None:
    def broken_session() -> Iterator[Session]:
        raise RuntimeError("secret internal detail")
        yield

    register(client, "anna@example.com")
    app.dependency_overrides[get_session] = broken_session
    try:
        with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as crash_client:
            crash_client.cookies = client.cookies
            response = crash_client.get("/notes")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500
    assert "Something went wrong" in response.text
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text


def test_api_docs_are_turned_off(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_app_startup_creates_tables_in_empty_database() -> None:
    SQLModel.metadata.drop_all(engine)
    assert inspect(engine).get_table_names() == []
    with TestClient(app):
        table_names = set(inspect(engine).get_table_names())
    assert {"user", "note", "vocabulary"} <= table_names
