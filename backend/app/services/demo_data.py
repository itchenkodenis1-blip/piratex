"""Demo-data overlay for the admin analytics dashboards.

When demo mode is ON, the admin / showcase analytics endpoints display a
deterministic, synthetic financial picture (≈500 000 ₽/мес) instead of the
real (near-empty) numbers — so the product can be demonstrated as a working
prototype.

Честные ограничения (почему это не подделка реальных данных):

  * Все цифры ГЕНЕРИРУЮТСЯ в памяти на каждый запрос. В базу данных ничего не
    пишется. Реальная платёжная логика (вебхуки, провайдеры, записи Payment)
    остаётся нетронутой.
  * Платёжные строки используют только синтетические личности — никаких
    реальных пользователей.
  * Оверлей включается админ-тумблером (`is_demo_mode`), а в UI всегда виден
    бейдж «DEMO», пока режим активен.
  * Выключение демо-режима мгновенно возвращает реальные числа.

Модель: единственный источник правды — синтетический ростер активных
подписчиков (``_subscriber_roster``). Из него выводятся И MRR, И поток платежей
(ежемесячные продления). Поэтому выручка за месяц всегда сходится с MRR — на
дашборде нет противоречащих друг другу цифр.

Детерминизм: каждое значение засеивается из календарной даты, поэтому дашборд
стабилен между обновлениями (не мерцает), но естественно меняется день ото дня
и автоматически продлевается до «сегодня».
"""

from __future__ import annotations

import calendar
import hashlib
import random
import uuid
from datetime import date, datetime, timedelta
from functools import lru_cache

from app.config import TIER_PRICING, TIER_PRICING_EUR, settings
from app.core.redis_pool import get_redis

# ---------------------------------------------------------------------------
# Toggle
# ---------------------------------------------------------------------------

_REDIS_KEY = "demo_mode:enabled"


async def is_demo_mode() -> bool:
    """True when the demo overlay should be applied.

    Runtime Redis override (set via the admin toggle) wins; otherwise falls
    back to the DEMO_MODE env default in settings.
    """
    try:
        r = await get_redis()
        if r is not None:
            val = await r.get(_REDIS_KEY)
            if val is not None:
                return str(val).lower() in ("1", "true", "yes", "on")
    except Exception:
        pass
    return settings.demo_mode


async def set_demo_mode(enabled: bool) -> None:
    """Persist the runtime demo-mode toggle in Redis."""
    r = await get_redis()
    if r is None:
        raise RuntimeError("Redis unavailable")
    await r.set(_REDIS_KEY, "1" if enabled else "0")


# ---------------------------------------------------------------------------
# Tunables — adjust these to change the demonstrated scale
# ---------------------------------------------------------------------------

# First registration date the demo history starts from (matches the showcase
# baseline default). Lifetime totals are summed from here to "today".
LAUNCH_DATE = datetime(2026, 3, 21, 18, 30)

# Active-subscriber roster size per month. Counts are tuned (with the real
# config prices) so MRR lands at ≈500 000 ₽/мес. Because the payment stream is
# these same subscribers renewing once a month, a full month of collections
# also lands at ≈MRR — the two figures reconcile by construction.
_RUB_START = (88, 96)
_RUB_PRO = (38, 44)
_RUB_UNLIM = (10, 14)
_EUR_START = (4, 9)
_EUR_PRO = (2, 5)
_EUR_UNLIM = (0, 2)

# Share of monthly renewals that succeed (the rest are failed/cancelled card
# charges — realistic involuntary churn, slightly below MRR).
_RENEWAL_SUCCESS_PCT = 96

