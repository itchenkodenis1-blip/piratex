import asyncio
import logging
from pathlib import Path

import html as html_lib

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.api.router import api_router
from app.api.ws import ws_router
from app.config import settings
from app.core.rate_limit import limiter
from app.database import Base, async_session, engine
from app.models import feedback, job, library, message, niches, production, promo, referral, subscription, tier_config, trends, user  # noqa: F401 — register all models

app = FastAPI(
    title="Piratex.ai",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Refine-Used", "X-Refine-Limit"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

app.include_router(api_router, prefix="/api")
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve frontend static assets in production
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend-dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="static-assets")

    _index_html_cache: str | None = None

    def _get_index_html() -> str:
        global _index_html_cache
        if _index_html_cache is None:
            _index_html_cache = (_frontend_dist / "index.html").read_text()
        return _index_html_cache

    def _inject_og_tags(base_html: str, title: str, description: str, image_url: str, page_url: str) -> str:
        """Inject Open Graph and Twitter Card meta tags into HTML <head>."""
        t = html_lib.escape(title)
        d = html_lib.escape(description[:200])
        og_tags = (
            f'<meta property="og:title" content="{t}" />\n'
            f'<meta property="og:description" content="{d}" />\n'
            f'<meta property="og:image" content="{html_lib.escape(image_url)}" />\n'
            f'<meta property="og:url" content="{html_lib.escape(page_url)}" />\n'
            f'<meta property="og:type" content="website" />\n'
            f'<meta property="og:site_name" content="Piratex.ai" />\n'
            f'<meta property="og:locale" content="ru_RU" />\n'
            f'<meta name="twitter:card" content="summary_large_image" />\n'
            f'<meta name="twitter:title" content="{t}" />\n'
            f'<meta name="twitter:description" content="{d}" />\n'
            f'<meta name="twitter:image" content="{html_lib.escape(image_url)}" />\n'
            f'<title>{t} — Piratex.ai</title>\n'
        )
        # Replace existing <title> and inject OG tags
        import re
        result = re.sub(r"<title>[^<]*</title>", "", base_html, count=1)
        result = result.replace("</head>", og_tags + "</head>", 1)
        return result

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        # Serve actual files if they exist (favicon, etc.)
        file_path = (_frontend_dist / path).resolve()
        if path and file_path.is_file() and file_path.is_relative_to(_frontend_dist.resolve()):
            return FileResponse(file_path)

        # Inject OG meta tags for /share/{token} pages
        if path.startswith("share/"):
            token = path.removeprefix("share/").split("/")[0]
            if token:
                try:
                    from sqlalchemy import select as sa_select

                    from app.models.job import Job, JobStatus

                    async with async_session() as db:
                        result = await db.execute(
                            sa_select(
                                Job.video_title, Job.video_author,
                                Job.video_platform, Job.adaptation_summary,
                                Job.share_token, Job.id,
                            ).where(
                                Job.share_token == token,
                                Job.status == JobStatus.COMPLETED,
                            )
                        )
                        row = result.first()
                        if row:
                            title = row.video_title or "Анализ рилса"
                            author = row.video_author or ""
                            summary = row.adaptation_summary or {}
                            desc = summary.get("script", "")[:200] if summary else ""
                            if author:
                                title = f"{title} — {author}"

                            # Use second frame (cover) as OG image
                            image_url = f"{settings.app_url}/api/share/{token}/frames/1"
                            page_url = f"{settings.app_url}/share/{token}"

                            html_content = _inject_og_tags(
                                _get_index_html(), title, desc, image_url, page_url,
                            )
                            return HTMLResponse(html_content)
                except Exception:
                    pass  # Fall through to default SPA

        # Otherwise serve index.html (SPA routing)
        return FileResponse(_frontend_dist / "index.html")


