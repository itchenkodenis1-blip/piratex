import axios from "axios";
import type {
  AdminAnalytics,
  AdminConversation,
  AdminJob,
  AdminJobStats,
  AdminLibraryItem,
  AdminListResponse,
  AdminMessage,
  AdminPaymentListResponse,
  AdminStats,
  AdminTierConfig,
  AdminUser,
  AdminUserDetail,
  AuthUser,
  CostAnalytics,
  DefaultPrompts,
  JobListResponse,
  JobResult,
  LibraryListResponse,
  LibraryReelDetail,
  MeResponse,
  PipelineDetail,
  PipelineItem,
  ProductionStatus,
  ProfilePresets,
  SharedJobResult,
  TagInfo,
  LibraryReelCard,
  ScriptTranslation,
  UserProfile,
  UserScript,
  UserSettingsData,
} from "../types";

const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
});

// Response interceptor for 429
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 429) {
      const detail = error.response.data?.detail;
      window.dispatchEvent(
        new CustomEvent("piratex:limit-reached", { detail })
      );
    }
    return Promise.reject(error);
  }
);

// Attach token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auth
export async function getMe(): Promise<MeResponse> {
  const { data } = await api.get("/auth/me");
  return data;
}

export async function logout(): Promise<void> {
  await api.post("/auth/logout");
}

export async function createTelegramCode(): Promise<{
  code: string;
  deep_link: string;
  expires_at: string;
}> {
  const { data } = await api.post("/auth/telegram-code");
  return data;
}

export async function checkTelegramCode(code: string): Promise<{
  confirmed: boolean;
  expired?: boolean;
  token?: string;
  user?: AuthUser;
}> {
  const { data } = await api.get("/auth/telegram-check", { params: { code } });
  return data;
}

// OAuth
export async function getOAuthProviders(): Promise<{
  providers: { name: string; configured: boolean }[];
}> {
  const { data } = await api.get("/auth/oauth/providers");
  return data;
}

export async function startOAuth(provider: string, redirectUrl?: string): Promise<{
  authorize_url: string;
}> {
  const { data } = await api.get(`/auth/oauth/${provider}/start`, {
    params: {
      ...(redirectUrl ? { redirect_url: redirectUrl } : {}),
      origin: window.location.origin,
    },
  });
  return data;
}

// Magic link (email)
export async function sendMagicLink(email: string, lang?: string, brand?: string): Promise<{
  sent: boolean;
  expires_in_minutes: number;
  link?: string;
}> {
  const { data } = await api.post("/auth/magic-link/send", { email, lang, brand });
  return data;
}

export async function checkMagicLink(code: string): Promise<{
  confirmed: boolean;
  expired?: boolean;
  token?: string;
}> {
  const { data } = await api.get("/auth/magic-link/check", { params: { code } });
  return data;
}

export async function verifyMagicLinkPin(email: string, pin: string): Promise<{
  verified: boolean;
  token?: string;
}> {
  const { data } = await api.post("/auth/magic-link/verify-pin", { email, pin });
  return data;
}

// Phone auth
export async function sendPhoneCode(phone: string): Promise<{
  sent: boolean;
  expires_in_minutes: number;
  code?: string;
}> {
  const { data } = await api.post("/auth/phone/send-code", { phone });
  return data;
}

export async function verifyPhoneCode(phone: string, code: string): Promise<{
  verified: boolean;
  expired?: boolean;
  too_many_attempts?: boolean;
  attempts_remaining?: number;
  token?: string;
  user?: AuthUser;
}> {
  const { data } = await api.post("/auth/phone/verify", { phone, code });
  return data;
}

// Settings
export async function getSettings(): Promise<UserSettingsData> {
  const { data } = await api.get("/settings");
  return data;
}

export async function updateSettings(payload: {
  language?: string;
  custom_content_prompt?: string;
  custom_strategy_prompt?: string;
  profile?: UserProfile;
  onboarding_completed?: boolean;
}): Promise<UserSettingsData> {
  const { data } = await api.put("/settings", payload);
  return data;
}

