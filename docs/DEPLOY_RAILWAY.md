# Deploy to Railway — step by step

This guide deploys Piratex.ai to [Railway](https://railway.app): three services
(**web**, **worker**, **scheduler**) from this one repository, plus managed
**PostgreSQL** and **Redis**. Database migrations run automatically on startup —
there is no manual migration step.

If you're following along with Claude Code, it will do most of the clicking-equivalent
work and ask you only for the keys. If you're doing it by hand, just go top to bottom.

**Time:** ~30 minutes. **You'll need:** a GitHub account, a Railway account, and the
keys from [GETTING_KEYS.md](GETTING_KEYS.md) (at minimum one LLM key + an Apify token).

---

## Step 1 — Put the code on GitHub

Railway deploys from a GitHub repo.

- If you forked/cloned this project, push it to a repository on your own GitHub account.
- Make sure your `.env` is **not** committed (it's git-ignored by default — never add it).

## Step 2 — Create a Railway project

1. Sign in at <https://railway.app> (with GitHub is easiest).
2. **New Project → Deploy from GitHub repo →** pick your repository.
3. Railway will create one service from the repo. We'll configure it as **web** in
   Step 4 and add the other two services later.

## Step 3 — Add the databases

In the project canvas:

1. **+ New → Database → Add PostgreSQL.**
2. **+ New → Database → Add Redis.**

Railway provisions both and exposes connection strings as **reference variables**
you'll wire up next (`${{Postgres.DATABASE_URL}}` and `${{Redis.REDIS_URL}}`).

## Step 4 — Configure the `web` service

Open the service created in Step 2 (rename it to `web`).

**Settings → Build:**
- Builder: **Dockerfile**. Config-as-code / Railway config file path: **`railway.toml`**
  (this points at the root `Dockerfile`).
- Add a **build argument** if you use the captcha: `VITE_TURNSTILE_SITE_KEY` = your
  Turnstile *public* site key. (Vite bakes `VITE_*` in at build time.)

**Settings → Networking:** click **Generate Domain**. Note the URL
(e.g. `https://your-app.up.railway.app`) — you'll reuse it below.

**Variables** (Step 6 lists them all). At minimum set:
- `JWT_SECRET` — generate with `openssl rand -hex 32`
- `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
- `REDIS_URL` = `${{Redis.REDIS_URL}}`
- one LLM key (`OPENROUTER_API_KEY` or `OPENAI_API_KEY`) and `APIFY_API_TOKEN`

The health check (`/health`) and restart policy are already defined in `railway.toml`.

## Step 5 — Add the `worker` and `scheduler` services

Both run the **same repo**, just a different Dockerfile/config.

1. **+ New → GitHub Repo →** select the **same** repository. Name it `worker`.
   - **Settings → Build → Railway config file path: `railway.worker.toml`**
     (uses `Dockerfile.worker`, runs `python run_worker.py`, 3 replicas).
   - It needs the **same variables** as web (see Step 6). The simplest way: use
     Railway **shared variables** at the project level, or copy the same variables
     into this service. It does **not** need a domain.
2. Repeat for `scheduler`: **+ New → GitHub Repo →** same repo, name it `scheduler`.
   - **Railway config file path: `railway.scheduler.toml`** (uses `Dockerfile.scheduler`,
     runs `python run_scheduler.py`, 1 replica).
   - Same variables, no domain.

> **Tip:** Define the shared keys (JWT, DB, Redis, LLM, Apify, …) as **project-level
> shared variables** so all three services inherit them. Then you only edit values once.

## Step 6 — Set environment variables

Use [.env.example](../.env.example) as the checklist. Required for every service:

| Variable        | Value                                   |
|-----------------|------------------------------------------|
| `JWT_SECRET`    | output of `openssl rand -hex 32`         |
| `DATABASE_URL`  | `${{Postgres.DATABASE_URL}}`             |
| `REDIS_URL`     | `${{Redis.REDIS_URL}}`                   |

Strongly recommended (core features):

| Variable             | Where to get it ([details](GETTING_KEYS.md)) |
|----------------------|-----------------------------------------------|
| `OPENROUTER_API_KEY` | openrouter.ai — chat + vision                 |
| `ANTHROPIC_API_KEY`  | console.anthropic.com — scripts/strategy      |
| `WHISPER_API_KEY`    | console.groq.com — audio transcription        |
| `APIFY_API_TOKEN`    | console.apify.com — scraping/download         |

Set these to your generated web domain (used for links, CORS and webhooks):

| Variable              | Value                                        |
|-----------------------|----------------------------------------------|
| `APP_URL`             | `https://your-app.up.railway.app`            |
| `CORS_ORIGINS`        | `https://your-app.up.railway.app`            |
| `TELEGRAM_WEBHOOK_URL`| `https://your-app.up.railway.app` (if using Telegram) |

Everything else (payments, OAuth, email, S3, captcha) is optional — add it when you
want that feature. `PORT` is injected by Railway automatically; don't set it.

## Step 7 — Persistent storage for media

Downloaded audio/frames are written to disk by default. Pick one:

- **Volume (simplest):** add a **Volume** to the `web` and `worker` services mounted at
  `/data/storage`, and set `STORAGE_DIR=/data/storage`.
- **Object storage (recommended for scale):** set `S3_BUCKET` + `S3_ACCESS_KEY` +
  `S3_SECRET_KEY` (+ `S3_ENDPOINT` for Cloudflare R2 / Railway Buckets). See
  [GETTING_KEYS.md](GETTING_KEYS.md). With `S3_BUCKET` set, local disk isn't used.

## Step 8 — Deploy & verify

1. Trigger a deploy on each service (Railway redeploys on push, or use **Deploy**).
2. Open `https://your-app.up.railway.app/health` → expect `{"status":"ok"}`.
3. Open the site root → the UI loads.
4. Watch the **web** logs: you should see migrations run (`alembic upgrade head` +
   idempotent column checks) before uvicorn starts.

## Step 9 — Make yourself admin & finish

- Set `ADMIN_EMAILS` (and/or `ADMIN_TELEGRAM_IDS`) to your account, then sign up with
  that email to unlock the admin dashboards.
- If you enabled Telegram, set the bot webhook to `TELEGRAM_WEBHOOK_URL` (the app
  registers it on startup when the token + URL are present).
- If you enabled payments, add each provider's **webhook secret** and point the
  provider's webhook at your domain (see GETTING_KEYS.md).

## Troubleshooting

- **Service crashes immediately, log says `JWT_SECRET is not configured`** → set
  `JWT_SECRET` (and not the literal `change-me-in-production`).
- **`/health` never goes green** → check `DATABASE_URL`/`REDIS_URL` reference the
  Postgres/Redis services; check the build logs for the Docker build finishing.
- **Frontend captcha missing / login blocked** → set `VITE_TURNSTILE_SITE_KEY` as a
  **build arg** (not just a runtime var) and redeploy, or leave both Turnstile keys
  empty to disable captcha.
- **Run `python scripts/check_env.py`** locally against the values you plan to use to
  catch missing required vars before deploying.