async def _run_migrations():
    """Run database migrations and backfills. Called during startup.

    Uses pg_advisory_lock to prevent concurrent execution when multiple
    uvicorn workers start simultaneously.
    """
    import logging
    from sqlalchemy import text

    logger = logging.getLogger(__name__)

    try:
        async with engine.begin() as conn:
            # Distributed lock: only one uvicorn worker runs migrations
            # Use try_advisory_lock to avoid blocking if previous connection holds lock
            lock_result = await conn.execute(text("SELECT pg_try_advisory_lock(42)"))
            got_lock = lock_result.scalar()
            if not got_lock:
                logger.info("Another process holds migration lock, skipping migrations")
                return
            await conn.run_sync(Base.metadata.create_all)

            # Migrate: add columns if missing (safe, idempotent)
            await conn.execute(text("ALTER TABLE library_reels ADD COLUMN IF NOT EXISTS cover_frame_index INTEGER"))
            await conn.execute(text("ALTER TABLE library_reels ADD COLUMN IF NOT EXISTS video_comments FLOAT"))
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS video_comments FLOAT"))
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS share_token VARCHAR"))
            await conn.execute(text("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS anthropic_api_key VARCHAR"))
            await conn.execute(text("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS profile_json JSONB"))
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_filmed BOOLEAN DEFAULT false"))
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0"))
            await conn.execute(text("ALTER TABLE user_scripts ADD COLUMN IF NOT EXISTS active_hook_index INTEGER DEFAULT 0"))

            # Production pipeline fields on user_scripts
            await conn.execute(text("ALTER TABLE user_scripts ADD COLUMN IF NOT EXISTS production_status VARCHAR(20)"))
            await conn.execute(text("ALTER TABLE user_scripts ADD COLUMN IF NOT EXISTS assignee_id VARCHAR"))
            await conn.execute(text("ALTER TABLE user_scripts ADD COLUMN IF NOT EXISTS due_date TIMESTAMP"))
            await conn.execute(text("ALTER TABLE user_scripts ADD COLUMN IF NOT EXISTS scheduled_publish_at TIMESTAMP"))
            await conn.execute(text("ALTER TABLE user_scripts ADD COLUMN IF NOT EXISTS published_at TIMESTAMP"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_scripts_production_status ON user_scripts(production_status)"))

            # Shooting queue: filmed_at timestamp
            await conn.execute(text("ALTER TABLE shooting_queue ADD COLUMN IF NOT EXISTS filmed_at TIMESTAMP"))

            # Original script snapshots for comparison
            await conn.execute(text("ALTER TABLE user_scripts ADD COLUMN IF NOT EXISTS original_script TEXT"))
            await conn.execute(text("ALTER TABLE user_scripts ADD COLUMN IF NOT EXISTS original_description TEXT"))
            await conn.execute(text("ALTER TABLE user_scripts ADD COLUMN IF NOT EXISTS original_editor_instructions TEXT"))

            # Production pipeline role on users
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS team_role VARCHAR(20) DEFAULT 'owner'"))

            # Ghost user / tier system columns
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_anonymous BOOLEAN DEFAULT false"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS session_token VARCHAR(64)"))
            # Seed/demo flag — outbound automations must skip these
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_seed BOOLEAN NOT NULL DEFAULT false"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_is_seed ON users (is_seed) WHERE is_seed = true"))
            # Backfill: mark existing seed users by email pattern
            await conn.execute(text(
                "UPDATE users SET is_seed = true "
                "WHERE is_seed = false AND email LIKE 'seed-%@piratex.local'"
            ))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS tier VARCHAR(20) DEFAULT 'ANONYMOUS'"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_user_id VARCHAR"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_username VARCHAR"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_subscribed BOOLEAN DEFAULT false"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_checked_at TIMESTAMP"))

            # Billing: Stripe customer ID on users
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255)"))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_stripe_customer_id "
                "ON users(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL"
            ))

            # Billing: referral fields on users
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(12)"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by VARCHAR"))

            # Trends v2: delta-tracking & priority columns
            await conn.execute(text("ALTER TABLE profile_reels ADD COLUMN IF NOT EXISTS previous_views INTEGER"))
            await conn.execute(text("ALTER TABLE profile_reels ADD COLUMN IF NOT EXISTS views_updated_at TIMESTAMP"))
            await conn.execute(text("ALTER TABLE tracked_profiles ADD COLUMN IF NOT EXISTS check_priority VARCHAR DEFAULT 'normal'"))

            # Hot score: composite scoring model
            await conn.execute(text("ALTER TABLE profile_reels ADD COLUMN IF NOT EXISTS velocity FLOAT"))
            await conn.execute(text("ALTER TABLE profile_reels ADD COLUMN IF NOT EXISTS hot_score FLOAT"))
            await conn.execute(text("ALTER TABLE tracked_profiles ADD COLUMN IF NOT EXISTS consecutive_cold_checks INTEGER DEFAULT 0"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_profile_reels_hot_score "
                "ON profile_reels(is_trending, hot_score DESC NULLS LAST)"
            ))

            # Dynamic interests: topics column on tracked_profiles
            await conn.execute(text("ALTER TABLE tracked_profiles ADD COLUMN IF NOT EXISTS topics JSONB"))
            await conn.execute(text("ALTER TABLE tracked_profiles ADD COLUMN IF NOT EXISTS consecutive_scrape_failures INTEGER DEFAULT 0"))

            # Persistent thumbnails: storage key for downloaded thumbnails
            await conn.execute(text("ALTER TABLE profile_reels ADD COLUMN IF NOT EXISTS thumbnail_key VARCHAR"))

            # Author freeze: frozen flag on user_tracked_profiles for tier enforcement
            await conn.execute(text("ALTER TABLE user_tracked_profiles ADD COLUMN IF NOT EXISTS frozen BOOLEAN NOT NULL DEFAULT FALSE"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_user_tracked_profiles_frozen "
                "ON user_tracked_profiles(user_id, frozen)"
            ))

            # Telegram Bot jobs: source tracking columns on jobs
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'web'"))
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR"))
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS telegram_message_id INTEGER"))

            # Content Radar: dedup column for push notifications
            await conn.execute(text("ALTER TABLE profile_reels ADD COLUMN IF NOT EXISTS radar_notified_at TIMESTAMP"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_profile_reels_radar_pending "
                "ON profile_reels(is_trending, radar_notified_at) "
                "WHERE is_trending = true AND radar_notified_at IS NULL"
            ))

            # OAuth: frontend redirect path after auth
            await conn.execute(text("ALTER TABLE oauth_states ADD COLUMN IF NOT EXISTS frontend_redirect VARCHAR"))

            # Subscription proration: scheduled downgrade + actual paid amount
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS scheduled_tier VARCHAR(20)"))
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS scheduled_interval VARCHAR(10)"))
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS paid_amount_kopecks BIGINT"))

            # Support: block spammers
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS support_blocked BOOLEAN DEFAULT false"))

            # Security: JWT token version for revocation
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER DEFAULT 1"))

            # Security: store payment URL for checkout deduplication
            await conn.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_url TEXT"))

            # Security: server-side checkout intent (anti-spoofing for CloudPayments)
            await conn.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS checkout_tier VARCHAR(20)"))
            await conn.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS checkout_interval VARCHAR(20)"))
            await conn.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS expected_amount_kopecks BIGINT"))

            # Security: track client IP for abuse detection
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS client_ip VARCHAR"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_client_ip ON jobs (client_ip) WHERE client_ip IS NOT NULL"))

            # Ratings: admin viewed_at for unread tracking
            await conn.execute(text("ALTER TABLE script_ratings ADD COLUMN IF NOT EXISTS viewed_at TIMESTAMP"))

            # ── Performance indexes ──────────────────────────────────

            # Jobs: user dashboard + usage count (user_id prefix covers single-col queries too)
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_jobs_user_created "
                "ON jobs(user_id, created_at DESC)"
            ))
            # Jobs: URL dedup on create (jobs.url has no index!)
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_jobs_url_status "
                "ON jobs(url, status)"
            ))
            # Jobs: admin list + stuck recovery + analytics
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status_created "
                "ON jobs(status, created_at DESC)"
            ))

            # Trends: date filter + recent sort (partial — only trending rows)
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_profile_reels_trending_published "
                "ON profile_reels(is_trending, published_at DESC) "
                "WHERE is_trending = true"
            ))
            # Trends: cron stale check with priority passes (partial — only active)
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_tracked_profiles_stale_check "
                "ON tracked_profiles(is_active, check_priority, last_checked_at ASC NULLS FIRST) "
                "WHERE is_active = true"
            ))

            # Library: FK for admin join + cascade deletes
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_library_reels_submitted_by "
                "ON library_reels(submitted_by)"
            ))
            # Library: sort by recent on browse page
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_library_reels_created_at "
                "ON library_reels(created_at DESC)"
            ))

            # Messages: admin conversation view (filter + sort)
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_telegram_messages_tg_user_created "
                "ON telegram_messages(telegram_user_id, created_at)"
            ))

            # Text search: pg_trgm GIN for ILIKE on transcripts and titles
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_library_reels_transcript_trgm "
                "ON library_reels USING gin (transcript_text gin_trgm_ops)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_library_reels_title_trgm "
                "ON library_reels USING gin (video_title gin_trgm_ops)"
            ))

            # Make columns nullable for ghost users
            await conn.execute(text("ALTER TABLE users ALTER COLUMN email DROP NOT NULL"))
            await conn.execute(text("ALTER TABLE users ALTER COLUMN name DROP NOT NULL"))
            await conn.execute(text("ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL"))

            # Partial unique indexes
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_session_token "
                "ON users(session_token) WHERE session_token IS NOT NULL"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_user_id "
                "ON users(telegram_user_id) WHERE telegram_user_id IS NOT NULL"
            ))

            # Consent log table (376-ФЗ compliance)
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS consent_logs (
                    id VARCHAR PRIMARY KEY,
                    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    consent_type VARCHAR(50) NOT NULL,
                    action VARCHAR(20) NOT NULL,
                    ip_address VARCHAR(45),
                    user_agent VARCHAR(500),
                    metadata_json VARCHAR(2000),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_consent_logs_user_id ON consent_logs(user_id)"
            ))

            # Script ratings table (quality feedback)
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS script_ratings (
                    id VARCHAR PRIMARY KEY,
                    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    job_id VARCHAR NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    rating INTEGER NOT NULL,
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_script_ratings_user_id ON script_ratings(user_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_script_ratings_job_id ON script_ratings(job_id)"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_script_rating_user_job "
                "ON script_ratings(user_id, job_id)"
            ))

            # Support conversations table (in-app messenger)
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS support_conversations (
                    id VARCHAR PRIMARY KEY,
                    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status VARCHAR(20) DEFAULT 'open',
                    unread_admin INTEGER DEFAULT 0,
                    unread_user INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_support_conversations_user_id "
                "ON support_conversations(user_id)"
            ))

            # Support messages table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS support_messages (
                    id VARCHAR PRIMARY KEY,
                    conversation_id VARCHAR NOT NULL REFERENCES support_conversations(id) ON DELETE CASCADE,
                    sender_type VARCHAR(10) NOT NULL,
                    sender_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    text TEXT,
                    image_key VARCHAR,
                    read_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_support_messages_conversation_id "
                "ON support_messages(conversation_id)"
            ))

            # Fix: change ghost_user_id FK from CASCADE to SET NULL
            # so deleting a ghost user doesn't cascade-delete the auth code
            await conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE constraint_name = 'telegram_auth_codes_ghost_user_id_fkey'
                          AND table_name = 'telegram_auth_codes'
                    ) THEN
                        ALTER TABLE telegram_auth_codes
                            DROP CONSTRAINT telegram_auth_codes_ghost_user_id_fkey;
                        ALTER TABLE telegram_auth_codes
                            ADD CONSTRAINT telegram_auth_codes_ghost_user_id_fkey
                            FOREIGN KEY (ghost_user_id) REFERENCES users(id)
                            ON DELETE SET NULL;
                    END IF;
                END $$;
            """))

            # Trend-watching: indexes for feed queries and thumbnail backfill
            # Note: scheduler stale-check covered by idx_tracked_profiles_stale_check (partial, is_active=true)
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_profile_reel_published_at "
                "ON profile_reels (published_at)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_profile_reel_thumbnail_missing "
                "ON profile_reels (thumbnail_key) WHERE thumbnail_key IS NULL"
            ))

            # Cost tracking per job
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cost_breakdown JSONB"))

            # Admin trending reels: date of trend detection
            await conn.execute(text("ALTER TABLE profile_reels ADD COLUMN IF NOT EXISTS trending_since TIMESTAMPTZ"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_profile_reels_trending_since "
                "ON profile_reels(is_trending, trending_since DESC) "
                "WHERE is_trending = true"
            ))

            # Magic link: short PIN code for manual entry
            await conn.execute(text("ALTER TABLE magic_link_codes ADD COLUMN IF NOT EXISTS pin VARCHAR(6)"))
            await conn.execute(text("ALTER TABLE magic_link_codes ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0"))

            # Bilingual scripts: second-language translations of a UserScript
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS script_translations (
                    id VARCHAR PRIMARY KEY,
                    user_script_id VARCHAR NOT NULL REFERENCES user_scripts(id) ON DELETE CASCADE,
                    language VARCHAR(8) NOT NULL,
                    script TEXT NOT NULL,
                    description TEXT NOT NULL,
                    editor_instructions TEXT NOT NULL,
                    original_script TEXT,
                    original_description TEXT,
                    original_editor_instructions TEXT,
                    source_revision VARCHAR(64),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_script_translations_user_script_id "
                "ON script_translations(user_script_id)"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_script_translation "
                "ON script_translations(user_script_id, language)"
            ))

        # Backfill operations in separate transactions (PostgreSQL aborts entire
        # transaction on error, so each fallible operation needs its own tx)
        async def _safe_exec(label: str, sql: str) -> None:
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(sql))
            except Exception as e:
                logger.info(f"[migration] {label}: {e}")

        await _safe_exec("backfill share_token", """
            UPDATE jobs
            SET share_token = substr(md5(random()::text || id), 1, 24)
            WHERE share_token IS NULL
        """)

        await _safe_exec("backfill cover_frame_index", """
            UPDATE library_reels
            SET cover_frame_index = (frames_json->1->>'frame_index')::integer
            WHERE cover_frame_index IS NULL
              AND frames_json IS NOT NULL
        """)

        await _safe_exec("backfill user_scripts", """
            INSERT INTO user_scripts
                (id, user_id, library_reel_id, script, description, editor_instructions, created_at, updated_at)
            SELECT
                gen_random_uuid()::text,
                j.user_id,
                j.library_reel_id,
                j.adaptation_summary->>'script',
                j.adaptation_summary->>'description',
                j.adaptation_summary->>'editor_instructions',
                NOW(),
                NOW()
            FROM jobs j
            WHERE j.library_reel_id IS NOT NULL
              AND j.adaptation_summary IS NOT NULL
              AND j.status = 'completed'
              AND j.adaptation_summary->>'script' IS NOT NULL
            ON CONFLICT (user_id, library_reel_id) DO NOTHING
        """)

        await _safe_exec("backfill trending_since", """
            UPDATE profile_reels SET trending_since = updated_at
            WHERE is_trending = true AND trending_since IS NULL
        """)

        await _safe_exec("backfill check_priority", """
            UPDATE tracked_profiles SET check_priority = 'normal' WHERE check_priority IS NULL
        """)

        await _safe_exec("backfill consecutive_cold_checks", """
            UPDATE tracked_profiles SET consecutive_cold_checks = 0 WHERE consecutive_cold_checks IS NULL
        """)

        await _safe_exec("backfill user tiers", """
            UPDATE users SET tier = 'FREE', is_anonymous = false
            WHERE email IS NOT NULL AND (tier IS NULL OR tier = 'ANONYMOUS')
        """)


        # Cleanup expired telegram auth codes
        await _safe_exec("cleanup expired telegram auth codes", """
            DELETE FROM telegram_auth_codes
            WHERE expires_at < NOW() - INTERVAL '1 hour'
        """)

        # Migrate BASIC → START (rename tier)
        await _safe_exec("migrate BASIC tier to START", """
            UPDATE users SET tier = 'START' WHERE tier = 'BASIC'
        """)
        await _safe_exec("migrate BASIC tier_config to START", """
            DELETE FROM tier_configs WHERE name = 'BASIC'
        """)

        # Seed tier_configs from TIER_LIMITS defaults (idempotent)
        await _safe_exec("seed tier_configs", """
            INSERT INTO tier_configs (name, max_monthly, max_total)
            VALUES
                ('ANONYMOUS', NULL, 1),
                ('REGISTERED', 0, NULL),
                ('FREE', 3, NULL),
                ('START', 50, NULL),
                ('PRO', 150, NULL),
                ('UNLIMITED', 500, NULL)
            ON CONFLICT (name) DO NOTHING
        """)

        # Add max_refines_daily column to tier_configs
        await _safe_exec("add max_refines_daily to tier_configs", """
            ALTER TABLE tier_configs ADD COLUMN IF NOT EXISTS max_refines_daily INTEGER
        """)

        # Seed max_refines_daily defaults (only if NULL — don't overwrite admin values)
        await _safe_exec("seed max_refines_daily defaults", """
            UPDATE tier_configs SET max_refines_daily = CASE name
                WHEN 'FREE' THEN 5
                WHEN 'START' THEN 30
                WHEN 'PRO' THEN 100
                WHEN 'UNLIMITED' THEN 200
            END
            WHERE max_refines_daily IS NULL
              AND name IN ('FREE', 'START', 'PRO', 'UNLIMITED')
        """)

        # Seed early bird promo code (idempotent)
        await _safe_exec("seed early bird promo", """
            INSERT INTO promo_codes (id, code, discount_percent, max_uses, used_count, duration_months, valid_tiers, is_active, created_at)
            VALUES (
                'earlybird-001',
                'EARLYBIRD30',
                30,
                200,
                0,
                3,
                'START,PRO,UNLIMITED',
                true,
                NOW()
            )
            ON CONFLICT (code) DO NOTHING
        """)


        # Deduplicate active subscriptions before adding unique constraint
        await _safe_exec("dedup active subscriptions", """
            UPDATE subscriptions SET status = 'expired'
            WHERE id IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY user_id
                        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                    ) AS rn
                    FROM subscriptions
                    WHERE status IN ('active', 'past_due')
                ) ranked
                WHERE rn > 1
            )
        """)

        await _safe_exec("unique index active subscriptions", """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_subscription_user_active
            ON subscriptions(user_id)
            WHERE status IN ('active', 'past_due')
        """)

        # Profile parsings table (tracks deep-analyze runs)
        await _safe_exec("create profile_parsings table", """
            CREATE TABLE IF NOT EXISTS profile_parsings (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                analysis_id VARCHAR(36) NOT NULL,
                platform VARCHAR(20) NOT NULL DEFAULT 'instagram',
                username VARCHAR(100) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'running',
                error TEXT,
                duration_seconds FLOAT,
                result_json JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
        """)
        await _safe_exec("index profile_parsings user_id",
            "CREATE INDEX IF NOT EXISTS ix_profile_parsings_user_id ON profile_parsings(user_id)")
        await _safe_exec("unique index profile_parsings analysis_id",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_profile_parsings_analysis_id ON profile_parsings(analysis_id)")

        # ── 2026-03-23: Check BEFORE seed — do new niches already exist? ──
        _needs_niche_reset = False
        _new_niche_check = await _safe_exec("check new niches exist before seed",
            "SELECT COUNT(*) FROM niches WHERE slug IN ('psychology', 'astrology', 'cinema', 'fishing') AND is_active = true")
        if _new_niche_check:
            row = _new_niche_check.fetchone()
            _needs_niche_reset = (row[0] if row else 0) < 4

        # Seed niches from NICHE_DEFINITIONS
        from app.core.niches import NICHE_DEFINITIONS, NICHE_GROUPS

        _group_for_slug: dict[str, str] = {}
        for gk, slugs in NICHE_GROUPS.items():
            for s in slugs:
                _group_for_slug[s] = gk

        _niche_values = []
        for idx, (slug, nd) in enumerate(NICHE_DEFINITIONS.items()):
            import json as _niche_json
            kw = "'" + _niche_json.dumps(nd.keywords) + "'"
            dn = nd.display_name.replace("'", "''")
            desc = nd.description.replace("'", "''") if nd.description else ""
            gk = _group_for_slug.get(slug, "other")
            _niche_values.append(
                f"('{slug}', '{dn}', '{desc}', {kw}, '{gk}', {idx}, true, NOW(), NOW())"
            )

        if _niche_values:
            _niche_sql = (
                "INSERT INTO niches (slug, display_name, description, keywords, group_key, sort_order, is_active, created_at, updated_at) VALUES "
                + ", ".join(_niche_values)
                + " ON CONFLICT (slug) DO UPDATE SET group_key = EXCLUDED.group_key, sort_order = EXCLUDED.sort_order, updated_at = NOW()"
            )
            await _safe_exec("seed niches from NICHE_DEFINITIONS", _niche_sql)

        # Index on tracked_profiles.niche (missing, causes slow GROUP BY in admin)
        await _safe_exec("index tracked_profiles niche",
            "CREATE INDEX IF NOT EXISTS idx_tracked_profiles_niche ON tracked_profiles(niche)")

        # ── Reset niches for reclassification (one-time, only on first deploy with new niches) ──
        if _needs_niche_reset:
            await _safe_exec("reset profile niches for 100-niche expansion",
                "UPDATE tracked_profiles SET niche = NULL WHERE niche IS NOT NULL")
            await _safe_exec("reset reel niches for 100-niche expansion",
                "UPDATE profile_reels SET niche = NULL WHERE niche IS NOT NULL")
            logger.info("[startup] Reset all niches for 100-niche reclassification")

        # Initialize niche cache after seeding
        from app.core.niche_cache import niche_cache
        try:
            async with async_session() as _nc_session:
                await niche_cache.refresh(_nc_session)
                logger.info("[startup] Niche cache loaded: %d niches", len(niche_cache._niches))
        except Exception as e:
            logger.info(f"[startup] Niche cache init error: {e}")

        # Ghost user cleanup
        from app.api.admin import cleanup_ghost_users

        async with async_session() as session:
            try:
                deleted = await cleanup_ghost_users(session)
                if deleted:
                    logger.info(f"[startup] Cleaned up {deleted} ghost users")
            except Exception as e:
                logger.info(f"[startup] Ghost cleanup error: {e}")

        # Storage garbage collection — delete orphaned files
        from app.services.storage_cleanup import garbage_collect_orphaned_files

        async with async_session() as session:
            try:
                gc_result = await garbage_collect_orphaned_files(session)
                if gc_result["orphaned_jobs"]:
                    logger.info("[startup] Storage GC: cleaned %d orphaned job(s), %d file(s)",
                                len(gc_result["orphaned_jobs"]), gc_result["deleted_frames"])
            except Exception as e:
                logger.info(f"[startup] Storage GC error: {e}")

        # Cleanup old failed jobs
        from app.services.storage_cleanup import cleanup_failed_jobs

        async with async_session() as session:
            try:
                result = await cleanup_failed_jobs(session, ttl_days=settings.failed_job_retention_days)
                if result["deleted_jobs"]:
                    logger.info("[startup] Cleaned up %d failed job(s), %d frame(s)",
                                result["deleted_jobs"], result["deleted_frames"])
            except Exception as e:
                logger.info(f"[startup] Failed job cleanup error: {e}")

        logger.info("[startup] Migrations completed successfully")
    except Exception as e:
        logger.error(f"[startup] Migration error: {e}")


async def _register_telegram_webhook():
    """Register Telegram bot webhook if configured."""
    import logging

    import httpx

    logger = logging.getLogger(__name__)

    webhook_url = settings.telegram_webhook_url
    bot_token = settings.telegram_bot_token

    if not webhook_url or not bot_token:
        logger.info("[startup] Telegram webhook not configured, skipping")
        return

    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    payload = {
        "url": f"{webhook_url}/api/telegram/webhook",
        "allowed_updates": ["message", "callback_query"],
    }
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200 and resp.json().get("ok"):
                logger.info(
                    f"[startup] Telegram webhook registered: {webhook_url}/api/telegram/webhook"
                )
            else:
                logger.error(f"[startup] Failed to register Telegram webhook: {resp.text}")

            # Register bot commands with BotFather
            from app.services.telegram import set_bot_commands
            await set_bot_commands(bot_token)
            logger.info("[startup] Telegram bot commands registered")
    except Exception as e:
        logger.error(f"[startup] Telegram webhook registration error: {e}")



# Background loops (watchdog, billing, trends, engagement, radar, etc.)
# have been moved to app/scheduler/loops.py and run via run_scheduler.py.


@app.on_event("startup")
async def startup():
    import asyncio
    import logging

    from app.core.arq_pool import managed_arq_pool

    logger = logging.getLogger(__name__)

    # Validate JWT secret is set and not a placeholder
    if not settings.jwt_secret or settings.jwt_secret == "change-me-in-production":
        raise RuntimeError(
            "JWT_SECRET is not configured. "
            "Set a strong secret via environment variable: "
            "export JWT_SECRET=$(openssl rand -hex 32)"
        )

    # Create managed arq Redis pool with auto-reconnect
    app.state.managed_arq_pool = managed_arq_pool
    app.state.arq_pool = await managed_arq_pool.connect()

    # Log pool configuration for debugging connection issues
    from app.database import engine
    pool = engine.pool
    logger.info(
        "[startup] DB pool: size=%d, max_overflow=%d, timeout=%d → max %d connections",
        pool.size(), pool._max_overflow, pool._timeout, pool.size() + pool._max_overflow,
    )

    # Migrations must complete before anything else
    await _run_migrations()
    asyncio.create_task(_register_telegram_webhook())

    # NOTE: Background loops (watchdog, billing, trends, engagement, radar, etc.)
    # have been moved to the scheduler service (run_scheduler.py).
    # They must NOT run in the web process — multi-process uvicorn would
    # duplicate them (billing charged N times, notifications sent N times).


@app.on_event("shutdown")
async def shutdown():
    import logging

    logger = logging.getLogger(__name__)
    logger.info("[shutdown] Closing connection pools...")

    # Close arq Redis pool
    managed = getattr(app.state, "managed_arq_pool", None)
    if managed:
        await managed.close()

    # Close shared Redis pool
    from app.core.redis_pool import close_pool
    await close_pool()

    # Close DB engine
    from app.database import engine
    await engine.dispose()

    logger.info("[shutdown] All pools closed.")
