from datetime import datetime

from pydantic import BaseModel


class AdminJobItem(BaseModel):
    id: str
    user_id: str
    user_email: str | None = None
    user_name: str | None = None
    user_tier: str | None = None
    url: str
    status: str
    progress: float
    progress_message: str | None = None
    error: str | None = None
    video_title: str | None = None
    video_platform: str | None = None
    share_token: str | None = None
    source: str | None = None
    retry_count: int = 0
    duration_seconds: float | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class AdminJobListResponse(BaseModel):
    items: list[AdminJobItem]
    total: int
    page: int
    per_page: int


class AdminJobStatsResponse(BaseModel):
    queued: int = 0
    running: int = 0
    completed_today: int = 0
    failed_today: int = 0
    completed_total: int = 0
    failed_total: int = 0
    avg_duration_seconds: float | None = None
    error_rate_pct: float = 0.0
    completed_week: int = 0


class AdminLibraryItem(BaseModel):
    id: str
    url: str
    video_title: str | None = None
    video_platform: str | None = None
    video_author: str | None = None
    submitted_by_email: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminLibraryListResponse(BaseModel):
    items: list[AdminLibraryItem]
    total: int
    page: int
    per_page: int


class AdminUserItem(BaseModel):
    id: str
    email: str | None = None
    name: str | None = None
    is_anonymous: bool
    tier: str
    telegram_username: str | None = None
    telegram_subscribed: bool
    created_at: datetime | None = None
    jobs_count: int

    model_config = {"from_attributes": True}


class AdminUserSettings(BaseModel):
    language: str = "ru"
    onboarding_completed: bool = False
    has_custom_content_prompt: bool = False
    has_custom_strategy_prompt: bool = False
    has_api_keys: bool = False
    # Profile fields (from profile_json)
    about_me: str | None = None
    tone: str | None = None
    niches: list[str] = []
    interests: list[str] = []
    forbidden_words: str | None = None
    script_cta: str | None = None
    description_cta: str | None = None
    video_format: str | None = None
    radar_enabled: bool | None = None
    radar_mode: str | None = None


class AdminUserScript(BaseModel):
    id: str
    script: str
    description: str
    editor_instructions: str
    original_script: str | None = None
    original_description: str | None = None
    original_editor_instructions: str | None = None
    active_hook_index: int = 0
    reel_url: str | None = None
    reel_title: str | None = None
    reel_platform: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminUserSubscription(BaseModel):
    id: str
    tier: str
    status: str
    payment_provider: str | None = None
    billing_interval: str | None = None
    amount_kopecks: int = 0
    currency: str = "RUB"
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    scheduled_tier: str | None = None
    scheduled_interval: str | None = None
    created_at: datetime | None = None


class AdminUserPayment(BaseModel):
    id: str
    amount_kopecks: int
    currency: str
    status: str
    payment_provider: str | None = None
    payment_method: str | None = None
    paid_at: datetime | None = None
    created_at: datetime


class AdminUserDetail(AdminUserItem):
    auth_provider: str | None = None
    recent_jobs: list[AdminJobItem] = []
    jobs_total: int = 0
    settings: AdminUserSettings | None = None
    scripts: list[AdminUserScript] = []
    scripts_total: int = 0
    subscription: AdminUserSubscription | None = None
    payments: list[AdminUserPayment] = []
    payments_total: int = 0


class AdminUserListResponse(BaseModel):
    items: list[AdminUserItem]
    total: int
    page: int
    per_page: int


class UpdateTierRequest(BaseModel):
    tier: str
    duration_months: int | None = None  # 1, 3, 6, 12 or None (indefinite)
    reason: str | None = None


class AdminStatsResponse(BaseModel):
    total_users: int
    anonymous_users: int
    registered_users: int
    free_users: int
    start_users: int
    pro_users: int
    unlimited_users: int
    total_jobs: int
    jobs_today: int
    jobs_running: int
    jobs_completed: int
    jobs_failed: int
    jobs_failed_today: int
    library_reels: int


class CostPeriod(BaseModel):
    apify_usd: float = 0.0
    whisper_usd: float = 0.0
    vision_usd: float = 0.0
    sonnet_usd: float = 0.0
    haiku_usd: float = 0.0
    total_usd: float = 0.0
    jobs_count: int = 0


class CostDayStats(BaseModel):
    date: str
    total_usd: float = 0.0
    jobs_count: int = 0


