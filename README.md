# ВидеоРентген (VideoRentgen)

Self-hostable platform for **short-form video analysis and content production**.
Paste an Instagram Reel / TikTok / YouTube Short URL and the app downloads it,
transcribes the audio, analyzes the visuals and structure with AI, and helps you
turn the insight into your own scripts, hooks and a production pipeline.

> **Deploying for the first time and not a programmer?**
> You don't need to read any of this. Open the project in **Claude Code** and paste
> the prompt in [Deploy with Claude Code](#deploy-with-claude-code) — it will walk
> you through every step, one key at a time, in your own language.

---

## What it does

- **Reel/Short analysis** — download → Whisper transcription → scene detection →
  vision analysis → structured breakdown (hook, retention, structure, etc.).
- **Trend watching** — track creators/profiles and surface their breakout videos.
- **Script & strategy generation** — turn an analysis into your own hooks, scripts
  and an editor brief (Claude / GPT).
- **Production pipeline** — shooting queue, teleprompter, multi-language scripts.
- **Accounts, tiers & billing** — anonymous trial, registered/free/paid tiers,
  referral bonuses, and pluggable payment providers.

## Architecture

One repository, three runtime services that share the same code and environment,
plus two managed datastores:

```
                ┌──────────── PostgreSQL ───────────┐
                │                                    │
  Browser ──▶  web (FastAPI + built React)  ─────────┤
                │      │                             │
                │      ├──▶ Redis (arq queue) ──▶ worker  (video download,
                │      │                            transcription, AI analysis)
                │      └──────────────────────▶ scheduler (billing, watchdog,
                │                                          trend checks, alerts)
                └────────────────────────────────────┘
```

- **web** — `Dockerfile` → serves the API and the compiled frontend, runs DB
  migrations on startup, registers webhooks. Health check: `GET /health`.
- **worker** — `Dockerfile.worker` → processes the heavy jobs (scale with replicas).
- **scheduler** — `Dockerfile.scheduler` → background loops (billing, retries, trends).

**Stack:** Python 3.13 · FastAPI · SQLAlchemy (async) · arq · PostgreSQL · Redis ·
React 19 · TypeScript · Vite · Tailwind. AI via OpenRouter / OpenAI / Anthropic /
Groq-Whisper. Scraping via Apify. Payments via YooKassa / Stripe / CloudPayments.

## Deploy with Claude Code

The easiest path. Install [Claude Code](https://www.claude.com/product/claude-code),
open this project folder, and paste this prompt:

```
You are my deployment assistant for this ВидеоРентген (VideoRentgen) project. I am not a programmer.
Guide me step by step to deploy it to production on Railway, in the language I write to you.

Rules:
- First read docs/SETUP_WITH_CLAUDE_CODE.md, docs/DEPLOY_RAILWAY.md and docs/GETTING_KEYS.md, then follow them.
- Do ONE step at a time and wait for me to confirm before the next.
- Whenever you need an API key, tell me exactly which website to open, where to click
  to get it, and what it looks like — then ask me to paste it. Never invent values.
- After I set environment variables, run `python scripts/check_env.py` with me to verify.
- Assume I know no commands: give me exact copy-paste commands and say where to run them.

Begin with a short overview of what we'll do and the rough monthly cost, then start step 1.
```

That's it — Claude Code reads the guides in this repo and drives the whole deployment.

## Manual deploy

Prefer to do it yourself? Follow **[docs/DEPLOY_RAILWAY.md](docs/DEPLOY_RAILWAY.md)**
(step-by-step Railway guide) and **[docs/GETTING_KEYS.md](docs/GETTING_KEYS.md)**
(where to obtain every key, and which are required vs optional).

## Run locally

```bash
cp .env.example .env          # then fill JWT_SECRET + your keys (see GETTING_KEYS.md)
python scripts/check_env.py   # confirm what's configured
docker compose up --build     # web + worker + Postgres + Redis
```

The app comes up at <http://localhost:8000>. Generate a `JWT_SECRET` with
`openssl rand -hex 32`. The minimum to boot is `JWT_SECRET`, `DATABASE_URL` and
`REDIS_URL`; everything else is optional and unlocks features as you add keys.

## Configuration

All configuration is via environment variables — see **[.env.example](.env.example)**
for the full, commented list, and run `python scripts/check_env.py` to see what's set
and which features are on. The single source of truth for defaults is
[`backend/app/config.py`](backend/app/config.py).

## Project structure

```
backend/app/
  api/        FastAPI routers          services/   business logic
  models/     SQLAlchemy models        workers/    arq task handlers
  schemas/    Pydantic schemas         scheduler/  background loops
  config.py   settings + tiers/pricing  alembic/   DB migrations
frontend/src/
  components/  api/  hooks/  i18n/  types/  region.ts  (brand/legal config)
docs/         deployment & key-setup guides
scripts/      check_env.py self-check
```

## Before you go live

- **Rebrand & legal.** Edit `frontend/src/region.ts` to set your own brand name,
  legal entity, support email and Telegram links. Do **not** ship someone else's
  company details. Review the terms/privacy pages under `frontend/src`.
- **Your own keys.** You provide all API keys and payment accounts. Costs (AI, Apify,
  hosting) are billed to you by those providers.
- **Respect platform terms.** Scraping and downloading from Instagram/TikTok/YouTube
  is subject to their Terms of Service and your local law. You are responsible for
  how you use it.

## License

[MIT](LICENSE). Provided as-is, without warranty.
