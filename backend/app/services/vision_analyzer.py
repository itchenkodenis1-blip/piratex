import asyncio
import base64
import json
from pathlib import Path
from typing import Callable, Optional

from openai import AsyncOpenAI

from app.config import settings
from app.core.exceptions import VisionAnalysisError
from app.schemas.analysis import FrameAnalysis, SceneType, TranscriptSegment

LANGUAGE_NAMES = {
    "ru": "Russian",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "pt": "Portuguese",
    "de": "German",
}

FRAME_ANALYSIS_PROMPT = """Analyze this video frame from a short-form reel/video.
Respond entirely in {target_language}. All text fields must be in {target_language}.
For "screen_text": transcribe visible text as-is (original language), then add a translation in parentheses if the original language differs from {target_language}.
Return ONLY valid JSON:
{{
  "screen_text": ["visible text (translation if needed)"],
  "visual_description": "detailed description in {target_language}",
  "scene_type": "one of: talking_head, screencast, animation, text_card, split_screen, b_roll",
  "ui_elements": ["UI elements described in {target_language}"]
}}"""


def _find_transcript_at(
    segments: list[TranscriptSegment], timestamp: float
) -> Optional[str]:
    """Find transcript text that overlaps with the given timestamp."""
    for seg in segments:
        if seg.start <= timestamp <= seg.end:
            return seg.text
    # If no exact overlap, find nearest segment within 2 seconds
    closest = None
    min_dist = float("inf")
    for seg in segments:
        dist = min(abs(seg.start - timestamp), abs(seg.end - timestamp))
        if dist < min_dist and dist < 2.0:
            min_dist = dist
            closest = seg.text
    return closest


async def _analyze_single_frame(
    client: AsyncOpenAI,
    frame_path: Path,
    timestamp: float,
    frame_index: int,
    transcript_segment: Optional[str],
    language: str = "en",
) -> FrameAnalysis:
    """Analyze a single frame with GPT-4o vision."""
    lang_name = LANGUAGE_NAMES.get(language, "English")
    prompt = FRAME_ANALYSIS_PROMPT.format(target_language=lang_name)

    with open(frame_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    data = None
    last_error = None
    for attempt in range(3):
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=settings.vision_model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{b64}",
                                        "detail": "low",
                                    },
                                },
                            ],
                        }
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=500,
                ),
                timeout=60,
            )

            content = response.choices[0].message.content
            if content is None:
                last_error = "GPT-4o returned empty content"
                await asyncio.sleep(1)
                continue

            data = json.loads(content)

            # Cost tracking — only after successful parse (avoid 3x on retries)
            from app.core.cost_tracker import track_vision
            track_vision(response)
            break
        except Exception as e:
            last_error = str(e)
            if attempt < 2:
                await asyncio.sleep(1)

    if data is None:
        # Return a fallback instead of crashing the whole pipeline
        minutes, seconds = divmod(int(timestamp), 60)
        return FrameAnalysis(
            frame_index=frame_index,
            timestamp=timestamp,
            timecode=f"{minutes:02d}:{seconds:02d}",
            frame_path=str(frame_path),
            screen_text=[],
            visual_description=f"[Analysis failed: {last_error}]",
            scene_type=SceneType.B_ROLL,
            ui_elements=[],
            transcript_segment=transcript_segment,
        )

    minutes, seconds = divmod(int(timestamp), 60)

    scene_type_raw = data.get("scene_type", "b_roll")
    try:
        scene_type = SceneType(scene_type_raw)
    except ValueError:
        scene_type = SceneType.B_ROLL

    return FrameAnalysis(
        frame_index=frame_index,
        timestamp=timestamp,
        timecode=f"{minutes:02d}:{seconds:02d}",
        frame_path=str(frame_path),
        screen_text=data.get("screen_text", []),
        visual_description=data.get("visual_description", ""),
        scene_type=scene_type,
        ui_elements=data.get("ui_elements", []),
        transcript_segment=transcript_segment,
    )


async def analyze_frames(
    frame_paths: list[Path],
    timestamps: list[float],
    transcript_segments: list[TranscriptSegment],
    on_progress: Optional[Callable] = None,
    on_frame_done: Optional[Callable] = None,
    max_concurrent: int | None = None,
    api_key: str = "",
    language: str = "en",
) -> list[FrameAnalysis]:
    """Analyze all frames with GPT-4o vision, respecting concurrency limit."""
    if max_concurrent is None:
        max_concurrent = settings.max_concurrent_vision_calls

    from app.core.openai_client import get_openai_client
    client = get_openai_client(api_key)
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _analyze_with_limit(i: int, path: Path, ts: float):
        async with semaphore:
            segment_text = _find_transcript_at(transcript_segments, ts)
            result = await _analyze_single_frame(
                client, path, ts, i, segment_text, language=language
            )
            if on_frame_done:
                await on_frame_done(result)
            if on_progress:
                await on_progress(i, len(frame_paths))
            return result

    tasks = [
        _analyze_with_limit(i, path, ts)
        for i, (path, ts) in enumerate(zip(frame_paths, timestamps))
    ]
    results = await asyncio.gather(*tasks)
    return sorted(results, key=lambda r: r.timestamp)
