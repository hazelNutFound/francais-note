from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import engine
from app.models import Vocabulary
from conftest import logout, post_form, register


def create_word(client: TestClient, french_word: str = "le chat", english_meaning: str = "the cat") -> int:
    data = {"french_word": french_word, "english_meaning": english_meaning}
    post_form(client, "/vocabulary/new", "/vocabulary/new", data)
    with Session(engine) as session:
        word = session.exec(select(Vocabulary).order_by(Vocabulary.id.desc())).first()
        assert word is not None
        return word.id


def get_word(word_id: int) -> Vocabulary | None:
    with Session(engine) as session:
        return session.get(Vocabulary, word_id)


def create_other_users_word(client: TestClient) -> int:
    register(client, "owner@example.com")
    word_id = create_word(client, french_word="le secret")
    logout(client)
    register(client, "intruder@example.com")
    return word_id


@pytest.mark.parametrize("path", ["/vocabulary", "/vocabulary/new", "/vocabulary/1", "/vocabulary/1/edit"])
def test_vocabulary_pages_redirect_to_login_when_logged_out(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_create_word_when_logged_out_redirects_to_login(client: TestClient) -> None:
    data = {"french_word": "le chat", "english_meaning": "the cat"}
    response = post_form(client, "/login", "/vocabulary/new", data)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_create_word(client: TestClient) -> None:
    register(client, "anna@example.com")
    data = {"french_word": "le chien", "english_meaning": "the dog"}
    response = post_form(client, "/vocabulary/new", "/vocabulary/new", data)
    assert response.status_code == 303
    assert response.headers["location"] == "/vocabulary"
    page = client.get("/vocabulary")
    assert "le chien" in page.text
    assert "the dog" in page.text


def test_new_word_is_immediately_due(client: TestClient) -> None:
    register(client, "anna@example.com")
    word = get_word(create_word(client))
    assert word is not None
    assert word.next_review_date == word.created_at
    assert word.next_review_date.tzinfo is not None
    assert word.next_review_date <= datetime.now(timezone.utc)


def test_vocabulary_list_shows_newest_first(client: TestClient) -> None:
    register(client, "anna@example.com")
    create_word(client, french_word="ancien")
    create_word(client, french_word="nouveau")
    page = client.get("/vocabulary").text
    assert page.index("nouveau") < page.index("ancien")


def test_vocabulary_list_shows_only_own_words(client: TestClient) -> None:
    create_other_users_word(client)
    assert "le secret" not in client.get("/vocabulary").text


def test_view_word(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client, french_word="la pomme", english_meaning="the apple")
    response = client.get(f"/vocabulary/{word_id}")
    assert response.status_code == 200
    assert "la pomme" in response.text
    assert "the apple" in response.text


def test_edit_word_updates_fields(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    edit_url = f"/vocabulary/{word_id}/edit"
    data = {"french_word": "le chaton", "english_meaning": "the kitten"}
    response = post_form(client, edit_url, edit_url, data)
    assert response.status_code == 303
    assert response.headers["location"] == f"/vocabulary/{word_id}"
    word = get_word(word_id)
    assert word is not None
    assert word.french_word == "le chaton"
    assert word.english_meaning == "the kitten"


def test_edit_word_keeps_next_review_date(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    later_date = datetime(2030, 1, 15, 9, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        word = session.get(Vocabulary, word_id)
        assert word is not None
        word.next_review_date = later_date
        session.add(word)
        session.commit()

    edit_url = f"/vocabulary/{word_id}/edit"
    post_form(client, edit_url, edit_url, {"french_word": "le chaton", "english_meaning": "the kitten"})
    word = get_word(word_id)
    assert word is not None
    assert word.next_review_date == later_date


def test_delete_word(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    response = post_form(client, f"/vocabulary/{word_id}", f"/vocabulary/{word_id}/delete", {})
    assert response.status_code == 303
    assert response.headers["location"] == "/vocabulary"
    assert get_word(word_id) is None


def test_delete_word_with_get_is_not_allowed(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    assert client.get(f"/vocabulary/{word_id}/delete").status_code == 405
    assert get_word(word_id) is not None


@pytest.mark.parametrize(
    ("french_word", "english_meaning", "message"),
    [
        ("", "the cat", "French word is required."),
        ("   ", "the cat", "French word is required."),
        ("le chat", "", "English meaning is required."),
        ("x" * 101, "the cat", "French word must be at most 100 characters."),
        ("le chat", "x" * 301, "English meaning must be at most 300 characters."),
    ],
)
def test_create_word_with_invalid_input_returns_400(
    client: TestClient, french_word: str, english_meaning: str, message: str
) -> None:
    register(client, "anna@example.com")
    data = {"french_word": french_word, "english_meaning": english_meaning}
    response = post_form(client, "/vocabulary/new", "/vocabulary/new", data)
    assert response.status_code == 400
    assert message in response.text


def test_edit_word_with_invalid_input_returns_400_and_keeps_word(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client, french_word="le chat")
    edit_url = f"/vocabulary/{word_id}/edit"
    response = post_form(client, edit_url, edit_url, {"french_word": "", "english_meaning": "the cat"})
    assert response.status_code == 400
    word = get_word(word_id)
    assert word is not None
    assert word.french_word == "le chat"


def test_word_input_is_trimmed(client: TestClient) -> None:
    register(client, "anna@example.com")
    word = get_word(create_word(client, french_word="  le chat ", english_meaning=" the cat  "))
    assert word is not None
    assert word.french_word == "le chat"
    assert word.english_meaning == "the cat"


def test_create_word_without_csrf_token_returns_403(client: TestClient) -> None:
    register(client, "anna@example.com")
    data = {"french_word": "le chat", "english_meaning": "the cat"}
    assert client.post("/vocabulary/new", data=data).status_code == 403


def test_edit_word_without_csrf_token_returns_403(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client, french_word="le chat")
    data = {"french_word": "changed", "english_meaning": "changed"}
    assert client.post(f"/vocabulary/{word_id}/edit", data=data).status_code == 403
    word = get_word(word_id)
    assert word is not None
    assert word.french_word == "le chat"


def test_delete_word_without_csrf_token_returns_403(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    assert client.post(f"/vocabulary/{word_id}/delete").status_code == 403
    assert get_word(word_id) is not None


@pytest.mark.parametrize("path", ["/vocabulary/99999", "/vocabulary/99999/edit"])
def test_missing_word_returns_404(client: TestClient, path: str) -> None:
    register(client, "anna@example.com")
    assert client.get(path).status_code == 404


def test_delete_missing_word_returns_404(client: TestClient) -> None:
    register(client, "anna@example.com")
    assert post_form(client, "/vocabulary", "/vocabulary/99999/delete", {}).status_code == 404


def test_user_cannot_view_other_users_word(client: TestClient) -> None:
    word_id = create_other_users_word(client)
    assert client.get(f"/vocabulary/{word_id}").status_code == 404


def test_user_cannot_open_edit_form_for_other_users_word(client: TestClient) -> None:
    word_id = create_other_users_word(client)
    assert client.get(f"/vocabulary/{word_id}/edit").status_code == 404


def test_user_cannot_edit_other_users_word(client: TestClient) -> None:
    word_id = create_other_users_word(client)
    data = {"french_word": "hacked", "english_meaning": "hacked"}
    response = post_form(client, "/vocabulary", f"/vocabulary/{word_id}/edit", data)
    assert response.status_code == 404
    word = get_word(word_id)
    assert word is not None
    assert word.french_word == "le secret"


def test_user_cannot_delete_other_users_word(client: TestClient) -> None:
    word_id = create_other_users_word(client)
    response = post_form(client, "/vocabulary", f"/vocabulary/{word_id}/delete", {})
    assert response.status_code == 404
    assert get_word(word_id) is not None
