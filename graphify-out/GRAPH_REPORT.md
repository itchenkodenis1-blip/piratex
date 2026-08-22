# Graph Report - piratex  (2026-08-17)

## Corpus Check
- 310 files · ~361,006 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3997 nodes · 9989 edges · 166 communities (156 shown, 10 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 1166 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `8f3837dc`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App.tsx
- Job
- trend_monitor.py
- config.py
- DownloadError
- useTranslation
- Base
- types/index.ts
- i18n/index.ts
- Subscription
- api/pipeline.py
- client.ts
- api/trends.py
- PipelineSidePanel.tsx
- User
- api/admin.py
- ws.py
- ShowcaseDashboard.tsx
- api/telegram.py
- tasks.py
- WebhookEvent
- services/billing.py
- ProfileReel
- api/library.py
- test_video_validation.py
- AdminPage.tsx
- UserProfile
- AdminDashboard.tsx
- magic_link.py
- strategist.py
- NicheCache
- summarizer.py
- AdminLibrary.tsx
- post
- AsyncSession
- YouTubeScraper
- api/billing.py
- StorageBackend
- Deploy to Railway — step by step
- orchestrator.py
- generate_canary
- api/support.py
- TrendsPage.tsx
- test_blog_analyzer.py
- compose_content_prompt
- auth_headers
- OAuthProvider
- patch
- asyncio
- useAuth
- _apify_client.py
- calculate_proration
- email_sender.py
- SupportMessage
- demo_data.py
- compilerOptions
- DeepAnalyzeResult
- AdminJobs.tsx
- _build_synthesis_prompt
- test_support_notifier.py
- AdminUserDetail.tsx
- _parse_json_response
- get_frames_dir
- AdminTrends.tsx
- compilerOptions
- metrics.py
- LocalStorage
- AdminNiches.tsx
- main.py
- make_user
- S3Storage
- UserScript
- get_redis
- test_translator.py
- detect_platform
- dependencies
- UserSettingsUpdate
- devDependencies
- _process_single_reel
- AdminTiers.tsx
- ProgressTracker
- morning_brief.py
- test_rating_api.py
- Piratex.ai — Playbook масштабирования
- AdminUsers.tsx
- get_interests
- TestProfileMergeLogic
- ffmpeg_slot
- extract_youtube_video_id
- test_script_translations.py
- like_reel
- ChatWidget.tsx
- Teleprompter.tsx
- speech-recognition.d.ts
- get_me
- compose_strategy_prompt
- AdminPayments.tsx
- get_rating_detail
- oauth_callback
- TierConfig
- refine_field
- ManagedArqPool
- transcribe
- ShowcaseTracker
- AdminRatings.tsx
- build_system_blocks
- refine_usage.py
- package.json
- trend_watching_activity
- detect_same_language
- .parse_webhook
- _is_youtube_short
- _parse_duration_str
- yookassa_client.py
- calculate_daily_metrics
- get_shared_job
- If the user is developing
- Deploy with Claude Code (for non-programmers)
- MaskedPII.tsx
- check_env.py
- cost_tracker.py
- cloudpayments.d.ts
- 010_fix_pipeline_fk_and_index.py
- delete_my_account
- send_founder_welcome
- _Heartbeat
- TestAnalyzeBlogNoneValuesFromClaude
- Piratex.ai — Pricing & Limits
- 009_add_production_pipeline.py
- 013_add_multiauth_tables.py
- garbage_collect_orphaned_files
- SecurityHeadersMiddleware
- async_engine
- 011_add_payment_provider_to_payments.py
- WorkerSettings
- _aggregate_costs
- Settings
- tsconfig.json
- start.sh
- DEPLOY.md
- @eslint/js
- react-dom
- tailwindcss
- @types/react
- typescript-eslint

## God Nodes (most connected - your core abstractions)
1. `User` - 289 edges
2. `Job` - 102 edges
3. `UserProfile` - 100 edges
4. `useTranslation()` - 83 edges
5. `JobStatus` - 77 edges
6. `ProfileReel` - 67 edges
7. `Base` - 58 edges
8. `TrackedProfile` - 56 edges
9. `auth_headers()` - 54 edges
10. `Subscription` - 53 edges

## Surprising Connections (you probably didn't know these)
- `test_dual_language_defaults_are_none()` --uses--> `UserProfile`  [INFERRED]
  backend/tests/test_script_translations.py → backend/app/schemas/profile.py
- `test_user_profile_accepts_dual_language_fields()` --uses--> `UserProfile`  [INFERRED]
  backend/tests/test_script_translations.py → backend/app/schemas/profile.py
- `test_user_profile_rejects_invalid_second_language()` --uses--> `UserProfile`  [INFERRED]
  backend/tests/test_script_translations.py → backend/app/schemas/profile.py
- `list_users()` --uses--> `Job`  [INFERRED]
  backend/app/api/admin.py → backend/app/models/job.py
- `list_users()` --uses--> `AdminUserItem`  [INFERRED]
  backend/app/api/admin.py → backend/app/schemas/admin.py

## Import Cycles
- None detected.

## Communities (166 total, 10 thin omitted)

### Community 0 - "App.tsx"
Cohesion: 0.03
Nodes (87): cancelSubscription(), cancelSubscriptionByToken(), createCheckout(), getPaymentProviders(), getPayments(), getPortalUrl(), getSharedFrameUrl(), getSharedJob() (+79 more)

### Community 1 - "Job"
Cohesion: 0.04
Nodes (90): create_job(), limit, post, Request, rate_job(), Rate a completed job (1-5 stars). Upserts: one rating per user per job., InvalidURLError, URL failed validation (SSRF, unsupported platform, etc.). (+82 more)

### Community 2 - "trend_monitor.py"
Cohesion: 0.04
Nodes (89): analyze_instagram(), Analyze user's Instagram profile to extract interests for personalization., niche_prompt_compact(), niche_prompt_detailed(), NicheDefinition, Central niche definitions registry — single source of truth for the entire app., For Haiku / lightweight classification: 'slug: description' per line., For GPT-4o / full classification: includes signal keywords. (+81 more)

### Community 3 - "config.py"
Cohesion: 0.05
Nodes (66): Admin Trend Watching endpoints — monitoring dashboard for trend pipeline.…, get_frame_image(), get_job(), get_rating(), hide_job(), list_jobs(), AsyncSession, delete (+58 more)

### Community 4 - "DownloadError"
Cohesion: 0.05
Nodes (62): DownloadError, Return a compact summary of an Apify item for logging. Shows all keys with…, Run an Apify actor and return dataset items. Retries up to _MAX_EMPTY_RETRIES…, Extract domain from URL for logging (no secrets in CDN URLs)., run_actor(), _safe_domain(), _summarise_item(), _first() (+54 more)

### Community 5 - "useTranslation"
Cohesion: 0.05
Nodes (66): createJob(), getJob(), getPricing(), updateJobFields(), AuthCallbackPage, AdaptationSummary(), CollapsibleSection(), CopyBlock() (+58 more)

### Community 6 - "Base"
Cohesion: 0.06
Nodes (65): do_run_migrations(), Alembic async environment for PostgreSQL migrations., Run migrations in 'offline' mode (generate SQL script)., Run migrations in 'online' mode with async engine., Run migrations in 'online' mode., run_async_migrations(), run_migrations_offline(), run_migrations_online() (+57 more)

### Community 7 - "types/index.ts"
Cohesion: 0.04
Nodes (63): adminGetTrendWatchingActivity(), adminGetTrendWatchingPipeline(), adminGetTrendWatchingSparklines(), adminGetTrendWatchingStats(), ActivityFeed(), EventRow(), formatTime(), AdminTrendWatching() (+55 more)

### Community 8 - "i18n/index.ts"
Cohesion: 0.05
Nodes (58): deepAnalyzeInstagram(), deleteAccount(), disconnectTelegram(), getDefaultPrompts(), getProfilePresets(), getRadarSettings(), getSettingsInterests(), getTelegramStatus() (+50 more)

### Community 9 - "Subscription"
Cohesion: 0.06
Nodes (63): Payment, Subscription, billing_loop(), Process recurring payments, expiry, and reminders (every hour). Uses Redis lock…, generate_cancel_token(), handle_proration_payment(), handle_subscription_deleted(), Generate a signed cancel token (valid 7 days, HMAC-SHA256). Format:… (+55 more)

### Community 10 - "api/pipeline.py"
Cohesion: 0.07
Nodes (70): add_comment(), add_to_pipeline(), add_to_pipeline_by_job(), assign_script(), AssignRequest, change_status(), confirm_asset_upload(), delete_asset() (+62 more)

### Community 11 - "client.ts"
Cohesion: 0.05
Nodes (48): addToShootingQueue(), adminBlockSupportUser(), adminGetSupportMessages(), adminListSupportConversations(), adminResolveSupportConversation(), adminSendSupportMessage(), api, bookmarkReel() (+40 more)

### Community 12 - "api/trends.py"
Cohesion: 0.06
Nodes (62): add_my_author(), _build_trend_item(), _collect_user_signals(), _escape_like(), _get_exclude_ids(), get_for_you(), get_trend_frame(), get_trend_thumbnail() (+54 more)

### Community 13 - "PipelineSidePanel.tsx"
Cohesion: 0.06
Nodes (51): addPipelineComment(), assignPipeline(), changePipelineStatus(), confirmPipelineAsset(), deletePipelineAsset(), getAssetDownloadUrl(), getPipelineAssets(), getPipelineComments() (+43 more)

### Community 14 - "User"
Cohesion: 0.07
Nodes (65): admin_support_unread_count(), apify_budget(), cleanup_ghost_users(), cleanup_ghosts(), deactivate_niche(), delete_job(), delete_library_item(), delete_tracked_profile() (+57 more)

### Community 15 - "api/admin.py"
Cohesion: 0.09
Nodes (62): get_analytics(), get_user_detail(), list_niches(), list_trending_reels(), List trending reels for admin dashboard with date filtering and summary stats., List all niches with video/author counts., AdminAnalyticsResponse, AdminConversationItem (+54 more)

### Community 16 - "ws.py"
Cohesion: 0.07
Nodes (43): admin_showcase_ws(), admin_trend_watching_ws(), _authenticate_ws(), blog_analysis_ws(), _check_connection_limits(), _get_client_ip(), _is_admin_user(), job_progress_ws() (+35 more)

### Community 17 - "ShowcaseDashboard.tsx"
Cohesion: 0.06
Nodes (47): checkMilestone(), daysSinceLaunch(), drawStar(), EVENT_CONFIG, formatDuration(), formatMoney(), formatNumber(), getAudioCtx() (+39 more)

### Community 18 - "api/telegram.py"
Cohesion: 0.07
Nodes (54): _cb_analyze_reel(), _cb_send_content(), _cb_support_reply_prompt(), _cmd_help(), _cmd_start(), _cmd_start_code(), _cmd_status(), create_connect_code() (+46 more)

### Community 19 - "tasks.py"
Cohesion: 0.07
Nodes (51): init_cost_tracker(), Create a new tracker and set it as current. Call at the start of a job., is_transient_error(), Classify raw system errors into user-friendly messages. Raw errors are kept in…, Return True if the error is transient and the job should be retried., Progress tracker with Redis Pub/Sub bridge. Workers call broadcast() →…, emit_showcase_event(), Publish a showcase event to Redis (best-effort, never raises). Events with… (+43 more)

### Community 20 - "WebhookEvent"
Cohesion: 0.07
Nodes (29): field_validator, model_validator, CheckoutResult, PaymentProvider, ABC, Base classes for the multi-provider payment system., Normalised webhook event — same shape regardless of provider., Interface every payment provider must implement. (+21 more)

### Community 21 - "services/billing.py"
Cohesion: 0.07
Nodes (46): Validate a promo code without creating a payment., validate_promo(), PromoCode, cancel_by_token(), cancel_scheduled_downgrade(), cancel_subscription(), change_tier(), create_checkout() (+38 more)

### Community 22 - "ProfileReel"
Cohesion: 0.08
Nodes (50): list_trend_niches(), _personal_score(), Calculate personalization score for a reel based on Interest Graph. Components:…, Get niche stats: how many trending reels per niche., ProfileReel, TrackedProfile, check_and_alert_er_drops(), _compute_er_from_reels() (+42 more)

### Community 23 - "api/library.py"
Cohesion: 0.09
Nodes (48): bookmark_reel(), _build_reel_card(), generate_script(), get_library_reel(), list_bookmarks(), list_library(), list_tags(), AsyncSession (+40 more)

### Community 24 - "test_video_validation.py"
Cohesion: 0.07
Nodes (49): _download_file(), _download_via_ytdlp(), download_video_to_local(), ensure_video_local(), _merge_video_audio(), Path, Merge separate video and audio streams using ffmpeg., Download video from a direct URL to local storage. If audio_url is provided… (+41 more)

### Community 25 - "AdminPage.tsx"
Cohesion: 0.06
Nodes (40): adminGetConversation(), adminGetParsingStats(), adminGetSupportUnreadCount(), adminGetUnreadRatingsCount(), adminListConversations(), adminListHiddenReels(), adminListParsings(), adminSendMessage() (+32 more)

### Community 26 - "UserProfile"
Cohesion: 0.08
Nodes (7): field_validator, Structured profile fields that compose into personalized prompts., UserProfile, TestUserProfileInterestValidation, TestUserProfileNicheValidation, TestUserProfileRadarValidation, TestUserProfile

### Community 27 - "AdminDashboard.tsx"
Cohesion: 0.07
Nodes (39): adminCleanupGhosts(), adminGetFounderAvatar(), adminReextractFrames(), adminUploadFounderAvatar(), getAdminAnalytics(), getAdminCostAnalytics(), getAdminStats(), getDemoMode() (+31 more)

### Community 28 - "magic_link.py"
Cohesion: 0.08
Nodes (42): check_magic_link(), MagicLinkRequest, PinVerifyRequest, AsyncSession, BaseModel, get, limit, post (+34 more)

### Community 29 - "strategist.py"
Cohesion: 0.09
Nodes (38): Track GPT-4o-mini vision call cost from OpenAI response., Track OpenAI text generation call cost (fallback model)., track_openai_text(), track_vision(), InsufficientDataError, Not enough data (transcript + frames) to generate content., CommentsStrategy, CoverRecommendation (+30 more)

### Community 30 - "NicheCache"
Cohesion: 0.06
Nodes (23): get_niche_tree(), NicheChild, NicheGroup, NicheTreeResponse, AsyncSession, BaseModel, get, Public niches API — returns niche tree for 2-step dropdown. (+15 more)

### Community 31 - "summarizer.py"
Cohesion: 0.10
Nodes (37): anthropic_create_with_retry(), _delay_with_jitter(), openai_create_with_retry(), Retry helpers for external API calls (Anthropic, OpenAI). Handles transient…, Exponential backoff with ±25% jitter: 3s, 6s, 12s, 24s., Call client.messages.create() with retry on transient errors. Returns the API…, Call client.chat.completions.create() with retry on transient errors. Returns…, cache_get() (+29 more)

### Community 32 - "AdminLibrary.tsx"
Cohesion: 0.09
Nodes (33): adminDeleteLibraryItem(), getLibrary(), getLibraryTags(), hideJob(), listJobs(), toggleJobFilmed(), MyVideosPage, AdminLibrary() (+25 more)

### Community 33 - "post"
Cohesion: 0.05
Nodes (39): AdminSendMessageRequest, AdminSupportSendRequest, activate_niche(), admin_send_message(), admin_send_support_message(), block_support_user(), block_tracked_profile(), cancel_job() (+31 more)

### Community 34 - "AsyncSession"
Cohesion: 0.12
Nodes (38): cancel(), cancel_by_token_endpoint(), change_tier_endpoint(), checkout(), create_portal(), delete_payment_method(), _handle_webhook(), _log_consent() (+30 more)

### Community 35 - "YouTubeScraper"
Cohesion: 0.08
Nodes (24): NotYouTubeShortsError, URL is a regular YouTube video, not a Short., YouTube Shorts scraper with three-tier fallback. 1. Primary:…, Disabled — comment count already comes from the main video actor. Saves…, YouTubeScraper, _dc_response(), _marielise_response(), Tests for YouTube Shorts-only filtering (Phase 1). Tests: -… (+16 more)

### Community 36 - "api/billing.py"
Cohesion: 0.12
Nodes (33): cancel_downgrade(), cloudpayments_config(), get_pricing(), get_subscription(), list_payments(), list_providers(), proration_preview(), delete (+25 more)

### Community 37 - "StorageBackend"
Cohesion: 0.07
Nodes (20): ABC, Path, Abstract storage backend interface., Write file from bytes. Returns the storage key., Upload a local file to storage. Returns the storage key., Read file contents as bytes., Read only the first N bytes of a file. Default: full read + slice., Get a URL for the file. Pre-signed for S3, local path for disk. If… (+12 more)

### Community 38 - "Deploy to Railway — step by step"
Cohesion: 0.06
Nodes (32): Deploy to Railway — step by step, Step 1 — Put the code on GitHub, Step 2 — Create a Railway project, Step 3 — Add the databases, Step 4 — Configure the `web` service, Step 5 — Add the `worker` and `scheduler` services, Step 6 — Set environment variables, Step 7 — Persistent storage for media (+24 more)

### Community 39 - "orchestrator.py"
Cohesion: 0.09
Nodes (30): PiratexError, Exception, SceneDetectionError, VideoTooLongError, VisionAnalysisError, get_openai_client(), Get or create an AsyncOpenAI client for chat/vision completions via OpenRouter., Record interest signals for a user. Returns count of signals added. Args:… (+22 more)

### Community 40 - "generate_canary"
Cohesion: 0.11
Nodes (16): check_canary(), generate_canary(), OutputValidationError, Exception, Prompt injection defenses for LLM system prompts. Provides: -…, Raised when LLM output fails structural validation., Validate that content generation output has required non-empty fields., Validate that strategy generation output has required fields. (+8 more)

### Community 41 - "api/support.py"
Cohesion: 0.12
Nodes (31): get_conversation(), get_founder_avatar(), get_support_image(), get_unread_count(), _is_valid_image(), _notify_admin_telegram(), presign_support_upload(), AsyncSession (+23 more)

### Community 42 - "TrendsPage.tsx"
Cohesion: 0.10
Nodes (29): addMyAuthor(), adminBlockProfile(), adminHideReel(), adminListTrendingReels(), getMyAuthors(), getNicheTree(), getTrends(), TrendsPage (+21 more)

### Community 43 - "test_blog_analyzer.py"
Cohesion: 0.12
Nodes (27): deep_analyze_instagram(), post, Deep-analyze user's Instagram blog: download reels, transcribe, analyze frames,…, _ai_call_with_fallback(), analyze_blog(), _analyze_posts_batch(), EmptyProfileError, _esc() (+19 more)

### Community 44 - "compose_content_prompt"
Cohesion: 0.10
Nodes (19): compose_content_prompt(), _format_ai_markers(), _format_forbidden_words(), Compose personalized prompts from structured user profile fields. The templates…, Expand a preset key into full text, or return custom text as-is., Convert comma-separated words into a bullet-point line for the prompt., Wrap a value in XML tags if it was user-provided (not a default/preset).…, Build AI marker ban-list for the target language (no fallback to unrelated… (+11 more)

### Community 45 - "auth_headers"
Cohesion: 0.16
Nodes (30): One active support conversation per user (like Intercom)., SupportConversation, ConsentLog, Audit log for user consents and revocations (376-ФЗ, 69-ФЗ compliance)., auth_headers(), Generate JWT auth headers for a test user., admin_user(), asyncio (+22 more)

### Community 46 - "OAuthProvider"
Cohesion: 0.10
Nodes (13): GoogleProvider, OAuthProvider, OAuthUserInfo, Any, VK ID uses a slightly different token exchange flow., Normalised user info returned by any provider., Base class — subclasses implement provider-specific URLs/parsing., Build the full authorization redirect URL. (+5 more)

### Community 47 - "patch"
Cohesion: 0.09
Nodes (17): patch, If ALL niches from AI are invalid, result should have empty niches list., AI returns more than 3 valid niches -- only first 3 should survive., Happy path: AI returns valid JSON essence., If AI call returns None, return a minimal fallback dict., If AI returns invalid JSON, return fallback., Reel with empty fields should not crash., Transcript longer than 1500 chars should be truncated in the prompt. (+9 more)

### Community 48 - "asyncio"
Cohesion: 0.09
Nodes (17): asyncio, fixture, Test GET /api/proration-preview., Create user with active START subscription., Downgrade preview should show is_upgrade=False, proration=0., Free user with no subscription gets full price preview., Test POST /api/change-tier., Downgrade should schedule tier change, not apply immediately. (+9 more)

### Community 49 - "useAuth"
Cohesion: 0.12
Nodes (25): checkTelegramCode(), createTelegramCode(), createTelegramConnectCode(), getMe(), logout(), AdminGuard, AdminGuard(), LinkedAccountsSection() (+17 more)

### Community 50 - "_apify_client.py"
Cohesion: 0.11
Nodes (28): AsyncClient, track_apify(), ApifyBudgetExhausted, Apify daily run limit or balance threshold exceeded., check_apify_balance(), _check_budget_gate(), _get_budget_redis(), _get_token() (+20 more)

### Community 51 - "calculate_proration"
Cohesion: 0.12
Nodes (17): calculate_proration(), datetime, Calculate proration for a tier change. Pure function, no DB access. Returns…, datetime, Tests for subscription proration — calculate_proration and change-tier…, PRO→START is a downgrade., When user paid with promo, credit should use paid_amount_kopecks, not full…, Annual subscription proration works correctly. (+9 more)

### Community 52 - "email_sender.py"
Cohesion: 0.11
Nodes (27): _billing_email_html(), _get_strings(), _is_seed_recipient(), _pin_digits_html(), Block emails to seed/demo addresses to prevent bounces and noise., Render 6-digit PIN as individual styled digit boxes for email., Send a magic-link email via Unisender Go. Falls back to logging in dev., Send an email via Unisender Go. Returns True on success. (+19 more)

### Community 53 - "SupportMessage"
Cohesion: 0.13
Nodes (27): User rating for a completed analysis (1-5 stars + optional comment)., Individual message in a support conversation., ScriptRating, SupportMessage, admin_user(), asyncio, fixture, Tests for feedback models: ScriptRating, SupportConversation, SupportMessage. (+19 more)

### Community 54 - "demo_data.py"
Cohesion: 0.15
Nodes (26): _all_payments(), cost_revenue(), _det_uuid(), funnel(), mask_email(), payments_page(), datetime, Demo-data overlay for the admin analytics dashboards. When demo mode is ON, the… (+18 more)

### Community 55 - "compilerOptions"
Cohesion: 0.07
Nodes (26): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection, moduleResolution (+18 more)

### Community 56 - "DeepAnalyzeResult"
Cohesion: 0.11
Nodes (14): anyio, DeepAnalyzeResult, All reels return None from _process_single_reel; analysis should still proceed…, If first synthesis attempt returns None, second attempt should still succeed., DeepAnalyzeResult has no max_length — should accept any string length., DeepAnalyzeResult should accept many interests (no limit at schema level)., model_dump + reconstruct should produce the same object., Custom tone and video_format strings (custom:...) should be accepted. (+6 more)

### Community 57 - "AdminJobs.tsx"
Cohesion: 0.10
Nodes (20): adminCancelJob(), adminDeleteJob(), adminGetJobStats(), adminListJobs(), adminRetryJob(), AdminJobs(), handleCancel(), handleDelete() (+12 more)

### Community 58 - "_build_synthesis_prompt"
Cohesion: 0.12
Nodes (13): niche_slugs_csv(), Comma-separated list of all niche slugs for inline use in prompts., _build_synthesis_prompt(), Build compact synthesis prompt from pre-extracted essences., REGRESSION: Curly braces in user content caused str.format() KeyError crash., Curly braces in the biography field should not crash., Curly braces in fullName should not crash., Curly braces in posts analysis fields should not crash. (+5 more)

### Community 59 - "test_support_notifier.py"
Cohesion: 0.13
Nodes (24): notify_user_support_reply(), Send email notification to user., Check if the support message is still unread and notify the user., _send_email(), admin_message(), conversation(), asyncio, fixture (+16 more)

### Community 60 - "AdminUserDetail.tsx"
Cohesion: 0.11
Nodes (17): adminGetUser(), AdminUserDetail(), loadMoreJobs(), DURATION_OPTIONS, formatDate(), formatMoney(), PAID_TIERS, ScriptCard() (+9 more)

### Community 61 - "_parse_json_response"
Cohesion: 0.13
Nodes (10): _parse_json_response(), Extract JSON from Claude response, handling markdown code blocks and…, Claude often prepends explanatory text before the JSON code block., Claude may add text both before and after the code block., Fallback: extract outermost { ... } when no code block is present., JSON with nested objects should be extracted correctly., Deeply nested JSON objects should parse correctly., Code block with just ``` (no 'json' tag) should still be parsed. (+2 more)

### Community 62 - "get_frames_dir"
Cohesion: 0.15
Nodes (22): extract_frames(), extract_frames_pipelined(), _extract_single(), Path, Extract frames at specific timestamps (sequential, legacy)., Extract all frames in parallel (up to max_concurrent ffmpeg processes). Calls…, Run ffmpeg with timeout. Returns True if output file is valid. Acquires a…, Extract one frame with 2-strategy fallback. Strategy 1: Fast seek (-ss before… (+14 more)

### Community 63 - "AdminTrends.tsx"
Cohesion: 0.12
Nodes (21): adminDeleteTrackedProfile(), adminListTrackedProfiles(), adminToggleTrackedProfile(), adminUnblockProfile(), ACTIVE_OPTIONS, AdminTrends(), handleBlock(), handleDelete() (+13 more)

### Community 64 - "compilerOptions"
Cohesion: 0.09
Nodes (22): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, moduleResolution, noEmit (+14 more)

### Community 65 - "metrics.py"
Cohesion: 0.14
Nodes (21): hourly_stats_loop(), Send hourly mini-summary to admin Telegram IDs., calculate_period_metrics(), _format_auth_breakdown(), _format_duration(), _format_period_report(), _format_platform_breakdown(), _format_source_breakdown() (+13 more)

### Community 66 - "LocalStorage"
Cohesion: 0.17
Nodes (8): get_audio_dir(), get_storage_dir(), get_videos_dir(), LocalStorage, Path, Local disk storage backend + legacy helper functions., Get the local filesystem path for a key. LocalStorage only., Copy file from local storage to another local path.

### Community 67 - "AdminNiches.tsx"
Cohesion: 0.13
Nodes (18): adminActivateNiche(), adminCreateNiche(), adminDeactivateNiche(), adminListNiches(), adminUpdateNiche(), AdminNiches(), handleActivate(), handleDeactivate() (+10 more)

### Community 68 - "main.py"
Cohesion: 0.13
Nodes (20): close_pool(), Close the shared pool on shutdown., _get_index_html(), health(), _inject_og_tags(), get, _rate_limit_handler(), Run database migrations and backfills. Called during startup. Uses… (+12 more)

### Community 69 - "make_user"
Cohesion: 0.27
Nodes (20): A second-language version of a UserScript, generated as a separate iteration.…, ScriptTranslation, make_user(), Factory fixture for creating test users., _make_reel_with_script(), _mock_translate(), asyncio, Phase 3 — bilingual scripts: API endpoints + library response. Covers: - POST… (+12 more)

### Community 70 - "S3Storage"
Cohesion: 0.16
Nodes (6): Path, Stream file from S3 to local disk without loading into memory., Generate a pre-signed PUT URL for direct browser upload., Retry S3 operation with exponential backoff on transient errors., Read only the first N bytes of a file (range request)., S3Storage

### Community 71 - "UserScript"
Cohesion: 0.19
Nodes (19): add_to_queue(), check_in_queue(), list_queue(), mark_done(), AsyncSession, delete, get, post (+11 more)

### Community 72 - "get_redis"
Cohesion: 0.16
Nodes (18): _ensure_pool(), get_redis(), Shared Redis connection pool for all backend services. Instead of each module…, Get a Redis client from the shared pool. Returns None if unavailable., Persist the runtime demo-mode toggle in Redis., set_demo_mode(), check_scheduled_drips(), drip_first_analysis() (+10 more)

### Community 73 - "test_translator.py"
Cohesion: 0.25
Nodes (18): _fake_response(), _patches(), _payload(), asyncio, Phase 2 — bilingual scripts: the translation service (separate LLM iteration).…, First call returns non-JSON, second returns valid JSON → success., Build the common mock stack for translate_script., A leading VIDEO REFERENCE line (URL) must survive verbatim, untranslated. (+10 more)

### Community 74 - "detect_platform"
Cohesion: 0.17
Nodes (10): detect_platform(), normalize_url(), Platform, Enum, Strip tracking params and normalize URL for caching and dedup., Detect platform from URL hostname., Tests for TikTok platform detection and URL normalization (Phase 2)., Error message for unsupported platforms should list TikTok as supported. (+2 more)

### Community 75 - "dependencies"
Cohesion: 0.11
Nodes (19): axios, @dnd-kit/core, @dnd-kit/sortable, @dnd-kit/utilities, dependencies, axios, @dnd-kit/core, @dnd-kit/sortable (+11 more)

### Community 76 - "UserSettingsUpdate"
Cohesion: 0.17
Nodes (9): AnalyzeInstagramRequest, DeepAnalyzeRequest, BaseModel, BaseModel, field_validator, UserSettingsResponse, UserSettingsUpdate, Tests for input validation on schemas. (+1 more)

### Community 77 - "devDependencies"
Cohesion: 0.11
Nodes (19): eslint, eslint-plugin-react-hooks, eslint-plugin-react-refresh, devDependencies, eslint, eslint-plugin-react-hooks, eslint-plugin-react-refresh, globals (+11 more)

### Community 78 - "_process_single_reel"
Cohesion: 0.17
Nodes (12): _process_single_reel(), Semaphore, Process a single reel: download → audio → transcribe → frames → vision., _make_reel_post(), Unit tests for the download->transcribe->frames->vision pipeline. Note:…, Happy path: all stages succeed., When audio extraction returns None, transcript should be empty., Reel with no videoUrl (and scraping fails) should return caption-only result. (+4 more)

### Community 79 - "AdminTiers.tsx"
Cohesion: 0.18
Nodes (16): adminListTiers(), adminUpdateTierConfig(), AdminTiers(), getEdit(), handleSave(), isChanged(), loadTiers(), setEdit() (+8 more)

### Community 80 - "ProgressTracker"
Cohesion: 0.18
Nodes (9): ProgressTracker, WebSocket, Remove WebSocket from local connections. Clean up subscription if no clients…, Publish progress to Redis Pub/Sub (or fallback to local broadcast)., Subscribe to Redis Pub/Sub channel and forward messages to local WebSockets., Send data to locally connected WebSocket clients only., Get Redis from shared pool. Returns None if unavailable., Accept WebSocket and start subscribing to Redis channel for this job. (+1 more)

### Community 81 - "morning_brief.py"
Cohesion: 0.18
Nodes (16): _fmt_views(), format_morning_brief(), _format_reel_line(), get_tracked_authors_updates(), get_trending_by_niches(), AsyncSession, Morning Brief — personalized daily briefing in Telegram. Sent at 09:00 UTC to…, Build morning brief text. Returns None if nothing to show. (+8 more)

### Community 82 - "test_rating_api.py"
Cohesion: 0.20
Nodes (16): asyncio, Tests for rating API endpoints: POST /jobs/{id}/rate, GET /jobs/{id}/rating,…, Second rate should update, not create duplicate., test_get_job_includes_my_rating(), test_get_job_no_rating_returns_null(), test_get_rating_exists(), test_get_rating_not_found(), test_rate_job_5_stars_no_comment() (+8 more)

### Community 83 - "Piratex.ai — Playbook масштабирования"
Cohesion: 0.12
Nodes (16): Piratex.ai — Playbook масштабирования, Быстрая справка: команды, Важно помнить, Сигналы что пора:, Сигналы что пора:, Сигналы что пора:, Текущая конфигурация (22 марта 2026), Уровень 1: до 500 пользователей (ТЕКУЩИЙ) (+8 more)

### Community 84 - "AdminUsers.tsx"
Cohesion: 0.15
Nodes (15): adminDeleteUser(), adminListUsers(), adminUpdateUserTier(), handleDelete(), handleTierSave(), AdminUsers(), doTierUpdate(), handleDelete() (+7 more)

### Community 85 - "get_interests"
Cohesion: 0.17
Nodes (16): get_default_prompts(), get_interests(), get_profile_presets(), get_radar_settings(), get_settings(), _profile_from_db(), AsyncSession, get (+8 more)

### Community 86 - "TestProfileMergeLogic"
Cohesion: 0.12
Nodes (9): Test the profile merge logic from settings.py update_settings endpoint.…, Updating only `tone` should preserve about_me, niches, etc., Updating only niches should preserve all other fields., Sending all fields should overwrite everything., If existing profile is empty, new fields should be added., Updating with an empty profile (all None) should preserve everything., Verify that model_dump(exclude_none=True) only includes set fields., UserSettingsUpdate should accept a partial profile. (+1 more)

### Community 87 - "ffmpeg_slot"
Cohesion: 0.17
Nodes (11): ffmpeg_slot, _get_semaphore(), Semaphore, Global ffmpeg process limiter. Limits the number of concurrent ffmpeg…, Return (or create) the process-wide ffmpeg semaphore. Safe in asyncio: only one…, Async context manager for acquiring an ffmpeg execution slot., extract_audio(), _has_audio_stream() (+3 more)

### Community 88 - "extract_youtube_video_id"
Cohesion: 0.23
Nodes (4): extract_youtube_video_id(), Extract 11-char video ID from any YouTube URL format., YouTube video IDs are exactly 11 characters., TestExtractYoutubeVideoId

### Community 89 - "test_script_translations.py"
Cohesion: 0.16
Nodes (13): _make_translation(), asyncio, ScriptTranslation, Phase 1 — bilingual scripts: data model + schemas. Covers: - ScriptTranslation…, Same (user_script_id, language) must be rejected; different language is fine., test_dual_language_defaults_are_none(), test_script_translation_out_serialization(), test_script_translation_persists() (+5 more)

### Community 90 - "like_reel"
Cohesion: 0.18
Nodes (13): get_liked_urls(), like_reel(), AsyncSession, delete, get, post, Return all URLs liked by the current user., Like a reel by URL. Idempotent. (+5 more)

### Community 91 - "ChatWidget.tsx"
Cohesion: 0.22
Nodes (11): getSupportConversation(), getSupportUnreadCount(), presignSupportUpload(), sendSupportMessage(), SupportMessage, ChatWidget, ChatBubble(), ChatBubbleProps (+3 more)

### Community 92 - "Teleprompter.tsx"
Cohesion: 0.22
Nodes (13): DEFAULT_SETTINGS, findMatch(), FONT_LABELS, FONT_SIZES, loadSettings(), normWord(), Props, RECOG_LANG (+5 more)

### Community 93 - "speech-recognition.d.ts"
Cohesion: 0.14
Nodes (8): SpeechRecognition, SpeechRecognitionAlternative, SpeechRecognitionConstructor, SpeechRecognitionErrorEvent, SpeechRecognitionEvent, SpeechRecognitionResult, SpeechRecognitionResultList, Window

### Community 94 - "get_me"
Cohesion: 0.26
Nodes (13): check_telegram_code(), create_telegram_code(), get_me(), logout(), AsyncSession, get, limit, post (+5 more)

### Community 95 - "compose_strategy_prompt"
Cohesion: 0.19
Nodes (6): compose_strategy_prompt(), UserProfile, Build the full strategy system prompt from profile fields., Ensure prompts still contain required structural elements., TestPromptIntegrity, TestStrategyXmlWrapping

### Community 96 - "AdminPayments.tsx"
Cohesion: 0.19
Nodes (10): adminListPayments(), AdminPayments(), load(), formatAmount(), formatDate(), METHOD_LABELS, PROVIDER_LABELS, STATUS_COLORS (+2 more)

### Community 97 - "get_rating_detail"
Cohesion: 0.29
Nodes (11): get_rating_detail(), list_ratings(), Deep detail for a single rating — for investigating bad ratings., List all script ratings with user and job info., AdminRatingDetail, AdminRatingItem, AdminRatingListResponse, OtherRatingItem (+3 more)

### Community 98 - "oauth_callback"
Cohesion: 0.23
Nodes (12): list_providers(), oauth_callback(), oauth_start(), AsyncSession, get, limit, Request, Handle OAuth callback — exchange code, create/find user, redirect. (+4 more)

### Community 99 - "TierConfig"
Cohesion: 0.18
Nodes (11): patch, put, Update a promo code (toggle active, change limits, etc.)., Toggle is_active for a tracked profile., Update an existing niche., toggle_tracked_profile(), update_niche(), update_promo() (+3 more)

### Community 100 - "refine_field"
Cohesion: 0.20
Nodes (11): AsyncSession, BaseModel, limit, post, Request, Stream refined text from OpenRouter (Claude/GPT), yielding SSE events., Stream a refined version of a content field via SSE., refine_field() (+3 more)

### Community 101 - "ManagedArqPool"
Cohesion: 0.20
Nodes (6): ManagedArqPool, ArqRedis, Managed arq Redis pool with auto-reconnect. The web process needs an arq pool…, arq pool wrapper with health check and auto-reconnect., Create initial connection., Get a healthy pool, reconnecting if necessary.

### Community 102 - "transcribe"
Cohesion: 0.25
Nodes (10): track_whisper(), TranscriptionError, get_whisper_client(), AsyncOpenAI, Get or create an AsyncOpenAI client for Whisper transcription. Uses a separate…, TranscriptWord, Path, TranscriptSegment (+2 more)

### Community 103 - "ShowcaseTracker"
Cohesion: 0.27
Nodes (4): WebSocket, Showcase event tracker — Redis Pub/Sub bridge for live dashboard. Backend…, Get Redis from shared pool. Returns None if unavailable., ShowcaseTracker

### Community 104 - "AdminRatings.tsx"
Cohesion: 0.24
Nodes (8): adminGetRatingDetail(), adminListRatings(), AdminRatings(), fmt(), RatingDetailPanel(), MaskedPII(), AdminRatingDetail, AdminRatingItem

### Community 105 - "build_system_blocks"
Cohesion: 0.33
Nodes (3): build_system_blocks(), Build the 3-block system prompt array for the Claude API. Block 1: Immutable…, TestBuildSystemBlocks

### Community 106 - "refine_usage.py"
Cohesion: 0.27
Nodes (9): check_refine_allowed(), get_refine_usage(), increment_refine_usage(), _key(), AsyncSession, Redis-based daily refine usage counter. Key pattern: refine:{user_id}:{YYYY-MM-…, Return number of refines used today., Increment and return the new count. (+1 more)

### Community 107 - "package.json"
Cohesion: 0.20
Nodes (9): name, private, scripts, build, dev, lint, preview, type (+1 more)

### Community 108 - "trend_watching_activity"
Cohesion: 0.47
Nodes (9): _get_redis_from_request(), AsyncSession, get, Request, Get Redis connection from app state (web process)., trend_watching_activity(), trend_watching_pipeline(), trend_watching_sparklines() (+1 more)

### Community 109 - "detect_same_language"
Cohesion: 0.31
Nodes (8): detect_same_language(), _is_cyrillic(), _is_latin(), Lightweight language detection based on Unicode character ranges. No external…, Return the fraction of alphabetic characters matching the given script., Check if text is predominantly Latin script (en, fr, de, pt, es, etc.)., Detect if the transcript is likely in the same language as target_language.…, _script_ratio()

### Community 110 - ".parse_webhook"
Cohesion: 0.25
Nodes (5): _detect_payment_method(), Verify CloudPayments webhook HMAC-SHA256 signature., Parse webhook body — supports both form-urlencoded and JSON., Parse CloudPayments Recurrent webhook (subscription status change). Returns a…, Detect payment method from CloudPayments webhook data.

### Community 111 - "_is_youtube_short"
Cohesion: 0.28
Nodes (6): _is_youtube_short(), Check if a YouTube video is a Short via HEAD request. HEAD…, On network error, fail-open (let duration check handle it)., HEAD /shorts/{id} returns 200 → is a Short., HEAD /shorts/{id} returns 303 → NOT a Short., TestIsYoutubeShort

### Community 112 - "_parse_duration_str"
Cohesion: 0.36
Nodes (3): _parse_duration_str(), Parse duration: float/int seconds, or string like '3:33' / '0:36'., TestParseDuration

### Community 113 - "yookassa_client.py"
Cohesion: 0.31
Nodes (8): cancel_payment(), create_payment(), _ensure_configured(), get_payment(), YooKassa payment provider integration. Wraps the synchronous yookassa SDK with…, Create a YooKassa payment and return the full response dict. For first payment:…, Fetch payment details from YooKassa., Cancel a pending payment.

### Community 114 - "calculate_daily_metrics"
Cohesion: 0.25
Nodes (8): Send metrics digest to admin Telegram IDs now., send_digest_now(), calculate_daily_metrics(), format_metrics_digest(), Format metrics as a Telegram-friendly text message., Calculate key business metrics for the last 24 hours., Calculate metrics and send daily digest to admin Telegram IDs., send_daily_digest()

### Community 115 - "get_shared_job"
Cohesion: 0.29
Nodes (8): get_shared_frame(), get_shared_job(), AsyncSession, get, limit, Request, View a shared job result by token. No authentication required., Get a frame image from a shared job. No authentication required.

### Community 116 - "If the user is developing"
Cohesion: 0.25
Nodes (7): Commands, Conventions, If the user is deploying (default assumption for a fresh clone), If the user is developing, Layout, Piratex.ai — guide for Claude Code, Stack

### Community 117 - "Deploy with Claude Code (for non-programmers)"
Cohesion: 0.25
Nodes (7): A few safety rules, Deploy with Claude Code (for non-programmers), Step 1 — Install Claude Code, Step 2 — Get this project onto your computer, Step 3 — Open the project and paste this prompt, What happens next, What you'll need

### Community 118 - "MaskedPII.tsx"
Cohesion: 0.25
Nodes (3): MaskedPIIProps, maskers, MaskType

### Community 119 - "check_env.py"
Cohesion: 0.39
Nodes (6): _feature(), is_set(), load_env(), main(), Print one optional-feature line. Default: enabled if the first key is set., Parse a .env file (KEY=VALUE), then overlay the real environment.

### Community 120 - "cost_tracker.py"
Cohesion: 0.33
Nodes (5): CostTracker, get_cost_tracker(), Lightweight per-job cost accumulator using contextvars. Usage in worker tasks:…, Accumulates API costs during a single job's processing pipeline., Get the current tracker (if any).

### Community 121 - "cloudpayments.d.ts"
Cohesion: 0.33
Nodes (4): CloudPayments, CloudPaymentsWidget, CloudPaymentsWidgetOptions, cp

### Community 122 - "010_fix_pipeline_fk_and_index.py"
Cohesion: 0.60
Nodes (5): downgrade(), _find_fk_constraint(), _index_exists(), Find the actual FK constraint name on a given column., upgrade()

### Community 123 - "delete_my_account"
Cohesion: 0.33
Nodes (6): delete_my_account(), delete, limit, Request, Response, Permanently delete the current user's account and all associated data. GDPR…

### Community 124 - "send_founder_welcome"
Cohesion: 0.40
Nodes (6): _get_founder_user_id(), AsyncSession, Find founder's user ID from admin_emails config., Create a support conversation with a welcome message from the founder. Returns…, send_founder_welcome(), SupportConversation

### Community 126 - "TestAnalyzeBlogNoneValuesFromClaude"
Cohesion: 0.33
Nodes (4): Test that analyze_blog handles None/missing values in Claude's JSON response., AI returns JSON with None/missing fields -- defaults should be applied., AI response with completely missing keys should still produce valid result., TestAnalyzeBlogNoneValuesFromClaude

### Community 127 - "Piratex.ai — Pricing & Limits"
Cohesion: 0.33
Nodes (5): Piratex.ai — Pricing & Limits, Источник правды, Платёжные провайдеры, Реферальная программа, Тарифы

### Community 128 - "009_add_production_pipeline.py"
Cohesion: 0.60
Nodes (3): _column_exists(), _table_exists(), upgrade()

### Community 129 - "013_add_multiauth_tables.py"
Cohesion: 0.60
Nodes (3): _column_exists(), _table_exists(), upgrade()

### Community 130 - "garbage_collect_orphaned_files"
Cohesion: 0.40
Nodes (5): gc_storage(), Find and delete orphaned storage files whose jobs no longer exist., garbage_collect_orphaned_files(), AsyncSession, Find and delete storage files whose jobs/reels no longer exist in DB. Returns…

### Community 131 - "SecurityHeadersMiddleware"
Cohesion: 0.40
Nodes (4): Request, Response, SecurityHeadersMiddleware, BaseHTTPMiddleware

### Community 132 - "async_engine"
Cohesion: 0.40
Nodes (5): async_engine(), db_session(), fixture, Create a fresh test database for each test., Async DB session with automatic rollback after each test.

### Community 133 - "011_add_payment_provider_to_payments.py"
Cohesion: 0.83
Nodes (3): _column_exists(), downgrade(), upgrade()

### Community 134 - "WorkerSettings"
Cohesion: 0.50
Nodes (3): Configuration for arq worker process., WorkerSettings, Entry point for the arq worker process. Usage: python run_worker.py

### Community 146 - "_aggregate_costs"
Cohesion: 0.67
Nodes (3): _aggregate_costs(), Aggregate cost_breakdown JSON from multiple jobs into a CostPeriod., CostPeriod

## Knowledge Gaps
- **293 isolated node(s):** `NicheDefinition`, `start.sh script`, `name`, `private`, `version` (+288 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User` to `Job`, `garbage_collect_orphaned_files`, `config.py`, `trend_monitor.py`, `Base`, `Subscription`, `api/pipeline.py`, `api/trends.py`, `api/admin.py`, `ws.py`, `api/telegram.py`, `tasks.py`, `services/billing.py`, `ProfileReel`, `api/library.py`, `magic_link.py`, `post`, `AsyncSession`, `api/billing.py`, `api/support.py`, `test_blog_analyzer.py`, `auth_headers`, `SupportMessage`, `test_support_notifier.py`, `metrics.py`, `make_user`, `UserScript`, `get_redis`, `morning_brief.py`, `test_rating_api.py`, `get_interests`, `like_reel`, `get_me`, `get_rating_detail`, `oauth_callback`, `TierConfig`, `refine_field`, `trend_watching_activity`, `calculate_daily_metrics`, `get_shared_job`, `delete_my_account`, `send_founder_welcome`?**
  _High betweenness centrality (0.166) - this node is a cross-community bridge._
- **Why does `UserProfile` connect `UserProfile` to `trend_monitor.py`, `config.py`, `test_blog_analyzer.py`, `api/trends.py`, `UserSettingsUpdate`, `compose_content_prompt`, `morning_brief.py`, `get_interests`, `ProfileReel`, `TestProfileMergeLogic`, `test_script_translations.py`, `summarizer.py`, `strategist.py`, `compose_strategy_prompt`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Why does `get_redis()` connect `get_redis` to `post`, `trend_monitor.py`, `config.py`, `Job`, `ShowcaseTracker`, `api/support.py`, `refine_usage.py`, `User`, `api/admin.py`, `ProgressTracker`, `ws.py`, `morning_brief.py`, `tasks.py`, `_apify_client.py`, `demo_data.py`, `api/library.py`, `test_support_notifier.py`, `summarizer.py`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Are the 241 inferred relationships involving `User` (e.g. with `activate_niche()` and `admin_send_message()`) actually correct?**
  _`User` has 241 INFERRED edges - model-reasoned connections that need verification._
- **Are the 73 inferred relationships involving `Job` (e.g. with `cancel_job()` and `cleanup_ghost_users()`) actually correct?**
  _`Job` has 73 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `UserProfile` (e.g. with `analyze_instagram()` and `deep_analyze_instagram()`) actually correct?**
  _`UserProfile` has 26 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `JobStatus` (e.g. with `cancel_job()` and `get_analytics()`) actually correct?**
  _`JobStatus` has 51 INFERRED edges - model-reasoned connections that need verification._