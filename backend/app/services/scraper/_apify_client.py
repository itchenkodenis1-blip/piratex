import asyncio
import json
import logging
import time
from datetime import date
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.core.exceptions import ApifyBudgetExhausted, DownloadError

logger = logging.getLogger(__name__)


def _summarise_item(item: dict, max_value_len: int = 120) -> dict:
    """Return a compact summary of an Apify item for logging.

    Shows all keys with their value types and truncated values,
    so we can diagnose missing fields without dumping the full payload.
    """
    summary: dict = {}
    for key, value in item.items():
        if value is None:
            summary[key] = None
        elif isinstance(value, str):
            summary[key] = value[:max_value_len] + ("…" if len(value) > max_value_len else "")
        elif isinstance(value, (int, float, bool)):
            summary[key] = value
        elif isinstance(value, dict):
            summary[key] = f"{{dict, {len(value)} keys: {list(value.keys())[:8]}}}"
        elif isinstance(value, list):
            summary[key] = f"[list, {len(value)} items]"
        else:
            summary[key] = f"<{type(value).__name__}>"
    return summary


def _safe_domain(url: str | None) -> str:
    """Extract domain from URL for logging (no secrets in CDN URLs)."""
    if not url:
        return "<empty>"
    try:
        return urlparse(url).netloc or "<no-host>"
    except Exception:
        return "<parse-error>"

APIFY_BASE = "https://api.apify.com/v2"

# Statuses that mean the run is still in progress
_IN_PROGRESS_STATUSES = {"READY", "RUNNING"}
_POLL_INTERVAL = 10  # seconds between status checks
_MAX_POLL_ATTEMPTS = 30  # 30 * 10 = 300 seconds max polling


# ---------------------------------------------------------------------------
# Budget gate (circuit breaker + daily run counter for observability)
# ---------------------------------------------------------------------------



async def _get_budget_redis():
    """Get Redis from shared pool for budget tracking."""
    from app.core.redis_pool import get_redis
    return await get_redis()


async def _check_budget_gate(caller: str = "") -> None:
    """Pre-flight check before every Apify actor run.

    Circuit breaker: if Apify balance is below threshold, block all calls.
    Daily counter: always incremented for observability (no hard cap).

    Fail-open: if Redis is unavailable, the gate passes through.
    """
    r = await _get_budget_redis()
    if r is None:
        logger.warning("[apify-budget] Redis unavailable, skipping budget check")
        return

    # Circuit breaker (set by _update_balance_circuit_breaker when balance is low)
    if await r.exists("apify:circuit_breaker"):
        raise ApifyBudgetExhausted(
            "Баланс Apify критически низкий — все вызовы приостановлены. "
            "Обратитесь к администратору."
        )

    # Increment daily counter for monitoring (no hard cap — scales with users)
    today_key = f"apify:runs:{date.today().isoformat()}"
    count = await r.incr(today_key)
    if count == 1:
        await r.expire(today_key, 86400)
    logger.debug("[apify-budget] Daily run #%d (caller=%s)", count, caller)


# ---------------------------------------------------------------------------
# Balance checker (circuit breaker management)
# ---------------------------------------------------------------------------

async def check_apify_balance() -> dict:
    """Check Apify account usage via GET /v2/users/me/limits."""
    token = _get_token()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{APIFY_BASE}/users/me/limits",
            params={"token": token},
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

        limits = data.get("limits", {})
        current = data.get("current", {})

        max_usd = limits.get("maxMonthlyUsageUsd", 0)
        used_usd = current.get("monthlyUsageUsd", 0)
        remaining = max_usd - used_usd if max_usd else float("inf")

        return {
            "max_monthly_usd": max_usd,
            "used_monthly_usd": round(used_usd, 2),
            "remaining_usd": round(remaining, 2),
        }


