import json

from app.config import settings
from app.core.niches import niche_prompt_detailed, DISAMBIGUATION_RULES
from app.schemas.analysis import TranscriptSegment

TAGGING_PROMPT = """Classify this short-form video reel. Return ONLY valid JSON.

Video metadata:
- Title: {{title}}
- Platform: {{platform}}
- Author: {{author}}
- Duration: {{duration}}s

Full transcript:
{{transcript}}

NICHE DEFINITIONS:
{niche_list}

{rules}

Return JSON:
{{{{
  "language": "two-letter ISO code of the spoken language (e.g. en, es, ru)",
  "content_format": "one of: tutorial, review, comparison, story, behind_the_scenes, news, motivation, entertainment, demo, explainer",
  "topics": ["3-6 topic slugs in English, lowercase with hyphens, e.g. ai-tools, vibe-coding, no-code, saas, automation, cursor, productivity"],
  "keywords": ["5-10 specific keywords/names mentioned: product names, tools, concepts, techniques — in the original language"],
  "niche": "one slug from the NICHE DEFINITIONS above"
}}}}""".format(niche_list=niche_prompt_detailed(), rules=DISAMBIGUATION_RULES)


async def tag_reel(
    metadata: dict,
    transcript_segments: list[TranscriptSegment],
    api_key: str = "",
) -> dict:
    """Auto-tag a reel using GPT-4o. Returns classification dict."""
    from app.core.openai_client import get_openai_client
    client = get_openai_client(api_key)

    full_transcript = " ".join(seg.text for seg in transcript_segments)

    prompt = TAGGING_PROMPT.format(
        title=metadata.get("title", "Unknown"),
        platform=metadata.get("platform", "unknown"),
        author=metadata.get("uploader", "unknown"),
        duration=metadata.get("duration", 0),
        transcript=full_transcript[:3000],
    )

    try:
        response = await client.chat.completions.create(
            model=settings.vision_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=500,
        )

        content = response.choices[0].message.content
        if content is None:
            return _default_tags()

        return json.loads(content)
    except Exception:
        return _default_tags()


def _default_tags() -> dict:
    return {
        "language": "en",
        "content_format": "other",
        "topics": [],
        "keywords": [],
        "niche": "other",
    }
