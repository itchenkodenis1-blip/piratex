#!/usr/bin/env python3
"""
ВидеоРентген (VideoRentgen) — environment self-check.

Shows what's configured and what each integration still needs. Use it after
editing your .env (or after setting variables on Railway) to confirm you're
ready to boot, and to see which optional features are turned on.

    python scripts/check_env.py                # reads ./.env  (or ./backend/.env)
    python scripts/check_env.py path/to/.env   # reads a specific file

No third-party dependencies — plain Python 3.
Exit code 0 = required vars present (app can boot). 1 = something required is missing.
"""
from __future__ import annotations

import os
import sys

# ── tiny ANSI helpers (degrade to plain text if not a TTY) ──────────────────
_TTY = sys.stdout.isatty()
def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _TTY else s
GREEN = lambda s: _c("32", s)
RED = lambda s: _c("31", s)
YELLOW = lambda s: _c("33", s)
DIM = lambda s: _c("2", s)
BOLD = lambda s: _c("1", s)

OK = GREEN("✓ set")
MISSING = "  —  "


def load_env(path: str | None) -> dict[str, str]:
    """Parse a .env file (KEY=VALUE), then overlay the real environment."""
    env: dict[str, str] = {}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip().strip('"').strip("'")
    # Real environment variables win (this is how Railway/Render inject config).
    for key, val in os.environ.items():
        if val != "":
            env[key] = val
    return env


def is_set(env: dict[str, str], key: str) -> bool:
    return bool(env.get(key, "").strip())


def main() -> int:
    # Resolve which .env to read.
    if len(sys.argv) > 1:
        path = sys.argv[1]
    elif os.path.exists(".env"):
        path = ".env"
    elif os.path.exists("backend/.env"):
        path = "backend/.env"
    else:
        path = None

    env = load_env(path)
    src = path if path else "(no .env file — reading process environment only)"
    print(BOLD("\nВидеоРентген (VideoRentgen) — environment check"))
    print(DIM(f"source: {src}\n"))

    problems: list[str] = []

    # ── REQUIRED ────────────────────────────────────────────────────────────
    print(BOLD("REQUIRED (app will not boot without these)"))
    required = [
        ("JWT_SECRET", "auth token signing key  (generate: openssl rand -hex 32)"),
        ("DATABASE_URL", "PostgreSQL connection string"),
        ("REDIS_URL", "Redis (task queue + realtime)"),
    ]
    for key, note in required:
        if is_set(env, key):
            extra = ""
            if key == "JWT_SECRET":
                val = env[key].strip()
                if val == "change-me-in-production":
                    extra = RED("  ← placeholder! app refuses to start with this")
                    problems.append("JWT_SECRET is the forbidden placeholder value")
                elif len(val) < 32:
                    extra = YELLOW("  ← weak; use openssl rand -hex 32")
            print(f"  {OK}  {key:<14} {DIM(note)}{extra}")
        else:
            print(f"  {RED('✗ MISSING')}  {key:<14} {DIM(note)}")
            problems.append(f"{key} is required but not set")

    # ── CORE FEATURES ────────────────────────────────────────────────────────
    print(BOLD("\nAI / analysis  (need at least one LLM provider)"))
    llm_ok = is_set(env, "OPENROUTER_API_KEY") or is_set(env, "OPENAI_API_KEY")
    print(f"  {'  '+OK if llm_ok else YELLOW('! none ')}  LLM chat+vision "
          + DIM("(OPENROUTER_API_KEY or OPENAI_API_KEY)"))
    if not llm_ok:
        print(DIM("        analysis won't run until one of these is set"))
    _feature(env, "Claude scripts/strategy", ["ANTHROPIC_API_KEY"])
    _feature(env, "Audio transcription", ["WHISPER_API_KEY", "OPENROUTER_API_KEY"],
             any_of=True, note="(Groq free tier, or falls back to OpenRouter)")

    print(BOLD("\nScraping"))
    _feature(env, "Apify (IG/TikTok/YouTube)", ["APIFY_API_TOKEN"],
             note="(required to analyze real public content)")

    print(BOLD("\nOptional integrations"))
    _feature(env, "Telegram bot/login", ["TELEGRAM_BOT_TOKEN"])
    _feature(env, "Turnstile captcha", ["TURNSTILE_SECRET_KEY"], note="(empty = disabled)")
    _feature(env, "Yandex login", ["YANDEX_CLIENT_ID", "YANDEX_CLIENT_SECRET"], all_of=True)
    _feature(env, "Google login", ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"], all_of=True)
    _feature(env, "VK login", ["VK_CLIENT_ID", "VK_CLIENT_SECRET"], all_of=True)
    _feature(env, "Email (Unisender)", ["UNISENDER_API_KEY"], note="(empty = emails only logged)")
    _feature(env, "S3/R2 storage", ["S3_BUCKET"], note="(empty = local disk)")

    print(BOLD("\nPayments  (configure any you need)"))
    _feature(env, "YooKassa (RUB)", ["YOOKASSA_SHOP_ID", "YOOKASSA_SECRET_KEY"], all_of=True)
    _feature(env, "Stripe (EUR)", ["STRIPE_SECRET_KEY"])
    _feature(env, "CloudPayments (RUB)", ["CLOUDPAYMENTS_PUBLIC_ID", "CLOUDPAYMENTS_API_SECRET"], all_of=True)

    # ── verdict ──────────────────────────────────────────────────────────────
    print()
    if problems:
        print(RED(BOLD("NOT READY — fix the required vars above:")))
        for p in problems:
            print(RED(f"  • {p}"))
        print()
        return 1
    print(GREEN(BOLD("READY ✓  — required vars present, the app can boot.")))
    if not llm_ok:
        print(YELLOW("Note: no LLM key set, so analysis features will be inactive."))
    print()
    return 0


def _feature(env, label, keys, *, all_of=False, any_of=False, note="") -> None:
    """Print one optional-feature line. Default: enabled if the first key is set."""
    if all_of:
        enabled = all(is_set(env, k) for k in keys)
    elif any_of:
        enabled = any(is_set(env, k) for k in keys)
    else:
        enabled = is_set(env, keys[0])
    mark = GREEN("on ") if enabled else DIM("off")
    tail = DIM(" " + note) if note else ""
    print(f"  [{mark}]  {label:<26}{tail}")


if __name__ == "__main__":
    raise SystemExit(main())
