# FrançaisNote

FrançaisNote is a small web app for learning French. You can keep personal notes, save French words with their English meanings, and review your words with a simple spaced-review schedule (Again / Good / Easy).

It is a server-rendered Python app built with FastAPI, Jinja2 templates and PostgreSQL. There is no JavaScript framework and no client-side JavaScript.

## Main features

- **Accounts**: register, log in and log out with email and password.
- **My Notes**: create, view, edit and delete notes. Notes are shown as pastel cards (newest first) with a short preview and the date.
- **My Vocabulary**: add, view, edit and delete French words with their English meaning.
- **Review**: one due word at a time. The French word is shown first, and the meaning is revealed with a click. Rate it:

  | Button | Next review |
  | ------ | ----------- |
  | Again  | in 1 day    |
  | Good   | in 3 days   |
  | Easy   | in 7 days   |

  New words are due immediately. A word can only be rated when it is due.

- **Private data**: every user only sees and changes their own notes and words.
- **Friendly error pages** for 400, 403, 404, 405 and 500.
- **Responsive layout** for desktop, tablet and mobile.

## Screenshots

| My Notes                                | Note detail                                      |
| --------------------------------------- | ------------------------------------------------ |
| ![My Notes](docs/screenshots/notes.jpg) | ![Note detail](docs/screenshots/note-detail.jpg) |

| My Vocabulary                                     | Review                                 |
| ------------------------------------------------- | -------------------------------------- |
| ![My Vocabulary](docs/screenshots/vocabulary.jpg) | ![Review](docs/screenshots/review.jpg) |

| Log in                                | Mobile                                       |
| ------------------------------------- | -------------------------------------------- |
| ![Log in](docs/screenshots/login.jpg) | ![Mobile](docs/screenshots/mobile-notes.jpg) |

## Technology stack

| Layer          | Choice                                                                           |
| -------------- | -------------------------------------------------------------------------------- |
| Language       | Python 3.14.2                                                                    |
| Web framework  | FastAPI                                                                          |
| Templates      | Jinja2 + HTML + one hand-written CSS file                                        |
| Database       | PostgreSQL                                                                       |
| ORM            | SQLModel                                                                         |
| Authentication | Signed cookie sessions (Starlette `SessionMiddleware`) + Argon2 password hashing |
| Tests          | pytest + FastAPI `TestClient`                                                    |
| Hosting        | Render (app) and Neon (PostgreSQL)                                               |

All dependencies are pinned to exact versions in `requirements.txt`.

## Application architecture

Every page is a Jinja2 template rendered on the server. Forms use normal HTML `POST` requests, and the server redirects after a successful change (Post/Redirect/Get). Because HTML forms only support `GET` and `POST`, edit and delete actions use `POST` routes.

```
app/
├── main.py          # creates the app, session middleware, error pages, startup
├── config.py        # reads environment variables
├── database.py      # database engine and session
├── models.py        # SQLModel tables
├── security.py      # password hashing, current user, CSRF check
├── routes/
│   ├── auth.py      # /, /register, /login, /logout
│   ├── notes.py     # /notes...
│   ├── vocabulary.py  # /vocabulary...
│   └── review.py    # /review...
├── templates/       # base.html layout + one template per page
└── static/
    └── style.css
tests/               # pytest tests
docs/                # design references and screenshots
```

### Routes

| Method     | Path                      | Purpose                                      |
| ---------- | ------------------------- | -------------------------------------------- |
| GET        | `/`                       | Redirect to `/notes` (logged in) or `/login` |
| GET / POST | `/register`               | Register page / submit                       |
| GET / POST | `/login`                  | Login page / submit                          |
| POST       | `/logout`                 | Log out                                      |
| GET        | `/notes`                  | List notes                                   |
| GET / POST | `/notes/new`              | New note form / create                       |
| GET        | `/notes/{id}`             | View note                                    |
| GET / POST | `/notes/{id}/edit`        | Edit form / update                           |
| POST       | `/notes/{id}/delete`      | Delete note                                  |
| GET        | `/vocabulary`             | List words                                   |
| GET / POST | `/vocabulary/new`         | New word form / create                       |
| GET        | `/vocabulary/{id}`        | View word                                    |
| GET / POST | `/vocabulary/{id}/edit`   | Edit form / update                           |
| POST       | `/vocabulary/{id}/delete` | Delete word                                  |
| GET        | `/review`                 | Show the next due word                       |
| POST       | `/review/{id}`            | Submit a rating (`again`, `good` or `easy`)  |

## Database models

All dates are stored as timezone-aware UTC timestamps and shown in UTC.

**User**: `id`, `email` (unique, lowercase, max 255), `password_hash` (Argon2), `created_at`

**Note**: `id`, `user_id` (foreign key → User), `title` (max 200), `content` (max 10,000), `created_at`, `updated_at`

