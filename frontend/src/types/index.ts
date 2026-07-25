export type SceneType =
  | "talking_head"
  | "screencast"
  | "animation"
  | "text_card"
  | "split_screen"
  | "b_roll";

export type JobStatus =
  | "pending"
  | "downloading"
  | "extracting_audio"
  | "transcribing"
  | "detecting_scenes"
  | "extracting_frames"
  | "analyzing_frames"
  | "generating_summary"
  | "completed"
  | "failed";

export interface TranscriptWord {
  word: string;
  start: number;
  end: number;
}

export interface TranscriptSegment {
  text: string;
  start: number;
  end: number;
  words: TranscriptWord[];
}

export interface FrameAnalysis {
  frame_index: number;
  timestamp: number;
  timecode: string;
  frame_path: string;
  screen_text: string[];
  visual_description: string;
  scene_type: SceneType;
  ui_elements: string[];
  transcript_segment: string | null;
}

export interface CommentsStrategy {
  [key: string]: never;
}

export interface Hashtags {
  primary: string[];
  secondary: string[];
}

export interface HookVariant {
  text: string;
  score: number;
  why: string;
}

export interface StrategyData {
  virality_breakdown: string;
  hook_variants: (HookVariant | string)[];
  primary_hook_score?: number;
  primary_hook_why?: string;
  comments_strategy: CommentsStrategy;
  hashtags: Hashtags;
}

export interface AdaptationSummary {
  script: string;
  description: string;
  editor_instructions: string;
  // Strategy fields (optional — merged from backend, absent in older jobs)
  virality_breakdown?: string;
  hook_variants?: (HookVariant | string)[];
  primary_hook_score?: number;
  primary_hook_why?: string;
  comments_strategy?: CommentsStrategy;
  hashtags?: Hashtags;
}

export interface JobResult {
  job_id: string;
  url: string;
  status: JobStatus;
  progress: number;
  video_title: string | null;
  video_duration: number | null;
  video_platform: string | null;
  video_author: string | null;
  video_description: string | null;
  video_views: number | null;
  video_likes: number | null;
  video_comments: number | null;
  transcript: TranscriptSegment[] | null;
  frames: FrameAnalysis[] | null;
  adaptation_summary: AdaptationSummary | null;
  share_token: string | null;
  library_reel_id: string | null;
  user_script_id: string | null;
  production_status: string | null;

  // Teaser mode for anonymous users (truncated results)
  is_teaser?: boolean;
  teaser_limits?: {
    frames_shown: number;
    frames_total: number;
    transcript_pct: number;
    script_pct: number;
  } | null;

  // User's own rating for this job (null if not rated)
  my_rating?: number | null;

  created_at: string;
  completed_at: string | null;
  error: string | null;
}

export interface SharedJobResult {
  video_title: string | null;
  video_duration: number | null;
  video_platform: string | null;
  video_author: string | null;
  video_url: string | null;
  script: string;
  description: string;
  editor_instructions: string;
  frames: FrameAnalysis[] | null;
  created_at: string;
  library_reel_id: string | null;
}

export interface ProgressUpdate {
  status: JobStatus;
  progress: number;
  message: string;
  error?: boolean;
}

// Auth types
export interface AuthUser {
  id: string;
  email: string | null;
  name: string | null;
  is_anonymous: boolean;
  tier: string;
  telegram_user_id: string | null;
  telegram_subscribed: boolean;
  auth_providers: string[];
  is_admin: boolean;
  subscription_status?: string | null;
}

// Admin types
export interface AdminUser {
  id: string;
  email: string | null;
  name: string | null;
  is_anonymous: boolean;
  tier: string;
  telegram_username: string | null;
  telegram_subscribed: boolean;
  created_at: string | null;
  jobs_count: number;
}

