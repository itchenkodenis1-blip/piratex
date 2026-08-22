# ВидеоРентген (VideoRentgen) — guide for Claude Code

This file tells Claude Code how to help with this project. There are two common
audiences: people **deploying** the app (often non-programmers) and people **developing**
it. Detect which one you're helping and act accordingly.

## If the user is deploying (default assumption for a fresh clone)

Act as a **step-by-step deployment co-pilot**. The user may not be a programmer.

- Read `docs/SETUP_WITH_CLAUDE_CODE.md`, `docs/DEPLOY_RAILWAY.md` and
  `docs/GETTING_KEYS.md`, then follow them. Railway is the supported target.
- Work **one step at a time**; wait for confirmation before continuing.
- When a credential is needed, name the exact website, where to click to get it, and
  what the value looks like — then ask the user to paste it. **Never invent keys/values.**
- Speak in the user's language. Give exact, copy-pasteable commands and say where to run them.
- After env changes, run `python scripts/check_env.py` together to verify.
- Treat keys as secrets: they go in `.env` (git-ignored) or the host's variable settings —
  never into commits, logs, screenshots or chat that will be shared.
- Before go-live, help the user edit `frontend/src/region.ts` to set **their own** brand,
  legal entity, support email and Telegram links (placeholders ship by default).

The minimum to boot is `JWT_SECRET`, `DATABASE_URL`, `REDIS_URL`. Every integration
(LLM, scraping, Telegram, OAuth, email, S3, payments) is optional and degrades
gracefully when its key is absent — so help the user start small and add features later.

## If the user is developing

### Stack
- **Backend:** Python 3.13, FastAPI, SQLAlchemy (async), arq, PostgreSQL, Redis
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS
- **AI:** OpenRouter / OpenAI (chat+vision), Anthropic (Claude), Groq (Whisper)
- **Scraping:** Apify · **Payments:** YooKassa / Stripe / CloudPayments

### Layout
```
backend/app/  api/ models/ schemas/ services/ workers/ scheduler/ config.py  alembic/
frontend/src/ components/ api/client.ts hooks/ i18n/ types/ region.ts
docs/         deploy + key-setup guides       scripts/ check_env.py
```

### Commands
```bash
# Frontend
cd frontend && npm install && npm run dev   # dev server
cd frontend && npx tsc --noEmit             # type check
cd frontend && npm run lint                 # eslint

# Backend
cd backend && uvicorn app.main:app --port 8001   # API
cd backend && pytest --tb=short -q               # tests
cd backend && python run_worker.py               # arq worker
cd backend && python run_scheduler.py            # background loops

# Whole stack locally
docker compose up --build
```

### Conventions
- Config & defaults live in `backend/app/config.py` (tier limits, pricing, all settings).
  Read it before changing prices/limits.
- DB schema changes: add an Alembic migration in `backend/alembic/versions/`. The web
  service runs `alembic upgrade head` plus idempotent column checks on startup (`start.sh`).
- The frontend proxies `/api` to the backend — don't hardcode backend URLs.
- Match the style of surrounding code; keep changes minimal and well-scoped.