**Vocabulary**: `id`, `user_id` (foreign key → User), `french_word` (max 100), `english_meaning` (max 300), `next_review_date`, `created_at`

Tables are created automatically when the app starts (`SQLModel.metadata.create_all`). This only creates missing tables and never changes or drops existing ones. There is no migration tool.

## Authentication and security

- **Passwords** are hashed with Argon2. Plain passwords are never stored or logged.
- **Sessions** use Starlette's signed cookie sessions. The cookie is signed with `SECRET_KEY` so it cannot be changed, but it is not encrypted, so it only stores the user id and the CSRF token. The cookie is `HttpOnly`, `SameSite=Lax`, lasts 7 days, and is `Secure` (HTTPS only) in production.
- **Session rotation**: the session is cleared and a new CSRF token is created on every login and registration.
- **CSRF protection**: every `POST` form has a hidden CSRF token. The server checks it on every `POST` (including login, register and logout) and returns 403 if it is missing or wrong.
- **Data isolation**: every notes and vocabulary query filters by the logged-in user. Another user's note or word returns 404, so the app does not reveal that it exists.
- **Input validation**: all form fields are trimmed and checked on the server (required fields, maximum lengths, email format, password at least 8 characters). Invalid input shows the form again with an error (HTTP 400). A duplicate email returns HTTP 409.
- **Review rules**: only `again`, `good` and `easy` are accepted, and only for a word that is due. Anything else returns 400 and nothing changes.
- **Safe output**: Jinja2 autoescaping is on, so user content is always shown as text, never as HTML.
- **Error pages** never show exception details or stack traces.
- **Secrets** come only from environment variables.

## Local development setup

Requirements: Python 3.14.2 and PostgreSQL.

1. Create two local PostgreSQL databases, one for development and one only for tests:

   ```bash
   createdb francaisnote
   createdb francaisnote_test
   ```

2. Create a virtual environment and install the dependencies:

   ```bash
   python3.14 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in the values (see [Environment variables](#environment-variables)). Generate a secret key with:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

4. Start the app:

   ```bash
   uvicorn app.main:app --reload
   ```

   Open http://localhost:8000. The tables are created on the first start.

## Environment variables

| Name                | Purpose                                                                          |
| ------------------- | -------------------------------------------------------------------------------- |
| `DATABASE_URL`      | PostgreSQL connection string. It must start with `postgresql+psycopg://`.        |
| `TEST_DATABASE_URL` | A separate database used only by pytest. Never the same as `DATABASE_URL`.       |
| `SECRET_KEY`        | Long random string used to sign session cookies.                                 |
| `ENVIRONMENT`       | `development` or `production`. In `production` the session cookie is HTTPS-only. |

Example `.env` for local development (never commit this file, it is in `.gitignore`):

```
DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/francaisnote
TEST_DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/francaisnote_test
SECRET_KEY=<a long random string>
ENVIRONMENT=development
```

The app stops at startup with an error if `DATABASE_URL` or `SECRET_KEY` is missing.

## Running tests

```bash
python -m pytest
```

Run it from the project root. The tests:

- use only `TEST_DATABASE_URL`, and stop with an error if it is missing or equal to `DATABASE_URL`,
- drop and recreate the tables in the test database before each test (never in the development or production database),
- cover registration, login, logout, CSRF, notes and vocabulary CRUD, validation, user data isolation, review scheduling (+1/+3/+7 days), review of words that are not due, error pages, and table creation on an empty database.

## Deployment

The app is hosted on Render with the PostgreSQL database on Neon.

### 1. Neon (database)

1. Create a Neon project and a database for production.
2. Copy its connection string. Neon gives a string like `postgresql://user:password@host/dbname?sslmode=require`.
3. Change the start from `postgresql://` to `postgresql+psycopg://`. Keep the rest, including `?sslmode=require`.

Use this production database only for the deployed app. Never use your local development or test database in production.

### 2. Render (web service)

1. Push the code to a GitHub repository.
2. In Render, create a **Web Service** from that repository.
3. Use these settings:

   | Setting       | Value                                              |
   | ------------- | -------------------------------------------------- |
   | Runtime       | Python                                             |
   | Build command | `pip install -r requirements.txt`                  |
   | Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

4. Add these environment variables in the Render dashboard:

   | Name           | Value                                                  |
   | -------------- | ------------------------------------------------------ |
   | `DATABASE_URL` | the Neon connection string from step 1                 |
   | `SECRET_KEY`   | a new long random string (do not reuse your local one) |
   | `ENVIRONMENT`  | `production`                                           |

   Do not set `TEST_DATABASE_URL` on Render. Do not set `PYTHON_VERSION` either: Render reads `3.14.2` from the `.python-version` file.

5. Deploy. On the first start the app creates the `user`, `note` and `vocabulary` tables in the empty Neon database.
