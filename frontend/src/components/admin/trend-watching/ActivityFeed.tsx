import type { TrendWatchingActivityEvent } from "../../../types";
import { EVENT_STYLES } from "./constants";

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

function EventRow({ event }: { event: TrendWatchingActivityEvent }) {
  const style = EVENT_STYLES[event.type] || EVENT_STYLES.profile_status;
  const details = event.details || {};

  let description = event.type;
  if (event.type === "check_complete") {
    const reels = (details.new_reels as number) || 0;
    const trending = (details.trending_count as number) || 0;
    description = `${reels} new, ${trending} trending`;
  } else if (event.type === "trend_found") {
    const xf = details.x_factor as number;
    description = `x${xf || "?"} trend`;
  } else if (event.type === "error") {
    description = (details.error as string) || "error";
  } else if (event.type === "notification_sent" || event.type === "notifications_sent") {
    const total = (details.total_sent as number) || 0;
    description = `${total} sent`;
  } else if (event.type === "batch_start") {
    const count = (details.profile_count as number) || (details as Record<string, unknown>).profile_count || 0;
    description = `batch ${count} profiles`;
  }

  return (
    <div className="flex items-start gap-2 py-1.5 px-2 rounded-lg hover:bg-zinc-800/50 transition-colors text-xs">
      <span className="text-zinc-600 font-mono shrink-0 w-16">{formatTime(event.timestamp)}</span>
      <span className={`shrink-0 w-3 text-center ${style.color}`}>{style.icon}</span>
      <span className="text-zinc-400 truncate">
        {event.profile_username !== "radar" && (
          <span className="text-zinc-300">@{event.profile_username}</span>
        )}
        {event.profile_username !== "radar" && " "}
        <span className="text-zinc-500">{description}</span>
      </span>
    </div>
  );
}

export function ActivityFeed({ events }: { events: TrendWatchingActivityEvent[] }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl flex flex-col h-full">
      <div className="px-3 py-2.5 border-b border-zinc-800 flex items-center justify-between">
        <span className="text-xs font-medium text-zinc-300">Activity</span>
        <span className="text-xs font-mono text-zinc-600">{events.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto max-h-[60vh] py-1">
        {events.length === 0 ? (
          <div className="text-center text-zinc-600 text-xs py-8">Нет событий</div>
        ) : (
          events.map((e, i) => <EventRow key={`${e.timestamp}-${e.type}-${e.profile_username}-${i}`} event={e} />)
        )}
      </div>
    </div>
  );
}
