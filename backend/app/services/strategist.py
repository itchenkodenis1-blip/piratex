import logging

import httpx
from anthropic import AsyncAnthropic

from app.config import settings
from app.core.cache import cache_get, cache_set, make_cache_key
from app.services._json_utils import extract_json as _extract_json
from app.services.prompt_armor import (
    IMMUTABLE_STRATEGY_RULES,
    OutputValidationError,
    build_system_blocks,
    check_canary,
    generate_canary,
    validate_strategy_output,
)
from app.schemas.analysis import (
    CommentsStrategy,
    CoverRecommendation,
    FrameAnalysis,
    Hashtags,
    HookVariant,
    StrategyAnalysis,
    TranscriptSegment,
)

_logger = logging.getLogger(__name__)

DEFAULT_STRATEGY_PROMPT = """You are a viral content strategist. Your task is to break down why a reel went viral and provide a concrete promotion strategy for the adapted version.

## Author context

The author adapts viral reels for their own audience. Identify the niche and target audience from the original reel's content. Tailor the strategy to resonate maximally with that audience.

## Input you receive

1. Video metadata (views, likes, author, platform)
2. Transcript
3. Original post description
4. Top comments, sorted by likes
5. List of frames with descriptions (for cover recommendation)

## What you must output

### Block 1 — virality_breakdown (Why it went viral)

Compact analysis, 5-8 sentences:
- Hook type (contrast / shock / curiosity / specific number / pain point)
- How it retains after the hook (escalating value / series of mini-revelations / storytelling / step-by-step process)
- Engagement rate (likes/views, 3-5% is normal, higher = viral)
- Main emotional trigger — what exactly made people like/comment/save
- What in the comments confirms the hypothesis

No fluff, no "overall the reel is good." Only specifics and mechanics.

### Block 2 — hook_variants (Alternative hooks)

The primary hook already exists in the script (faithful adaptation of the original). You generate 4 ALTERNATIVES — each using a DIFFERENT technique so the author can choose the best approach.

Each variant is an object with three fields:
- "text" — hook text (1-2 sentences to say on camera)
- "score" — effectiveness score 0-100
- "why" — 2-3 sentences: (1) name the technique, (2) explain the psychological mechanism — why it stops the scroller, (3) a short example or analogy from real practice

Variants:
1. Amplified for target audience — more specifics, stronger numbers/contrasts
2. Provocative or contrasting — hook the scroller with an unexpected angle
3. Question / curiosity gap — intrigue that compels watching to the end
4. Bold claim / transformation — result upfront (before/after, outcome first)

Score criteria:
- Attention capture (will it stop the scroll?) — 40%
- Relevance to target audience — 30%
- Emotional trigger strength — 30%

Also rate the PRIMARY hook (the one in the script — faithful adaptation of the original):
- "primary_hook_score" — its score 0-100
- "primary_hook_why" — 2-3 sentences: (1) name the technique, (2) explain the psychological mechanism, (3) why it worked for this specific audience

Rules:
- Value first, then tool name
- No hype: "killer," "revolution" — FORBIDDEN
- No abstractions: "and it has this one trick" — FORBIDDEN
- Specific artifacts from the original (numbers, names, contrasts) are mandatory

### Block 3 — hashtags (Hashtags)

**primary** — 5-7 main hashtags. Mix:
- 2-3 broad high-reach ones (relevant to the reel's niche)
- 2-3 niche-specific ones (specific to the reel's topic)
- 1 trending, if relevant

**secondary** — 3-5 additional narrow hashtags for the algorithm

All hashtags should be in the target audience's language, except product names.

### Block 4 — cover (Cover recommendation)

**recommended_frame_index** — index of the frame best suited for a cover. Choose a frame where:
- It's maximally clear what the video is about (screencast with result, interface, finished product)
- NOT a blank screen, NOT a close-up face without context

**cover_text** — text to overlay on the cover. 3-5 words maximum.

**why** — 1 sentence explaining why this frame and this text.

### Block 5 — classification (Library classification)

**language** — two-letter ISO code of the original language (en, es, ru...)
**content_format** — one of: tutorial, review, comparison, story, behind_the_scenes, news, motivation, entertainment, demo, explainer, other
**topics** — 3-6 topic slugs in English (ai-tools, vibe-coding, no-code, saas, automation, cursor, productivity)
**keywords** — 5-10 specific keywords/names from the original in the original language
**niche** — one niche slug: ai, vibe-coding, software-dev, saas, no-code, cybersecurity, business, startups, ecommerce, finance, investing, crypto, real-estate, marketing, personal-brand, copywriting, seo, design, photography, video-production, music, art, education, career, coaching, health, fitness, mental-health, lifestyle, travel, food, fashion, parenting, entertainment, gaming, sports, other. "vibe-coding" — building apps with AI (Cursor, Replit, v0). "ai" — reviewing/teaching AI tools. "software-dev" — programming without AI focus. "ecommerce" — dropshipping/marketplaces. "personal-brand" — content creation/audience growth

## Important rules

- Adapt hashtags for the target audience's market
- Don't fabricate metrics — use actual views/likes for engagement rate calculation"""