async def _send_budget_alert(message: str) -> None:
    """Send Apify budget alert to admin Telegram IDs."""
    try:
        if not settings.admin_telegram_ids or not settings.telegram_bot_token:
            logger.warning("[apify-budget] No admin Telegram IDs configured, skipping alert")
            return
        from app.services.telegram import send_telegram_message

        admin_ids = [tid.strip() for tid in settings.admin_telegram_ids.split(",") if tid.strip()]
        for tid in admin_ids:
            await send_telegram_message(tid, settings.telegram_bot_token, message)
    except Exception as e:
        logger.error("[apify-budget] Failed to send alert: %s", e)


async def _update_balance_circuit_breaker() -> None:
    """Check balance and set/clear circuit breaker in Redis.

    Thresholds are percentage-based (of monthly limit) so they scale
    automatically as the Apify plan grows.
    """
    try:
        info = await check_apify_balance()
        remaining = info["remaining_usd"]
        max_monthly = info["max_monthly_usd"]

        r = await _get_budget_redis()
        if r is None:
            return

        # Cache balance info
        await r.set(
            "apify:balance:cached",
            json.dumps({**info, "checked_at": time.time()}),
            ex=settings.apify_balance_check_interval * 2,
        )

        # Calculate thresholds from percentages of monthly limit
        if max_monthly > 0:
            circuit_threshold = max_monthly * settings.apify_balance_min_pct / 100
            alert_threshold = max_monthly * settings.apify_balance_alert_pct / 100
        else:
            # No monthly limit set — skip budget protection
            await r.delete("apify:circuit_breaker")
            return

        if remaining <= circuit_threshold:
            logger.critical(
                "[apify-budget] CIRCUIT BREAKER OPEN: remaining=$%.2f (%.1f%% of $%.0f), threshold=%.1f%%",
                remaining, (remaining / max_monthly * 100) if max_monthly else 0, max_monthly,
                settings.apify_balance_min_pct,
            )
            await r.set("apify:circuit_breaker", "open", ex=3600)
            # Alert at most once per 6 hours for circuit breaker
            cb_alert_key = "apify:circuit_breaker_alert_sent"
            if not await r.exists(cb_alert_key):
                await r.set(cb_alert_key, "1", ex=21600)
                await _send_budget_alert(
                    f"🔴 Apify CIRCUIT BREAKER: ${remaining:.2f} remaining ({remaining/max_monthly*100:.0f}% of ${max_monthly:.0f}). All scraping paused!"
                )
        else:
            await r.delete("apify:circuit_breaker")
            if remaining <= alert_threshold:
                # Alert at most once per 6 hours
                alert_key = "apify:balance_alert_sent"
                if not await r.exists(alert_key):
                    await r.set(alert_key, "1", ex=21600)
                    await _send_budget_alert(
                        f"⚠️ Apify balance low: ${remaining:.2f} remaining ({remaining/max_monthly*100:.0f}% of ${max_monthly:.0f}). Top up soon."
                    )
            logger.info(
                "[apify-budget] Balance OK: $%.2f remaining (%.1f%% of $%.0f)",
                remaining, (remaining / max_monthly * 100) if max_monthly else 0, max_monthly,
            )
    except Exception as e:
        logger.error("[apify-budget] Balance check failed: %s", e)


# ---------------------------------------------------------------------------
# Scrape fail-rate tracker (in-process, fail-open)
# ---------------------------------------------------------------------------

_SCRAPE_RESULTS: list[bool] = []  # True = success, False = fail
_SCRAPE_WINDOW = 20  # sliding window size


def _record_scrape_result(success: bool) -> None:
    """Record a scrape outcome for fail-rate monitoring."""
    _SCRAPE_RESULTS.append(success)
    if len(_SCRAPE_RESULTS) > _SCRAPE_WINDOW:
        _SCRAPE_RESULTS.pop(0)


