"""Lightweight per-job cost accumulator using contextvars.

Usage in worker tasks:
    tracker = init_cost_tracker()
    ... run pipeline ...
    job.cost_breakdown = tracker.to_dict()

Services call track_*() helpers — if no tracker is active, calls are no-ops.
No function signature changes needed.
"""

import contextvars
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (USD) — March 2026
_ANTHROPIC_PRICING = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-5-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
    "sonnet": {"input": 3.0, "output": 15.0},
    "haiku": {"input": 0.80, "output": 4.0},
}

_OPENAI_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "output": 0.60},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    "gpt-4.1-2025-04-14": {"input": 2.0, "output": 8.0},
    "openai/gpt-4.1": {"input": 2.0, "output": 8.0},
    "gpt-5.4": {"input": 2.5, "output": 15.0},
    "openai/gpt-5.4": {"input": 2.5, "output": 15.0},
}

_WHISPER_PRICE_PER_MINUTE = 0.006

# Context variable — one tracker per async task chain
_current_tracker: contextvars.ContextVar["CostTracker | None"] = contextvars.ContextVar(
    "cost_tracker", default=None
)


@dataclass
class CostTracker:
    """Accumulates API costs during a single job's processing pipeline."""

    apify_usd: float = 0.0
    whisper_usd: float = 0.0
    vision_usd: float = 0.0
    sonnet_usd: float = 0.0
    haiku_usd: float = 0.0
    fallback_usd: float = 0.0
    _vision_calls: int = field(default=0, repr=False)

    def to_dict(self) -> dict:
        total = self.apify_usd + self.whisper_usd + self.vision_usd + self.sonnet_usd + self.haiku_usd + self.fallback_usd
        d = {
            "apify_usd": round(self.apify_usd, 6),
            "whisper_usd": round(self.whisper_usd, 6),
            "vision_usd": round(self.vision_usd, 6),
            "sonnet_usd": round(self.sonnet_usd, 6),
            "haiku_usd": round(self.haiku_usd, 6),
            "total_usd": round(total, 6),
            "vision_calls": self._vision_calls,
        }
        if self.fallback_usd > 0:
            d["fallback_usd"] = round(self.fallback_usd, 6)
        return d


def init_cost_tracker() -> CostTracker:
    """Create a new tracker and set it as current. Call at the start of a job."""
    tracker = CostTracker()
    _current_tracker.set(tracker)
    return tracker


def get_cost_tracker() -> CostTracker | None:
    """Get the current tracker (if any)."""
    return _current_tracker.get(None)


# --- Track helpers (no-op if no tracker active) ---

def track_apify(usage_usd: float | None) -> None:
    tracker = _current_tracker.get(None)
    if tracker and usage_usd and usage_usd > 0:
        tracker.apify_usd += usage_usd


def track_whisper(audio_duration_seconds: float) -> None:
    tracker = _current_tracker.get(None)
    if tracker and audio_duration_seconds > 0:
        tracker.whisper_usd += (audio_duration_seconds / 60.0) * _WHISPER_PRICE_PER_MINUTE


def track_vision(response) -> None:
    """Track GPT-4o-mini vision call cost from OpenAI response."""
    tracker = _current_tracker.get(None)
    if not tracker:
        return
    usage = getattr(response, "usage", None)
    if not usage:
        return
    model = getattr(response, "model", "openai/gpt-4o-mini")
    pricing = _OPENAI_PRICING.get(model, _OPENAI_PRICING["openai/gpt-4o-mini"])
    cost = (
        (usage.prompt_tokens * pricing["input"] / 1_000_000)
        + (usage.completion_tokens * pricing["output"] / 1_000_000)
    )
    tracker.vision_usd += cost
    tracker._vision_calls += 1


def track_anthropic(response) -> None:
    """Track Claude API call cost from Anthropic response."""
    tracker = _current_tracker.get(None)
    if not tracker:
        return
    usage = getattr(response, "usage", None)
    if not usage:
        return
    model = getattr(response, "model", "")

    pricing = None
    for key, p in _ANTHROPIC_PRICING.items():
        if key in model:
            pricing = p
            break
    if not pricing:
        pricing = _ANTHROPIC_PRICING["sonnet"]

    cost = (
        (usage.input_tokens * pricing["input"] / 1_000_000)
        + (usage.output_tokens * pricing["output"] / 1_000_000)
    )

    if "haiku" in model:
        tracker.haiku_usd += cost
    else:
        tracker.sonnet_usd += cost


def track_openai_text(response) -> None:
    """Track OpenAI text generation call cost (fallback model)."""
    tracker = _current_tracker.get(None)
    if not tracker:
        return
    usage = getattr(response, "usage", None)
    if not usage:
        return
    model = getattr(response, "model", "openai/gpt-4.1")
    pricing = _OPENAI_PRICING.get(model, _OPENAI_PRICING.get("openai/gpt-4.1", {"input": 2.0, "output": 8.0}))
    cost = (
        (usage.prompt_tokens * pricing["input"] / 1_000_000)
        + (usage.completion_tokens * pricing["output"] / 1_000_000)
    )
    tracker.fallback_usd += cost
