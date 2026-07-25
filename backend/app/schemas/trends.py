from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TrendAuthor(BaseModel):
    profile_id: str
    username: str
    display_name: Optional[str] = None
    platform: str
    followers_count: Optional[int] = None
    median_views: Optional[float] = None
    niche: Optional[str] = None


class TrendItem(BaseModel):
    id: str
    url: str
    caption: Optional[str] = None
    thumbnail_url: Optional[str] = None
    published_at: Optional[datetime] = None
    duration: Optional[float] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    x_factor: Optional[float] = None
    velocity: Optional[float] = None
    hot_score: Optional[float] = None
    niche: Optional[str] = None  # per-reel niche
    author: TrendAuthor
    is_parsed: bool = False
    library_reel_id: Optional[str] = None
    trending_since: Optional[datetime] = None
    frame_count: int = 0
    is_followed: bool = False


class TrendsListResponse(BaseModel):
    items: list[TrendItem]
    total: int
    page: int
    per_page: int
    interest_source: Optional[str] = None  # "manual" | "auto" | "none"
    niche_source: Optional[str] = None  # "manual" | "auto" | "none"


class NicheStats(BaseModel):
    niche: str
    trending_count: int
    total_profiles: int


class AddAuthorRequest(BaseModel):
    input: str


class TrackedAuthorResponse(BaseModel):
    id: str
    platform: str
    username: str
    display_name: Optional[str] = None
    profile_url: Optional[str] = None
    followers_count: Optional[int] = None
    median_views: Optional[float] = None
    niche: Optional[str] = None
    total_reels: int = 0
    last_checked_at: Optional[datetime] = None
    trending_count: int = 0


class MyAuthorsResponse(BaseModel):
    authors: list[TrackedAuthorResponse]
    count: int
    limit: int
    frozen_count: int = 0


class ForYouResponse(BaseModel):
    items: list[TrendItem]
    user_niches: list[str]
    niche_source: str  # "manual" | "auto" | "none"
    user_interests: list[str] = []
    interest_source: str = "none"  # "manual" | "auto" | "none"