class CostAnalyticsResponse(BaseModel):
    today: CostPeriod
    yesterday: CostPeriod
    month: CostPeriod
    all_time: CostPeriod
    avg_per_reel_usd: float = 0.0
    apify_budget: dict | None = None
    revenue_today_rub: int = 0
    revenue_yesterday_rub: int = 0
    revenue_month_rub: int = 0
    revenue_today_eur: int = 0
    revenue_month_eur: int = 0
    mrr_rub: int = 0
    mrr_eur: int = 0
    daily_costs: list[CostDayStats] = []
    paid_users: int = 0
    cost_per_paid_user_usd: float = 0.0


class TierConfigItem(BaseModel):
    name: str
    max_monthly: int | None = None
    max_total: int | None = None
    max_refines_daily: int | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TierConfigUpdateRequest(BaseModel):
    max_monthly: int | None = None
    max_total: int | None = None
    max_refines_daily: int | None = None


# Messages / Conversations
class AdminSendMessageRequest(BaseModel):
    text: str


class AdminMessageItem(BaseModel):
    id: str
    telegram_user_id: str
    direction: str
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminConversationItem(BaseModel):
    telegram_user_id: str
    telegram_username: str | None = None
    telegram_name: str | None = None
    user_id: str | None = None
    message_count: int
    last_message_text: str | None = None
    last_message_at: datetime | None = None

    model_config = {"from_attributes": True}


class AdminConversationListResponse(BaseModel):
    items: list[AdminConversationItem]
    total: int
    page: int
    per_page: int


# Analytics
class JobDayStats(BaseModel):
    date: str
    total: int
    completed: int
    failed: int


class UserDayStats(BaseModel):
    date: str
    new_users: int


class PlatformHealth(BaseModel):
    platform: str
    total_jobs: int
    completed: int
    failed: int
    success_rate: float


class RecentError(BaseModel):
    url: str
    platform: str | None = None
    error: str | None = None
    share_token: str | None = None
    created_at: datetime


class AdminAnalyticsResponse(BaseModel):
    jobs_per_day: list[JobDayStats]
    users_per_day: list[UserDayStats]
    platform_health: list[PlatformHealth]
    recent_errors: list[RecentError]


# Payments
class AdminPaymentItem(BaseModel):
    id: str
    user_id: str
    user_email: str | None = None
    user_name: str | None = None
    subscription_id: str | None = None
    provider_payment_id: str | None = None
    payment_provider: str | None = None
    amount_kopecks: int
    currency: str
    status: str
    payment_method: str | None = None
    description: str | None = None
    receipt_url: str | None = None
    paid_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminPaymentListResponse(BaseModel):
    items: list[AdminPaymentItem]
    total: int
    page: int
    per_page: int
    total_all: int = 0
    total_succeeded: int = 0
    total_rub_kopecks: int = 0
    total_eur_cents: int = 0


# Tracked Profiles (Trends)
class AdminTrackedProfileItem(BaseModel):
    id: str
    platform: str
    username: str
    display_name: str | None = None
    followers_count: int | None = None
    median_views: float | None = None
    total_reels: int
    niche: str | None = None
    is_active: bool
    is_blocked: bool = False
    blocked_at: datetime | None = None
    blocked_reason: str | None = None
    check_priority: str
    last_checked_at: datetime | None = None
    created_at: datetime
    tracking_users_count: int = 0
    trending_reels_count: int = 0

    model_config = {"from_attributes": True}


class AdminTrackedProfileStats(BaseModel):
    total: int = 0
    today: int = 0
    yesterday: int = 0
    week: int = 0
    month: int = 0


class AdminTrackedProfileListResponse(BaseModel):
    items: list[AdminTrackedProfileItem]
    total: int
    page: int
    per_page: int
    stats: AdminTrackedProfileStats | None = None


# Content Moderation
class BlockProfileRequest(BaseModel):
    reason: str = ""


class HideReelRequest(BaseModel):
    reason: str = ""


class AdminHiddenReelItem(BaseModel):
    id: str
    url: str
    caption: str | None = None
    thumbnail_url: str | None = None
    views: int | None = None
    profile_username: str
    profile_platform: str
    hidden_at: datetime | None = None
    hidden_reason: str | None = None

    model_config = {"from_attributes": True}


class AdminHiddenReelListResponse(BaseModel):
    items: list[AdminHiddenReelItem]
    total: int
    page: int
    per_page: int


# Profile Parsing (deep-analyze tracking)
class AdminParsingItem(BaseModel):
    id: str
    user_id: str
    user_email: str | None = None
    user_name: str | None = None
    user_tier: str | None = None
    analysis_id: str
    platform: str
    username: str
    status: str
    error: str | None = None
    duration_seconds: float | None = None
    result_json: dict | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class AdminParsingListResponse(BaseModel):
    items: list[AdminParsingItem]
    total: int
    page: int
    per_page: int


