from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_session
from app.models import User
from app.security import check_csrf, get_csrf_token, hash_password, log_in, verify_password

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

MIN_PASSWORD_LENGTH = 8
MAX_EMAIL_LENGTH = 255


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    if len(email) > MAX_EMAIL_LENGTH:
        return False
    if email.count("@") != 1:
        return False
    if any(character.isspace() for character in email):
        return False
    local_part, domain = email.split("@")
    return local_part != "" and domain != ""


def render_form(
    request: Request, template_name: str, email: str, error: str | None, status_code: int = 200
) -> HTMLResponse:
    context = {"csrf_token": get_csrf_token(request), "email": email, "error": error}
    return templates.TemplateResponse(request, template_name, context, status_code=status_code)


@router.get("/")
def home(request: Request) -> RedirectResponse:
    if "user_id" in request.session:
        return RedirectResponse("/notes", status_code=303)
    return RedirectResponse("/login", status_code=303)


@router.get("/register")
def register_page(request: Request) -> HTMLResponse:
    return render_form(request, "register.html", email="", error=None)


@router.post("/register", dependencies=[Depends(check_csrf)])
def register(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    session: Session = Depends(get_session),
) -> Response:
    email = normalize_email(email)
    if not is_valid_email(email):
        return render_form(request, "register.html", email, "Please enter a valid email address.", 400)
    if len(password) < MIN_PASSWORD_LENGTH:
        return render_form(request, "register.html", email, "Password must be at least 8 characters.", 400)

    existing_user = session.exec(select(User).where(User.email == email)).first()
    if existing_user is not None:
        return render_form(request, "register.html", email, "An account with this email already exists.", 409)

    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)

    log_in(request, user.id)
    return RedirectResponse("/notes", status_code=303)


@router.get("/login")
def login_page(request: Request) -> HTMLResponse:
    return render_form(request, "login.html", email="", error=None)


@router.post("/login", dependencies=[Depends(check_csrf)])
def login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    session: Session = Depends(get_session),
) -> Response:
    email = normalize_email(email)
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None or not verify_password(user.password_hash, password):
        return render_form(request, "login.html", email, "Invalid email or password", 400)

    log_in(request, user.id)
    return RedirectResponse("/notes", status_code=303)


@router.post("/logout", dependencies=[Depends(check_csrf)])
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
