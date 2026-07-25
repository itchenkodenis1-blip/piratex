export const COLUMNS = [
  { id: "queued", label: "Очередь", color: "text-amber-400", border: "border-t-amber-500", bg: "bg-amber-500/10" },
  { id: "scraping", label: "Скрейпинг", color: "text-blue-400", border: "border-t-blue-500", bg: "bg-blue-500/10", pulse: true },
  { id: "analyzing", label: "Анализ", color: "text-purple-400", border: "border-t-purple-500", bg: "bg-purple-500/10", pulse: true },
  { id: "completed", label: "Готово", color: "text-emerald-400", border: "border-t-emerald-500", bg: "bg-emerald-500/10" },
  { id: "failed", label: "Ошибки", color: "text-red-400", border: "border-t-red-500", bg: "bg-red-500/10" },
] as const;

export type ColumnId = (typeof COLUMNS)[number]["id"];

export const EVENT_STYLES: Record<string, { icon: string; color: string }> = {
  check_complete: { icon: "\u2713", color: "text-emerald-400" },
  trend_found: { icon: "\u2191", color: "text-amber-400" },
  notification_sent: { icon: "\u25B6", color: "text-blue-400" },
  error: { icon: "\u2717", color: "text-red-400" },
  batch_start: { icon: "\u25CB", color: "text-cyan-400" },
  notifications_sent: { icon: "\u25B6", color: "text-blue-400" },
  profile_status: { icon: "\u25CF", color: "text-zinc-400" },
};

export const PRIORITY_STYLES: Record<string, string> = {
  high: "bg-red-900/50 text-red-300",
  normal: "bg-blue-900/50 text-blue-300",
  cold: "bg-zinc-800 text-zinc-500",
  new: "bg-amber-900/50 text-amber-300",
};

export const PLATFORM_ICONS: Record<string, string> = {
  instagram: "IG",
  tiktok: "TT",
  youtube: "YT",
};
