from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_session
from app.models import User, Vocabulary, utc_now
from app.routes.vocabulary import get_user_word
from app.security import check_csrf, get_csrf_token, get_current_user

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

DAYS_UNTIL_NEXT_REVIEW = {"again": 1, "good": 3, "easy": 7}


@router.get("/review")
def review_page(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    statement = (
        select(Vocabulary)
        .where(Vocabulary.user_id == user.id, Vocabulary.next_review_date <= utc_now())
        .order_by(Vocabulary.next_review_date)
    )
    word = session.exec(statement).first()
    context = {"word": word, "csrf_token": get_csrf_token(request)}
    return templates.TemplateResponse(request, "review.html", context)


@router.post("/review/{word_id}", dependencies=[Depends(check_csrf)])
def submit_review(
    word_id: int,
    rating: str = Form(""),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    word = get_user_word(session, word_id, user)
    if rating not in DAYS_UNTIL_NEXT_REVIEW:
        raise HTTPException(status_code=400, detail="Rating must be again, good or easy")

    now = utc_now()
    if word.next_review_date > now:
        raise HTTPException(status_code=400, detail="This word is not due for review yet")

    word.next_review_date = now + timedelta(days=DAYS_UNTIL_NEXT_REVIEW[rating])
    session.add(word)
    session.commit()
    return RedirectResponse("/review", status_code=303)
