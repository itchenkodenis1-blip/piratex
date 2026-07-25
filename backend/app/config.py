import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Piratex.ai"
    debug: bool = False
    storage_dir: str = "./storage"
    demo_mode: bool = False

    # Database
    database_url: str = ""

    @property
    def effective_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openai_api_key: str = ""

    # Whisper
    whisper_api_key: str = ""
    whisper_base_url: str = "https://api.groq.com/openai/v1"

    # Anthropic
    anthropic_api_key: str = ""

    # Apify
    apify_api_token: str = ""
    apify_timeout: int = 300
    apify_instagram_actor: str = "apify~instagram-reel-scraper"
    apify_youtube_actor: str = "dc_solutions~youtube-downloader-pro"
    apify_youtube_fallback_actor: str = "marielise.dev~youtube-video-downloader"
    apify_tiktok_actor: str = "apidojo~tiktok-scraper"
    apify_tiktok_fallback_actor: str = "clockworks~tiktok-scraper"
    apify_youtube_comments_actor: str = "streamers~youtube-comments-scraper"
    apify_tiktok_comments_actor: str = "clockworks~tiktok-comments-scraper"
    apify_instagram_profile_actor: str = "apify~instagram-profile-scraper"
    apify_balance_min_pct: float = 5.0
    apify_balance_alert_pct: float = 20.0
    apify_balance_check_interval: int = 300

    # Auth
    jwt_secret: str = os.environ.get("JWT_SECRET", "")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080

    # CORS
    cors_origins: str = "http://localhost:5173"

    # Processing limits
    max_video_duration_seconds: int = 300
    scene_detect_threshold: float = 27.0
    safety_frame_interval: float = 5.0
    max_concurrent_vision_calls: int = 10
    max_concurrent_ffmpeg: int = 4
    failed_job_retention_days: int = 7

    # Models
    whisper_model: str = "whisper-large-v3-turbo"
    vision_model: str = "openai/gpt-4o-mini"
    text_model: str = "claude-sonnet-4-6"
    light_text_model: str = "claude-haiku-4-5"
    fallback_text_model: str = "openai/gpt-4.1"

    # Telegram
    telegram_bot_token: str = ""
    telegram_bot_name: str = "go_piratex_bot"
    telegram_channel_id: str = ""
    telegram_channel_url: str = ""  # Invite link (e.g. https://t.me/+abc)
    telegram_webhook_url: str = ""  # e.g. "https://piratex.ai"
    telegram_webhook_secret: str = ""  # REQUIRED in production — webhook is rejected without it

    # Cloudflare Turnstile (empty = disabled, anonymous users skip captcha)
    turnstile_secret_key: str = ""

    # OAuth providers (all optional — empty = disabled)
    # Yandex ID
    yandex_client_id: str = ""
    yandex_client_secret: str = ""

    # VK ID
    vk_client_id: str = ""
    vk_client_secret: str = ""

    # Google
    google_client_id: str = ""
    google_client_secret: str = ""

    # Email (Unisender Go)
    unisender_api_key: str = ""
    email_from_domain: str = "piratex.ai"
    magic_link_ttl_minutes: int = 15

    # Phone auth (SMS)
    sms_provider_api_key: str = ""
    phone_code_ttl_minutes: int = 5
    phone_code_max_attempts: int = 3

    # Redis (task queue + pub/sub)
    redis_url: str = "redis://localhost:6379"

    # Database pool tuning (different per service: app, worker, scheduler)
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # S3-compatible object storage (optional — falls back to local disk)
    # Works with Railway Buckets, Cloudflare R2, AWS S3, MinIO
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_endpoint: str = ""  # For S3-compatible (Railway, R2, MinIO)
    s3_addressing_style: str = ""  # "path" | "virtual" | "" (auto-detect)
    cdn_url: str = ""  # Public CDN URL for serving files

    # YooKassa
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_webhook_secret: str = ""  # REQUIRED in production — webhook returns 503 without it
    app_url: str = "https://piratex.ai"  # for return URLs

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # CloudPayments
    cloudpayments_public_id: str = ""      # Public ID (pk_xxx) — passed to JS widget
    cloudpayments_api_secret: str = ""     # API Secret — server-side auth + HMAC verification

    # Admin
    admin_emails: str = ""  # Comma-separated list of admin emails
    admin_telegram_ids: str = ""  # Comma-separated Telegram user IDs


settings = Settings()

TIER_LIMITS = {
    "ANONYMOUS": {"max_total": 1},
    "REGISTERED": {"max_monthly": 0},
    "FREE": {"max_monthly": 3, "max_refines_daily": 5},
    "START": {"max_monthly": 50, "max_refines_daily": 30},
    "PRO": {"max_monthly": 150, "max_refines_daily": 100},
    "UNLIMITED": {"max_monthly": 300, "max_refines_daily": 200},  # soft cap; 300 at full speed, then throttle (15/day)
}

# Pricing in kopecks (1 ruble = 100 kopecks)
TIER_PRICING = {
    "START": {
        "monthly": 200_000,     # 2000 ₽
        "yearly": 1_800_000,    # 18000 ₽ (1500 ₽/мес, -25%)
    },
    "PRO": {
        "monthly": 500_000,     # 5000 ₽
        "yearly": 4_500_000,    # 45000 ₽ (3750 ₽/мес, -25%)
    },
    "UNLIMITED": {
        "monthly": 1_000_000,   # 10000 ₽
        "yearly": 9_000_000,    # 90000 ₽ (7500 ₽/мес, -25%)
    },
}

REFERRAL_BONUS_AMOUNT = 5  # bonus reels per referral (both sides)
REFERRAL_MAX_PER_REFERRER = 50  # max referrals one user can attract

# Default currency per provider
PROVIDER_CURRENCY: dict[str, str] = {
    "yookassa": "RUB",
    "stripe": "EUR",
    "cloudpayments": "RUB",
}

# Pricing in cents for EUR-based providers (Stripe)
TIER_PRICING_EUR: dict[str, dict[str, int]] = {
    "START": {
        "monthly": 2_000,     # €20
        "yearly": 18_000,     # €180 (€15/mo, -25%)
    },
    "PRO": {
        "monthly": 5_000,     # €50
        "yearly": 45_000,     # €450 (€37.50/mo, -25%)
    },
    "UNLIMITED": {
        "monthly": 55_000,    # €550
        "yearly": 495_000,    # €4950 (€412.50/mo, -25%)
    },
}

# Stripe Price IDs — create products/prices in YOUR Stripe Dashboard and paste
# the resulting price IDs here (used for mode: "subscription"). Placeholders
# below must be replaced before Stripe checkout will work.
STRIPE_PRICE_IDS: dict[str, dict[str, str]] = {
    "START": {
        "monthly": "price_REPLACE_START_MONTHLY",
        "yearly": "price_REPLACE_START_YEARLY",
    },
    "PRO": {
        "monthly": "price_REPLACE_PRO_MONTHLY",
        "yearly": "price_REPLACE_PRO_YEARLY",
    },
    "UNLIMITED": {
        "monthly": "price_REPLACE_UNLIMITED_MONTHLY",
        "yearly": "price_REPLACE_UNLIMITED_YEARLY",
    },
}

# Reverse mapping: Stripe Price ID → (tier, interval)
STRIPE_PRICE_TO_TIER: dict[str, tuple[str, str]] = {
    price_id: (tier, interval)
    for tier, intervals in STRIPE_PRICE_IDS.items()
    for interval, price_id in intervals.items()
}
