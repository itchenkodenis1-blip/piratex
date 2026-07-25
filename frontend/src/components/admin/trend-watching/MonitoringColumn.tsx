import type { PipelineProfile } from "../../../types";
import type { ColumnId } from "./constants";
import { ProfileCard } from "./ProfileCard";

export function MonitoringColumn({
  id,
  label,
  border,
  color,
  pulse,
  profiles,
  total,
}: {
  id: ColumnId;
  label: string;
  border: string;
  color: string;
  pulse?: boolean;
  profiles: PipelineProfile[];
  total?: number;
}) {
  const count = total != null && total > profiles.length ? total : profiles.length;

  return (
    <div className={`min-w-[220px] w-[220px] shrink-0 bg-zinc-900/50 border border-zinc-800 rounded-xl ${border} border-t-2`}>
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          {pulse && profiles.length > 0 && (
            <span className="relative flex h-2 w-2">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                id === "scraping" ? "bg-blue-400" : "bg-purple-400"
              }`} />
              <span className={`relative inline-flex rounded-full h-2 w-2 ${
                id === "scraping" ? "bg-blue-500" : "bg-purple-500"
              }`} />
            </span>
          )}
          <span className={`text-xs font-medium ${color}`}>{label}</span>
        </div>
        <span className="text-xs font-mono text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded">
          {count}
        </span>
      </div>

      <div className="p-2 space-y-2 max-h-[60vh] overflow-y-auto">
        {profiles.length === 0 ? (
          <div className="text-center text-zinc-600 text-xs py-4">Пусто</div>
        ) : (
          profiles.map((p, i) => (
            <ProfileCard key={p.profile_id || `${p.username}-${i}`} profile={p} status={id} />
          ))
        )}
      </div>
    </div>
  );
}
