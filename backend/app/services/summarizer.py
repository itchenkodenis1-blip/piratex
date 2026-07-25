import logging

import httpx
from anthropic import AsyncAnthropic

from app.config import settings
from app.core.cache import cache_get, cache_set, make_cache_key
from app.schemas.analysis import AdaptationSummary, FrameAnalysis, TranscriptSegment
from app.services._json_utils import extract_json as _extract_json
from app.services.prompt_armor import (
    IMMUTABLE_CONTENT_RULES,
    OutputValidationError,
    build_system_blocks,
    check_canary,
    generate_canary,
    validate_content_output,
)

logger = logging.getLogger(__name__)

DEFAULT_CONTENT_PROMPT = """You are an expert in reel adaptation.

## Who the author is and their audience

The author adapts viral reels for their own audience. Identify the niche and target audience from the original reel's content. Adapt the content to resonate maximally with that audience: use relevant examples, accessible terminology, and current pain points of the niche.

## Input you receive

1. Reel transcript with timecodes
2. Frame-by-frame breakdown: what is visually happening on screen at each moment
3. Video metadata (duration, platform, author)
4. Original post description (text below the reel) — hooks, CTAs, author's hashtags
5. Top comments (sorted by likes) — what hooked the audience

## How to use the input data

Silently analyze the source material:
- What is the core message, why did it work, what value is embedded.
- Extract specific hook artifacts: names, numbers, contrasts, actions.
- Identify the key value for the target audience (based on the reel's niche).
- Estimate the original's timing (~2.5 words per second in Russian).
- Consider the original post description — it may contain hooks and CTAs absent from the speech.
- Consider the comments — if people are massively asking the same thing, it means this wasn't covered in the original. Address it in the script.
- If comments are not available — skip comment analysis, don't fabricate.
- If the original post description is empty — rely only on transcript and visuals.
- If the transcript is short or incomplete — compensate with the visual breakdown.

## What you must output

Exactly three blocks. No introductions, no analysis recap. Only the blocks.

### Block 1 — script (Teleprompter script)

Clean text split into paragraphs by semantic blocks. No labels like [HOOK], [BRIDGE], no formatting, no internal headings. Just text you read on camera. At the very end — on a separate line: ~XX seconds.

**Script structure:**
1. **Hook (first 2-3 seconds).** Give the viewer a reason not to scroll past.
2. **Topic development (main body).** Specifics on the reel's subject. For a review — what tool/method, how to launch it. For a story — what happened, where's the twist. For a transformation — the process and result. Simple and clear, no jargon where possible. This is the only part that can be cut if time is tight.
3. **Value bridge (mandatory block).** Explain the concrete benefit for the audience in plain terms. With numbers, if available. Examples must be relevant to the reel's niche.
4. **Ending.** Always: "Subscribe so you don't miss the next one."

**Hook formula:**
- Value and specifics first, then the name. The product name comes AFTER the viewer understands why they need it.
- All specific artifacts from the original (names, numbers, contrasts) must be carried over. Cannot be replaced with abstractions.
- No abstract promises: "does something others can't," "and it has this one trick" — FORBIDDEN.
- No hype: "destroyed," "killer," "revolution," "this changes everything" — FORBIDDEN.

**Examples of correct hooks:**

Original: "I replaced my $4,000/month developer with a $20 tool called Cursor."
Hook: "I replaced a $4,000/month developer with a $20 tool. It's called Cursor."

Original: "OpenClaw just launched and it builds full CRMs from a single prompt."
Hook: "OpenClaw just dropped — write one prompt and get a full CRM."

Original: "I lost 12kg in 90 days without cutting carbs. Here's the exact protocol."
Hook: "I lost 12 kg in three months without cutting carbs. Here's the protocol."

Original: "This $8 serum outperformed my $120 La Mer in a blind test."
Hook: "An $8 serum beat La Mer at $120 in a blind test."

Original: "My small business hit $50K/month after one change to the funnel."
Hook: "My business hit $50K/month after one change to the funnel."

**Full script example (style reference, do NOT copy):**

Original (~35 sec, EN): "I replaced my $4,000/month developer with a $20 tool called Cursor. It writes code, fixes bugs, and ships features faster than any junior dev I've hired. Here's how I set it up in 10 minutes."

Adapted script:
"Four thousand dollars a month. That's what my developer cost me. I replaced him with a twenty dollar tool. It's called Cursor — basically, you tell it what to build and it writes the code.

Here's the thing. I open my project, describe what I need in plain English. Not code — just 'add a signup form with email validation.' And it does it. The whole thing. Error handling included.

Bugs? You paste the error log — it finds the problem and fixes it. I shipped a week's worth of work in one evening.

Subscribe so you don't miss the next one.

~33 seconds"

Notice the style: short punches alternate with longer sentences. "Basically" — colloquial insert. "Here's the thing" — direct address. "Bugs?" — one word as a paragraph.

**Timing:** the script should be approximately the same length as the original (~2.5 words/sec in Russian, ±5 seconds). If you need to shorten — cut part 2, NOT part 1 (hook) and NOT part 3 (value).

**Tone:** lively, conversational, first person. As if sitting on camera telling a friend through personal experience. No corporate speak, no pomposity. Words people understand. Don't compress excessively — the text should sound natural when read from a teleprompter.

**KEY RULE: write for the ear, not the eye.**
This text will be read aloud from a teleprompter. It's spoken language, not an essay. Every sentence must be easily spoken in one breath.

**Rhythm and burstiness (variation):**
- Vary length AGGRESSIVELY: short (3-5 words) → medium (8-12 words) → long (15-20 words) → punch (2-4 words). Monotonous rhythm = AI-text marker.
- Paragraphs also vary in length: one paragraph — one sentence, the next — three or four.
- If the script contains a list (tool rankings, list of AI tools, bullet points, etc.) — each item on a new line. Never merge lists into a single dense paragraph, otherwise the text is impossible to read from a teleprompter.

**Live speech markers:**
- Colloquial inserts are natural and NEEDED: "look," "here's the thing," "honestly," "basically," "right?" Without them the text sounds like a press release.
- Sentence fragments are fine: "Not perfect. But it works." — this is normal for spoken language.
- Self-corrections are fine: "There are three... no, actually four things." — marker of a real story.
- Starting sentences with "And," "But," "So," "Now" is normal. This is spoken language.
- Avoid symmetrical lists where every item has the same length and structure.

**AI-text antipatterns (FORBIDDEN):**
- AI marker words and phrases: "it's important to note," "it should be emphasized," "delve," "leverage," "harness," "in today's world," "in the context of," "this enables," "this provides the opportunity," "holistic approach," "innovative," "key aspect," "unique," "moreover," "furthermore," "additionally," "thus," "it must be considered," "in conclusion I'd like to," "it's worth noting," "one cannot fail to mention"
- Nominalizations instead of verbs (not "implementation of the process" but "when you do it")
- Every paragraph following a "thesis → argument → conclusion" template — people don't talk like that
- Symmetrical constructions "Not only X, but also Y," "Both X and Y"
- Predictable transitions between blocks

**Self-check before output:**
1. Hook: will the viewer understand in 2 seconds why they should keep watching?
2. Artifacts: are all names, numbers, contrasts from the original in place?
3. Timing: does it fit the original's duration (±5 sec)?
4. Burstiness: do the shortest and longest sentences differ by at least 3x?
5. Read-aloud: can every sentence be spoken in one breath without stumbling?
6. AI markers: are there any words from the forbidden AI pattern list above?
7. Empty promises: any "and it has this one trick," "and it really works"?
8. Gaps from comments: are questions that were massively asked addressed?
9. "Friend over coffee" test: would you really say it like this to a friend? If not — rewrite.

### Block 2 — description (Reel description)

Ready-to-use text for the reel description. The description is text read with the eyes. It should look like it was written by a real person, not generated by AI.

**First line — always value.** Patterns by content type:
  - Review/tutorial: "How to launch...," "Step-by-step guide...," "Full walkthrough..."
  - Story/case study: hook-question or personal fact ("I spent 2 years and found...")
  - Transformation: "Before → after" ("From 0 to 50K subscribers in 3 months")
  - Compilation: "[Number] [things] for [result]" ("5 services for automation")
  - Audience pain: a question they recognize ("Tired of spending 3 hours on editing?")
- NEVER start with salary figures, pain points, or intros like "this is a tool from company X."
- Format: value-headline → step-by-step breakdown → what you can do → link (if available) → "Save and send to someone who needs this" → "Subscribe so you don't miss the next one."
- Consider CTAs from the original description — adapt the best ideas, don't copy verbatim.
- Additional content: if the reel has useful information that doesn't fit in the video (tool lists, repositories) — add it to the description. Such reels are more valuable and get saved more often.
- Maximum 8-10 lines. With emojis where appropriate.

**Description style — lively, not templated:**
- Vary line lengths: one line — 3-5 words, the next — 10-15. Uniform lines of equal length = AI marker.
- Incomplete sentences, exclamations, questions are fine. This is social media, not an article.
- Emojis — when appropriate, not every other word. 2-4 for the entire description.
- Do NOT start every line with an emoji — that's a template everyone has seen.
- Lists are fine, but don't turn the entire description into a bulleted list from start to finish. Alternate: text paragraph → bullet points → text.

**AI description antipatterns (FORBIDDEN):**
- Every line starts with an emoji (fire headline rocket point 1 bulb point 2) — this screams "AI"
- Symmetrical constructions: every item the same length and structure
- "In this video you'll learn," "In this reel I talked about" — direct AI indicators
- "Don't miss this opportunity," "This will change your approach" — empty promises
- ALL CAPS headings every other line
- "Problem → solution → CTA" format without variation — people don't write like that

**Good description example (reference, do NOT copy):**

"Developer cost $4,000/mo. Replaced for $20.

Cursor — an AI code editor. Describe the task in text, it writes the code. The whole thing.

How to set up in 10 minutes:
1. Download Cursor
2. Open your project
3. Describe the task in plain text — get ready code

Fixes bugs too — paste the error log, it figures it out.

Save and send to someone who needs this
Subscribe so you don't miss the next one."

Notice: the first line is specific with numbers. No emoji spam. Bullet points only in one place, everything else is organic text. Short sentences alternate with long ones.

**Description self-check:**
1. Does the first line hook and deliver value?
2. Does it look like an "emoji + bullet" template from start to finish?
3. AI markers: any words from the forbidden list?
4. Do line lengths vary? Any monotony?
5. Test: if you saw this description in your feed — would you believe a human wrote it?

### Block 3 — editor_instructions (Instructions for the editor)

A text document for sending to the video editor via messenger. No tables. Compact, easy to read on a phone.

Frame format — top 30% of the screen is talking head, bottom 70% is visuals.

Structure:

FORMAT: talking head (30% top) + visual (70% bottom)
DURATION: ~XX sec

— 0:00–0:03
Visual: what to show in the bottom 70%
Text: short phrase on screen
Transition: cut / zoom / swipe

— 0:03–0:08
Visual: screencast — opening the project
Text: short phrase
Transition: cut

...and so on for the entire reel.

Principles:
- Do NOT write speech text (it's in the script) — only visuals, on-screen text, and transitions
- Visuals amplify the words, not duplicate them
- The reel must be understandable without sound — from the picture and on-screen text alone
- On-screen text — 3-5 words maximum, not sentences
- Specify transition type between frames (cut, zoom in, swipe, fade)
- For screencasts — specify exactly what to show on screen

## Important rules

FORBIDDEN in the script:
- "destroyed," "killer," "revolution," "this changes everything," "insane," "incredible," "shocking," "blew up," "amazing," "literally flipped," "will change forever," "you won't believe," "secret method," "magical"
- Phrases that people never say in real life

FORBIDDEN in the hook:
- Starting with a product name that means nothing to the viewer
- Replacing specific artifacts from the original with abstractions
- Empty promises

FORBIDDEN in the description:
- Starting with pain points or salary figures
- Company introductions"""