export interface AdminJob {
  id: string;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  user_tier: string | null;
  url: string;
  status: string;
  progress: number;
  progress_message: string | null;
  error: string | null;
  video_title: string | null;
  video_platform: string | null;
  share_token: string | null;
  source: string | null;
  retry_count: number;
  duration_seconds: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface AdminJobStats {
  queued: number;
  running: number;
  completed_today: number;
  failed_today: number;
  completed_total: number;
  failed_total: number;
  avg_duration_seconds: number | null;
  error_rate_pct: number;
  completed_week: number;
}

export interface AdminLibraryItem {
  id: string;
  url: string;
  video_title: string | null;
  video_platform: string | null;
  video_author: string | null;
  submitted_by_email: string | null;
  created_at: string;
}

export interface AdminStats {
  total_users: number;
  anonymous_users: number;
  registered_users: number;
  free_users: number;
  start_users: number;
  pro_users: number;
  unlimited_users: number;
  total_jobs: number;
  jobs_today: number;
  jobs_running: number;
  jobs_completed: number;
  jobs_failed: number;
  jobs_failed_today: number;
  library_reels: number;
}

export interface AdminUserSettings {
  language: string;
  onboarding_completed: boolean;
  has_custom_content_prompt: boolean;
  has_custom_strategy_prompt: boolean;
  has_api_keys: boolean;
  about_me: string | null;
  tone: string | null;
  niches: string[];
  interests: string[];
  forbidden_words: string | null;
  script_cta: string | null;
  description_cta: string | null;
  video_format: string | null;
  radar_enabled: boolean | null;
  radar_mode: string | null;
}

export interface AdminUserScript {
  id: string;
  script: string;
  description: string;
  editor_instructions: string;
  original_script: string | null;
  original_description: string | null;
  original_editor_instructions: string | null;
  active_hook_index: number;
  reel_url: string | null;
  reel_title: string | null;
  reel_platform: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AdminUserSubscription {
  id: string;
  tier: string;
  status: string;
  payment_provider: string | null;
  billing_interval: string | null;
  amount_kopecks: number;
  currency: string;
  current_period_start: string | null;
  current_period_end: string | null;
  scheduled_tier: string | null;
  scheduled_interval: string | null;
  created_at: string | null;
}

export interface AdminUserPayment {
  id: string;
  amount_kopecks: number;
  currency: string;
  status: string;
  payment_provider: string | null;
  payment_method: string | null;
  paid_at: string | null;
  created_at: string;
}

export interface AdminUserDetail extends AdminUser {
  auth_provider: string | null;
  recent_jobs: AdminJob[];
  jobs_total: number;
  settings: AdminUserSettings | null;
  scripts: AdminUserScript[];
  scripts_total: number;
  subscription: AdminUserSubscription | null;
  payments: AdminUserPayment[];
  payments_total: number;
}

export interface AdminTierConfig {
  name: string;
  max_monthly: number | null;
  max_total: number | null;
  max_refines_daily: number | null;
  updated_at: string | null;
}

export interface AdminConversation {
  telegram_user_id: string;
  telegram_username: string | null;
  telegram_name: string | null;
  user_id: string | null;
  message_count: number;
  last_message_text: string | null;
  last_message_at: string | null;
}

export interface AdminMessage {
  id: string;
  telegram_user_id: string;
  direction: "in" | "out";
  text: string;
  created_at: string;
}

// Analytics types
export interface JobDayStats {
  date: string;
  total: number;
  completed: number;
  failed: number;
}

export interface UserDayStats {
  date: string;
  new_users: number;
}

export interface PlatformHealth {
  platform: string;
  total_jobs: number;
  completed: number;
  failed: number;
  success_rate: number;
}

export interface RecentError {
  url: string;
  platform: string | null;
  error: string | null;
  share_token: string | null;
  created_at: string;
}

export interface AdminAnalytics {
  jobs_per_day: JobDayStats[];
  users_per_day: UserDayStats[];
  platform_health: PlatformHealth[];
  recent_errors: RecentError[];
}

export interface CostPeriod {
  apify_usd: number;
  whisper_usd: number;
  vision_usd: number;
  sonnet_usd: number;
  haiku_usd: number;
  total_usd: number;
  jobs_count: number;
}

export interface CostDayStats {
  date: string;
  total_usd: number;
  jobs_count: number;
}

export interface CostAnalytics {
  today: CostPeriod;
  yesterday: CostPeriod;
  month: CostPeriod;
  all_time: CostPeriod;
  avg_per_reel_usd: number;
  apify_budget: { max_monthly_usd: number; used_monthly_usd: number; remaining_usd: number } | null;
  revenue_today_rub: number;
  revenue_yesterday_rub: number;
  revenue_month_rub: number;
  revenue_today_eur: number;
  revenue_month_eur: number;
  mrr_rub: number;
  mrr_eur: number;
  daily_costs: CostDayStats[];
  paid_users: number;
  cost_per_paid_user_usd: number;
}

export interface AdminTrackedProfile {
  id: string;
  platform: string;
  username: string;
  display_name: string | null;
  followers_count: number | null;
  median_views: number | null;
  total_reels: number;
  niche: string | null;
  is_active: boolean;
  is_blocked: boolean;
  blocked_at: string | null;
  blocked_reason: string | null;
  check_priority: string;
  last_checked_at: string | null;
  created_at: string;
  tracking_users_count: number;
  trending_reels_count: number;
}

export interface AdminHiddenReel {
  id: string;
  url: string;
  caption: string | null;
  thumbnail_url: string | null;
  views: number | null;
  profile_username: string;
  profile_platform: string;
  hidden_at: string | null;
  hidden_reason: string | null;
}

export interface AdminTrendingReel {
  id: string;
  url: string;
  caption: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  trending_since: string | null;
  duration: number | null;
  views: number | null;
  likes: number | null;
  comments: number | null;
  x_factor: number | null;
  velocity: number | null;
  hot_score: number | null;
  niche: string | null;
  author_id: string;
  author_username: string;
  author_platform: string;
  author_display_name: string | null;
  author_followers: number | null;
}

export interface AdminTrendingNicheStat {
  niche: string;
  count: number;
}

export interface AdminTrendingSummary {
  total_trending: number;
  avg_hot_score: number | null;
  top_niches: AdminTrendingNicheStat[];
}

export interface AdminTrendingReelsResponse {
  items: AdminTrendingReel[];
  total: number;
  page: number;
  per_page: number;
  summary: AdminTrendingSummary;
}

export interface AdminPayment {
  id: string;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  subscription_id: string | null;
  provider_payment_id: string | null;
  payment_provider: string | null;
  amount_kopecks: number;
  currency: string;
  status: string;
  payment_method: string | null;
  description: string | null;
  receipt_url: string | null;
  paid_at: string | null;
  created_at: string;
}

export interface AdminPaymentListResponse {
  items: AdminPayment[];
  total: number;
  page: number;
  per_page: number;
  total_all: number;
  total_succeeded: number;
  total_rub_kopecks: number;
  total_eur_cents: number;
}

export interface AdminListResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

export interface AdminTrackedProfileStats {
  total: number;
  today: number;
  yesterday: number;
  week: number;
  month: number;
}

export interface AdminTrackedProfileListResponse {
  items: AdminTrackedProfile[];
  total: number;
  page: number;
  per_page: number;
  stats: AdminTrackedProfileStats | null;
}

export interface MeResponse {
  user: AuthUser;
  usage: UsageInfo;
  token?: string;
}

export interface UsageInfo {
  used: number;
  limit: number;
}

export interface UserProfile {
  about_me?: string | null;
  tone?: string | null;
  script_cta?: string | null;
  description_cta?: string | null;
  forbidden_words?: string | null;
  video_format?: string | null;
  niches?: string[] | null;
  interests?: string[] | null;
  content_prompt_additions?: string | null;

