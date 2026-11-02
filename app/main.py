from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app import models  # noqa: F401  (imported so create_all knows about the tables)
from app.config import ENVIRONMENT, SECRET_KEY
from app.database import create_tables
from app.routes import auth, notes, review, vocabulary

SEVEN_DAYS_IN_SECONDS = 7 * 24 * 60 * 60

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

ERROR_PAGES = {
    400: ("Bad request", "Something in that request was not right. Please go back and try again."),
    403: ("Forbidden", "This form has expired or is not valid. Please go back, reload the page and try again."),
    404: ("Page not found", "We could not find the page you were looking for."),
    405: ("Not allowed", "That action is not allowed on this page."),
    500: ("Something went wrong", "An unexpected error happened. Please try again later."),
}


def render_error_page(request: Request, status_code: int, message: str | None = None) -> HTMLResponse:
    title, default_message = ERROR_PAGES.get(status_code, ERROR_PAGES[500])
    context = {"status_code": status_code, "title": title, "message": message or default_message}
    return templates.TemplateResponse(request, "error.html", context, status_code=status_code)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    create_tables()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=SEVEN_DAYS_IN_SECONDS,
    same_site="lax",
    https_only=ENVIRONMENT == "production",
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(auth.router)
app.include_router(notes.router)
app.include_router(vocabulary.router)
app.include_router(review.router)


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException) -> Response:
    if exc.status_code < 400:
        return await http_exception_handler(request, exc)
    if exc.status_code == 400:
        return render_error_page(request, 400, message=exc.detail)
    return render_error_page(request, exc.status_code)


@app.exception_handler(RequestValidationError)
async def handle_invalid_path(request: Request, exc: RequestValidationError) -> HTMLResponse:
    return render_error_page(request, 404)


# The real error is still written to the server log; the visitor only sees a generic page.
@app.exception_handler(Exception)
async def handle_server_error(request: Request, exc: Exception) -> HTMLResponse:
    return render_error_page(request, 500)
