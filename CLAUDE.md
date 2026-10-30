# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

SNEAKRS. — a sneaker marketplace with a FastAPI backend and a React frontend, developed as two independent, unconnected projects in one repo (no shared config, no Docker/orchestration tying them together):

- `Backend/` — FastAPI + SQLAlchemy 2.0 (async, `aiosqlite` driver), managed with `uv`, Python >=3.14.
- `Frontend/` — React 19 + Vite, React Router 7, plain JS/JSX (no TypeScript), managed with `npm`.

The project is early/in-progress: the backend API is largely implemented, but most frontend pages are stubs not yet wired to it (see Known issues below).

## Commands

### Backend (run from `Backend/` — `config.py` loads `.env` (`SECRET_KEY` etc.) relative to the current directory; the SQLite path itself is anchored to `Backend/`)

- Install deps: `uv sync`
- Run dev server: `uv run fastapi dev main.py` (or `uv run uvicorn main:app --reload`) — serves on port 8000
- Seed the product catalog from `sneakers.json`: `uv run python harvest_scripts/seed.py`
- Run tests: `uv run pytest` (in `tests/`; the app runs on an async engine over a temp-file SQLite DB, fixtures use a sync engine on the same file). No ruff/black/mypy config exists yet.

### Frontend (run from `Frontend/`)

- Install deps: `npm install`
- Dev server: `npm run dev` (Vite, port 5173)
- Build: `npm run build`
- Lint: `npm run lint` (ESLint flat config)
- No test framework is configured.

## Architecture

### Backend structure