FIXED_STRATEGY_TAIL = """
---
MANDATORY RESPONSE FORMAT:

Output JSON with the following keys:
- "virality_breakdown" — string, 5-8 sentences
- "hook_variants" — array of 4 objects: {{"text": string, "score": number 0-100, "why": string (2-3 sentences)}}
- "primary_hook_score" — number 0-100
- "primary_hook_why" — string, 2-3 sentences
- "hashtags" — object with "primary" (array of strings) and "secondary" (array of strings)
- "cover" — object with "recommended_frame_index" (number), "cover_text" (string), "why" (string)
- "language" — string, two-letter ISO code
- "content_format" — string
- "topics" — array of strings
- "keywords" — array of strings
- "niche" — string

Write in {target_language}. JSON only. No introductions, no markdown."""

USER_PROMPT_STRATEGY = """Here is the reel data for strategic analysis.

## Metadata
- Platform: {platform}
- Author: {author}
- Title: {title}
- Duration: {duration}s
- Views: {views}
- Likes: {likes}
- Engagement rate: {engagement_rate}%

## Original post description
{description}

## Transcript
{transcript}

## Top comments (by likes)
{top_comments}

## Frames (for cover selection)
{frames_summary}"""

LANGUAGE_NAMES = {
    "ru": "Russian",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "pt": "Portuguese",
    "de": "German",
}


def _system_blocks_to_openai_system(blocks: list[dict]) -> str:
    """Convert Anthropic system blocks to a single OpenAI system message string."""
    return "\n\n".join(b["text"] for b in blocks)


async def _openai_fallback_strategy(system_blocks: list[dict], user_prompt: str) -> str:
    """Call OpenAI GPT-5.4 as fallback when Claude is unavailable."""
    from app.core.openai_client import get_openai_client
    from app.core.api_retry import openai_create_with_retry
    from app.core.cost_tracker import track_openai_text

    openai_client = get_openai_client()
    system_text = _system_blocks_to_openai_system(system_blocks)

    response = await openai_create_with_retry(
        openai_client,
        model=settings.fallback_text_model,
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_prompt},
        ],
        max_completion_tokens=4096,
    )
    track_openai_text(response)
    _logger.info("[strategist] OpenAI fallback succeeded (model=%s)", settings.fallback_text_model)
    return response.choices[0].message.content