  // Content Radar notification preferences
  radar_enabled?: boolean | null;
  radar_mode?: "instant" | "digest" | "both" | null;
  radar_min_x_factor?: number | null;
  radar_niches?: string[] | null;
  radar_quiet_hours?: boolean | null;

  // Bilingual scripts: auto-generate a second-language version after the primary one
  dual_language_enabled?: boolean | null;
  second_language?: string | null; // 'en' | 'fr' | 'de' | 'pt'
}

export interface RadarSettings {
  radar_enabled: boolean;
  radar_mode: string;
  radar_min_x_factor: number;
  radar_niches: string[] | null;
  radar_quiet_hours: boolean;
  has_telegram: boolean;
}

export interface PresetInfo {
  text: string;
  labels: Record<string, string>;
}

export interface ProfilePresets {
  tone_presets: Record<string, PresetInfo>;
  video_format_presets: Record<string, PresetInfo>;
  defaults: {
    about_me: string;
    script_cta: string;
    description_cta: string;
    forbidden_words: string;
  };
}

export interface UserSettingsData {
  language: string;
  custom_content_prompt: string | null;
  custom_strategy_prompt: string | null;
  profile: UserProfile | null;
  onboarding_completed: boolean;
}

export interface DeepAnalyzeResult {
  analysis_id: string;
  about_me: string;
  tone: string;
  niches: string[];
  interests: string[];
  video_format: string;
  script_cta: string;
  description_cta: string;
  forbidden_words: string;
  content_prompt_additions: string | null;
}

export interface BlogAnalysisProgress {
  type: "progress";
  status: "scraping" | "downloading" | "transcribing" | "analyzing_frames" | "generating_profile" | "done";
  progress: number;
  message: string;
}

export const DEEP_ANALYSIS_KEY = "deep_analysis_state";
export interface DeepAnalysisCache {
  status: "analyzing" | "done" | "error";
  username: string;
  analysisId: string;
  startedAt: number;
  error?: string;
}

export interface DefaultPrompts {
  content_prompt: string;
  strategy_prompt: string;
}

// Library types
export interface TagInfo {
  id: number;
  name: string;
  display_name: string;
  category: string;
  reel_count: number;
}

export interface UserScript {
  id: string;
  script: string;
  description: string;
  editor_instructions: string;
  active_hook_index: number;
  created_at: string;
  updated_at: string;
}

export interface ScriptTranslation {
  id: string;
  language: string;
  script: string;
  description: string;
  editor_instructions: string;
  stale: boolean;
  created_at: string;
  updated_at: string;
}

export interface LibraryReelCard {
  id: string;
  url: string;
  video_title: string | null;
  video_duration: number | null;
  video_platform: string | null;
  video_author: string | null;
  video_views: number | null;
  video_likes: number | null;
  video_comments: number | null;
  original_language: string | null;
  content_format: string | null;
  tags: string[];
  job_id: string;
  cover_frame_index: number | null;
  has_user_script: boolean;
  created_at: string;
}

export interface LibraryReelDetail {
  id: string;
  url: string;
  video_title: string | null;
  video_duration: number | null;
  video_platform: string | null;
  video_author: string | null;
  video_description: string | null;
  video_views: number | null;
  video_likes: number | null;
  video_comments: number | null;
  original_language: string | null;
  content_format: string | null;
  transcript_text: string | null;
  transcript_json: TranscriptSegment[] | null;
  frames_json: FrameAnalysis[] | null;
  tags: TagInfo[];
  job_id: string;
  cover_frame_index: number | null;
  is_bookmarked: boolean;
  has_user_script: boolean;
  user_script: UserScript | null;
  translations: ScriptTranslation[];
  hook_variants: (HookVariant | string)[] | null;
  primary_hook_score: number | null;
  primary_hook_why: string | null;
  original_primary_hook: string | null;
  hashtags: Hashtags | null;
  share_token: string | null;
  created_at: string;
}

export interface LibraryListResponse {
  items: LibraryReelCard[];
  total: number;
  page: number;
  per_page: number;
}

// Trends types
export interface TrendAuthor {
  profile_id: string;
  username: string;
  display_name: string | null;
  platform: string;
  followers_count: number | null;
  median_views: number | null;
  niche: string | null;
}

export interface TrendItem {
  id: string;
  url: string;
  caption: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  duration: number | null;
  views: number | null;
  likes: number | null;
  comments: number | null;
  x_factor: number | null;
  velocity: number | null;
  hot_score: number | null;
  niche: string | null;
  author: TrendAuthor;
  is_parsed: boolean;
  library_reel_id: string | null;
  trending_since: string | null;
  frame_count: number;
  is_followed: boolean;
}

export interface TrendsListResponse {
  items: TrendItem[];
  total: number;
  page: number;
  per_page: number;
  interest_source?: "manual" | "auto" | "none" | null;
  niche_source?: "manual" | "auto" | "none" | null;
}

export interface NicheStats {
  niche: string;
  trending_count: number;
  total_profiles: number;
}

// ── Niche Tree (public API for 2-step dropdown) ─────────────────

export interface NicheChild {
  slug: string;
  display_name: string;
  display_name_en?: string | null;
  keywords?: string[];
  trending_count: number;
}

export interface NicheGroup {
  key: string;
  label: string;
  label_en: string;
  children: NicheChild[];
  trending_count: number;
}

export interface NicheTreeResponse {
  groups: NicheGroup[];
}

export interface TrackedAuthor {
  id: string;
  platform: string;
  username: string;
  display_name: string | null;
  profile_url: string | null;
  followers_count: number | null;
  median_views: number | null;
  niche: string | null;
  total_reels: number;
  last_checked_at: string | null;
  trending_count: number;
}

export interface MyAuthorsResponse {
  authors: TrackedAuthor[];
  count: number;
  limit: number;
  frozen_count: number;
}

export interface ForYouResponse {
  items: TrendItem[];
  user_niches: string[];
  niche_source: "manual" | "auto" | "none";
  user_interests: string[];
  interest_source: "manual" | "auto" | "none";
}

export interface SuggestedInterest {
  topic: string;
  display_name: string;
  count: number;
}

export interface InterestsData {
  interests: string[];
  suggested: SuggestedInterest[];
}

// My Videos types
export interface JobCard {
  job_id: string;
  url: string;
  status: JobStatus;
  progress: number;
  progress_message: string | null;
  video_title: string | null;
  video_duration: number | null;
  video_platform: string | null;
  video_author: string | null;
  video_views: number | null;
  video_likes: number | null;
  video_comments: number | null;
  thumbnail_url: string | null;
  is_filmed: boolean;
  library_reel_id: string | null;
  share_token: string | null;
  x_factor: number | null;
  user_script_id: string | null;
  production_status: string | null;
  created_at: string;
  completed_at: string | null;
  error: string | null;
}

export interface JobListResponse {
  items: JobCard[];
  total: number;
  page: number;
  per_page: number;
}

// Unified card data (used by UnifiedReelCard)
export interface UnifiedCardData {
  id: string;
  url: string;

