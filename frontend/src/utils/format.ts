export function formatViews(n: number | null): string {
  if (n === null || n === undefined) return "-";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function timeAgo(
  dateStr: string | null,
  t: { trends_days_ago: string; trends_hours_ago: string },
): string {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 24) return t.trends_hours_ago.replace("{n}", String(hours));
  const days = Math.floor(hours / 24);
  return t.trends_days_ago.replace("{n}", String(days));
}

export function commentRate(
  views: number | null,
  comments: number | null,
): number | null {
  if (!views || views < 1000) return null;
  if (!comments || comments <= 0) return null;
  return (comments / views) * 100;
}
