# Getting your keys

Every credential the app uses, where to obtain it, and whether you actually need it.
The matching variable names are in [.env.example](../.env.example); run
`python scripts/check_env.py` any time to see what's set.

## The minimum to "just make it run"

You can have a working deployment with only these:

| Variable             | Why                          | Where                                            |
|----------------------|------------------------------|--------------------------------------------------|
| `JWT_SECRET`         | required to boot             | run `openssl rand -hex 32`                        |
| `DATABASE_URL`       | required to boot             | provided by the managed Postgres                  |
| `REDIS_URL`          | required to boot             | provided by the managed Redis                     |
| `OPENROUTER_API_KEY` | AI analysis + scripts        | <https://openrouter.ai/keys>                      |
| `APIFY_API_TOKEN`    | download IG/TikTok/YouTube   | <https://console.apify.com/account/integrations>  |

Everything below is **optional** — add it only when you want that feature. Without a
key, the related feature is simply turned off; the app still runs.

---

## AI / LLM

You need **at least one** LLM provider for analysis to work.

- **OpenRouter** — primary provider for chat + vision (one key, many models).
  Get a key: <https://openrouter.ai/keys>. Pay-as-you-go; add credit in the dashboard.
  Sets `OPENROUTER_API_KEY`.
- **OpenAI** — alternative used only if OpenRouter is empty.
  <https://platform.openai.com/api-keys>. Sets `OPENAI_API_KEY`.
- **Anthropic (Claude)** — script & strategy generation.
  <https://console.anthropic.com> → API Keys. Sets `ANTHROPIC_API_KEY`.
- **Groq (Whisper)** — audio transcription, has a free tier.
  <https://console.groq.com> → API Keys. Sets `WHISPER_API_KEY`
  (if empty, transcription falls back to your OpenRouter key).

> Rough cost: analysis is a few cents per video depending on length and models.
> You control the spend in each provider's dashboard.

## Scraping — Apify

Downloads and metadata for Instagram / TikTok / YouTube go through Apify actors.

- Sign up at <https://apify.com>, then copy your token at
  <https://console.apify.com/account/integrations>. Sets `APIFY_API_TOKEN`.
- The default actor IDs in `.env.example` are public actors; you usually don't change
  them. Apify charges per run/result — watch your usage; the app has built-in budget
  guardrails (`APIFY_BALANCE_*`).

## Telegram (optional) — login + subscription gate

- Create a bot with **@BotFather** (<https://t.me/botfather>) → `/newbot` → copy the
  token into `TELEGRAM_BOT_TOKEN`, and put the bot's username in `TELEGRAM_BOT_NAME`.
- To gate free analyses behind a channel subscription, set `TELEGRAM_CHANNEL_ID`
  (`@yourchannel` or the `-100…` id) and `TELEGRAM_CHANNEL_URL` (invite link).
- For the bot to receive messages set `TELEGRAM_WEBHOOK_URL` (your public domain) and
  a random `TELEGRAM_WEBHOOK_SECRET`. Leave all of these empty to disable Telegram.

## OAuth logins (optional)

Each provider is enabled only when **both** its id and secret are set.

- **Yandex ID** — <https://oauth.yandex.ru/> → register an app → `YANDEX_CLIENT_ID` /
  `YANDEX_CLIENT_SECRET`.
- **Google** — <https://console.cloud.google.com/> → APIs & Services → Credentials →
  OAuth 2.0 Client ID → `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
- **VK ID** — <https://id.vk.com/business/go> → `VK_CLIENT_ID` / `VK_CLIENT_SECRET`.

Set each provider's **redirect URI** to `https://your-domain/…/callback` as shown in
the app's auth settings. Magic-link email login works without any OAuth provider.

## Email (optional) — magic links & notifications

- **Unisender Go** — <https://go.unisender.ru/> → API key → `UNISENDER_API_KEY`,
  and set `EMAIL_FROM_DOMAIN` to a domain you've verified there.
- If empty, the app **logs** outgoing emails instead of sending them — fine for testing.

## Captcha (optional) — Cloudflare Turnstile

- <https://dash.cloudflare.com> → **Turnstile** → add a site. You get two keys:
  - the **secret** key → backend `TURNSTILE_SECRET_KEY`
  - the **site** (public) key → frontend `VITE_TURNSTILE_SITE_KEY` (a Docker **build arg**)
- Leave both empty to disable the captcha entirely.

## Object storage (optional) — S3 / Cloudflare R2

Empty `S3_BUCKET` = files are stored on local disk (or a mounted volume).

- **Cloudflare R2** — <https://dash.cloudflare.com> → R2 → create bucket + API token.
  Set `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and `S3_ENDPOINT`
  (`https://<account-id>.r2.cloudflarestorage.com`). Optionally `CDN_URL` for serving.
- **AWS S3 / MinIO / Railway Buckets** also work with the same variables.

## Payments (optional)

Configure only the provider(s) you need; each is independent.

- **YooKassa (RUB)** — <https://yookassa.ru/> → shop id + secret key →
  `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`, and `YOOKASSA_WEBHOOK_SECRET`
  (required in production). Point its webhook at `https://your-domain/…`.
- **Stripe (EUR)** — <https://dashboard.stripe.com/apikeys> → `STRIPE_SECRET_KEY`,
  `STRIPE_WEBHOOK_SECRET`. Create your products/prices in Stripe and paste the
  resulting **Price IDs** into `backend/app/config.py → STRIPE_PRICE_IDS`.
- **CloudPayments (RUB)** — <https://merchant.cloudpayments.ru/> →
  `CLOUDPAYMENTS_PUBLIC_ID`, `CLOUDPAYMENTS_API_SECRET`.

## Admin access

Set `ADMIN_EMAILS` (comma-separated) and/or `ADMIN_TELEGRAM_IDS` to your own account
so you get the admin dashboards after signing up with that email.

---

**Security reminder:** keys are secrets. Put them only in your `.env` file (which is
git-ignored) or in your host's environment-variable settings. Never paste them into a
public chat, screenshot, commit, or issue.