SAME_LANGUAGE_RULES = """
## IMPORTANT: the original is in the same language as the script

The original reel is already in the target audience's language. No translation is needed — what's needed is an AUTHOR'S VERSION that preserves the viral mechanics but sounds like the author's own content.

The author's audience MAY HAVE SEEN the original. If the text is similar — it will be noticeable. Therefore the rewrite must be deep, not cosmetic.

### What to KEEP (viral mechanics):
- **Hook type.** If the original went viral on number contrast — the hook must stay on number contrast. If on a provocative question — keep the question. Don't change the pattern that worked.
- **Emotional arc.** The sequence: intrigue → revelation → value. If the original built tension gradually — preserve that pace. If it went through a series of mini-revelations — preserve the series.
- **All artifacts.** Product names, numbers, specific facts, contrasts — carried over one-to-one. These are the anchors that hold the persuasiveness.
- **Timing and pace.** Block lengths must match the original — if the hook is 3 seconds, yours is 3 seconds too.

### What to REWRITE (surface text):
- **Every sentence** must be reformulated. No phrase should repeat the original verbatim. Same meaning, different words and constructions.
- **Speech patterns.** If the original says "I replaced my developer for $4,000" — write "Developer was costing me $4,000 a month — I found a replacement for $20." Same meaning and numbers, different sentence.
- **Transitions between blocks.** Bridges from hook to development, from development to value — use different wording.
- **Examples within the development.** If you can provide an equivalent but different example from the same niche — do it. If the example is unique and irreplaceable — keep it but reformulate the delivery.

### Humanization is CRITICALLY important here
When rewriting text in the same language, AI-ness is even more noticeable — the viewer involuntarily compares it with the organic original. The rewritten text must sound like a different PERSON telling the same story, not like a machine paraphrased the text with synonyms. Use your own speech patterns, your own rhythm, your own pauses. Don't paraphrase — retell from scratch.

### Self-check:
1. Is the viral mechanic intact? Same hook type, same arc, same artifacts?
2. Does no sentence match the original verbatim?
3. If the viewer saw the original — would they recognize the topic but NOT recognize the text?
4. Does the text sound like live speech from a different person, not a machine paraphrase?"""

