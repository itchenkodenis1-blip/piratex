from enum import Enum
from typing import Optional

from pydantic import BaseModel, model_validator


class SceneType(str, Enum):
    TALKING_HEAD = "talking_head"
    SCREENCAST = "screencast"
    ANIMATION = "animation"
    TEXT_CARD = "text_card"
    SPLIT_SCREEN = "split_screen"
    B_ROLL = "b_roll"


class TranscriptWord(BaseModel):
    word: str
    start: float
    end: float


class TranscriptSegment(BaseModel):
    text: str
    start: float
    end: float
    words: list[TranscriptWord] = []


class FrameAnalysis(BaseModel):
    frame_index: int
    timestamp: float
    timecode: str
    frame_path: str
    screen_text: list[str] = []
    visual_description: str = ""
    scene_type: SceneType = SceneType.B_ROLL
    ui_elements: list[str] = []
    transcript_segment: Optional[str] = None


def _sanitize_dashes(text: str) -> str:
    """Replace em dash (—) with hyphen-minus (-)."""
    return text.replace("\u2014", "-")


def _deep_sanitize(obj: BaseModel) -> BaseModel:
    """Recursively replace em dashes in all string fields of a Pydantic model."""
    for field_name in obj.model_fields:
        val = getattr(obj, field_name)
        if isinstance(val, str):
            setattr(obj, field_name, _sanitize_dashes(val))
        elif isinstance(val, BaseModel):
            _deep_sanitize(val)
        elif isinstance(val, list):
            new_list = []
            for item in val:
                if isinstance(item, str):
                    new_list.append(_sanitize_dashes(item))
                elif isinstance(item, BaseModel):
                    _deep_sanitize(item)
                    new_list.append(item)
                else:
                    new_list.append(item)
            setattr(obj, field_name, new_list)
    return obj


class AdaptationSummary(BaseModel):
    script: str
    description: str
    editor_instructions: str

    @model_validator(mode="after")
    def _sanitize(self) -> "AdaptationSummary":
        return _deep_sanitize(self)


class CommentsStrategy(BaseModel):
    pass


class Hashtags(BaseModel):
    primary: list[str] = []
    secondary: list[str] = []


class CoverRecommendation(BaseModel):
    recommended_frame_index: int = 1
    cover_text: str = ""
    why: str = ""


class HookVariant(BaseModel):
    text: str
    score: int = 50
    why: str = ""


class StrategyAnalysis(BaseModel):
    virality_breakdown: str = ""
    hook_variants: list[HookVariant] = []
    primary_hook_score: int = 0
    primary_hook_why: str = ""
    comments_strategy: CommentsStrategy = CommentsStrategy()
    hashtags: Hashtags = Hashtags()
    cover: CoverRecommendation = CoverRecommendation()
    # Classification (replaces tagger)
    language: str = "en"
    content_format: str = "other"
    topics: list[str] = []
    keywords: list[str] = []
    niche: str = "other"

    @model_validator(mode="after")
    def _sanitize(self) -> "StrategyAnalysis":
        return _deep_sanitize(self)