class AdminParsingStatsResponse(BaseModel):
    running: int = 0
    completed_today: int = 0
    failed_today: int = 0
    completed_total: int = 0
    failed_total: int = 0
    avg_duration_seconds: float | None = None


# Showcase Dashboard
class ShowcaseDayStats(BaseModel):
    date: str
    new_users: int
    revenue_rub_kopecks: int = 0
    revenue_eur_cents: int = 0
    analyses: int = 0


class ShowcasePlatformStat(BaseModel):
    platform: str
    total: int
    completed: int
    failed: int
    success_rate: float


class ShowcaseActiveJob(BaseModel):
    job_id: str
    status: str
    progress: float
    video_platform: str | None = None
    video_author: str | None = None
    video_title: str | None = None
    source: str | None = None
    masked_email: str | None = None
    created_at: str


class ShowcaseHeatmapCell(BaseModel):
    weekday: int  # 0=Mon .. 6=Sun
    hour: int     # 0-23
    count: int


class ShowcaseStatsResponse(BaseModel):
    # Users
    total_registered: int
    total_paid: int
    conversion_pct: float
    free_users: int
    start_users: int
    pro_users: int
    unlimited_users: int

    # Revenue
    total_rub_kopecks: int
    total_eur_cents: int

    # Analyses
    total_analyses: int
    analyses_today: int

    # Ratings
    avg_rating: float | None = None
    total_ratings: int = 0
    unread_ratings: int = 0

    # Support
    unread_support: int = 0

    # Growth (30 days)
    daily: list[ShowcaseDayStats]

    # Meta
    launched_at: str | None = None  # first user registration date

    # Job stats
    jobs_completed: int = 0
    jobs_failed: int = 0
    jobs_running: int = 0
    jobs_success_rate: float = 0.0

    # Platform breakdown
    platform_stats: list[ShowcasePlatformStat] = []

    # Speed metrics
    avg_processing_seconds: float | None = None
    fastest_today_seconds: float | None = None
    jobs_per_hour: float = 0.0

    # Active jobs (for pipeline visualization)
    active_jobs: list[ShowcaseActiveJob] = []

    # Activity heatmap (hour x weekday)
    activity_heatmap: list[ShowcaseHeatmapCell] = []

    # Trend monitoring stats
    tracked_authors: int = 0
    total_trends_found: int = 0
    trends_currently_hot: int = 0
    avg_trends_per_author: float = 0.0


# ── Niches ───────────────────────────────────────────────────────────────

class AdminNicheItem(BaseModel):
    id: int
    slug: str
    display_name: str
    display_name_en: str | None = None
    description: str | None = None
    keywords: list[str] = []
    group_key: str = "other"
    sort_order: int = 0
    is_active: bool = True
    videos_count: int = 0
    authors_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminNicheGroup(BaseModel):
    key: str
    label: str
    niches: list[str]


class AdminNichesResponse(BaseModel):
    items: list[AdminNicheItem]
    groups: list[AdminNicheGroup]
    stats: "AdminNicheStatsResponse"


class AdminNicheStatsResponse(BaseModel):
    total_niches: int = 0
    active_niches: int = 0
    videos_without_niche: int = 0
    authors_without_niche: int = 0


class AdminNicheCreateRequest(BaseModel):
    slug: str
    display_name: str
    display_name_en: str | None = None
    description: str | None = None
    keywords: list[str] = []
    group_key: str = "other"
    sort_order: int = 0


class AdminNicheUpdateRequest(BaseModel):
    display_name: str | None = None
    display_name_en: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    group_key: str | None = None
    sort_order: int | None = None


# ── Admin Trending Reels ─────────────────────────────────────────────────

class AdminTrendingReelItem(BaseModel):
    id: str
    url: str
    caption: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    trending_since: datetime | None = None
    duration: float | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    x_factor: float | None = None
    velocity: float | None = None
    hot_score: float | None = None
    niche: str | None = None
    author_id: str
    author_username: str
    author_platform: str
    author_display_name: str | None = None
    author_followers: int | None = None


class AdminTrendingNicheStat(BaseModel):
    niche: str
    count: int


class AdminTrendingSummary(BaseModel):
    total_trending: int
    avg_hot_score: float | None = None
    top_niches: list[AdminTrendingNicheStat] = []


class AdminTrendingReelsResponse(BaseModel):
    items: list[AdminTrendingReelItem]
    total: int
    page: int
    per_page: int
    summary: AdminTrendingSummary