  // Display
  title: string | null;
  author: string | null;
  platform: string | null;
  duration: number | null;
  views: number | null;
  likes: number | null;
  comments: number | null;
  publishedAt: string | null;
  createdAt: string;

  // Thumbnail
  thumbnailSrc: string | null;
  thumbnailUrl: string | null;

  // Trends-specific
  xFactor: number | null;
  velocity: number | null;
  niche: string | null;
  isParsed: boolean;
  isNewViral: boolean;
  isTodaysCatch: boolean;
  rank: number | null;
  frameCount: number;
  trendId: string | null;
  caption: string | null;

  // Jobs-specific
  jobId: string | null;
  status: string | null;
  progress: number;
  progressMessage: string | null;
  error: string | null;
  isFilmed: boolean;
  shareToken: string | null;

  // Pipeline-specific
  userScriptId: string | null;
  productionStatus: string | null;

  // Library-specific
  libraryReelId: string | null;
  tags: string[];
  contentFormat: string | null;
  hasUserScript: boolean;
}

// Billing types
export interface PaymentProviderInfo {
  name: string;
  display_name: string;
  icon: string;
}

export interface FeatureItem {
  text: string;
  style: "normal" | "highlight" | "disabled";
}

export interface PricingTier {
  tier: string;
  name: string;
  price_monthly: number;
  price_yearly: number;
  limit_monthly: number | null;
  features: FeatureItem[];
  popular: boolean;
}

export interface PricingResponse {
  tiers: PricingTier[];
  free_limit: number | null;
}

export interface CheckoutResponse {
  payment_url: string;
  payment_id: string;
  provider: string | null;
}

export interface SubscriptionInfo {
  id: string;
  tier: string;
  status: string;
  billing_interval: string;
  amount_kopecks: number;
  currency: string;
  payment_provider?: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  cancelled_at: string | null;
  created_at: string;
  has_payment_method?: boolean;
  auto_renewal_enabled?: boolean;
}

export interface PaymentItem {
  id: string;
  amount_kopecks: number;
  currency: string;
  status: string;
  payment_provider?: string | null;
  payment_method: string | null;
  description: string | null;
  paid_at: string | null;
  created_at: string;
}


// Pipeline types
export type ProductionStatus =
  | "script_ready"
  | "filming"
  | "editing"
  | "review"
  | "rejected"
  | "scheduled"
  | "published";

export interface PipelineItem {
  script_id: string;
  production_status: ProductionStatus | null;
  assignee_id: string | null;
  due_date: string | null;
  scheduled_publish_at: string | null;
  published_at: string | null;
  script: string | null;
  description: string | null;
  editor_instructions: string | null;
  library_reel_id: string | null;
  job_id: string | null;
  url: string | null;
  video_title: string | null;
  video_author: string | null;
}

export interface PipelineDetail {
  item: PipelineItem;
  assets: PipelineAsset[];
  comments: PipelineComment[];
  history: PipelineHistoryEntry[];
}

export interface PipelineAsset {
  id: string;
  stage: string;
  file_key: string;
  file_name: string;
  file_size: number | null;
  file_type: string | null;
  uploaded_by: string | null;
  created_at: string;
}

export interface PipelineComment {
  id: string;
  stage: string;
  author_id: string;
  author_name: string | null;
  text: string;
  created_at: string;
}

export interface PipelineHistoryEntry {
  from_status: string | null;
  to_status: string;
  triggered_by: string;
  triggered_by_name: string | null;
  comment: string | null;
  created_at: string;
}

// Admin Ratings
export interface AdminRatingItem {
  id: string;
  rating: number;
  comment: string | null;
  created_at: string;
  viewed_at: string | null;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  user_telegram: string | null;
  job_id: string;
  job_url: string | null;
  video_title: string | null;
  library_reel_id: string | null;
}

export interface AdminRatingDetail {
  id: string;
  rating: number;
  comment: string | null;
  created_at: string;
  // User
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  user_telegram: string | null;
  user_tier: string | null;
  user_registered_at: string | null;
  user_profile: Record<string, unknown> | null;
  // Video
  job_id: string;
  job_url: string | null;
  video_title: string | null;
  video_platform: string | null;
  video_author: string | null;
  video_duration: number | null;
  video_views: number | null;
  video_likes: number | null;
  video_comments: number | null;
  // Timing
  job_created_at: string | null;
  job_completed_at: string | null;
  processing_seconds: number | null;
  // Script
  adaptation_summary: {
    script?: string;
    description?: string;
    editor_instructions?: string;
    hook_variants?: { text: string; score: number; why: string }[];
    [key: string]: unknown;
  } | null;
  // Library reel
  library_reel_id: string | null;
  reel_first_parsed_at: string | null;
  reel_submitted_by_email: string | null;
  // Stats
  total_jobs_for_reel: number;
  total_scripts_for_reel: number;
  // Other users
  other_ratings: {
    user_email: string | null;
    user_name: string | null;
    rating: number;
    comment: string | null;
    created_at: string;
  }[];
  other_scripts: {
    user_email: string | null;
    user_name: string | null;
    script_preview: string;
    created_at: string;
  }[];
}

// Admin Support
export interface AdminSupportConversation {
  id: string;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  user_telegram: string | null;
  status: string;
  unread_admin: number;
  last_message_text: string | null;
  last_message_at: string | null;
  created_at: string;
}

export interface AdminSupportMessage {
  id: string;
  sender_type: "user" | "admin";
  sender_id: string;
  text: string | null;
  image_key: string | null;
  read_at: string | null;
  created_at: string;
}

// Admin Parsing (deep-analyze tracking)
export interface AdminParsingItem {
  id: string;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  user_tier: string | null;
  analysis_id: string;
  platform: string;
  username: string;
  status: string;
  error: string | null;
  duration_seconds: number | null;
  result_json: Record<string, unknown> | null;
  created_at: string;
  completed_at: string | null;
}

export interface AdminParsingStats {
  running: number;
  completed_today: number;
  failed_today: number;
  completed_total: number;
  failed_total: number;
  avg_duration_seconds: number | null;
}

// ── Trend Watching Dashboard ────────────────────────────────────

export interface TrendWatchingStats {
  total_profiles: number;
  checked_today: number;
  queue_size: number;
  currently_scraping: number;
  currently_analyzing: number;
  trends_found_today: number;
  hot_trends_today: number;
  notifications_sent_today: number;
  profiles_by_priority: { high: number; normal: number; cold: number };
  scrape_errors_24h: number;
  last_check_run_at: string | null;
  next_check_run_at: string | null;
  apify_balance_pct: number | null;
  apify_used_usd: number | null;
  apify_remaining_usd: number | null;
  apify_runs_today: number;
  ai_tokens_today: number;
  ai_calls_today: number;
  ai_cost_estimate_usd: number;
}

export interface TrendingReel {
  thumbnail_url: string | null;
  url: string | null;
  x_factor: number | null;
  views: number | null;
  caption: string;
}

export interface PipelineProfile {
  profile_id: string | null;
  username: string;
  platform: string;
  display_name: string | null;
  followers_count: number | null;
  niche: string | null;
  check_priority: string;
  last_checked_at: string | null;
  trending_count: number;
  stale_since_minutes?: number | null;
  started_at?: string;
  error?: string;
  details?: Record<string, unknown>;
  trending_reels?: TrendingReel[];
}

export interface TrendWatchingPipeline {
  queued: PipelineProfile[];
  scraping: PipelineProfile[];
  analyzing: PipelineProfile[];
  completed: PipelineProfile[];
  failed: PipelineProfile[];
}

export interface TrendWatchingActivityEvent {
  timestamp: string;
  type: string;
  profile_username: string;
  platform: string;
  details?: Record<string, unknown>;
}

export interface TrendWatchingActivity {
  events: TrendWatchingActivityEvent[];
  total: number;
}

export interface TrendWatchingSparklines {
  checks_per_hour: number[];
  trends_per_hour: number[];
  notifications_per_hour: number[];
  errors_per_hour: number[];
}

// ── Niches Admin ────────────────────────────────────────────────────────

export interface AdminNiche {
  id: number;
  slug: string;
  display_name: string;
  display_name_en?: string | null;
  description?: string | null;
  keywords: string[];
  group_key: string;
  sort_order: number;
  is_active: boolean;
  videos_count: number;
  authors_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminNicheGroup {
  key: string;
  label: string;
  niches: string[];
}

export interface AdminNicheStats {
  total_niches: number;
  active_niches: number;
  videos_without_niche: number;
  authors_without_niche: number;
}

export interface AdminNichesResponse {
  items: AdminNiche[];
  groups: AdminNicheGroup[];
  stats: AdminNicheStats;
}
