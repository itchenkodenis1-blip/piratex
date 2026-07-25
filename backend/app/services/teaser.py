"""Build truncated teaser results for anonymous users.

Full data stays in the DB — only the API response is trimmed.
When the user registers, the same job_id returns the full result.
"""
from __future__ import annotations

import math
from typing import Any

from app.models.job import Job

# How much content anonymous users see
TEASER_FRAMES_MAX = 3
TEASER_TRANSCRIPT_PCT = 20  # percent of segments
TEASER_SCRIPT_PCT = 20      # percent of characters


def build_teaser_result(job: Job) -> dict[str, Any]:
    """Return truncated fields + teaser_limits metadata."""
    # --- Frames (all frames visible — they showcase the product) ---
    raw_frames = job.frames or []
    frames_total = len(raw_frames)
    frames_shown = frames_total
    teaser_frames = raw_frames

    # --- Transcript ---
    raw_transcript = job.transcript or []
    transcript_total = len(raw_transcript)
    transcript_count = max(1, math.ceil(transcript_total * TEASER_TRANSCRIPT_PCT / 100))
    teaser_transcript = raw_transcript[:transcript_count]

    # --- Adaptation summary ---
    raw_summary = job.adaptation_summary or {}
    full_script = raw_summary.get("script", "")
    script_cutoff = max(1, math.ceil(len(full_script) * TEASER_SCRIPT_PCT / 100))
    teaser_script = full_script[:script_cutoff]
    if len(full_script) > script_cutoff:
        teaser_script += "\n\n…"

    teaser_summary: dict[str, Any] = {
        "script": teaser_script,
        # Everything else is hidden
        "description": None,
        "editor_instructions": None,
        "hook_variants": None,
        "hashtags": None,
        "virality_breakdown": None,
        "primary_hook_score": None,
        "primary_hook_why": None,
        "comments_strategy": None,
    }

    teaser_limits = {
        "frames_shown": frames_shown,
        "frames_total": frames_total,
        "transcript_pct": TEASER_TRANSCRIPT_PCT,
        "script_pct": TEASER_SCRIPT_PCT,
    }

    return {
        "frames": teaser_frames,
        "transcript": teaser_transcript,
        "adaptation_summary": teaser_summary,
        "teaser_limits": teaser_limits,
    }
