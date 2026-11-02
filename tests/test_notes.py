from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import engine
from app.models import Note
from conftest import logout, post_form, register


def create_note(client: TestClient, title: str = "Bonjour", content: str = "Hello in French.") -> int:
    post_form(client, "/notes/new", "/notes/new", {"title": title, "content": content})
    with Session(engine) as session:
        note = session.exec(select(Note).order_by(Note.id.desc())).first()
        assert note is not None
        return note.id


def get_note(note_id: int) -> Note | None:
    with Session(engine) as session:
        return session.get(Note, note_id)


def create_other_users_note(client: TestClient) -> int:
    register(client, "owner@example.com")
    note_id = create_note(client, title="Private note")
    logout(client)
    register(client, "intruder@example.com")
    return note_id


@pytest.mark.parametrize("path", ["/notes", "/notes/new", "/notes/1", "/notes/1/edit"])
def test_notes_pages_redirect_to_login_when_logged_out(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_create_note_when_logged_out_redirects_to_login(client: TestClient) -> None:
    response = post_form(client, "/login", "/notes/new", {"title": "Hi", "content": "There"})
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_create_note(client: TestClient) -> None:
    register(client, "anna@example.com")
    response = post_form(client, "/notes/new", "/notes/new", {"title": "Bonjour", "content": "Hello"})
    assert response.status_code == 303
    assert response.headers["location"] == "/notes"
    page = client.get("/notes")
    assert "Bonjour" in page.text
    assert "Hello" in page.text


def test_new_note_has_equal_utc_timestamps(client: TestClient) -> None:
    register(client, "anna@example.com")
    before = datetime.now(timezone.utc)
    note = get_note(create_note(client))
    assert note is not None
    assert note.created_at == note.updated_at
    assert note.created_at.tzinfo is not None
    assert before <= note.created_at <= datetime.now(timezone.utc)


def test_notes_list_shows_newest_first(client: TestClient) -> None:
    register(client, "anna@example.com")
    create_note(client, title="Older note")
    create_note(client, title="Newer note")
    page = client.get("/notes").text
    assert page.index("Newer note") < page.index("Older note")


def test_notes_list_shows_only_own_notes(client: TestClient) -> None:
    create_other_users_note(client)
    assert "Private note" not in client.get("/notes").text


def test_view_note(client: TestClient) -> None:
    register(client, "anna@example.com")
    note_id = create_note(client, title="Le chat", content="The cat sleeps.")
    response = client.get(f"/notes/{note_id}")
    assert response.status_code == 200
    assert "Le chat" in response.text
    assert "The cat sleeps." in response.text


def test_edit_note_updates_fields_and_updated_at(client: TestClient) -> None:
    register(client, "anna@example.com")
    note_id = create_note(client)
    original = get_note(note_id)
    assert original is not None

    edit_url = f"/notes/{note_id}/edit"
    response = post_form(client, edit_url, edit_url, {"title": "Au revoir", "content": "Goodbye"})
    assert response.status_code == 303
    assert response.headers["location"] == f"/notes/{note_id}"

    edited = get_note(note_id)
    assert edited is not None
    assert edited.title == "Au revoir"
    assert edited.content == "Goodbye"
    assert edited.created_at == original.created_at
    assert edited.updated_at > original.updated_at


def test_delete_note(client: TestClient) -> None:
    register(client, "anna@example.com")
    note_id = create_note(client)
    response = post_form(client, f"/notes/{note_id}", f"/notes/{note_id}/delete", {})
    assert response.status_code == 303
    assert response.headers["location"] == "/notes"
    assert get_note(note_id) is None


def test_delete_note_with_get_is_not_allowed(client: TestClient) -> None:
    register(client, "anna@example.com")
    note_id = create_note(client)
    assert client.get(f"/notes/{note_id}/delete").status_code == 405
    assert get_note(note_id) is not None


@pytest.mark.parametrize(
    ("title", "content", "message"),
    [
        ("", "Some content", "Title is required."),
        ("   ", "Some content", "Title is required."),
        ("A title", "", "Content is required."),
        ("x" * 201, "Some content", "Title must be at most 200 characters."),
        ("A title", "x" * 10001, "Content must be at most 10,000 characters."),
    ],
)
def test_create_note_with_invalid_input_returns_400(
    client: TestClient, title: str, content: str, message: str
) -> None:
    register(client, "anna@example.com")
    response = post_form(client, "/notes/new", "/notes/new", {"title": title, "content": content})
    assert response.status_code == 400
    assert message in response.text


def test_invalid_note_form_keeps_user_input(client: TestClient) -> None:
    register(client, "anna@example.com")
    response = post_form(client, "/notes/new", "/notes/new", {"title": "", "content": "Keep me"})
    assert "Keep me" in response.text


def test_edit_note_with_invalid_input_returns_400_and_keeps_note(client: TestClient) -> None:
    register(client, "anna@example.com")
    note_id = create_note(client, title="Original")
    edit_url = f"/notes/{note_id}/edit"
    response = post_form(client, edit_url, edit_url, {"title": "", "content": "New content"})
    assert response.status_code == 400
    note = get_note(note_id)
    assert note is not None
    assert note.title == "Original"


def test_note_input_is_trimmed(client: TestClient) -> None:
    register(client, "anna@example.com")
    note = get_note(create_note(client, title="  Bonjour  ", content="  Hello  "))
    assert note is not None
    assert note.title == "Bonjour"
    assert note.content == "Hello"


def test_note_html_is_escaped(client: TestClient) -> None:
    register(client, "anna@example.com")
    note_id = create_note(client, title="<script>alert(1)</script>")
    page = client.get(f"/notes/{note_id}").text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_create_note_without_csrf_token_returns_403(client: TestClient) -> None:
    register(client, "anna@example.com")
    response = client.post("/notes/new", data={"title": "Hi", "content": "There"})
    assert response.status_code == 403


def test_edit_note_without_csrf_token_returns_403(client: TestClient) -> None:
    register(client, "anna@example.com")
    note_id = create_note(client, title="Original")
    response = client.post(f"/notes/{note_id}/edit", data={"title": "Changed", "content": "x"})
    assert response.status_code == 403
    note = get_note(note_id)
    assert note is not None
    assert note.title == "Original"


def test_delete_note_without_csrf_token_returns_403(client: TestClient) -> None:
    register(client, "anna@example.com")
    note_id = create_note(client)
    assert client.post(f"/notes/{note_id}/delete").status_code == 403
    assert get_note(note_id) is not None


@pytest.mark.parametrize("path", ["/notes/99999", "/notes/99999/edit"])
def test_missing_note_returns_404(client: TestClient, path: str) -> None:
    register(client, "anna@example.com")
    assert client.get(path).status_code == 404


def test_delete_missing_note_returns_404(client: TestClient) -> None:
    register(client, "anna@example.com")
    assert post_form(client, "/notes", "/notes/99999/delete", {}).status_code == 404


def test_user_cannot_view_other_users_note(client: TestClient) -> None:
    note_id = create_other_users_note(client)
    assert client.get(f"/notes/{note_id}").status_code == 404


def test_user_cannot_open_edit_form_for_other_users_note(client: TestClient) -> None:
    note_id = create_other_users_note(client)
    assert client.get(f"/notes/{note_id}/edit").status_code == 404


def test_user_cannot_edit_other_users_note(client: TestClient) -> None:
    note_id = create_other_users_note(client)
    data = {"title": "Hacked", "content": "Hacked"}
    response = post_form(client, "/notes", f"/notes/{note_id}/edit", data)
    assert response.status_code == 404
    note = get_note(note_id)
    assert note is not None
    assert note.title == "Private note"


def test_user_cannot_delete_other_users_note(client: TestClient) -> None:
    note_id = create_other_users_note(client)
    response = post_form(client, "/notes", f"/notes/{note_id}/delete", {})
    assert response.status_code == 404
    assert get_note(note_id) is not None
