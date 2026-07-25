import { useMonitoringData } from "./useMonitoringData";
import { StatsBar } from "./StatsBar";
import { MonitoringBoard } from "./MonitoringBoard";
import { ActivityFeed } from "./ActivityFeed";
import type { WsStatus } from "./useMonitoringData";

function ConnectionBadge({ status }: { status: WsStatus }) {
  const styles: Record<WsStatus, { dot: string; label: string }> = {
    connected: { dot: "bg-emerald-500", label: "Live" },
    connecting: { dot: "bg-amber-500 animate-pulse", label: "Connecting..." },
    disconnected: { dot: "bg-zinc-600", label: "Offline" },
  };
  const s = styles[status];
  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${s.dot}`} />
      <span className="text-xs text-zinc-500">{s.label}</span>
    </div>
  );
}

export function AdminTrendWatching() {
  const { stats, pipeline, activity, sparklines, wsStatus, loading, refetch } = useMonitoringData();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-serif font-medium text-zinc-100">Trend Watching</h1>
        <div className="flex items-center gap-3">
          <ConnectionBadge status={wsStatus} />
          <button
            onClick={refetch}
            className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700 transition-colors"
          >
            Обновить
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <StatsBar stats={stats} sparklines={sparklines} />

      {/* Main area: Kanban + Activity feed */}
      {loading ? (
        <div className="flex gap-4">
          <div className="flex-1 h-96 bg-zinc-900/50 rounded-xl animate-pulse" />
          <div className="w-80 h-96 bg-zinc-900/50 rounded-xl animate-pulse hidden lg:block" />
        </div>
      ) : (
        <div className="flex gap-4">
          {/* Kanban board */}
          <div className="flex-1 min-w-0">
            <MonitoringBoard pipeline={pipeline} stats={stats} />
          </div>

          {/* Activity feed (desktop sidebar) */}
          <div className="hidden lg:block w-80 shrink-0">
            <ActivityFeed events={activity} />
          </div>
        </div>
      )}

      {/* Activity feed (mobile, below board) */}
      <div className="lg:hidden">
        <ActivityFeed events={activity} />
      </div>

      {/* Cost Dashboard + Priority (compact) */}
      {stats && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Cost Dashboard */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <div className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Расходы сегодня</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-[10px] text-zinc-600 uppercase">Apify runs</div>
                <div className="text-lg font-mono text-zinc-200">{stats.apify_runs_today ?? 0}</div>
              </div>
              <div>
                <div className="text-[10px] text-zinc-600 uppercase">Apify $</div>
                <div className="text-lg font-mono text-zinc-200">
                  {stats.apify_used_usd != null ? `$${stats.apify_used_usd.toFixed(2)}` : "—"}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-zinc-600 uppercase">AI calls</div>
                <div className="text-lg font-mono text-zinc-200">{stats.ai_calls_today ?? 0}</div>
              </div>
              <div>
                <div className="text-[10px] text-zinc-600 uppercase">AI tokens / $</div>
                <div className="text-lg font-mono text-zinc-200">
                  {(stats.ai_tokens_today ?? 0) > 0
                    ? `${((stats.ai_tokens_today ?? 0) / 1000).toFixed(0)}K`
                    : "0"
                  }
                  <span className="text-xs text-zinc-500 ml-1">
                    ${(stats.ai_cost_estimate_usd ?? 0).toFixed(3)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Priority — compact */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <div className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Приоритеты</div>
            <div className="flex items-center gap-4">
              {[
                { label: "high", count: stats.profiles_by_priority.high, dot: "bg-red-500" },
                { label: "normal", count: stats.profiles_by_priority.normal, dot: "bg-blue-500" },
                { label: "cold", count: stats.profiles_by_priority.cold, dot: "bg-zinc-600" },
              ].map((p) => (
                <div key={p.label} className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${p.dot}`} />
                  <span className="text-sm font-mono text-zinc-300">{p.count}</span>
                  <span className="text-xs text-zinc-600">{p.label}</span>
                </div>
              ))}
            </div>
            {/* Mini bar */}
            <div className="mt-3 flex h-2 rounded-full overflow-hidden bg-zinc-800">
              {[
                { count: stats.profiles_by_priority.high, color: "bg-red-500" },
                { count: stats.profiles_by_priority.normal, color: "bg-blue-500" },
                { count: stats.profiles_by_priority.cold, color: "bg-zinc-600" },
              ].map((p, i) => {
                const pct = stats.total_profiles > 0 ? (p.count / stats.total_profiles) * 100 : 0;
                return (
                  <div
                    key={i}
                    className={`${p.color} transition-all duration-700`}
                    style={{ width: `${pct}%` }}
                  />
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Timing info */}
      {stats?.last_check_run_at && (
        <div className="text-xs text-zinc-600 text-right">
          Последний цикл: {new Date(stats.last_check_run_at).toLocaleString("ru-RU")}
          {stats.next_check_run_at && (
            <> · Следующий: {new Date(stats.next_check_run_at).toLocaleString("ru-RU")}</>
          )}
          {stats.scrape_errors_24h > 0 && (
            <span className="text-red-500 ml-2">{stats.scrape_errors_24h} ошибок за 24ч</span>
          )}
        </div>
      )}
    </div>
  );
}