# Synthetic-identity pools (display names are Cyrillic; email handles latin —
# a realistic combination for the RU market).
_FIRST = [
    "Алексей", "Мария", "Дмитрий", "Анна", "Сергей", "Екатерина", "Иван",
    "Ольга", "Андрей", "Наталья", "Михаил", "Татьяна", "Павел", "Юлия",
    "Никита", "Дарья", "Владимир", "Ксения", "Артём", "Светлана", "Роман",
    "Виктория", "Денис", "Алёна", "Кирилл", "Полина", "Максим", "Елена",
]
_LAST = [
    "Иванов", "Петрова", "Смирнов", "Кузнецова", "Попов", "Соколова",
    "Лебедев", "Новикова", "Морозов", "Волкова", "Козлов", "Зайцева",
    "Соловьёв", "Павлова", "Васильев", "Орлова", "Фёдоров", "Макарова",
    "Никитин", "Андреева", "Захаров", "Белова", "Тарасов", "Комарова",
]
_HANDLES = [
    "alex", "masha", "dmitry", "anna", "sergey", "kate", "ivan", "olga",
    "andrey", "natali", "mike", "tanya", "pavel", "julia", "nikita", "daria",
    "vova", "ksenia", "artem", "sveta", "roman", "vika", "denis", "alyona",
    "kirill", "polina", "max", "elena", "creator", "smm", "blogger", "studio",
]
_DOMAINS = ["gmail.com", "yandex.ru", "mail.ru", "icloud.com", "outlook.com", "vk.com"]

# Money facts pulled from the single source of truth (config.py). We only READ
# them here — pricing is never modified.
_RUB = TIER_PRICING            # kopecks
_EUR = TIER_PRICING_EUR        # cents


# ---------------------------------------------------------------------------
# Deterministic RNG helpers
# ---------------------------------------------------------------------------

