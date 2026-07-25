import type { TrendWatchingPipeline, TrendWatchingStats } from "../../../types";
import { COLUMNS } from "./constants";
import { MonitoringColumn } from "./MonitoringColumn";

export function MonitoringBoard({
  pipeline,
  stats,
}: {
  pipeline: TrendWatchingPipeline | null;
  stats: TrendWatchingStats | null;
}) {
  if (!pipeline) {
    return (
      <div className="flex gap-3 overflow-x-auto pb-4 -mx-4 px-4 lg:mx-0 lg:px-0">
        {COLUMNS.map((col) => (
          <div
            key={col.id}
            className={`min-w-[220px] w-[220px] shrink-0 bg-zinc-900/50 border border-zinc-800 rounded-xl ${col.border} border-t-2 h-64 animate-pulse`}
          />
        ))}
      </div>
    );
  }

  const totals: Record<string, number | undefined> = {
    queued: stats?.queue_size,
  };

  return (
    <div className="flex gap-3 overflow-x-auto pb-4 -mx-4 px-4 lg:mx-0 lg:px-0">
      {COLUMNS.map((col) => (
        <MonitoringColumn
          key={col.id}
          id={col.id}
          label={col.label}
          border={col.border}
          color={col.color}
          pulse={"pulse" in col ? col.pulse : undefined}
          profiles={pipeline[col.id]}
          total={totals[col.id]}
        />
      ))}
    </div>
  );
}