def _should_retry_scrape() -> bool:
    """Return False if fail rate > 50% in the last window.

    Fail-open: if fewer than 4 results, always allow retry.
    """
    if len(_SCRAPE_RESULTS) < 4:
        return True
    fail_count = sum(1 for r in _SCRAPE_RESULTS if not r)
    return (fail_count / len(_SCRAPE_RESULTS)) <= 0.5


# ---------------------------------------------------------------------------
# Core Apify helpers
# ---------------------------------------------------------------------------

def _get_token() -> str:
    """Get Apify API token, fail fast if not configured."""
    token = settings.apify_api_token
    if not token:
        raise DownloadError(
            "APIFY_API_TOKEN is not configured. "
            "Set it in .env to use the scraping service."
        )
    return token


async def _wait_for_run(
    client: httpx.AsyncClient,
    run_id: str,
    token: str,
) -> dict:
    """Poll run status until it finishes or max attempts exceeded."""
    for attempt in range(_MAX_POLL_ATTEMPTS):
        await asyncio.sleep(_POLL_INTERVAL)
        resp = await client.get(
            f"{APIFY_BASE}/actor-runs/{run_id}",
            params={"token": token},
        )
        resp.raise_for_status()
        run_data = resp.json().get("data", {})
        status = run_data.get("status")
        logger.info("Apify run %s poll #%d: status=%s", run_id, attempt + 1, status)
        if status not in _IN_PROGRESS_STATUSES:
            return run_data
    return run_data


async def _run_actor_once(
    actor_id: str,
    input_data: dict,
    wait_secs: int,
) -> list[dict] | None:
    """Single Apify actor run. Returns items or None if dataset is empty."""
    token = _get_token()
    t0 = time.monotonic()

    async with httpx.AsyncClient(timeout=max(wait_secs + 30, 210)) as client:
        resp = await client.post(
            f"{APIFY_BASE}/acts/{actor_id}/runs",
            params={"token": token, "timeout": wait_secs, "waitForFinish": wait_secs},
            json=input_data,
        )
        resp.raise_for_status()
        run_data = resp.json().get("data", {})

        status = run_data.get("status")
        run_id = run_data.get("id")

        logger.info(
            "[apify-run] actor=%s run_id=%s initial_status=%s input=%s",
            actor_id, run_id, status, json.dumps(input_data, ensure_ascii=False)[:300],
        )

        if status in _IN_PROGRESS_STATUSES and run_id:
            logger.info(
                "[apify-run] actor=%s run_id=%s still %s after waitForFinish, polling…",
                actor_id, run_id, status,
            )
            run_data = await _wait_for_run(client, run_id, token)
            status = run_data.get("status")

        elapsed = time.monotonic() - t0
        usage_usd = run_data.get("usageTotalUsd")
        stats = run_data.get("stats") or {}

        if status != "SUCCEEDED":
            logger.error(
                "[apify-run] FAILED actor=%s run_id=%s status=%s "
                "elapsed=%.1fs usage=$%s stats=%s",
                actor_id, run_id, status, elapsed, usage_usd,
                json.dumps(stats, default=str)[:200],
            )
            _record_scrape_result(False)
            raise DownloadError(f"Apify actor {actor_id} failed: status={status}")

        dataset_id = run_data.get("defaultDatasetId")
        if not dataset_id:
            logger.error(
                "[apify-run] NO DATASET actor=%s run_id=%s elapsed=%.1fs",
                actor_id, run_id, elapsed,
            )
            _record_scrape_result(False)
            raise DownloadError(f"No dataset in Apify run response for {actor_id}")

        ds_resp = await client.get(
            f"{APIFY_BASE}/datasets/{dataset_id}/items",
            params={"token": token, "format": "json"},
        )
        ds_resp.raise_for_status()
        items = ds_resp.json()

        if not isinstance(items, list) or not items:
            logger.warning(
                "[apify-run] EMPTY DATASET actor=%s run_id=%s dataset=%s "
                "elapsed=%.1fs usage=$%s",
                actor_id, run_id, dataset_id, elapsed, usage_usd,
            )
            _record_scrape_result(False)
            return None  # empty dataset — caller may retry

        # Log summary of first item for diagnostics
        logger.info(
            "[apify-run] OK actor=%s run_id=%s items=%d elapsed=%.1fs "
            "usage=$%s first_item_keys=%s",
            actor_id, run_id, len(items), elapsed, usage_usd,
            list(items[0].keys()),
        )

        _record_scrape_result(True)

        # Cost tracking (no-op if no tracker active)
        from app.core.cost_tracker import track_apify
        track_apify(usage_usd)

        return items


