from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_session
from app.models import Note, User, format_utc_date, utc_now
from app.security import check_csrf, get_csrf_token, get_current_user

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.filters["utc_date"] = format_utc_date

MAX_TITLE_LENGTH = 200
MAX_CONTENT_LENGTH = 10000


def get_user_note(session: Session, note_id: int, user: User) -> Note:
    # Filtering by user_id means another user's note looks exactly like a missing note (404).
    statement = select(Note).where(Note.id == note_id, Note.user_id == user.id)
    note = session.exec(statement).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


def validate_note(title: str, content: str) -> str | None:
    if title == "":
        return "Title is required."
    if len(title) > MAX_TITLE_LENGTH:
        return "Title must be at most 200 characters."
    if content == "":
        return "Content is required."
    if len(content) > MAX_CONTENT_LENGTH:
        return "Content must be at most 10,000 characters."
    return None


def render_note_form(
    request: Request,
    heading: str,
    action: str,
    title: str,
    content: str,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    context = {
        "csrf_token": get_csrf_token(request),
        "heading": heading,
        "action": action,
        "title": title,
        "content": content,
        "error": error,
    }
    return templates.TemplateResponse(request, "note_form.html", context, status_code=status_code)


@router.get("/notes")
def list_notes(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    statement = select(Note).where(Note.user_id == user.id).order_by(Note.created_at.desc())
    notes = session.exec(statement).all()
    return templates.TemplateResponse(request, "notes.html", {"notes": notes})


@router.get("/notes/new")
def new_note_page(request: Request, user: User = Depends(get_current_user)) -> HTMLResponse:
    return render_note_form(request, "New note", "/notes/new", title="", content="")


@router.post("/notes/new", dependencies=[Depends(check_csrf)])
def create_note(
    request: Request,
    title: str = Form(""),
    content: str = Form(""),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    title = title.strip()
    content = content.strip()
    error = validate_note(title, content)
    if error is not None:
        return render_note_form(request, "New note", "/notes/new", title, content, error, 400)

    now = utc_now()
    note = Note(user_id=user.id, title=title, content=content, created_at=now, updated_at=now)
    session.add(note)
    session.commit()
    return RedirectResponse("/notes", status_code=303)


@router.get("/notes/{note_id}")
def view_note(
    request: Request,
    note_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    note = get_user_note(session, note_id, user)
    context = {"note": note, "csrf_token": get_csrf_token(request)}
    return templates.TemplateResponse(request, "note_detail.html", context)


@router.get("/notes/{note_id}/edit")
def edit_note_page(
    request: Request,
    note_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    note = get_user_note(session, note_id, user)
    return render_note_form(request, "Edit note", f"/notes/{note.id}/edit", note.title, note.content)


@router.post("/notes/{note_id}/edit", dependencies=[Depends(check_csrf)])
def update_note(
    request: Request,
    note_id: int,
    title: str = Form(""),
    content: str = Form(""),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    note = get_user_note(session, note_id, user)
    title = title.strip()
    content = content.strip()
    error = validate_note(title, content)
    if error is not None:
        return render_note_form(request, "Edit note", f"/notes/{note.id}/edit", title, content, error, 400)

    note.title = title
    note.content = content
    note.updated_at = utc_now()
    session.add(note)
    session.commit()
    return RedirectResponse(f"/notes/{note.id}", status_code=303)


@router.post("/notes/{note_id}/delete", dependencies=[Depends(check_csrf)])
def delete_note(
    note_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    note = get_user_note(session, note_id, user)
    session.delete(note)
    session.commit()
    return RedirectResponse("/notes", status_code=303)
