import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import engine
from app.models import User
from conftest import TEST_PASSWORD, get_csrf_token, login, logout, register


def get_user(email: str) -> User | None:
    with Session(engine) as session:
        return session.exec(select(User).where(User.email == email)).first()


def test_root_redirects_to_login_when_logged_out(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_and_register_pages_load(client: TestClient) -> None:
    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200


def test_register_creates_user_and_logs_in(client: TestClient) -> None:
    response = register(client, "anna@example.com")
    assert response.status_code == 303
    assert response.headers["location"] == "/notes"
    assert get_user("anna@example.com") is not None
    assert client.get("/").headers["location"] == "/notes"


def test_register_stores_argon2_hash_not_password(client: TestClient) -> None:
    register(client, "anna@example.com")
    user = get_user("anna@example.com")
    assert user is not None
    assert user.password_hash != TEST_PASSWORD
    assert user.password_hash.startswith("$argon2")


def test_register_stores_email_trimmed_and_lowercase(client: TestClient) -> None:
    register(client, "  Anna@Example.COM  ")
    assert get_user("anna@example.com") is not None


def test_register_duplicate_email_returns_409(client: TestClient) -> None:
    register(client, "anna@example.com")
    logout(client)
    response = register(client, "ANNA@example.com")
    assert response.status_code == 409
    assert "An account with this email already exists." in response.text


def test_register_short_password_returns_400(client: TestClient) -> None:
    response = register(client, "anna@example.com", password="short")
    assert response.status_code == 400
    assert "Password must be at least 8 characters." in response.text
    assert get_user("anna@example.com") is None


@pytest.mark.parametrize(
    "email",
    ["", "no-at-sign", "two@@example.com", "@example.com", "anna@", "an na@example.com", "a" * 250 + "@x.com"],
)
def test_register_invalid_email_returns_400(client: TestClient, email: str) -> None:
    response = register(client, email)
    assert response.status_code == 400
    assert "Please enter a valid email address." in response.text


def test_register_error_keeps_email_but_not_password(client: TestClient) -> None:
    response = register(client, "anna@example.com", password="secret7")
    assert 'value="anna@example.com"' in response.text
    assert "secret7" not in response.text


def test_login_with_correct_password(client: TestClient) -> None:
    register(client, "anna@example.com")
    logout(client)
    response = login(client, "anna@example.com")
    assert response.status_code == 303
    assert response.headers["location"] == "/notes"
    assert client.get("/").headers["location"] == "/notes"


def test_login_is_case_insensitive_for_email(client: TestClient) -> None:
    register(client, "anna@example.com")
    logout(client)
    response = login(client, " ANNA@example.com ")
    assert response.status_code == 303


def test_login_with_wrong_password_shows_generic_error(client: TestClient) -> None:
    register(client, "anna@example.com")
    logout(client)
    response = login(client, "anna@example.com", password="wrong-password")
    assert response.status_code == 400
    assert "Invalid email or password" in response.text
    assert client.get("/").headers["location"] == "/login"


def test_login_with_unknown_email_shows_same_generic_error(client: TestClient) -> None:
    response = login(client, "nobody@example.com")
    assert response.status_code == 400
    assert "Invalid email or password" in response.text


def test_logout_clears_session(client: TestClient) -> None:
    register(client, "anna@example.com")
    response = logout(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert client.get("/").headers["location"] == "/login"


def test_logout_with_get_is_not_allowed(client: TestClient) -> None:
    assert client.get("/logout").status_code == 405


def test_register_without_csrf_token_returns_403(client: TestClient) -> None:
    client.get("/register")
    form = {"email": "anna@example.com", "password": TEST_PASSWORD}
    response = client.post("/register", data=form)
    assert response.status_code == 403
    assert get_user("anna@example.com") is None


def test_login_with_wrong_csrf_token_returns_403(client: TestClient) -> None:
    register(client, "anna@example.com")
    logout(client)
    client.get("/login")
    form = {"email": "anna@example.com", "password": TEST_PASSWORD, "csrf_token": "wrong-token"}
    response = client.post("/login", data=form)
    assert response.status_code == 403


def test_logout_without_csrf_token_returns_403(client: TestClient) -> None:
    register(client, "anna@example.com")
    response = client.post("/logout")
    assert response.status_code == 403
    assert client.get("/").headers["location"] == "/notes"


def test_post_without_session_cookie_returns_403(client: TestClient) -> None:
    form = {"email": "anna@example.com", "password": TEST_PASSWORD, "csrf_token": "any-token"}
    response = client.post("/login", data=form)
    assert response.status_code == 403


def test_login_rotates_csrf_token(client: TestClient) -> None:
    register(client, "anna@example.com")
    logout(client)
    old_token = get_csrf_token(client, "/login")
    login(client, "anna@example.com")
    new_token = get_csrf_token(client, "/login")
    assert new_token != old_token
    assert client.post("/logout", data={"csrf_token": old_token}).status_code == 403


def test_session_cookie_is_httponly_and_samesite_lax(client: TestClient) -> None:
    response = client.get("/login")
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header
    assert "max-age=604800" in cookie_header