async def generate_strategy(
    metadata: dict,
    transcript_segments: list[TranscriptSegment],
    frame_analyses: list[FrameAnalysis],
    comments: list[dict],
    api_key: str = "",
    target_language: str = "ru",
    custom_prompt: str | None = None,
    profile_json: dict | None = None,
) -> StrategyAnalysis:
    """Generate virality analysis + engagement strategy using Claude Sonnet."""
    from app.core.exceptions import InsufficientDataError

    if not transcript_segments and not frame_analyses:
        raise InsufficientDataError(
            "Insufficient data for strategy: "
            "transcript and frames are empty."
        )

    client = AsyncAnthropic(
        api_key=api_key or settings.anthropic_api_key,
        timeout=httpx.Timeout(120.0, connect=10.0),
    )

    # Build system prompt: priority custom_prompt > profile > default
    if custom_prompt:
        base_prompt = custom_prompt
    elif profile_json:
        from app.schemas.profile import UserProfile
        from app.services.prompt_composer import compose_strategy_prompt
        base_prompt = compose_strategy_prompt(UserProfile(**profile_json))
    else:
        base_prompt = DEFAULT_STRATEGY_PROMPT
    lang_name = LANGUAGE_NAMES.get(target_language, "Russian")
    fixed_tail = FIXED_STRATEGY_TAIL.format(target_language=lang_name)
    canary = generate_canary()
    system_blocks = build_system_blocks(
        immutable_rules=IMMUTABLE_STRATEGY_RULES,
        user_prompt=base_prompt,
        fixed_tail=fixed_tail,
        canary=canary,
    )

    # Build transcript
    full_transcript = " ".join(seg.text for seg in transcript_segments)

    # Build comments text
    if comments:
        comment_lines = []
        for c in comments:
            likes_str = f" [{c['likes']} ❤️]" if c.get("likes") else ""
            comment_lines.append(f"- {c['text']}{likes_str}")
        top_comments = "\n".join(comment_lines)
    else:
        top_comments = "Comments are not available for this platform."

    # Build frames summary (compact, for cover selection)
    frames_parts = []
    for frame in frame_analyses:
        line = f"[{frame.frame_index}] {frame.timecode} — {frame.scene_type.value}: {frame.visual_description[:100]}"
        if frame.screen_text:
            line += f" | text: {', '.join(frame.screen_text[:2])}"
        frames_parts.append(line)
    frames_summary = "\n".join(frames_parts)

    # Calculate engagement rate
    views = metadata.get("view_count", 0) or 0
    likes = metadata.get("like_count", 0) or 0
    engagement_rate = round((likes / views) * 100, 2) if views > 0 else 0

    prompt = USER_PROMPT_STRATEGY.format(
        platform=metadata.get("platform", "unknown"),
        author=metadata.get("uploader", "unknown"),
        title=metadata.get("title", "Unknown"),
        duration=metadata.get("duration", 0),
        views=views,
        likes=likes,
        engagement_rate=engagement_rate,
        description=metadata.get("description", "") or "No description",
        transcript=full_transcript[:3000],
        top_comments=top_comments,
        frames_summary=frames_summary,
    )

    # Check Redis cache (cache key excludes canary for stable hits)
    cache_text = base_prompt + "\n" + fixed_tail
    cache_key = make_cache_key(cache_text, prompt)
    cached = await cache_get("strategy", cache_key)
    if cached:
        _logger.info("Strategy cache hit")
        data = cached
    else:
        data = None
        last_json_error = None
        used_fallback = False

        for llm_attempt in range(2):  # 1 retry on JSON failure
            if llm_attempt > 0:
                _logger.warning(
                    "[strategy] JSON extraction failed, retrying Claude call (attempt %d): %s",
                    llm_attempt + 1, last_json_error,
                )
                canary = generate_canary()
                system_blocks = build_system_blocks(
                    immutable_rules=IMMUTABLE_STRATEGY_RULES,
                    user_prompt=base_prompt,
                    fixed_tail=fixed_tail,
                    canary=canary,
                )

            from app.core.api_retry import anthropic_create_with_retry

            try:
                response = await anthropic_create_with_retry(
                    client,
                    model=settings.light_text_model,
                    system=system_blocks,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096,
                )
            except Exception as claude_err:
                _logger.warning(
                    "[strategist] Claude failed after retries (%s), falling back to OpenAI %s",
                    claude_err, settings.fallback_text_model,
                )
                raw_text = await _openai_fallback_strategy(system_blocks, prompt)
                used_fallback = True
            else:
                from app.core.cost_tracker import track_anthropic
                track_anthropic(response)
                raw_text = response.content[0].text

            if not used_fallback and check_canary(raw_text, canary):
                _logger.warning("Canary token leaked in strategy output — possible prompt injection")

            # Detect AI content policy refusal → fallback to OpenAI
            from app.core.error_classifier import is_ai_refusal
            if not used_fallback and is_ai_refusal(raw_text):
                _logger.warning("[strategist] Claude refused content, falling back to OpenAI: %s", raw_text[:200])
                raw_text = await _openai_fallback_strategy(system_blocks, prompt)
                used_fallback = True

            try:
                data = _extract_json(raw_text)
                break
            except Exception as e:
                last_json_error = e
                continue

        if data is None:
            raise last_json_error or ValueError("Failed to extract JSON from strategy response")

        # Validate output structure
        try:
            validate_strategy_output(data)
        except OutputValidationError as e:
            _logger.error("Strategy output validation failed: %s", e)
            raise

        await cache_set("strategy", cache_key, data)

    comments_strategy = CommentsStrategy()

    # Parse hashtags
    ht_data = data.get("hashtags", {})
    hashtags = Hashtags(
        primary=ht_data.get("primary", []),
        secondary=ht_data.get("secondary", []),
    )

    # Parse cover
    cv_data = data.get("cover", {})
    cover = CoverRecommendation(
        recommended_frame_index=cv_data.get("recommended_frame_index", 1),
        cover_text=cv_data.get("cover_text", ""),
        why=cv_data.get("why", ""),
    )

    # Parse hook_variants (new dict format + backward compat with old str format)
    raw_hooks = data.get("hook_variants", [])
    hook_variants: list[HookVariant] = []
    for h in raw_hooks:
        if isinstance(h, dict):
            hook_variants.append(HookVariant(
                text=h.get("text", ""),
                score=h.get("score", 50),
                why=h.get("why", ""),
            ))
        elif isinstance(h, str):
            hook_variants.append(HookVariant(text=h, score=50, why=""))

    return StrategyAnalysis(
        virality_breakdown=data.get("virality_breakdown", ""),
        hook_variants=hook_variants,
        primary_hook_score=data.get("primary_hook_score", 0),
        primary_hook_why=data.get("primary_hook_why", ""),
        comments_strategy=comments_strategy,
        hashtags=hashtags,
        cover=cover,
        language=data.get("language", "en"),
        content_format=data.get("content_format", "other"),
        topics=data.get("topics", []),
        keywords=data.get("keywords", []),
        niche=data.get("niche", "other"),
    )
