"""Robust JSON extraction from LLM responses."""

import json
import logging
import re

logger = logging.getLogger(__name__)


def extract_json(text: str) -> dict:
    """Extract JSON dict from Claude response.

    Steps:
    1. Strip markdown code blocks
    2. Find first '{'
    3. Try json.loads()
    4. If that fails, try json_repair
    5. Validate result is dict
    """
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    if not cleaned.startswith("{"):
        brace_start = cleaned.find("{")
        if brace_start != -1:
            cleaned = cleaned[brace_start:]
        else:
            raise ValueError(
                f"Claude вернул ответ без JSON-объекта (первые 200 символов): {text[:200]}"
            )

    # Step 1: try standard json.loads
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Step 2: try json_repair (lazy import — zero overhead on happy path)
        logger.warning("json.loads failed (%s), attempting json_repair", e)
        try:
            from json_repair import repair_json

            repaired = repair_json(cleaned, return_objects=True)
            if isinstance(repaired, dict):
                result = repaired
            elif isinstance(repaired, str):
                result = json.loads(repaired)
            else:
                raise ValueError(f"json_repair returned {type(repaired).__name__}")
        except Exception as repair_err:
            logger.error("json_repair also failed: %s", repair_err)
            raise e from repair_err

    if not isinstance(result, dict):
        raise ValueError(
            f"Claude вернул {type(result).__name__} вместо JSON-объекта: {text[:200]}"
        )
    return result