_MAX_EMPTY_RETRIES = 2  # retries on empty dataset only (3 attempts total)


async def run_actor(
    actor_id: str,
    input_data: dict,
    timeout: int | None = None,
) -> list[dict]:
    """Run an Apify actor and return dataset items.

    Retries up to _MAX_EMPTY_RETRIES times on empty dataset,
    subject to budget gate and global fail-rate check.
    Non-empty failures (bad status) raise immediately.
    """
    wait_secs = timeout or settings.apify_timeout

    for attempt in range(1 + _MAX_EMPTY_RETRIES):
        if attempt > 0:
            if not _should_retry_scrape():
                logger.warning(
                    "[apify-retry] Fail rate too high, skipping retry for %s",
                    actor_id,
                )
                break
            delay = 5 * attempt  # 5s, 10s
            logger.info(
                "[apify-retry] Empty dataset from %s, retry in %ds (attempt %d/%d)",
                actor_id, delay, attempt + 1, 1 + _MAX_EMPTY_RETRIES,
            )
            await asyncio.sleep(delay)

        await _check_budget_gate(
            caller=f"run_actor:{actor_id}" if attempt == 0
            else f"run_actor_retry:{actor_id}:{attempt}",
        )

        items = await _run_actor_once(actor_id, input_data, wait_secs)
        if items is not None:
            return items

    raise DownloadError(
        f"Apify actor {actor_id} returned empty dataset "
        f"after {1 + _MAX_EMPTY_RETRIES} attempts"
    )


async def run_actor_kv(
    actor_id: str,
    input_data: dict,
    timeout: int | None = None,
    record_key: str = "OUTPUT",
) -> dict | list:
    """Run an Apify actor and read result from key-value store.

    Some actors write to KV store instead of dataset.
    """
    await _check_budget_gate(caller=f"run_actor_kv:{actor_id}")

    token = _get_token()
    wait_secs = timeout or settings.apify_timeout

    async with httpx.AsyncClient(timeout=max(wait_secs + 30, 210)) as client:
        resp = await client.post(
            f"{APIFY_BASE}/acts/{actor_id}/runs",
            params={"token": token, "timeout": wait_secs, "waitForFinish": wait_secs},
            json=input_data,
        )
        resp.raise_for_status()
        run_data = resp.json().get("data", {})

        status = run_data.get("status")
        run_id = run_data.get("id")

        if status in _IN_PROGRESS_STATUSES and run_id:
            logger.info(
                "Apify actor %s run %s still %s, polling...",
                actor_id, run_id, status,
            )
            run_data = await _wait_for_run(client, run_id, token)
            status = run_data.get("status")

        if status != "SUCCEEDED":
            raise DownloadError(f"Apify actor {actor_id} failed: status={status}")

        kv_store_id = run_data.get("defaultKeyValueStoreId")
        if not kv_store_id:
            raise DownloadError(f"No KV store in Apify run response for {actor_id}")

        kv_resp = await client.get(
            f"{APIFY_BASE}/key-value-stores/{kv_store_id}/records/{record_key}",
            params={"token": token},
        )
        kv_resp.raise_for_status()

        # Cost tracking (no-op if no tracker active)
        from app.core.cost_tracker import track_apify
        track_apify(run_data.get("usageTotalUsd"))

        return kv_resp.json()