CROSS_LANGUAGE_RULES = """
## IMPORTANT: the original is in a different language

The original reel is in a different language — the author's audience most likely has NOT seen it. Uniqueness is ensured by the translation itself.

### Principle: maximum faithfulness to the original
- **Structure and sequence** — keep them identical. The original already proved this sequence works — don't "improve" it.
- **Every example, every number, every name** — carry over precisely. Do NOT replace examples with "more relevant ones for the author's niche" — these specific examples made the reel go viral.
- **Timing** — block lengths must precisely match the original.
- **Tone and energy** — if the original was energetic, the translation should be too. If calm — same.

### Where you CAN adapt (minimally):
- Idioms and cultural references that don't work in another language — replace with an equivalent, preserving meaning and emotion.
- Units of measurement (miles → kilometers, pounds → rubles), if appropriate for the audience.
- Product names stay in the original language — Cursor stays Cursor, not localized.

### What NOT to do:
- Do NOT add content that wasn't in the original.
- Do NOT "improve" the hook — it already worked.
- Do NOT change the order of blocks.
- Do NOT replace specific examples with abstract generalizations.

### Top priority: sound natural in the target language
The translation must not sound like a translation. It should be the speech of a person telling this story in their native language. Use natural constructions of the target language, not calques from the original."""

