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

- `main.py` — app entrypoint. Creates tables in the `lifespan` startup via `await conn.run_sync(Base.metadata.create_all)` and disposes the engine on shutdown (schema is created directly from the models — **there is no Alembic/migration tool**; changing a model requires dropping/recreating the SQLite file). Configures CORS for `http://localhost:5173` and `http://localhost:3000`. Mounts the routers. Exception handlers are async and delegate to FastAPI's `http_exception_handler` / `request_validation_exception_handler`.
- `database.py` — async engine (`sqlite+aiosqlite:///` + `my_database.db` anchored to `Backend/`), `AsyncSessionLocal` (`expire_on_commit=False`), and the async `get_db()` dependency generator.
- `models.py` — SQLAlchemy 2.0 ORM models (`Mapped`/`mapped_column` style): `User`, `Product`, `CartItem`, `Order`, `OrderItem`.
- `schemas.py` — Pydantic v2 request/response models, using `ConfigDict(from_attributes=True)` to serialize ORM objects directly.
- `auth.py` — password hashing (`pwdlib`, argon2), JWT creation/verification (`pyjwt`, settings from `config.py`/`.env`), and the `CurrentUser` / `AdminUser` dependencies. Soft-deleted users are rejected even with a valid token.
- `routers/` — one `APIRouter()` per resource, with the URL prefix and tag applied centrally in `main.py`, not in the router file:
  - `users.py` → `/api/users`: register, `POST /token` login (OAuth2 form, `username` = email), `GET /me`, and get/patch/delete by id. Patch and delete require the path id to match the token's user. Changing email or password requires `current_password`. Delete is a hard delete for users with no orders, otherwise a soft delete that anonymizes the row so order history is kept.
  - `products.py` → `/api/products`: list and get by id (public).
  - `cart.py` → `/api/cart`: the current user's cart (list, add, patch quantity, delete one, clear).
  - `orders.py` → `/api/orders`: checkout (turns the cart into an order with fixed prices and empties the cart), list, and get by id.
  - `admins.py` → `/api/admin`: the router-level `get_current_admin` dependency guards every route. Lists users (including soft-deleted) and orders, and changes order status along the transitions in `ALLOWED_TRANSITIONS`.
- `harvest_scripts/` — standalone tooling, not part of the API: `harvest.py` (async `httpx` script pulling sneaker data from a KicksDB-like API using `API_KEY`/`BASE_URL` from a `.env` file), `seed.py` (loads `sneakers.json` into the `products` table), and `make_admin.py` (`uv run python harvest_scripts/make_admin.py <email> [--revoke]`, the only way to grant admin, there's deliberately no endpoint for it).

**Conventions to follow when adding endpoints:**
- Handlers and dependencies are `async def`; inject the DB session with `Annotated[AsyncSession, Depends(get_db)]` and `await` `execute`/`commit`/`refresh`/`flush`/`delete` (`db.add` is not awaited).
- Add new resources as a new file under `routers/`, with the prefix/tag wired up in `main.py`.
- Async sessions can't lazy load: accessing an unloaded relationship raises `MissingGreenlet`. Eager load what the response schema needs with `selectinload(...)` in the query, or `await db.refresh(obj, attribute_names=[...])` after a commit.

### Frontend structure

- `src/main.jsx` mounts `<App />` inside `<BrowserRouter>`. `src/App.jsx` defines routes: `/` (Home), `/:username/cart` (Cart), `/login`, `/signup`.
- `src/pages/` — one component per route. Only `Home.jsx` currently calls the backend, via a hardcoded `fetch("http://localhost:8000/api/products")` (no env var or Vite proxy). `Login.jsx`, `Cart.jsx`, and `Signup.jsx` are stubs not yet wired to any API.
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
