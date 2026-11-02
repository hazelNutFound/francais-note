from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from httpx import Response
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


def get_word(word_id: int) -> Vocabulary:
    with Session(engine) as session:
        word = session.get(Vocabulary, word_id)
        assert word is not None
        return word


def set_next_review_date(word_id: int, next_review_date: datetime) -> None:
    with Session(engine) as session:
        word = session.get(Vocabulary, word_id)
        assert word is not None
        word.next_review_date = next_review_date
        session.add(word)
        session.commit()


def submit_rating(client: TestClient, word_id: int, rating: str) -> Response:
    return post_form(client, "/review", f"/review/{word_id}", {"rating": rating})


def test_review_page_redirects_to_login_when_logged_out(client: TestClient) -> None:
    response = client.get("/review")
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_submit_review_when_logged_out_redirects_to_login(client: TestClient) -> None:
    response = post_form(client, "/login", "/review/1", {"rating": "good"})
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_review_page_shows_empty_state_without_words(client: TestClient) -> None:
    register(client, "anna@example.com")
    response = client.get("/review")
    assert response.status_code == 200
    assert "Nothing to review right now." in response.text


def test_new_word_is_shown_for_review(client: TestClient) -> None:
    register(client, "anna@example.com")
    create_word(client, french_word="la fenêtre", english_meaning="the window")
    page = client.get("/review").text
    assert "la fenêtre" in page
    assert "the window" in page
    assert "<details" in page


def test_french_word_comes_before_hidden_meaning(client: TestClient) -> None:
    register(client, "anna@example.com")
    create_word(client, french_word="la fenêtre", english_meaning="the window")
    page = client.get("/review").text
    assert page.index("la fenêtre") < page.index("<details") < page.index("the window")


def test_future_word_is_not_shown(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client, french_word="demain")
    set_next_review_date(word_id, datetime.now(timezone.utc) + timedelta(days=1))
    page = client.get("/review").text
    assert "demain" not in page
    assert "Nothing to review right now." in page


def test_oldest_due_word_is_shown_first(client: TestClient) -> None:
    register(client, "anna@example.com")
    newer_id = create_word(client, french_word="récent")
    older_id = create_word(client, french_word="ancien")
    now = datetime.now(timezone.utc)
    set_next_review_date(newer_id, now - timedelta(days=1))
    set_next_review_date(older_id, now - timedelta(days=5))
    page = client.get("/review").text
    assert "ancien" in page
    assert "récent" not in page


def test_other_users_word_is_never_shown(client: TestClient) -> None:
    register(client, "owner@example.com")
    create_word(client, french_word="le secret")
    logout(client)
    register(client, "intruder@example.com")
    page = client.get("/review").text
    assert "le secret" not in page
    assert "Nothing to review right now." in page


@pytest.mark.parametrize(("rating", "days"), [("again", 1), ("good", 3), ("easy", 7)])
def test_rating_sets_next_review_date(client: TestClient, rating: str, days: int) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    before = datetime.now(timezone.utc)
    response = submit_rating(client, word_id, rating)
    after = datetime.now(timezone.utc)
    assert response.status_code == 303
    assert response.headers["location"] == "/review"
    next_review_date = get_word(word_id).next_review_date
    assert before + timedelta(days=days) <= next_review_date <= after + timedelta(days=days)


def test_rating_does_not_change_other_fields(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client, french_word="le chat", english_meaning="the cat")
    original = get_word(word_id)
    submit_rating(client, word_id, "good")
    reviewed = get_word(word_id)
    assert reviewed.french_word == "le chat"
    assert reviewed.english_meaning == "the cat"
    assert reviewed.created_at == original.created_at
    assert reviewed.user_id == original.user_id


def test_next_due_word_is_shown_after_rating(client: TestClient) -> None:
    register(client, "anna@example.com")
    first_id = create_word(client, french_word="premier")
    second_id = create_word(client, french_word="deuxième")
    now = datetime.now(timezone.utc)
    set_next_review_date(first_id, now - timedelta(days=2))
    set_next_review_date(second_id, now - timedelta(days=1))
    submit_rating(client, first_id, "easy")
    page = client.get("/review").text
    assert "deuxième" in page
    assert "premier" not in page


def test_completed_state_after_last_due_word(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client, french_word="dernier")
    submit_rating(client, word_id, "good")
    page = client.get("/review").text
    assert "dernier" not in page
    assert "Nothing to review right now." in page


@pytest.mark.parametrize("rating", ["", "hard", "AGAIN", "again "])
def test_invalid_rating_returns_400(client: TestClient, rating: str) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    original_date = get_word(word_id).next_review_date
    response = submit_rating(client, word_id, rating)
    assert response.status_code == 400
    assert get_word(word_id).next_review_date == original_date


def test_review_without_csrf_token_returns_403(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    original_date = get_word(word_id).next_review_date
    response = client.post(f"/review/{word_id}", data={"rating": "good"})
    assert response.status_code == 403
    assert get_word(word_id).next_review_date == original_date


def test_review_with_wrong_csrf_token_returns_403(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    original_date = get_word(word_id).next_review_date
    response = client.post(f"/review/{word_id}", data={"rating": "good", "csrf_token": "wrong-token"})
    assert response.status_code == 403
    assert get_word(word_id).next_review_date == original_date


def test_review_with_get_is_not_allowed(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    original_date = get_word(word_id).next_review_date
    assert client.get(f"/review/{word_id}").status_code == 405
    assert get_word(word_id).next_review_date == original_date


def test_review_missing_word_returns_404(client: TestClient) -> None:
    register(client, "anna@example.com")
    assert submit_rating(client, 99999, "good").status_code == 404


def test_user_cannot_review_other_users_word(client: TestClient) -> None:
    register(client, "owner@example.com")
    word_id = create_word(client, french_word="le secret")
    original_date = get_word(word_id).next_review_date
    logout(client)
    register(client, "intruder@example.com")
    response = submit_rating(client, word_id, "easy")
    assert response.status_code == 404
    assert get_word(word_id).next_review_date == original_date


def test_word_that_is_not_due_cannot_be_rated(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    future_date = datetime.now(timezone.utc) + timedelta(days=2)
    set_next_review_date(word_id, future_date)
    response = submit_rating(client, word_id, "easy")
    assert response.status_code == 400
    assert "This word is not due for review yet" in response.text
    assert get_word(word_id).next_review_date == future_date


def test_word_cannot_be_rated_twice_in_a_row(client: TestClient) -> None:
    register(client, "anna@example.com")
    word_id = create_word(client)
    submit_rating(client, word_id, "again")
    date_after_first_rating = get_word(word_id).next_review_date
    response = submit_rating(client, word_id, "easy")
    assert response.status_code == 400
    assert get_word(word_id).next_review_date == date_after_first_rating


def test_other_users_future_word_returns_404_not_400(client: TestClient) -> None:
    register(client, "owner@example.com")
    word_id = create_word(client)
    set_next_review_date(word_id, datetime.now(timezone.utc) + timedelta(days=2))
    logout(client)
    register(client, "intruder@example.com")
    assert submit_rating(client, word_id, "good").status_code == 404