export async function getDefaultPrompts(): Promise<DefaultPrompts> {
  const { data } = await api.get("/settings/default-prompts");
  return data;
}

export async function getProfilePresets(): Promise<ProfilePresets> {
  const { data } = await api.get("/settings/profile-presets");
  return data;
}

export async function deepAnalyzeInstagram(username: string, analysisId?: string): Promise<import("../types").DeepAnalyzeResult> {
  const { data } = await api.post("/settings/deep-analyze", { username, analysis_id: analysisId });
  return data;
}

// Delete account (GDPR right to erasure)
export async function deleteAccount(): Promise<{ deleted: boolean }> {
  const { data } = await api.delete("/settings/me");
  return data;
}

// Jobs
export async function createJob(url: string, turnstileToken?: string): Promise<{
  job_id: string;
  share_token: string | null;
  library_reel_id?: string | null;
  status?: string;
}> {
  const body: Record<string, string> = { url };
  if (turnstileToken) body.turnstile_token = turnstileToken;
  const { data } = await api.post("/jobs", body);
  return data;
}

export async function getJob(jobId: string): Promise<JobResult> {
  const { data } = await api.get(`/jobs/${jobId}`);
  return data;
}

export function getFrameUrl(jobId: string, frameIndex: number): string {
  return `/api/jobs/${jobId}/frames/${frameIndex}`;
}

export async function listJobs(params: {
  status_filter?: string;
  page?: number;
  per_page?: number;
}): Promise<JobListResponse> {
  const { data } = await api.get("/jobs", { params });
  return data;
}

export async function toggleJobFilmed(jobId: string): Promise<{ ok: boolean; is_filmed: boolean }> {
  const { data } = await api.patch(`/jobs/${jobId}/filmed`);
  return data;
}

export async function hideJob(jobId: string): Promise<{ ok: boolean }> {
  const { data } = await api.delete(`/jobs/${jobId}`);
  return data;
}

export async function updateJobFields(
  jobId: string,
  body: { script?: string; description?: string; editor_instructions?: string },
): Promise<{ ok: boolean }> {
  const { data } = await api.patch(`/jobs/${jobId}/fields`, body);
  return data;
}

export async function rateJob(
  jobId: string,
  rating: number,
  comment?: string,
): Promise<{ rating: number; comment: string | null; created_at: string }> {
  const { data } = await api.post(`/jobs/${jobId}/rate`, { rating, comment });
  return data;
}

// Support Chat
export interface SupportMessage {
  id: string;
  sender_type: "user" | "admin";
  sender_id: string;
  text: string | null;
  image_key: string | null;
  read_at: string | null;
  created_at: string;
}

export interface SupportConversation {
  id: string;
  status: string;
  unread_user: number;
  created_at: string | null;
  updated_at: string | null;
  messages: SupportMessage[];
}

export async function getSupportConversation(): Promise<SupportConversation> {
  const { data } = await api.get("/support/conversation");
  return data;
}

export async function sendSupportMessage(
  text?: string,
  imageKey?: string,
): Promise<SupportMessage> {
  const { data } = await api.post("/support/messages", {
    text: text || null,
    image_key: imageKey || null,
  });
  return data;
}

export async function getSupportUnreadCount(): Promise<number> {
  const { data } = await api.get("/support/unread-count");
  return data.count;
}

export async function presignSupportUpload(
  fileName: string,
  fileType: string,
): Promise<{ upload_url: string; image_key: string }> {
  const { data } = await api.post("/support/presign-upload", {
    file_name: fileName,
    file_type: fileType,
  });
  return data;
}

// Library
export async function getLibrary(params: {
  q?: string;
  tags?: string;
  platform?: string;
  sort?: string;
  page?: number;
  per_page?: number;
  my_scripts?: boolean;
}): Promise<LibraryListResponse> {
  const { data } = await api.get("/library", { params });
  return data;
}

export async function getLibraryReel(reelId: string): Promise<LibraryReelDetail> {
  const { data } = await api.get(`/library/${reelId}`);
  return data;
}

