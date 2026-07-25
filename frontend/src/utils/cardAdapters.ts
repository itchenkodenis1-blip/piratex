import { getFrameUrl } from "../api/client";
import type { TrendItem, JobCard, LibraryReelCard, UnifiedCardData } from "../types";

function getStatusGroup(status: string): "processing" | "completed" | "failed" {
  if (status === "completed") return "completed";
  if (status === "failed") return "failed";
  return "processing";
}

function isNewAndViral(item: TrendItem): boolean {
  if (!item.published_at || !item.x_factor) return false;
  const hoursSincePublished = (Date.now() - new Date(item.published_at).getTime()) / 3600000;
  return hoursSincePublished < 48 && item.x_factor >= 5;
}

function isCaughtToday(item: TrendItem): boolean {
  if (!item.trending_since) return false;
  const hoursSinceCaught = (Date.now() - new Date(item.trending_since).getTime()) / 3600000;
  return hoursSinceCaught < 24;
}

export function trendToCard(item: TrendItem, rank: number): UnifiedCardData {
  return {
    id: item.id,
    url: item.url,
    title: item.caption,
    author: item.author.username,
    platform: item.author.platform,
    duration: item.duration,
    views: item.views,
    likes: item.likes,
    comments: item.comments,
    publishedAt: item.published_at,
    createdAt: item.published_at || "",
    thumbnailSrc: item.thumbnail_url ? `/api/trends/thumbnail/${item.id}` : null,
    thumbnailUrl: null,
    xFactor: item.x_factor,
    velocity: item.velocity,
    niche: item.niche || item.author.niche,
    isParsed: item.is_parsed,
    isNewViral: isNewAndViral(item),
    isTodaysCatch: isCaughtToday(item),
    rank,
    frameCount: item.frame_count,
    trendId: item.id,
    caption: item.caption,
    jobId: null,
    status: null,
    progress: 0,
    progressMessage: null,
    error: null,
    isFilmed: false,
    shareToken: null,
    userScriptId: null,
    productionStatus: null,
    libraryReelId: item.library_reel_id,
    tags: [],
    contentFormat: null,
    hasUserScript: false,
  };
}

export function jobToCard(job: JobCard): UnifiedCardData {
  const statusGroup = getStatusGroup(job.status);
  return {
    id: job.job_id,
    url: job.url,
    title: job.video_title,
    author: job.video_author,
    platform: job.video_platform,
    duration: job.video_duration,
    views: job.video_views,
    likes: job.video_likes,
    comments: job.video_comments,
    publishedAt: null,
    createdAt: job.created_at,
    thumbnailSrc: statusGroup === "completed"
      ? getFrameUrl(job.job_id, 2)
      : null,
    thumbnailUrl: null,
    xFactor: job.x_factor ?? null,
    velocity: null,
    niche: null,
    isParsed: false,
    isNewViral: false,
    isTodaysCatch: false,
    rank: null,
    frameCount: 0,
    trendId: null,
    caption: null,
    jobId: job.job_id,
    status: statusGroup,
    progress: job.progress,
    progressMessage: job.progress_message,
    error: job.error,
    isFilmed: job.is_filmed,
    shareToken: job.share_token,
    userScriptId: job.user_script_id,
    productionStatus: job.production_status,
    libraryReelId: job.library_reel_id,
    tags: [],
    contentFormat: null,
    hasUserScript: !!job.user_script_id,
  };
}

export function libraryReelToCard(reel: LibraryReelCard): UnifiedCardData {
  return {
    id: reel.id,
    url: reel.url,
    title: reel.video_title,
    author: reel.video_author,
    platform: reel.video_platform,
    duration: reel.video_duration,
    views: reel.video_views,
    likes: reel.video_likes,
    comments: reel.video_comments,
    publishedAt: null,
    createdAt: reel.created_at,
    thumbnailSrc: reel.job_id ? getFrameUrl(reel.job_id, reel.cover_frame_index ?? 1) : null,
    thumbnailUrl: null,
    xFactor: null,
    velocity: null,
    niche: null,
    isParsed: false,
    isNewViral: false,
    isTodaysCatch: false,
    rank: null,
    frameCount: 0,
    trendId: null,
    caption: null,
    jobId: reel.job_id,
    status: null,
    progress: 0,
    progressMessage: null,
    error: null,
    isFilmed: false,
    shareToken: null,
    userScriptId: null,
    productionStatus: null,
    libraryReelId: reel.id,
    tags: reel.tags,
    contentFormat: reel.content_format,
    hasUserScript: reel.has_user_script,
  };
}
