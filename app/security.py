import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app.database import get_session
from app.models import User

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerificationError:
        return False


def get_csrf_token(request: Request) -> str:
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    return request.session["csrf_token"]


async def check_csrf(request: Request) -> None:
    form = await request.form()
    sent_token = str(form.get("csrf_token", ""))
    expected_token = request.session.get("csrf_token", "")
    # compare_digest takes the same time for any input, so the token cannot be guessed by timing.
    if not expected_token or not secrets.compare_digest(sent_token.encode(), expected_token.encode()):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def log_in(request: Request, user_id: int) -> None:
    request.session.clear()
    request.session["user_id"] = user_id
    request.session["csrf_token"] = secrets.token_urlsafe(32)


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})

    user = session.get(User, user_id)
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user
