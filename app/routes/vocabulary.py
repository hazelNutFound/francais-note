from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_session
from app.models import User, Vocabulary, format_utc_date, utc_now
from app.security import check_csrf, get_csrf_token, get_current_user

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.filters["utc_date"] = format_utc_date

MAX_FRENCH_WORD_LENGTH = 100
MAX_ENGLISH_MEANING_LENGTH = 300


def get_user_word(session: Session, word_id: int, user: User) -> Vocabulary:
    # Filtering by user_id means another user's word looks exactly like a missing word (404).
    statement = select(Vocabulary).where(Vocabulary.id == word_id, Vocabulary.user_id == user.id)
    word = session.exec(statement).first()
    if word is None:
        raise HTTPException(status_code=404, detail="Word not found")
    return word


def validate_word(french_word: str, english_meaning: str) -> str | None:
    if french_word == "":
        return "French word is required."
    if len(french_word) > MAX_FRENCH_WORD_LENGTH:
        return "French word must be at most 100 characters."
    if english_meaning == "":
        return "English meaning is required."
    if len(english_meaning) > MAX_ENGLISH_MEANING_LENGTH:
        return "English meaning must be at most 300 characters."
    return None


def render_word_form(
    request: Request,
    heading: str,
    action: str,
    french_word: str,
    english_meaning: str,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    context = {
        "csrf_token": get_csrf_token(request),
        "heading": heading,
        "action": action,
        "french_word": french_word,
        "english_meaning": english_meaning,
        "error": error,
    }
    return templates.TemplateResponse(request, "vocabulary_form.html", context, status_code=status_code)


@router.get("/vocabulary")
def list_words(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    statement = (
        select(Vocabulary).where(Vocabulary.user_id == user.id).order_by(Vocabulary.created_at.desc())
    )
    words = session.exec(statement).all()
    return templates.TemplateResponse(request, "vocabulary.html", {"words": words})


@router.get("/vocabulary/new")
def new_word_page(request: Request, user: User = Depends(get_current_user)) -> HTMLResponse:
    return render_word_form(request, "New word", "/vocabulary/new", french_word="", english_meaning="")


@router.post("/vocabulary/new", dependencies=[Depends(check_csrf)])
def create_word(
    request: Request,
    french_word: str = Form(""),
    english_meaning: str = Form(""),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    french_word = french_word.strip()
    english_meaning = english_meaning.strip()
    error = validate_word(french_word, english_meaning)
    if error is not None:
        return render_word_form(request, "New word", "/vocabulary/new", french_word, english_meaning, error, 400)

    now = utc_now()
    word = Vocabulary(
        user_id=user.id,
        french_word=french_word,
        english_meaning=english_meaning,
        next_review_date=now,
        created_at=now,
    )
    session.add(word)
    session.commit()
    return RedirectResponse("/vocabulary", status_code=303)


@router.get("/vocabulary/{word_id}")
def view_word(
    request: Request,
    word_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    word = get_user_word(session, word_id, user)
    context = {"word": word, "csrf_token": get_csrf_token(request)}
    return templates.TemplateResponse(request, "vocabulary_detail.html", context)


@router.get("/vocabulary/{word_id}/edit")
def edit_word_page(
    request: Request,
    word_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    word = get_user_word(session, word_id, user)
    action = f"/vocabulary/{word.id}/edit"
    return render_word_form(request, "Edit word", action, word.french_word, word.english_meaning)


@router.post("/vocabulary/{word_id}/edit", dependencies=[Depends(check_csrf)])
def update_word(
    request: Request,
    word_id: int,
    french_word: str = Form(""),
    english_meaning: str = Form(""),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    word = get_user_word(session, word_id, user)
    french_word = french_word.strip()
    english_meaning = english_meaning.strip()
    error = validate_word(french_word, english_meaning)
    if error is not None:
        action = f"/vocabulary/{word.id}/edit"
        return render_word_form(request, "Edit word", action, french_word, english_meaning, error, 400)

    word.french_word = french_word
    word.english_meaning = english_meaning
    session.add(word)
    session.commit()
    return RedirectResponse(f"/vocabulary/{word.id}", status_code=303)


@router.post("/vocabulary/{word_id}/delete", dependencies=[Depends(check_csrf)])
def delete_word(
    word_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    word = get_user_word(session, word_id, user)
    session.delete(word)
    session.commit()
    return RedirectResponse("/vocabulary", status_code=303)