export async function getLibraryTags(): Promise<TagInfo[]> {
  const { data } = await api.get("/library/tags");
  return data;
}

export async function getBookmarks(): Promise<LibraryReelCard[]> {
  const { data } = await api.get("/library/bookmarks");
  return data;
}

export async function bookmarkReel(reelId: string): Promise<void> {
  await api.post(`/library/${reelId}/bookmark`);
}

export async function unbookmarkReel(reelId: string): Promise<void> {
  await api.delete(`/library/${reelId}/bookmark`);
}

// Likes (universal, keyed on URL)
export async function getLikedUrls(): Promise<{ urls: string[] }> {
  const { data } = await api.get("/likes");
  return data;
}

export async function likeReel(url: string): Promise<void> {
  await api.post("/likes", { url });
}

export async function unlikeReel(url: string): Promise<void> {
  await api.delete("/likes", { data: { url } });
}

// Script generation
export async function generateScript(reelId: string): Promise<UserScript> {
  const { data } = await api.post(`/library/${reelId}/generate-script`);
  return data;
}

export async function rewriteScript(reelId: string): Promise<UserScript> {
  const { data } = await api.post(`/library/${reelId}/rewrite-script`);
  return data;
}

export async function updateScript(
  reelId: string,
  body: { script?: string; description?: string; editor_instructions?: string; active_hook_index?: number },
): Promise<UserScript> {
  const { data } = await api.patch(`/library/${reelId}/script`, body);
  return data;
}

// Second-language script translation (separate LLM iteration)
export async function translateScript(reelId: string, language: string): Promise<ScriptTranslation> {
  const { data } = await api.post(`/library/${reelId}/translate`, { language });
  return data;
}

export async function updateTranslation(
  reelId: string,
  language: string,
  body: { script?: string; description?: string; editor_instructions?: string },
): Promise<ScriptTranslation> {
  const { data } = await api.patch(`/library/${reelId}/translation/${language}`, body);
  return data;
}

// Trends
export async function getTrends(params: {
  tab?: string;
  niche?: string;
  platform?: string;
  min_x?: number;
  sort?: string;
  days?: number;
  page?: number;
  per_page?: number;
  q?: string;
}): Promise<import("../types").TrendsListResponse> {
  const { data } = await api.get("/trends", { params });
  return data;
}

export async function getTrendNiches(): Promise<import("../types").NicheStats[]> {
  const { data } = await api.get("/trends/niches");
  return data;
}

export async function getNicheTree(): Promise<import("../types").NicheTreeResponse> {
  const { data } = await api.get("/niches");
  return data;
}

export async function getMyAuthors(): Promise<import("../types").MyAuthorsResponse> {
  const { data } = await api.get("/trends/authors");
  return data;
}

export async function addMyAuthor(input: string): Promise<import("../types").TrackedAuthor> {
  const { data } = await api.post("/trends/authors", { input }, { timeout: 120000 });
  return data;
}

export async function removeMyAuthor(profileId: string): Promise<void> {
  await api.delete(`/trends/authors/${profileId}`);
}

export async function getSettingsInterests(): Promise<import("../types").InterestsData> {
  const { data } = await api.get("/settings/interests");
  return data;
}

export async function getRadarSettings(): Promise<import("../types").RadarSettings> {
  const { data } = await api.get("/settings/radar");
  return data;
}

export async function getForYouRecommendations(): Promise<import("../types").ForYouResponse> {
  const { data } = await api.get("/trends/for-you");
  return data;
}

// Telegram
export async function verifyTelegramSubscription(): Promise<{ subscribed: boolean; tier?: string; channel_url?: string }> {
  const { data } = await api.post("/telegram/verify");
  return data;
}

export async function getTelegramStatus(): Promise<{
  linked: boolean;
  telegram_username: string | null;
  subscribed: boolean;
  checked_at: string | null;
}> {
  const { data } = await api.get("/telegram/status");
  return data;
}

export async function createTelegramConnectCode(): Promise<{
  code: string;
  deep_link: string;
  expires_at: string;
}> {
  const { data } = await api.post("/telegram/connect-code");
  return data;
}

