import type { PipelineProfile } from "../../../types";
import { PRIORITY_STYLES, PLATFORM_ICONS } from "./constants";

function formatDuration(minutes: number | null | undefined): string {
  if (minutes == null) return "new";
  if (minutes < 60) return `${minutes}м`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}ч ${m}м` : `${h}ч`;
}

function formatFollowers(n: number | null): string {
  if (n == null) return "";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

function formatViews(n: number | null | undefined): string {
  if (n == null) return "";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

export function ProfileCard({
  profile,
  status,
}: {
  profile: PipelineProfile;
  status: "queued" | "scraping" | "analyzing" | "completed" | "failed";
}) {
  const isActive = status === "scraping" || status === "analyzing";
  const pulseClass = status === "scraping"
    ? "shadow-blue-500/20 shadow-lg"
    : status === "analyzing"
      ? "shadow-purple-500/20 shadow-lg"
      : "";

  return (
    <div
      className={`
        bg-zinc-900/80 border border-zinc-800 rounded-lg p-3 text-xs
        transition-all duration-300
        ${isActive ? `animate-pulse ${pulseClass}` : ""}
        ${status === "completed" ? "border-emerald-800/40" : ""}
        ${status === "failed" ? "border-red-800/40" : ""}
      `}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
          {PLATFORM_ICONS[profile.platform] || profile.platform}
        </span>
        <span className="font-medium text-zinc-200 truncate">@{profile.username}</span>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {profile.followers_count != null && (
          <span className="text-zinc-500">{formatFollowers(profile.followers_count)}</span>
        )}
        {profile.niche && (
          <span className="px-1.5 py-0.5 rounded bg-purple-900/40 text-purple-300 text-[10px]">
            {profile.niche}
          </span>
        )}
        <span className={`px-1.5 py-0.5 rounded text-[10px] ${PRIORITY_STYLES[profile.check_priority] || PRIORITY_STYLES.normal}`}>
          {profile.check_priority}
        </span>
      </div>

      {/* Queue: countdown timer */}
      {status === "queued" && (
        <div className="mt-1.5">
          {profile.stale_since_minutes == null ? (
            <span className="text-emerald-500/80 text-[10px] font-medium">Первая проверка</span>
          ) : profile.stale_since_minutes > 0 ? (
            <span className="text-red-400/80 text-[10px]">
              Просрочен {formatDuration(profile.stale_since_minutes)}
            </span>
          ) : (
            <span className="text-zinc-600 text-[10px]">
              Через {formatDuration(-profile.stale_since_minutes)}
            </span>
          )}
        </div>
      )}

      {/* Completed: trending count + reel thumbnails */}
      {status === "completed" && profile.trending_count > 0 && (
        <div className="mt-1.5">
          <div className="text-amber-400 text-[10px] mb-1">
            {profile.trending_count} trending
          </div>
          {profile.trending_reels && profile.trending_reels.length > 0 && (
            <div className="flex gap-1">
              {profile.trending_reels.map((reel, i) => (
                <a
                  key={i}
                  href={reel.url || "#"}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="relative group shrink-0"
                  title={reel.caption || ""}
                >
                  {reel.thumbnail_url ? (
                    <img
                      src={reel.thumbnail_url}
                      alt=""
                      className="w-10 h-10 rounded object-cover border border-zinc-700 group-hover:border-amber-500/50 transition-colors"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded bg-zinc-800 border border-zinc-700 flex items-center justify-center text-zinc-600 text-[8px]">
                      reel
                    </div>
                  )}
                  {/* X-factor overlay */}
                  {reel.x_factor != null && (
                    <span className="absolute -top-1 -right-1 bg-amber-500 text-black text-[7px] font-bold px-1 rounded-full leading-tight">
                      x{reel.x_factor}
                    </span>
                  )}
                  {/* Views overlay */}
                  {reel.views != null && (
                    <span className="absolute bottom-0 left-0 right-0 bg-black/70 text-zinc-300 text-[7px] text-center rounded-b leading-tight py-px">
                      {formatViews(reel.views)}
                    </span>
                  )}
                </a>
              ))}
            </div>
          )}
        </div>
      )}

      {status === "failed" && profile.error && (
        <div className="mt-1.5 text-red-400 truncate" title={profile.error}>
          {profile.error}
        </div>
      )}
    </div>
  );
}
