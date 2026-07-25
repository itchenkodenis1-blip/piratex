"""Retry helpers for external API calls (Anthropic, OpenAI).

Handles transient failures: overloaded (529), rate limits, timeouts,
connection errors. Retries with exponential backoff + jitter.

If Anthropic fails after all retries, falls back to OpenAI (GPT-4.1).
"""

import asyncio
import logging
import random

import anthropic
import httpx
import openai

logger = logging.getLogger(__name__)

_RETRYABLE_ANTHROPIC = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,  # 500, 529 (overloaded)
    httpx.ConnectError,
    httpx.ReadTimeout,
    TimeoutError,
    ConnectionResetError,
    BrokenPipeError,
)

_RETRYABLE_OPENAI = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    TimeoutError,
    ConnectionResetError,
    BrokenPipeError,
)

_MAX_ATTEMPTS = 5
_BASE_DELAY = 3  # seconds


def _delay_with_jitter(attempt: int) -> float:
    """Exponential backoff with ±25% jitter: 3s, 6s, 12s, 24s."""
    base = _BASE_DELAY * (2 ** attempt)
    jitter = base * 0.25 * (2 * random.random() - 1)  # ±25%
    return base + jitter


async def anthropic_create_with_retry(client, **kwargs):
    """Call client.messages.create() with retry on transient errors.

    Returns the API response on success, raises on permanent failure.
    """
    last_error = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return await client.messages.create(**kwargs)
        except _RETRYABLE_ANTHROPIC as e:
            last_error = e
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _delay_with_jitter(attempt)
                logger.warning(
                    "Anthropic API attempt %d/%d failed (%s: %s), retrying in %.1fs",
                    attempt + 1, _MAX_ATTEMPTS, type(e).__name__, str(e)[:120], delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Anthropic API failed after %d attempts: %s",
                    _MAX_ATTEMPTS, e,
                )
    raise last_error


async def openai_create_with_retry(client, **kwargs):
    """Call client.chat.completions.create() with retry on transient errors.

    Returns the API response on success, raises on permanent failure.
    """
    last_error = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return await client.chat.completions.create(**kwargs)
        except _RETRYABLE_OPENAI as e:
            last_error = e
            if attempt < _MAX_ATTEMPTS - 1:
                delay = _delay_with_jitter(attempt)
                logger.warning(
                    "OpenAI API attempt %d/%d failed (%s: %s), retrying in %.1fs",
                    attempt + 1, _MAX_ATTEMPTS, type(e).__name__, str(e)[:120], delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "OpenAI API failed after %d attempts: %s",
                    _MAX_ATTEMPTS, e,
                )
    raise last_error