export async function disconnectTelegram(): Promise<{ ok: boolean }> {
  const { data } = await api.post("/telegram/disconnect");
  return data;
}

// Admin
export async function getAdminStats(): Promise<AdminStats> {
  const { data } = await api.get("/admin/stats");
  return data;
}

export async function getAdminAnalytics(): Promise<AdminAnalytics> {
  const { data } = await api.get("/admin/analytics");
  return data;
}

export async function getAdminCostAnalytics(): Promise<CostAnalytics> {
  const { data } = await api.get("/admin/cost-analytics");
  return data;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function getShowcaseStats(todayOnly = false): Promise<any> {
  const { data } = await api.get("/admin/showcase", { params: todayOnly ? { today: true } : {} });
  return data;
}

export async function resetShowcaseBaseline(): Promise<{ baseline: string }> {
  const { data } = await api.post("/admin/reset-baseline");
  return data;
}

// Demo mode — synthetic analytics overlay (admin only)
export async function getDemoMode(): Promise<{ enabled: boolean }> {
  const { data } = await api.get("/admin/demo-mode");
  return data;
}

export async function setDemoMode(enabled: boolean): Promise<{ enabled: boolean }> {
  const { data } = await api.post("/admin/demo-mode", { enabled });
  return data;
}

export async function adminCleanupGhosts(): Promise<{ deleted: number }> {
  const { data } = await api.post("/admin/cleanup-ghosts");
  return data;
}

export async function adminReextractFrames(): Promise<{
  total_completed: number;
  missing_frames: number;
  enqueued_job_ids: string[];
}> {
  const { data } = await api.post("/admin/reextract-frames");
  return data;
}

export async function repairThumbnails(includeOrphans = false): Promise<{
  profiles_checked: number;
  thumbnails_fixed: number;
  still_broken: number;
}> {
  const { data } = await api.post("/trends/repair-thumbnails", null, {
    params: { include_orphans: includeOrphans },
  });
  return data;
}

export async function adminListUsers(params: {
  tier?: string;
  is_anonymous?: boolean;
  page?: number;
  per_page?: number;
}): Promise<AdminListResponse<AdminUser>> {
  const { data } = await api.get("/admin/users", { params });
  return data;
}

export async function adminGetUser(userId: string, page = 1, perPage = 20): Promise<AdminUserDetail> {
  const { data } = await api.get(`/admin/users/${userId}`, { params: { page, per_page: perPage } });
  return data;
}

export async function adminUpdateUserTier(
  userId: string,
  tier: string,
  durationMonths?: number | null,
  reason?: string | null,
): Promise<{ id: string; email: string | null; tier: string; subscription_id?: string; period_end?: string }> {
  const { data } = await api.patch(`/admin/users/${userId}/tier`, {
    tier,
    duration_months: durationMonths ?? null,
    reason: reason || null,
  });
  return data;
}

export async function adminDeleteUser(userId: string): Promise<{ deleted: boolean }> {
  const { data } = await api.delete(`/admin/users/${userId}`);
  return data;
}

export async function adminListJobs(params: {
  status?: string;
  platform?: string;
  source?: string;
  date_range?: string;
  q?: string;
  page?: number;
  per_page?: number;
}): Promise<AdminListResponse<AdminJob>> {
  const { data } = await api.get("/admin/jobs", { params });
  return data;
}

export async function adminDeleteJob(jobId: string): Promise<{ deleted: boolean }> {
  const { data } = await api.delete(`/admin/jobs/${jobId}`);
  return data;
}

export async function adminGetJobStats(): Promise<AdminJobStats> {
  const { data } = await api.get("/admin/jobs/stats");
  return data;
}

export async function adminRetryJob(jobId: string): Promise<{ retried: boolean }> {
  const { data } = await api.post(`/admin/jobs/${jobId}/retry`);
  return data;
}

export async function adminCancelJob(jobId: string): Promise<{ cancelled: boolean }> {
  const { data } = await api.post(`/admin/jobs/${jobId}/cancel`);
  return data;
}

export async function adminListLibrary(params: {
  page?: number;
  per_page?: number;
}): Promise<AdminListResponse<AdminLibraryItem>> {
  const { data } = await api.get("/admin/library", { params });
  return data;
}

export async function adminDeleteLibraryItem(reelId: string): Promise<{ deleted: boolean }> {
  const { data } = await api.delete(`/admin/library/${reelId}`);
  return data;
}

// Admin Payments
export async function adminListPayments(params: {
  status?: string;
  provider?: string;
  q?: string;
  page?: number;
  per_page?: number;
}): Promise<AdminPaymentListResponse> {
  const { data } = await api.get("/admin/payments", { params });
  return data;
}

// Admin Tiers
export async function adminListTiers(): Promise<AdminTierConfig[]> {
  const { data } = await api.get("/admin/tiers");
  return data;
}

export async function adminUpdateTierConfig(
  name: string,
  payload: { max_monthly: number | null; max_total: number | null; max_refines_daily: number | null }
): Promise<AdminTierConfig> {
  const { data } = await api.put(`/admin/tiers/${name}`, payload);
  return data;
}

// Admin Messages
export async function adminListConversations(params: {
  q?: string;
  page?: number;
  per_page?: number;
}): Promise<AdminListResponse<AdminConversation>> {
  const { data } = await api.get("/admin/messages/conversations", { params });
  return data;
}

export async function adminGetConversation(telegramUserId: string): Promise<AdminMessage[]> {
  const { data } = await api.get(`/admin/messages/${telegramUserId}`);
  return data;
}

export async function adminSendMessage(telegramUserId: string, text: string): Promise<AdminMessage> {
  const { data } = await api.post(`/admin/messages/${telegramUserId}/send`, { text });
  return data;
}

// Admin Trending Reels
export async function adminListTrendingReels(params: {
  date_range?: string;
  niche?: string;
  platform?: string;
  sort?: string;
  page?: number;
  per_page?: number;
}): Promise<import("../types").AdminTrendingReelsResponse> {
  const { data } = await api.get("/admin/trending-reels", { params });
  return data;
}

// Admin Tracked Profiles (Authors)
export async function adminListTrackedProfiles(params: {
  q?: string;
  source?: string;
  active?: string;
  blocked?: string;
  page?: number;
  per_page?: number;
}): Promise<import("../types").AdminTrackedProfileListResponse> {
  const { data } = await api.get("/admin/tracked-profiles", { params });
  return data;
}

export async function adminToggleTrackedProfile(profileId: string): Promise<{ id: string; is_active: boolean }> {
  const { data } = await api.patch(`/admin/tracked-profiles/${profileId}`);
  return data;
}

export async function adminDeleteTrackedProfile(profileId: string): Promise<{ deleted: boolean }> {
  const { data } = await api.delete(`/admin/tracked-profiles/${profileId}`);
  return data;
}

// Admin Content Moderation
export async function adminBlockProfile(profileId: string, reason?: string): Promise<{ id: string; is_blocked: boolean }> {
  const { data } = await api.post(`/admin/tracked-profiles/${profileId}/block`, { reason: reason || "" });
  return data;
}

export async function adminUnblockProfile(profileId: string): Promise<{ id: string; is_blocked: boolean }> {
  const { data } = await api.post(`/admin/tracked-profiles/${profileId}/unblock`);
  return data;
}

export async function adminHideReel(reelId: string, reason?: string): Promise<{ id: string; is_hidden: boolean }> {
  const { data } = await api.post(`/admin/reels/${reelId}/hide`, { reason: reason || "" });
  return data;
}

export async function adminUnhideReel(reelId: string): Promise<{ id: string; is_hidden: boolean }> {
  const { data } = await api.post(`/admin/reels/${reelId}/unhide`);
  return data;
}

export async function adminListHiddenReels(params: {
  q?: string;
  page?: number;
  per_page?: number;
}): Promise<AdminListResponse<import("../types").AdminHiddenReel>> {
  const { data } = await api.get("/admin/hidden-reels", { params });
  return data;
}

// Admin: Ratings
export async function adminListRatings(params: {
  rating?: number;
  has_comment?: boolean;
  date_from?: string;
  date_to?: string;
  page?: number;
  per_page?: number;
}): Promise<AdminListResponse<import("../types").AdminRatingItem>> {
  const { data } = await api.get("/admin/ratings", { params });
  return data;
}

export async function adminGetRatingDetail(ratingId: string): Promise<import("../types").AdminRatingDetail> {
  const { data } = await api.get(`/admin/ratings/${ratingId}`);
  return data;
}

export async function adminGetUnreadRatingsCount(): Promise<number> {
  const { data } = await api.get("/admin/ratings/unread-count");
  return data.count;
}

// Admin: Support
export async function adminListSupportConversations(params: {
  status?: string;
  q?: string;
  page?: number;
  per_page?: number;
}): Promise<AdminListResponse<import("../types").AdminSupportConversation>> {
  const { data } = await api.get("/admin/support/conversations", { params });
  return data;
}

export async function adminGetSupportMessages(
  conversationId: string,
): Promise<import("../types").AdminSupportMessage[]> {
  const { data } = await api.get(`/admin/support/conversations/${conversationId}`);
  return data;
}

export async function adminSendSupportMessage(
  conversationId: string,
  text: string,
): Promise<import("../types").AdminSupportMessage> {
  const { data } = await api.post(`/admin/support/conversations/${conversationId}/messages`, { text });
  return data;
}

export async function adminResolveSupportConversation(
  conversationId: string,
): Promise<{ ok: boolean; status: string }> {
  const { data } = await api.post(`/admin/support/conversations/${conversationId}/resolve`);
  return data;
}

export async function adminBlockSupportUser(
  conversationId: string,
): Promise<{ ok: boolean; blocked: boolean }> {
  const { data } = await api.post(`/admin/support/conversations/${conversationId}/block-user`);
  return data;
}

export async function adminUnblockSupportUser(
  conversationId: string,
): Promise<{ ok: boolean; blocked: boolean }> {
  const { data } = await api.post(`/admin/support/conversations/${conversationId}/unblock-user`);
  return data;
}

export async function adminGetSupportUnreadCount(): Promise<number> {
  const { data } = await api.get("/admin/support/unread-count");
  return data.count;
}

// Founder avatar
export async function adminUploadFounderAvatar(file: File): Promise<{ ok: boolean; key: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post("/admin/founder-avatar", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function adminGetFounderAvatar(): Promise<{ url: string | null; key: string | null }> {
  const { data } = await api.get("/admin/founder-avatar");
  return data;
}

// Billing
export async function getPricing(currency: "RUB" | "EUR" = "RUB"): Promise<import("../types").PricingResponse> {
  const { data } = await api.get("/billing/pricing", { params: { currency } });
  return data;
}

export async function getPaymentProviders(): Promise<import("../types").PaymentProviderInfo[]> {
  const { data } = await api.get("/billing/providers");
  return data.providers;
}

export async function createCheckout(
  tier: string,
  interval: string,
  promoCode?: string,
  provider?: string,
  email?: string,
): Promise<import("../types").CheckoutResponse> {
  const { data } = await api.post("/billing/checkout", {
    tier,
    interval,
    promo_code: promoCode || undefined,
    provider: provider || undefined,
    auto_renewal_consent: true,
    email: email || undefined,
  });
  return data;
}

export async function validatePromoCode(code: string): Promise<{
  valid: boolean;
  error?: string;
  discount_percent?: number;
  original_amount?: number;
  discounted_amount?: number;
  remaining_uses?: number | null;
}> {
  const { data } = await api.post("/billing/validate-promo", { code });
  return data;
}

export async function getSubscription(): Promise<{ subscription: import("../types").SubscriptionInfo | null }> {
  const { data } = await api.get("/billing/subscription");
  return data;
}

export async function cancelSubscription(): Promise<{ ok: boolean; message: string; active_until: string | null }> {
  const { data } = await api.post("/billing/cancel");
  return data;
}

export async function cancelSubscriptionByToken(token: string): Promise<{ ok: boolean; message: string; active_until: string | null }> {
  const { data } = await api.post("/billing/cancel-by-token", { token });
  return data;
}

export async function removePaymentMethod(): Promise<{ ok: boolean; message: string }> {
  const { data } = await api.delete("/billing/payment-method");
  return data;
}

export async function getPayments(): Promise<{ payments: import("../types").PaymentItem[] }> {
  const { data } = await api.get("/billing/payments");
  return data;
}

export async function getPortalUrl(): Promise<{ url: string }> {
  const { data } = await api.post("/billing/portal");
  return data;
}


// Pipeline
export async function getPipelineItems(
  statusFilter?: string,
  assigneeFilter?: string,
): Promise<PipelineItem[]> {
  const { data } = await api.get("/pipeline", {
    params: { status: statusFilter, assignee: assigneeFilter },
  });
  return data.items;
}

export async function getPipelineDetail(scriptId: string): Promise<PipelineDetail> {
  const { data } = await api.get(`/pipeline/${scriptId}`);
  return data;
}

export async function changePipelineStatus(
  scriptId: string,
  newStatus: ProductionStatus,
  comment?: string,
): Promise<void> {
  await api.patch(`/pipeline/${scriptId}/status`, { new_status: newStatus, comment });
}

export async function assignPipeline(scriptId: string, assigneeId: string | null): Promise<void> {
  await api.patch(`/pipeline/${scriptId}/assign`, { assignee_id: assigneeId });
}

export async function schedulePipeline(scriptId: string, scheduledAt: string | null): Promise<void> {
  await api.patch(`/pipeline/${scriptId}/schedule`, { scheduled_publish_at: scheduledAt });
}

export async function setDueDate(scriptId: string, dueDate: string | null): Promise<void> {
  await api.patch(`/pipeline/${scriptId}/due-date`, { due_date: dueDate });
}

export async function addToPipeline(scriptId: string): Promise<void> {
  await api.post(`/pipeline/add/${scriptId}`);
}

export async function addToPipelineByJob(jobId: string): Promise<{ script_id: string }> {
  const { data } = await api.post(`/pipeline/add-by-job/${jobId}`);
  return data;
}

export async function presignPipelineAsset(
  scriptId: string,
  fileName: string,
  fileType?: string,
): Promise<{ upload_url: string; file_key: string }> {
  const { data } = await api.post(`/pipeline/${scriptId}/assets/presign`, {
    file_name: fileName,
    file_type: fileType,
  });
  return data;
}

export async function confirmPipelineAsset(
  scriptId: string,
  body: { file_key: string; file_name: string; file_size?: number; file_type?: string },
): Promise<import("../types").PipelineAsset> {
  const { data } = await api.post(`/pipeline/${scriptId}/assets`, body);
  return data;
}

export async function getPipelineAssets(scriptId: string): Promise<import("../types").PipelineAsset[]> {
  const { data } = await api.get(`/pipeline/${scriptId}/assets`);
  return data;
}

export async function getAssetDownloadUrl(
  scriptId: string,
  assetId: string,
): Promise<{ download_url: string; file_name: string }> {
  const { data } = await api.get(`/pipeline/${scriptId}/assets/${assetId}/download`);
  return data;
}

export async function deletePipelineAsset(scriptId: string, assetId: string): Promise<void> {
  await api.delete(`/pipeline/${scriptId}/assets/${assetId}`);
}

export async function addPipelineComment(
  scriptId: string,
  text: string,
): Promise<import("../types").PipelineComment> {
  const { data } = await api.post(`/pipeline/${scriptId}/comments`, { text });
  return data;
}

export async function getPipelineComments(scriptId: string): Promise<import("../types").PipelineComment[]> {
  const { data } = await api.get(`/pipeline/${scriptId}/comments`);
  return data;
}

// ── Shooting Queue (admin-only) ─────────────────────────────────

export interface ShootingQueueItem {
  id: string;
  position: number;
  added_at: string | null;
  filmed_at: string | null;
  script_id: string;
  script_text: string;
  description: string;
  library_reel_id: string;
  video_title: string | null;
  video_author: string | null;
  video_platform: string | null;
  video_duration: number | null;
  url: string;
  job_id: string;
}

export async function getShootingQueue(): Promise<ShootingQueueItem[]> {
  const { data } = await api.get("/shooting-queue");
  return data.items;
}

export async function addToShootingQueue(jobId: string): Promise<{ item_id: string; script_id: string }> {
  const { data } = await api.post(`/shooting-queue/add/${jobId}`);
  return data;
}

export async function shootingQueueMarkDone(itemId: string): Promise<void> {
  await api.post(`/shooting-queue/${itemId}/done`);
}

export async function removeFromShootingQueue(itemId: string): Promise<void> {
  await api.delete(`/shooting-queue/${itemId}`);
}

export async function checkInShootingQueue(jobId: string): Promise<{ in_queue: boolean; item_id: string | null }> {
  const { data } = await api.get(`/shooting-queue/check/${jobId}`);
  return data;
}

// Share (public, no auth)
export async function getSharedJob(token: string): Promise<SharedJobResult> {
  const { data } = await axios.get(`/api/share/${token}`);
  return data;
}

export function getSharedFrameUrl(token: string, frameIndex: number): string {
  return `/api/share/${token}/frames/${frameIndex}`;
}

// ── Admin: Trend Watching Dashboard ─────────────────────────────

export async function adminGetTrendWatchingStats(): Promise<import("../types").TrendWatchingStats> {
  const { data } = await api.get("/admin/trend-watching/stats");
  return data;
}

export async function adminGetTrendWatchingPipeline(): Promise<import("../types").TrendWatchingPipeline> {
  const { data } = await api.get("/admin/trend-watching/pipeline");
  return data;
}

export async function adminGetTrendWatchingActivity(limit = 50): Promise<import("../types").TrendWatchingActivity> {
  const { data } = await api.get("/admin/trend-watching/activity", { params: { limit } });
  return data;
}

export async function adminGetTrendWatchingSparklines(): Promise<import("../types").TrendWatchingSparklines> {
  const { data } = await api.get("/admin/trend-watching/sparklines");
  return data;
}

// ── Admin Parsing ───────────────────────────────────────────────

export async function adminListParsings(params: {
  status?: string;
  platform?: string;
  q?: string;
  date_range?: string;
  page?: number;
  per_page?: number;
}): Promise<import("../types").AdminListResponse<import("../types").AdminParsingItem>> {
  const { data } = await api.get("/admin/parsings", { params });
  return data;
}

export async function adminGetParsingStats(): Promise<import("../types").AdminParsingStats> {
  const { data } = await api.get("/admin/parsings/stats");
  return data;
}

// ── Admin Niches ────────────────────────────────────────────────

export async function adminListNiches(): Promise<import("../types").AdminNichesResponse> {
  const { data } = await api.get("/admin/niches");
  return data;
}

export async function adminCreateNiche(req: {
  slug: string;
  display_name: string;
  display_name_en?: string;
  description?: string;
  keywords?: string[];
  group_key?: string;
  sort_order?: number;
}): Promise<import("../types").AdminNiche> {
  const { data } = await api.post("/admin/niches", req);
  return data;
}

export async function adminUpdateNiche(
  slug: string,
  req: {
    display_name?: string;
    display_name_en?: string;
    description?: string;
    keywords?: string[];
    group_key?: string;
    sort_order?: number;
  },
): Promise<import("../types").AdminNiche> {
  const { data } = await api.patch(`/admin/niches/${slug}`, req);
  return data;
}

export async function adminDeactivateNiche(slug: string): Promise<{ deactivated: boolean }> {
  const { data } = await api.delete(`/admin/niches/${slug}`);
  return data;
}

export async function adminActivateNiche(slug: string): Promise<{ activated: boolean }> {
  const { data } = await api.post(`/admin/niches/${slug}/activate`);
  return data;
}
