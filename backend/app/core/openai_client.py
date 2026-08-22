"""Pooled OpenAI-compatible async clients routed through OpenRouter.

Chat/vision completions go through OpenRouter.
Whisper transcription goes through a separate provider (Groq by default)
because OpenRouter doesn't support /audio/transcriptions.
"""

import httpx
from openai import AsyncOpenAI

from app.config import settings

_chat_clients: dict[str, AsyncOpenAI] = {}
_whisper_clients: dict[str, AsyncOpenAI] = {}


def get_openai_client(api_key: str = "") -> AsyncOpenAI:
    """Get or create an AsyncOpenAI client for chat/vision completions via OpenRouter."""
    # Prefer OpenRouter; fall back to direct OpenAI if no OpenRouter key
    if settings.openrouter_api_key:
        key = api_key or settings.openrouter_api_key
        base_url = settings.openrouter_base_url
    else:
        key = api_key or settings.openai_api_key
        base_url = None  # default OpenAI

    cache_key = f"{base_url}:{key}"
    client = _chat_clients.get(cache_key)
    if client is None:
        kwargs: dict = {
            "api_key": key,
            "timeout": httpx.Timeout(90.0, connect=10.0),
        }
        if base_url:
            kwargs["base_url"] = base_url
            kwargs["default_headers"] = {
                "HTTP-Referer": "https://videorentgen.ru",
                "X-Title": "VideoRentgen",
            }
        client = AsyncOpenAI(**kwargs)
        _chat_clients[cache_key] = client
    return client


def get_whisper_client(api_key: str = "") -> AsyncOpenAI:
    """Get or create an AsyncOpenAI client for Whisper transcription.

    Uses a separate provider (Groq by default) since OpenRouter
    doesn't support audio endpoints.
    """
    key = api_key or settings.whisper_api_key or settings.openai_api_key
    base_url = settings.whisper_base_url if settings.whisper_api_key else None

    cache_key = f"whisper:{base_url}:{key}"
    client = _whisper_clients.get(cache_key)
    if client is None:
        kwargs: dict = {
            "api_key": key,
            "timeout": httpx.Timeout(120.0, connect=10.0),
        }
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncOpenAI(**kwargs)
        _whisper_clients[cache_key] = client
    return client