- `main.py` — app entrypoint. `GET /` returns the home feed (the first page of products, by calling the products handler). Creates tables in the `lifespan` startup via `await conn.run_sync(Base.metadata.create_all)` and disposes the engine on shutdown (schema is created directly from the models — **there is no Alembic/migration tool**; changing a model requires dropping/recreating the SQLite file). Configures CORS for `http://localhost:5173` and `http://localhost:3000`. Mounts the routers. Exception handlers are async and delegate to FastAPI's `http_exception_handler` / `request_validation_exception_handler`.
- `database.py` — async engine (`sqlite+aiosqlite:///` + `my_database.db` anchored to `Backend/`), `AsyncSessionLocal` (`expire_on_commit=False`), and the async `get_db()` dependency generator.
- `models.py` — SQLAlchemy 2.0 ORM models (`Mapped`/`mapped_column` style): `User`, `Product`, `CartItem`, `Order`, `OrderItem`, `PasswordResetToken`.
- `schemas.py` — Pydantic v2 request/response models, using `ConfigDict(from_attributes=True)` to serialize ORM objects directly.
- `auth.py` — password hashing (`pwdlib`, argon2), JWT creation/verification (`pyjwt`, settings from `config.py`/`.env`), and the `CurrentUser` / `AdminUser` dependencies. Soft-deleted users are rejected even with a valid token.
- `routers/` — one `APIRouter()` per resource, with the URL prefix and tag applied centrally in `main.py`, not in the router file:
  - `users.py` → `/api/users`: register, `POST /token` login (OAuth2 form, `username` = email), `GET /me`, `PATCH /me/password` (`{current_password, new_password}`, 400 if the current password is wrong), and get/patch/delete by id. Patch and delete require the path id to match the token's user. Patch can't change the password (it's not in `UserUpdate`), and changing the email requires `current_password`. Every user has a `username` (required at register, 1-50 of letters/digits/`_`/`-` via `schemas.USERNAME_PATTERN` since it ends up in frontend urls, unique ignoring case but stored as typed, changeable through patch without `current_password`); login is still by email. Delete is a hard delete for users with no orders, otherwise a soft delete that anonymizes the row (username becomes `[deleted-<id>]`, which the pattern can never match) so order history is kept; either way the profile picture file is removed. `PATCH`/`DELETE /{user_id}/picture` upload (multipart field `file`, max `settings.max_upload_size_bytes`) or remove the profile picture. `image_file` is deliberately not in `UserUpdate`, so a user can't point at another user's file and get it deleted. Password reset: `POST /forgot-password` always returns the same 202 (no account enumeration), stores only a sha256 of the token, and emails the raw token as a `BackgroundTasks` job; `POST /reset-password` takes `{token, new_password}`. Tokens are single use, a new request replaces older ones, and changing email/password or deleting the account removes pending ones.
  - `products.py` → `/api/products`: paginated list and get by id (public).
  - `cart.py` → `/api/cart`: the current user's cart (paginated list, add, patch quantity, delete one, clear).
  - `orders.py` → `/api/orders`: checkout (turns the cart into an order with fixed prices and empties the cart), paginated list (newest first), and get by id.
  - `admins.py` → `/api/admin`: the router-level `get_current_admin` dependency guards every route. Lists users (including soft-deleted) and orders, and changes order status along the transitions in `ALLOWED_TRANSITIONS`.
- Pagination: list endpoints (products, cart, orders, admin users/orders) take `?skip=` and `?limit=` (default page sizes and the max limit live in `config.py`) and return `{<items key>, total, skip, limit, has_more}` (subclasses of `schemas.PaginatedResponse`). Each list query needs an `order_by`, and its count query must use the same filters.
- `image_utils.py` — sync Pillow helpers: `process_profile_image` (exif-rotate, 300x300 crop, save as a uuid-named JPEG in `media/profile_pics/`) and `delete_profile_image`. Processing is CPU-bound, so routes call it through `run_in_threadpool`. `main.py` serves uploads at `/media` and the default picture at `/static/profile_pics/default.jpg`; `User.image_path` returns whichever applies.
- `email_utils.py` — async SMTP sending (`aiosmtplib`, `MAIL_*` settings from `.env`; dev uses a Mailtrap sandbox) and the password reset email, whose HTML body is the Jinja template `templates/email/password_reset.html` (email only, the forgot/reset pages belong in the React app). Reset links point at `<FRONTEND_URL>/reset-password?token=...`, so `FRONTEND_URL` is the React dev server. Tests never send mail: the autouse `outbox` fixture in `conftest.py` replaces `send_email` and records each message.
- `harvest_scripts/` — standalone tooling, not part of the API. Each script resolves paths from `Backend/`, so it runs from any cwd:
  - `harvest.py` — async `httpx` script for the pckt.sh cached StockX catalog. It reads `API_KEY`/`BASE_URL` from `Backend/.env`, which `config.py` shares through `extra="ignore"`. Phase 1 searches each of `SEARCH_QUERIES` one page at a time, round-robin, keeping priced sneakers keyed by product id. Phase 2 fetches each product's details for gender and description. It is throttled to the free plan's 1 req/s, retries on 429, stops on 401/402/403, and is capped by `MAX_REQUESTS` (0.4 credits each). It writes `sneakers.json` only if something was harvested.
  - `seed.py` — loads `sneakers.json` into the `products` table, only when the table is empty. Price comes from `lowest_ask`, falling back to `avg_price`. Missing gender defaults to `"unisex"` and missing description to `""`.
  - `make_admin.py` (`uv run python harvest_scripts/make_admin.py <email> [--revoke]`, the only way to grant admin, there's deliberately no endpoint for it).

**Conventions to follow when adding endpoints:**
- Handlers and dependencies are `async def`; inject the DB session with `Annotated[AsyncSession, Depends(get_db)]` and `await` `execute`/`commit`/`refresh`/`flush`/`delete` (`db.add` is not awaited).
- Add new resources as a new file under `routers/`, with the prefix/tag wired up in `main.py`.
- Async sessions can't lazy load: accessing an unloaded relationship raises `MissingGreenlet`. Eager load what the response schema needs with `selectinload(...)` in the query, or `await db.refresh(obj, attribute_names=[...])` after a commit.

### Frontend structure

- `src/main.jsx` mounts `<App />` inside `<BrowserRouter>`. `src/App.jsx` defines routes: `/` (Home), `/:username/cart` (Cart), `/login`, `/signup`.
- `src/pages/` — one component per route. Only `Home.jsx` currently calls the backend, via a hardcoded `fetch("http://localhost:8000/api/products")` (no env var or Vite proxy), reading the first page from `data.products`. `Login.jsx`, `Cart.jsx`, and `Signup.jsx` are stubs not yet wired to any API.
- `src/contexts/SearchContext.jsx` — search state persisted to `localStorage`; consumed by `NavBar` via `useSearchContext()`.
- `src/components/` — shared UI (`NavBar`, `ItemCard`).
- Plain CSS per page/component under `src/css/` — no CSS-in-JS or Tailwind.

### Frontend/backend integration

- Backend on port 8000, frontend dev server on Vite's default port 5173; CORS in `Backend/main.py` allows exactly these two origins.
- There's no shared API client or base-URL config — API calls hardcode `http://localhost:8000`.
- Auth is implemented on the backend only: clients get a bearer token from `POST /api/users/token` and send it as `Authorization: Bearer <token>`. The frontend doesn't use it yet: `Login.jsx`'s submit handler only logs to the console, and `Signup.jsx`/`Cart.jsx` make no API calls.

## Known issues (be aware of before extending nearby code)

- `Frontend/src/contexts/SearchContext.jsx`'s `SearchProvider` is never mounted in `main.jsx`/`App.jsx`, but `NavBar` calls `useSearchContext()` — this throws at runtime once the nav bar renders unless a provider is added higher in the tree.
- `hash_password`/`verify_password` in `Backend/auth.py` are CPU-bound and called directly from async routes, so each hash briefly blocks the event loop. Fine at this scale; wrap them in `run_in_threadpool` if it ever matters.
