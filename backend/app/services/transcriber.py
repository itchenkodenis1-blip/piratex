import asyncio
import logging
from pathlib import Path

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.config import settings
from app.core.exceptions import TranscriptionError
from app.schemas.analysis import TranscriptSegment, TranscriptWord

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_RETRYABLE = (APIConnectionError, APITimeoutError, RateLimitError, TimeoutError, OSError)


async def transcribe(audio_path: Path, api_key: str = "") -> list[TranscriptSegment]:
    """Transcribe audio via OpenAI Whisper API with word-level timestamps."""
    from app.core.openai_client import get_whisper_client
    client = get_whisper_client(api_key)

    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with open(audio_path, "rb") as f:
                response = await client.audio.transcriptions.create(
                    model=settings.whisper_model,
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["word", "segment"],
                )
            break
        except _RETRYABLE as e:
            last_error = e
            if attempt < _MAX_ATTEMPTS - 1:
                delay = 2 ** attempt  # 1s, 2s
                logger.warning("Whisper attempt %d failed (%s), retrying in %ds", attempt + 1, e, delay)
                await asyncio.sleep(delay)
        except Exception as e:
            raise TranscriptionError(f"Whisper API error: {e}") from e
    else:
        raise TranscriptionError(f"Whisper API error after {_MAX_ATTEMPTS} attempts: {last_error}") from last_error

    # Cost tracking: estimate from audio file duration
    from app.core.cost_tracker import track_whisper
    duration = getattr(response, "duration", 0) or 0
    if not duration:
        # Fallback: estimate from segments
        all_segs = response.segments or []
        if all_segs:
            duration = max(s.end for s in all_segs)
    track_whisper(duration)

    segments = []
    for seg in response.segments or []:
        words = []
        if hasattr(seg, "words") and seg.words:
            words = [
                TranscriptWord(word=w.word.strip(), start=w.start, end=w.end)
                for w in seg.words
            ]
        segments.append(
            TranscriptSegment(
                text=seg.text.strip(),
                start=seg.start,
                end=seg.end,
                words=words,
            )
        )

    return segments
