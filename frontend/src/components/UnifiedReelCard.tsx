import { useCallback, useEffect, useRef, useState } from "react";
import type { Translations } from "../i18n/types";
import type { UnifiedCardData } from "../types";
import { formatViews, formatDuration, timeAgo, commentRate } from "../utils/format";
import { PlatformIcon } from "../utils/platform";

/* ─── X-factor badge ─── */
function XBadge({ value }: { value: number | null }) {
  if (value === null || value === undefined) return null;
  let color = "bg-zinc-800/80 text-zinc-300";
  if (value >= 10) color = "bg-red-500/25 text-red-400 ring-1 ring-red-500/40";
  else if (value >= 5) color = "bg-orange-500/25 text-orange-400 ring-1 ring-orange-500/40";
  else if (value >= 2) color = "bg-amber-500/25 text-amber-400 ring-1 ring-amber-500/40";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold backdrop-blur-sm ${color}`}>
      {value.toFixed(1)}x
    </span>
  );
}

/* ─── Frame preview interval ─── */
const FRAME_INTERVAL = 1200;

/* ─── Status styles ─── */
const STATUS_STYLES: Record<string, string> = {
  processing: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  completed: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  filmed: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  failed: "bg-red-500/20 text-red-300 border-red-500/30",
};

interface UnifiedReelCardProps {
  data: UnifiedCardData;
  variant: "trend" | "job" | "library";
  onClick: () => void;
  onParse?: (e: React.MouseEvent) => void;
  onHide?: (e: React.MouseEvent) => void;
  onToggleFilmed?: (e: React.MouseEvent) => void;
  onAdminHide?: (e: React.MouseEvent) => void;
  onAdminBlock?: (e: React.MouseEvent) => void;
  isLiked: boolean;
  onToggleLike: (e: React.MouseEvent) => void;
  parsingId?: string | null;
  t: Translations;
}

export function UnifiedReelCard({
  data,
  variant,
  onClick,
  onParse,
  onHide,
  onToggleFilmed,
  onAdminHide,
  onAdminBlock,
  isLiked,
  onToggleLike,
  parsingId,
  t,
}: UnifiedReelCardProps) {
  const [linkCopied, setLinkCopied] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [imgFallbackSrc, setImgFallbackSrc] = useState<string | null>(null);

  const isTrend = variant === "trend";
  const isJob = variant === "job";
  const isLibrary = variant === "library";
  const isCompleted = data.status === "completed" || data.status === null;
  const isProcessing = isJob && data.status === "processing";
  const isFailed = isJob && data.status === "failed";
  const cr = commentRate(data.views, data.comments);

  /* ─── Frame slideshow (trend only) ─── */
  const hasFrames = isTrend && data.frameCount > 1;
  const [hoverFrame, setHoverFrame] = useState<number | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const preloadedRef = useRef<Set<number>>(new Set());

  const preloadFrame = useCallback(
    (idx: number) => {
      if (!data.trendId || preloadedRef.current.has(idx)) return;
      preloadedRef.current.add(idx);
      const img = new Image();
      img.src = `/api/trends/${data.trendId}/frames/${idx}`;
    },
    [data.trendId],
  );

  const handleMouseEnter = useCallback(() => {
    if (!hasFrames) return;
    setHoverFrame(0);
    preloadFrame(0);
    preloadFrame(1);
    let current = 0;
    intervalRef.current = setInterval(() => {
      current = (current + 1) % data.frameCount;
      setHoverFrame(current);
      preloadFrame((current + 1) % data.frameCount);
    }, FRAME_INTERVAL);
  }, [hasFrames, data.frameCount, preloadFrame]);

  const handleMouseLeave = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setHoverFrame(null);
  }, []);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const showingFrame = hoverFrame !== null;
  const frameUrl = showingFrame && data.trendId ? `/api/trends/${data.trendId}/frames/${hoverFrame}` : null;

  /* ─── Share link copy ─── */
  const handleCopyShareLink = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!data.shareToken) return;
    const url = `${window.location.origin}/share/${data.shareToken}`;
    navigator.clipboard.writeText(url);
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 2000);
  };

  /* ─── Status ─── */
  const statusLabel = isJob
    ? data.isFilmed
      ? t.my_videos_status_filmed
      : data.status === "processing"
        ? t.my_videos_status_processing
        : data.status === "failed"
          ? t.my_videos_status_failed
          : t.my_videos_status_ready
    : null;

  const statusStyle = isJob
    ? data.isFilmed
      ? STATUS_STYLES.filmed
      : STATUS_STYLES[data.status || "completed"]
    : "";

  /* ─── Border ─── */
  const borderClass = isTrend && data.isParsed
    ? "border-green-500/30"
    : isJob && data.isFilmed && isCompleted
      ? "border-emerald-500/30 hover:border-emerald-400/40"
      : "border-border-subtle";

  /* ─── Niche label ─── */
  const nicheLabel = data.niche
    ? ((t as unknown as Record<string, string>)[`niche_${data.niche}`] || data.niche)
    : null;

  return (
    <div
      className={`group relative flex flex-col bg-surface border rounded-2xl overflow-hidden
        transition-all duration-200 cursor-pointer
        sm:hover:border-cream-muted/30 sm:hover:scale-[1.02] sm:hover:shadow-lg sm:hover:shadow-black/20
        active:scale-[0.98] active:opacity-90
        ${borderClass}`}
      onClick={onClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* ─── Thumbnail area ─── */}
      <div className="relative aspect-[3/4] bg-surface-light overflow-hidden">
        {/* Processing overlay (job) */}
        {isProcessing && (
          <div className="w-full h-full flex items-center justify-center bg-surface">
            <div className="flex flex-col items-center gap-2 px-4">
              <div className="w-8 h-8 border-2 border-border-subtle border-t-cream rounded-full animate-spin" />
              <span className="text-xs text-cream-muted text-center line-clamp-1">
                {data.progressMessage || `${Math.round(data.progress * 100)}%`}
              </span>
            </div>
          </div>
        )}

        {/* Failed overlay (job) */}
        {isFailed && (
          <div className="w-full h-full flex items-center justify-center bg-surface">
            <div className="flex flex-col items-center gap-2 px-4">
              <svg className="w-8 h-8 text-red-500/50" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="15" y1="9" x2="9" y2="15" />
                <line x1="9" y1="9" x2="15" y2="15" />
              </svg>
              {data.error && (
                <p className="text-[11px] text-red-400/80 text-center line-clamp-3 leading-snug">
                  {data.error.length > 80 ? data.error.slice(0, 80) + "\u2026" : data.error}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Thumbnail image (trend / completed job / library) */}
        {!isProcessing && !isFailed && data.thumbnailSrc && !imgError && (
          <img
            src={imgFallbackSrc || data.thumbnailSrc}
            alt={data.title || ""}
            className={`w-full h-full object-cover transition-transform duration-300 sm:group-hover:scale-105 ${
              showingFrame ? "opacity-0" : "opacity-100"
            } ${data.isFilmed ? "brightness-[0.85]" : ""}`}
            loading="lazy"
            onError={() => {
              if (!imgFallbackSrc && data.thumbnailSrc && data.jobId) {
                // Frame 2 failed — try frame 1
                setImgFallbackSrc(`/api/jobs/${data.jobId}/frames/1`);
              } else {
                setImgError(true);
              }
            }}
          />
        )}

        {/* No thumbnail fallback */}
        {!isProcessing && !isFailed && (!data.thumbnailSrc || imgError) && (
          <div className="w-full h-full flex items-center justify-center text-cream-dim text-xs">
            No img
          </div>
        )}

        {/* Frame slideshow overlay (trend hover) */}
        {frameUrl && (
          <img
            src={frameUrl}
            alt=""
            className="absolute inset-0 w-full h-full object-cover scale-105 transition-opacity duration-200"
          />
        )}

        {/* Frame progress bar (trend hover) */}
        {showingFrame && data.frameCount > 1 && (
          <div className="absolute bottom-0 inset-x-0 h-0.5 flex z-20">
            {Array.from({ length: data.frameCount }).map((_, i) => (
              <div
                key={i}
                className={`flex-1 transition-colors duration-150 ${i === hoverFrame ? "bg-cream" : "bg-white/20"}`}
              />
            ))}
          </div>
        )}

        {/* Gradient overlay at top */}
        <div className="absolute inset-x-0 top-0 h-16 sm:h-20 bg-gradient-to-b from-black/50 to-transparent pointer-events-none z-[1]" />

        {/* Gradient overlay at bottom */}
        {(isCompleted || isTrend || isLibrary) && (
          <div className="absolute inset-x-0 bottom-0 h-20 sm:h-24 bg-gradient-to-t from-black/80 via-black/40 to-transparent pointer-events-none" />
        )}

        {/* Top-left: Platform */}
        <div className="absolute top-2 left-2 sm:top-2.5 sm:left-2.5 flex items-center gap-1.5 z-10">
          {/* Filmed checkmark (job) */}
          {isJob && data.isFilmed && isCompleted && (
            <span className="w-5 h-5 flex items-center justify-center rounded-full bg-emerald-500/90 shadow-md">
              <svg className="w-3 h-3 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </span>
          )}
          {data.platform && <PlatformIcon platform={data.platform} />}
        </div>

        {/* Top-right zone */}
        <div className="absolute top-2 right-2 sm:top-2.5 sm:right-2.5 flex items-center gap-2 sm:gap-1.5 z-10">
          {/* Like heart */}
          <button
            onClick={(e) => { e.stopPropagation(); onToggleLike(e); }}
            className={`w-7 h-7 sm:w-8 sm:h-8 flex items-center justify-center rounded-full backdrop-blur-sm transition-colors ${
              isLiked
                ? "bg-red-500/30 text-red-400"
                : "bg-black/40 text-white/70 hover:text-white"
            }`}
          >
            <svg
              className="w-4 h-4"
              viewBox="0 0 24 24"
              fill={isLiked ? "currentColor" : "none"}
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
            </svg>
          </button>

          {/* Rank badge (trend top 3) */}
          {isTrend && data.rank !== null && data.rank <= 3 && (
            <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-cream/90 text-black flex items-center justify-center text-xs sm:text-sm font-bold shadow-lg">
              {data.rank}
            </div>
          )}

          {/* Today's catch badge (trend, caught in last 24h) */}
          {isTrend && data.isTodaysCatch && (data.rank === null || data.rank > 3) && (
            <span className="inline-flex items-center gap-1 px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-[11px] font-semibold bg-cyan-500/25 text-cyan-300 ring-1 ring-cyan-500/40 backdrop-blur-sm">
              <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
              </svg>
              {t.trends_caught_today}
            </span>
          )}

          {/* New viral badge (trend, not top 3, not today's catch) */}
          {isTrend && data.isNewViral && !data.isTodaysCatch && (data.rank === null || data.rank > 3) && (
            <span className="inline-flex items-center px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-[11px] font-semibold bg-orange-500/30 text-orange-300 ring-1 ring-orange-500/40 backdrop-blur-sm">
              {t.trends_new_viral}
            </span>
          )}

          {/* Status badge (job) */}
          {isJob && statusLabel && (
            <span
              className={`px-2 py-0.5 text-[10px] font-semibold rounded-full border backdrop-blur-sm ${statusStyle} ${
                isProcessing ? "animate-pulse" : ""
              }`}
            >
              {statusLabel}
            </span>
          )}

          {/* Hide button (job) */}
          {isJob && !isProcessing && onHide && (
            <span
              role="button"
              title={t.my_videos_hide}
              onClick={onHide}
              className="w-7 h-7 sm:w-5 sm:h-5 flex items-center justify-center rounded-full bg-black/50 backdrop-blur-sm text-cream-muted hover:text-cream hover:bg-red-500/60 transition-colors"
            >
              <svg className="w-3.5 h-3.5 sm:w-3 sm:h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </span>
          )}

          {/* Admin: hide reel from trends */}
          {onAdminHide && (
            <span
              role="button"
              title="Скрыть из трендов"
              onClick={onAdminHide}
              className="w-7 h-7 sm:w-5 sm:h-5 flex items-center justify-center rounded-full bg-black/50 backdrop-blur-sm text-cream-muted hover:text-red-400 hover:bg-red-500/30 transition-colors"
            >
              <svg className="w-3.5 h-3.5 sm:w-3 sm:h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                <line x1="1" y1="1" x2="23" y2="23" />
              </svg>
            </span>
          )}

          {/* Admin: block author */}
          {onAdminBlock && (
            <span
              role="button"
              title="Заблокировать автора"
              onClick={onAdminBlock}
              className="w-7 h-7 sm:w-5 sm:h-5 flex items-center justify-center rounded-full bg-black/50 backdrop-blur-sm text-cream-muted hover:text-red-400 hover:bg-red-500/30 transition-colors"
            >
              <svg className="w-3.5 h-3.5 sm:w-3 sm:h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <circle cx="12" cy="12" r="10" />
                <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
              </svg>
            </span>
          )}

          {/* Has script badge (library) */}
          {isLibrary && data.hasUserScript && (
            <span className="px-2 py-0.5 bg-cream/80 backdrop-blur-sm text-[#0C0C0C] text-[10px] font-medium rounded-full">
              {t.reel_has_script}
            </span>
          )}
        </div>

        {/* Progress bar (job processing) */}
        {isProcessing && (
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-border-subtle z-10">
            <div
              className="h-full bg-cream transition-all duration-500"
              style={{ width: `${data.progress * 100}%` }}
            />
          </div>
        )}

        {/* Bottom overlay: views + time + duration */}
        {!isProcessing && !isFailed && (
          <div className="absolute bottom-2 left-2 right-2 sm:bottom-2.5 sm:left-2.5 sm:right-2.5 z-10">
            {/* Views + timeAgo + duration */}
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5 min-w-0">
                {data.views != null && data.views > 0 && (
                  <span className="text-xs sm:text-sm font-semibold text-white drop-shadow-lg">
                    {formatViews(data.views)}
                  </span>
                )}
                {isTrend && data.velocity !== null && data.velocity > 0 && (
                  <span className="text-[10px] sm:text-[11px] text-green-400 font-medium drop-shadow-lg hidden xs:inline">
                    +{formatViews(Math.round(data.velocity))}/h
                  </span>
                )}
                {(data.publishedAt || data.createdAt) && (
                  <span className="text-[10px] sm:text-[11px] text-white/60 drop-shadow-lg flex-shrink-0">
                    {timeAgo(data.publishedAt || data.createdAt, t)}
                  </span>
                )}
              </div>
              {data.duration != null && (
                <span className="px-1.5 py-0.5 bg-black/70 backdrop-blur-sm text-white text-[10px] sm:text-[11px] font-mono rounded flex-shrink-0">
                  {formatDuration(data.duration)}
                </span>
              )}
            </div>

            {/* Title + author on thumbnail (job/library) */}
            {(isJob || isLibrary) && (
              <>
                <h3 className="text-[13px] font-semibold text-cream line-clamp-1 leading-snug drop-shadow-lg">
                  {data.title || t.reel_no_title}
                </h3>
                {data.author && (
                  <p className="text-[11px] text-cream-dim mt-0.5 drop-shadow">{data.author}</p>
                )}
              </>
            )}
          </div>
        )}

        {/* Title/author overlay for non-completed jobs */}
        {isJob && !isCompleted && (data.title || data.author) && (
          <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent pt-12 pb-2.5 px-2.5 z-10">
            {data.title && (
              <h3 className="text-[13px] font-semibold text-cream line-clamp-1 leading-snug drop-shadow-lg">
                {data.title}
              </h3>
            )}
            {data.author && (
              <p className="text-[11px] text-cream-dim mt-0.5 drop-shadow">{data.author}</p>
            )}
          </div>
        )}
      </div>

      {/* ─── Card body ─── */}
      <div className="flex flex-col gap-1.5 p-2 sm:p-2.5">
        {/* Row 1: Author + niche/tags (trend) */}
        {isTrend && (
          <div className="flex items-center gap-1.5 min-w-0">
            <p className="text-xs sm:text-sm font-medium text-cream truncate flex-1 min-w-0">
              @{data.author}
            </p>
            {nicheLabel && (
              <span className="flex-shrink-0 px-1.5 py-0.5 text-[10px] sm:text-[10px] bg-surface-light text-cream-muted rounded-full truncate max-w-[80px]">
                {nicheLabel}
              </span>
            )}
          </div>
        )}

        {/* Row 2: Metrics */}
        {isTrend && (
          <div className="flex items-center gap-2 sm:gap-2.5 text-[10px] sm:text-[11px] text-cream-dim">
            {cr !== null && (
              <span className={`font-medium ${cr >= 2 ? "text-orange-400" : cr >= 0.5 ? "text-green-400" : cr >= 0.1 ? "text-cream" : "text-cream-dim"}`}>
                {cr.toFixed(1)}% CR
              </span>
            )}
            <span className="ml-auto">
              <XBadge value={data.xFactor} />
            </span>
          </div>
        )}

        {/* Job completed: engagement metrics */}
        {isJob && isCompleted && (data.likes || data.comments || cr !== null || data.xFactor) && (
          <div className="flex items-center gap-2 sm:gap-2.5 text-[10px] sm:text-[11px] text-cream-dim">
            {data.likes != null && data.likes > 0 && (
              <span className="flex items-center gap-0.5">
                <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
                </svg>
                {formatViews(data.likes)}
              </span>
            )}
            {data.comments != null && data.comments > 0 && (
              <span className="flex items-center gap-0.5">
                <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                {formatViews(data.comments)}
              </span>
            )}
            {cr !== null && (
              <span className={`font-medium ${cr >= 5 ? "text-green-400" : cr >= 2 ? "text-amber-400" : "text-cream-dim"}`}>
                {cr.toFixed(1)}% CR
              </span>
            )}
            <span className="ml-auto">
              <XBadge value={data.xFactor} />
            </span>
          </div>
        )}

        {/* Library: stats */}
        {isLibrary && (data.views || data.likes || data.comments) && (
          <div className="flex items-center gap-3">
            {data.views != null && data.views > 0 && (
              <div className="flex items-center gap-1">
                <svg className="w-3.5 h-3.5 text-cream-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
                <span className="text-xs font-semibold text-cream">{formatViews(data.views)}</span>
              </div>
            )}
            {data.likes != null && data.likes > 0 && (
              <div className="flex items-center gap-1">
                <svg className="w-3.5 h-3.5 text-cream-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
                </svg>
                <span className="text-xs font-semibold text-cream">{formatViews(data.likes)}</span>
              </div>
            )}
            {data.comments != null && data.comments > 0 && (
              <div className="flex items-center gap-1">
                <svg className="w-3.5 h-3.5 text-cream-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                <span className="text-xs font-semibold text-cream">{formatViews(data.comments)}</span>
              </div>
            )}
          </div>
        )}

        {/* Library: tags */}
        {isLibrary && data.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {data.tags.slice(0, 3).map((tag) => (
              <span key={tag} className="px-1.5 py-0.5 bg-surface-light text-cream-muted text-[9px] rounded">
                {tag}
              </span>
            ))}
            {data.tags.length > 3 && (
              <span className="text-[9px] text-cream-muted">+{data.tags.length - 3}</span>
            )}
          </div>
        )}

        {/* Job actions row: time (non-completed) or share+filmed (completed) */}
        {isJob && (
          <div className="flex items-center justify-between">
            {!isCompleted && (
              <span className="text-[11px] text-cream-muted">
                {timeAgo(data.createdAt, t)}
              </span>
            )}
            {isCompleted && (
              <>
                <span className="text-[11px] text-cream-muted" />
                <div className="flex items-center gap-1.5">
                  {data.shareToken && (
                    <span
                      role="button"
                      title={linkCopied ? t.share_link_copied : t.share_copy_link}
                      onClick={handleCopyShareLink}
                      className={`w-7 h-7 flex items-center justify-center rounded-lg transition-colors ${
                        linkCopied
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-surface-light text-cream-muted border border-border-subtle hover:border-cream-muted hover:text-cream"
                      }`}
                    >
                      {linkCopied ? (
                        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      ) : (
                        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                        </svg>
                      )}
                    </span>
                  )}
                  {onToggleFilmed && (
                    <span
                      role="button"
                      title={data.isFilmed ? t.my_videos_filmed : t.my_videos_not_filmed}
                      onClick={onToggleFilmed}
                      className={`w-7 h-7 flex items-center justify-center rounded-lg transition-colors ${
                        data.isFilmed
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : "bg-surface-light text-cream-muted border border-border-subtle hover:border-cream-muted hover:text-cream"
                      }`}
                    >
                      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {/* Trend: CTA Parse / Open */}
        {isTrend && (
          <div>
            {data.isParsed ? (
              <button
                onClick={(e) => { e.stopPropagation(); onClick(); }}
                className="w-full py-2 sm:py-1.5 text-[11px] font-medium text-green-400 bg-green-500/10 rounded-lg active:bg-green-500/20 sm:hover:bg-green-500/15 transition-colors"
              >
                {t.trends_open}
              </button>
            ) : (
              <button
                onClick={(e) => { e.stopPropagation(); onParse?.(e); }}
                disabled={parsingId === data.id}
                className="w-full py-2 sm:py-1.5 text-[11px] font-medium text-cream bg-cream/10 rounded-lg active:bg-cream/20 sm:hover:bg-cream/15 transition-colors disabled:opacity-50"
              >
                {parsingId === data.id ? (
                  <span className="inline-block w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                ) : (
                  t.trends_parse
                )}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