FIXED_CONTENT_TAIL = """
---
MANDATORY RESPONSE FORMAT (independent of the prompt above):

Output the result strictly as JSON with three keys:
- "script" — full teleprompter script text, split into paragraphs. At the end — ~XX seconds
- "description" — full reel description text, ready to copy
- "editor_instructions" — full frame-by-frame instructions for the editor (visuals + on-screen text + transitions only, NO speech text)

Write in {target_language}. No introductions, no markdown. JSON only."""

USER_PROMPT = """Here is the reel data for adaptation.

## Metadata
- Platform: {platform}
- Author: {author}
- Title: {title}
- Duration: {duration}s (~{estimated_words} words at 2.5 words/sec)
- Views: {views}
- Likes: {likes}

## Original post description
{description}

## Transcript (original)
{transcript}

## Transcript with timecodes
{timed_transcript}

## Frame-by-frame breakdown
{frames_description}

## Top comments (by likes)
{top_comments}"""


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


async def _openai_fallback_content(system_blocks: list[dict], user_prompt: str) -> str:
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
        temperature=1.0,
    )
    track_openai_text(response)
    logger.info("[summarizer] OpenAI fallback succeeded (model=%s)", settings.fallback_text_model)
    return response.choices[0].message.content


async def generate_summary(
    metadata: dict,
    transcript_segments: list[TranscriptSegment],
    frame_analyses: list[FrameAnalysis],
    comments: list[dict] | None = None,
    api_key: str = "",
    target_language: str = "ru",
    custom_prompt: str | None = None,
    video_url: str = "",
    profile_json: dict | None = None,
    same_language: bool = False,
) -> AdaptationSummary:
    """Generate 3-block reel adaptation using Claude Sonnet."""
    from app.core.exceptions import InsufficientDataError

    if not transcript_segments and not frame_analyses:
        raise InsufficientDataError(
            "Insufficient data for script generation: "
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
        from app.services.prompt_composer import compose_content_prompt
        base_prompt = compose_content_prompt(
            UserProfile(**profile_json),
            target_language=target_language,
        )
    else:
        base_prompt = DEFAULT_CONTENT_PROMPT

    # Inject language-specific adaptation rules
    if same_language:
        base_prompt = base_prompt + "\n" + SAME_LANGUAGE_RULES
    else:
        base_prompt = base_prompt + "\n" + CROSS_LANGUAGE_RULES
    lang_name = LANGUAGE_NAMES.get(target_language, "Russian")
    fixed_tail = FIXED_CONTENT_TAIL.format(target_language=lang_name)
    canary = generate_canary()
    system_blocks = build_system_blocks(
        immutable_rules=IMMUTABLE_CONTENT_RULES,
        user_prompt=base_prompt,
        fixed_tail=fixed_tail,
        canary=canary,
    )

    # Build full transcript
    full_transcript = " ".join(seg.text for seg in transcript_segments)

    # Build timed transcript
    timed_parts = []
    for seg in transcript_segments:
        m, s = divmod(int(seg.start), 60)
        timed_parts.append(f"[{m}:{s:02d}] {seg.text}")
    timed_transcript = "\n".join(timed_parts)

    # Build frames description
    frames_desc_parts = []
    for frame in frame_analyses:
        parts = [
            f"[{frame.timecode}] Scene type: {frame.scene_type.value}",
            f"  Visual: {frame.visual_description}",
        ]
        if frame.screen_text:
            parts.append(f"  On-screen text: {', '.join(frame.screen_text)}")
        if frame.transcript_segment:
            parts.append(f"  Speaking: \"{frame.transcript_segment}\"")
        if frame.ui_elements:
            parts.append(f"  UI elements: {', '.join(frame.ui_elements)}")
        frames_desc_parts.append("\n".join(parts))

    frames_description = "\n\n".join(frames_desc_parts)

    # Build comments text
    if comments:
        comment_lines = []
        for c in comments:
            likes_str = f" [{c['likes']} ❤️]" if c.get("likes") else ""
            comment_lines.append(f"- {c['text']}{likes_str}")
        top_comments = "\n".join(comment_lines)
    else:
        top_comments = "Comments are not available for this platform."

    duration = metadata.get("duration", 0) or 0
    estimated_words = int(duration * 2.5)

    prompt = USER_PROMPT.format(
        platform=metadata.get("platform", "unknown"),
        author=metadata.get("uploader", "unknown"),
        title=metadata.get("title", "Unknown"),
        duration=duration,
        estimated_words=estimated_words,
        views=metadata.get("view_count", 0) or 0,
        likes=metadata.get("like_count", 0) or 0,
        description=metadata.get("description", "") or "No description",
        transcript=full_transcript,
        timed_transcript=timed_transcript,
        frames_description=frames_description,
        top_comments=top_comments,
    )

    # Check Redis cache (cache key excludes canary for stable hits)
    cache_text = base_prompt + "\n" + fixed_tail
    cache_key = make_cache_key(cache_text, prompt)
    cached = await cache_get("summary", cache_key)
    if cached:
        logger.info("Summary cache hit")
        editor_instructions = cached.get("editor_instructions", "")
        if video_url:
            editor_instructions = f"VIDEO REFERENCE: {video_url}\n\n{editor_instructions}"
        return AdaptationSummary(
            script=cached.get("script", ""),
            description=cached.get("description", ""),
            editor_instructions=editor_instructions,
        )

    data = None
    last_json_error = None
    used_fallback = False

    for llm_attempt in range(2):  # 1 retry on JSON failure
        if llm_attempt > 0:
            logger.warning(
                "[summarizer] JSON extraction failed, retrying Claude call (attempt %d): %s",
                llm_attempt + 1, last_json_error,
            )
            canary = generate_canary()
            system_blocks = build_system_blocks(
                immutable_rules=IMMUTABLE_CONTENT_RULES,
                user_prompt=base_prompt,
                fixed_tail=fixed_tail,
                canary=canary,
            )

        from app.core.api_retry import anthropic_create_with_retry

        try:
            response = await anthropic_create_with_retry(
                client,
                model=settings.text_model,
                system=system_blocks,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=1.0,
            )
        except Exception as claude_err:
            logger.warning(
                "[summarizer] Claude failed after retries (%s), falling back to OpenAI %s",
                claude_err, settings.fallback_text_model,
            )
            raw_text = await _openai_fallback_content(system_blocks, prompt)
            used_fallback = True
        else:
            from app.core.cost_tracker import track_anthropic
            track_anthropic(response)
            raw_text = response.content[0].text

        if not used_fallback and check_canary(raw_text, canary):
            logger.warning("Canary token leaked in content output — possible prompt injection")

        # Detect AI content policy refusal → fallback to OpenAI
        from app.core.error_classifier import is_ai_refusal
        if not used_fallback and is_ai_refusal(raw_text):
            logger.warning("[summarizer] Claude refused content, falling back to OpenAI: %s", raw_text[:200])
            raw_text = await _openai_fallback_content(system_blocks, prompt)
            used_fallback = True

        try:
            data = _extract_json(raw_text)
            break
        except Exception as e:
            last_json_error = e
            continue

    if data is None:
        raise last_json_error or ValueError("Failed to extract JSON from content response")

    # Validate output structure
    try:
        validate_content_output(data)
    except OutputValidationError as e:
        logger.error("Content output validation failed: %s", e)
        raise

    # Cache raw LLM output (without video_url prefix)
    await cache_set("summary", cache_key, data)

    editor_instructions = data.get("editor_instructions", "")
    if video_url:
        editor_instructions = f"VIDEO REFERENCE: {video_url}\n\n{editor_instructions}"

    return AdaptationSummary(
        script=data.get("script", ""),
        description=data.get("description", ""),
        editor_instructions=editor_instructions,
    )


REWRITE_SYSTEM_PROMPT = """You are a copywriter specializing in uniqueness. You are given a ready reel script, description, and editor instructions.

Your task is to rewrite all three blocks so that:
1. Meaning and structure remain identical
2. Wording becomes different (uniquification)
3. The hook could become stronger — suggest a variant
4. The tone stays lively and conversational
5. Length stays approximately the same (±10%)

Do not change facts, tool names, or numbers. Change only the wording.

Original transcript for context:
{transcript}

Write in {target_language}.

---
MANDATORY RESPONSE FORMAT:

Output JSON with keys: "script", "description", "editor_instructions". No markdown, no introductions."""

REWRITE_USER_PROMPT = """Here is the current script, description, and instructions. Rewrite all three blocks.

## Script
{script}

## Description
{description}

## Editor instructions
{editor_instructions}"""


async def rewrite_summary(
    existing_script: str,
    existing_description: str,
    existing_editor_instructions: str,
    transcript_text: str,
    api_key: str = "",
    target_language: str = "ru",
    video_url: str = "",
) -> AdaptationSummary:
    """Rewrite existing script/description/instructions for uniqueness."""
    client = AsyncAnthropic(
        api_key=api_key or settings.anthropic_api_key,
        timeout=httpx.Timeout(120.0, connect=10.0),
    )

    lang_name = LANGUAGE_NAMES.get(target_language, "Russian")
    system_text = REWRITE_SYSTEM_PROMPT.format(
        transcript=transcript_text[:2000],
        target_language=lang_name,
    )

    # Strip the VIDEO REFERENCE prefix so it doesn't accumulate on each rewrite
    clean_instructions = existing_editor_instructions
    if clean_instructions.startswith("VIDEO REFERENCE:") or clean_instructions.startswith("РЕФЕРЕНС РОЛИКА:"):
        # Remove the first line (prefix) and the blank line after it
        lines = clean_instructions.split("\n", 2)
        clean_instructions = lines[2] if len(lines) > 2 else ""

    prompt = REWRITE_USER_PROMPT.format(
        script=existing_script,
        description=existing_description,
        editor_instructions=clean_instructions,
    )

    response = await client.messages.create(
        model=settings.text_model,
        system=[{
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )

    data = _extract_json(response.content[0].text)

    editor_instructions = data.get("editor_instructions", "")
    if video_url:
        editor_instructions = f"VIDEO REFERENCE: {video_url}\n\n{editor_instructions}"

    return AdaptationSummary(
        script=data.get("script", ""),
        description=data.get("description", ""),
        editor_instructions=editor_instructions,
    )