def _rng(*parts) -> random.Random:
    """A reproducible RNG seeded from the given parts (stable across processes
    — unlike the hash-randomised builtin ``hash()``)."""
    key = ":".join(str(p) for p in parts)
    seed = int(hashlib.sha256(key.encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def _det_uuid(*parts) -> str:
    key = ":".join(str(p) for p in parts)
    return str(uuid.UUID(int=int(hashlib.sha256(key.encode()).hexdigest()[:32], 16)))


# ---------------------------------------------------------------------------
# Active-subscriber roster — the single source of truth
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _subscriber_roster(year: int, month: int) -> tuple[dict, ...]:
    """Deterministic set of active subscribers for the given month.

    Stable within a month, drifts slightly month to month. Each subscriber has
    a fixed billing day (1..days-in-month) so renewals spread evenly across the
    month. Returned as a tuple so the lru_cache result is immutable.
    """
    rng = _rng("roster", year, month)
    days_in_month = calendar.monthrange(year, month)[1]

    counts = [
        ("RUB", "START", rng.randint(*_RUB_START)),
        ("RUB", "PRO", rng.randint(*_RUB_PRO)),
        ("RUB", "UNLIMITED", rng.randint(*_RUB_UNLIM)),
        ("EUR", "START", rng.randint(*_EUR_START)),
        ("EUR", "PRO", rng.randint(*_EUR_PRO)),
        ("EUR", "UNLIMITED", rng.randint(*_EUR_UNLIM)),
    ]

    subs: list[dict] = []
    for currency, tier, n in counts:
        for k in range(n):
            srng = _rng("sub", year, month, currency, tier, k)
            billing_day = srng.randint(1, days_in_month)
            if currency == "EUR":
                provider = "stripe"
                method = "bank_card"
            else:
                provider = srng.choices(["yookassa", "cloudpayments"], weights=[78, 22])[0]
                method = (
                    srng.choices(["bank_card", "sbp", "yoomoney"], weights=[60, 30, 10])[0]
                    if provider == "yookassa" else "bank_card"
                )
            first = srng.choice(_FIRST)
            last = srng.choice(_LAST)
            handle = srng.choice(_HANDLES)
            domain = srng.choice(_DOMAINS)
            subs.append({
                "key": (currency, tier, k),
                "tier": tier,
                "currency": currency,
                "provider": provider,
                "method": method,
                "billing_day": billing_day,
                "amount": int((_EUR if currency == "EUR" else _RUB)[tier]["monthly"]),
                "user_name": f"{first} {last}",
                "user_email": f"{handle}{srng.randint(1, 998)}@{domain}",
                "user_id": _det_uuid("subuser", currency, tier, k),
            })
    return tuple(subs)


def demo_identity(seed_key: str) -> dict:
    """A deterministic synthetic display identity for a real user.

    Used to mask real PII (emails/names) in admin lists while demo mode is on.
    Keyed by the real user id so the same person maps to the same fake identity
    across all their rows (e.g. every job they ran).
    """
    rng = _rng("identity", seed_key)
    first = rng.choice(_FIRST)
    last = rng.choice(_LAST)
    handle = rng.choice(_HANDLES)
    domain = rng.choice(_DOMAINS)
    return {
        "user_name": f"{first} {last}",
        "user_email": f"{handle}{rng.randint(1, 998)}@{domain}",
    }


def mask_email(email: str | None) -> str | None:
    """Mask an email for cinematic display (e.g. ``mas***@gmail.com``)."""
    if not email:
        return None
    local, _, domain = email.partition("@")
    if not domain:
        return None
    if len(local) <= 2:
        return f"{local[0]}***@{domain}" if local else f"***@{domain}"
    return f"{local[:3]}***@{domain}"


def funnel(now: datetime) -> dict:
    """User funnel + MRR derived from the active-subscriber roster."""
    subs = _subscriber_roster(now.year, now.month)

    start_users = sum(1 for s in subs if s["tier"] == "START")
    pro_users = sum(1 for s in subs if s["tier"] == "PRO")
    unlimited_users = sum(1 for s in subs if s["tier"] == "UNLIMITED")
    paid = len(subs)

    mrr_rub = sum(s["amount"] for s in subs if s["currency"] == "RUB")
    mrr_eur = sum(s["amount"] for s in subs if s["currency"] == "EUR")

    frng = _rng("funnel", now.year, now.month)
    conversion = frng.uniform(0.065, 0.085)
    registered_total = round(paid / conversion)            # all non-anonymous users
    non_paid = max(registered_total - paid, 0)
    registered_tier = round(non_paid * frng.uniform(0.30, 0.40))  # signed up, no plan yet
    free = non_paid - registered_tier
    anonymous = round(registered_total * frng.uniform(0.5, 0.8))
    total_users = anonymous + registered_total

    return {
        "total_users": total_users,
        "anonymous": anonymous,
        "registered_total": registered_total,
        "registered_tier": registered_tier,
        "free": free,
        "start_users": start_users,
        "pro_users": pro_users,
        "unlimited_users": unlimited_users,
        "paid": paid,
        "mrr_rub": int(mrr_rub),
        "mrr_eur": int(mrr_eur),
        "conversion_pct": round(paid / registered_total * 100, 1) if registered_total else 0.0,
    }


# ---------------------------------------------------------------------------
# Payment stream — monthly renewals of the roster
# ---------------------------------------------------------------------------

def _renewals_on_day(d: date) -> list[dict]:
    """Subscription renewals charged on calendar day ``d``."""
    subs = _subscriber_roster(d.year, d.month)
    out: list[dict] = []
    for s in subs:
        if s["billing_day"] != d.day:
            continue
        currency, tier, k = s["key"]
        prng = _rng("renew", d.year, d.month, currency, tier, k)
        status = prng.choices(["succeeded", "cancelled"], weights=[_RENEWAL_SUCCESS_PCT, 100 - _RENEWAL_SUCCESS_PCT])[0]
        created = datetime(d.year, d.month, d.day, prng.randint(8, 23), prng.randint(0, 59), prng.randint(0, 59))
        out.append({
            "id": _det_uuid("payid", d.year, d.month, currency, tier, k),
            "user_id": s["user_id"],
            "user_email": s["user_email"],
            "user_name": s["user_name"],
            "subscription_id": _det_uuid("subid", currency, tier, k),
            "provider_payment_id": _det_uuid("ppid", d.year, d.month, currency, tier, k),
            "payment_provider": s["provider"],
            "amount_kopecks": s["amount"],
            "currency": currency,
            "status": status,
            "payment_method": s["method"],
            "description": f"Подписка {tier} (мес)",
            "receipt_url": None,
            "paid_at": created if status == "succeeded" else None,
            "created_at": created,
        })
    return out


def _all_payments(now: datetime) -> list[dict]:
    """Every synthetic renewal from launch up to ``now`` (newest first)."""
    payments: list[dict] = []
    d = LAUNCH_DATE.date()
    end = now.date()
    while d <= end:
        for p in _renewals_on_day(d):
            if LAUNCH_DATE <= p["created_at"] <= now:
                payments.append(p)
        d += timedelta(days=1)
    payments.sort(key=lambda p: p["created_at"], reverse=True)
    return payments


def _sum(payments, currency, *, since=None, until=None) -> int:
    total = 0
    for p in payments:
        if p["status"] != "succeeded" or p["currency"] != currency or p["paid_at"] is None:
            continue
        if since is not None and p["paid_at"] < since:
            continue
        if until is not None and p["paid_at"] >= until:
            continue
        total += p["amount_kopecks"]
    return total


def _sum_rub(payments, *, since=None, until=None) -> int:
    return _sum(payments, "RUB", since=since, until=until)


def _sum_eur(payments, *, since=None, until=None) -> int:
    return _sum(payments, "EUR", since=since, until=until)


def cost_revenue(now: datetime) -> dict:
    """Money fields for the /admin/cost-analytics dashboard.

    "Доход за месяц" uses a trailing-30-day window so it stays ≈MRR on any day
    (a calendar month-to-date sum would ramp from ~0 on the 1st and read as a
    near-dead business early in the month).
    """
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    trailing_30 = now - timedelta(days=30)

    payments = _all_payments(now)
    f = funnel(now)

    return {
        "revenue_today_rub": _sum_rub(payments, since=today_start),
        "revenue_yesterday_rub": _sum_rub(payments, since=yesterday_start, until=today_start),
        "revenue_month_rub": _sum_rub(payments, since=trailing_30),
        "revenue_today_eur": _sum_eur(payments, since=today_start),
        "revenue_month_eur": _sum_eur(payments, since=trailing_30),
        "mrr_rub": f["mrr_rub"],
        "mrr_eur": f["mrr_eur"],
        "paid_users": f["paid"],
    }


def payments_page(
    now: datetime,
    *,
    status: str = "",
    provider: str = "",
    q: str = "",
    page: int = 1,
    per_page: int = 50,
) -> dict:
    """A filtered + paginated page for /admin/payments, with aggregates.

    Mirrors the real endpoint's semantics: ``total_all`` and the succeeded
    aggregates respect the provider/q filters but NOT the status filter.
    """
    payments = _all_payments(now)

    # Base = provider/q filtered (status-independent) — matches the real endpoint.
    base = payments
    if provider:
        base = [p for p in base if p["payment_provider"] == provider]
    if q:
        ql = q.lower()
        base = [p for p in base if ql in (p["user_email"] or "").lower()]

    total_all = len(base)

    succeeded = [p for p in base if p["status"] == "succeeded"]
    total_succeeded = len(succeeded)
    total_rub = sum(p["amount_kopecks"] for p in succeeded if p["currency"] == "RUB")
    total_eur = sum(p["amount_kopecks"] for p in succeeded if p["currency"] == "EUR")

    filtered = [p for p in base if p["status"] == status] if status else base
    total = len(filtered)
    offset = (page - 1) * per_page
    items = filtered[offset:offset + per_page]

    return {
        "items": items,
        "total": total,
        "total_all": total_all,
        "total_succeeded": total_succeeded,
        "total_rub_kopecks": total_rub,
        "total_eur_cents": total_eur,
    }


def showcase_overlay(now: datetime, launch_date: datetime, today: bool) -> dict:
    """Funnel + revenue overlay for the /admin/showcase cinematic dashboard."""
    f = funnel(now)
    payments = _all_payments(now)

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if today:
        total_rub = _sum_rub(payments, since=today_start)
        total_eur = _sum_eur(payments, since=today_start)
    else:
        # Lifetime = the whole synthetic stream (spans LAUNCH_DATE..now), so it
        # always equals the /payments aggregate regardless of the Redis baseline.
        total_rub = _sum_rub(payments)
        total_eur = _sum_eur(payments)

    daily_rev: dict[str, dict] = {}
    today_date = now.date()
    for i in range(29, -1, -1):
        d = today_date - timedelta(days=i)
        day_start = datetime(d.year, d.month, d.day)
        day_end = day_start + timedelta(days=1)
        daily_rev[d.isoformat()] = {
            "rub": _sum_rub(payments, since=day_start, until=day_end),
            "eur": _sum_eur(payments, since=day_start, until=day_end),
        }

    return {
        "total_registered": f["registered_total"],
        "total_paid": f["paid"],
        "conversion_pct": f["conversion_pct"],
        "free_users": f["free"],
        "start_users": f["start_users"],
        "pro_users": f["pro_users"],
        "unlimited_users": f["unlimited_users"],
        "total_rub_kopecks": total_rub,
        "total_eur_cents": total_eur,
        "daily_revenue": daily_rev,
    }
