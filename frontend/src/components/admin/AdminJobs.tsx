import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  adminCancelJob,
  adminDeleteJob,
  adminGetJobStats,
  adminListJobs,
  adminRetryJob,
} from "../../api/client";
import type { AdminJob, AdminJobStats } from "../../types";

// ── Helpers ────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-green-900/50 text-green-300",
  failed: "bg-red-900/50 text-red-300",
  pending: "bg-zinc-700/50 text-zinc-400",
  downloading: "bg-blue-900/50 text-blue-300",
  extracting_audio: "bg-blue-900/50 text-blue-300",
  transcribing: "bg-indigo-900/50 text-indigo-300",
  detecting_scenes: "bg-violet-900/50 text-violet-300",
  extracting_frames: "bg-violet-900/50 text-violet-300",
  analyzing_frames: "bg-purple-900/50 text-purple-300",
  generating_summary: "bg-amber-900/50 text-amber-300",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "В очереди",
  downloading: "Скачивание",
  extracting_audio: "Аудио",
  transcribing: "Транскрипция",
  detecting_scenes: "Сцены",
  extracting_frames: "Кадры",
  analyzing_frames: "Анализ кадров",
  generating_summary: "Генерация",
  completed: "Готово",
  failed: "Ошибка",
};

const SOURCE_LABELS: Record<string, string> = {
  web: "Web",
  telegram: "Telegram",
  radar: "Radar",
};

const SOURCE_COLORS: Record<string, string> = {
  web: "text-zinc-400",
  telegram: "text-sky-400",
  radar: "text-orange-400",
};

const TIER_COLORS: Record<string, string> = {
  UNLIMITED: "bg-amber-900/40 text-amber-300",
  PRO: "bg-purple-900/40 text-purple-300",
  START: "bg-blue-900/40 text-blue-300",
  FREE: "bg-green-900/40 text-green-300",
  ANONYMOUS: "bg-zinc-800/60 text-zinc-500",
};

function formatDate(dt: string) {
  return new Date(dt).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}с`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}м ${s}с`;
}

function truncate(str: string, len: number) {
  return str.length > len ? str.slice(0, len) + "…" : str;
}

function isRunning(status: string): boolean {
  return !["completed", "failed", "pending"].includes(status);
}

// ── Sub-components ─────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "bg-yellow-900/50 text-yellow-300";
  const label = STATUS_LABELS[status] ?? status;
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}

function PlatformBadge({ platform }: { platform: string | null }) {
  if (!platform) return <span className="text-zinc-600">—</span>;
  const colors: Record<string, string> = {
    instagram: "text-pink-400",
    youtube: "text-red-400",
    tiktok: "text-cyan-400",
  };
  return (
    <span className={`text-xs ${colors[platform.toLowerCase()] ?? "text-zinc-400"}`}>
      {platform}
    </span>
  );
}

function ProgressBar({ progress }: { progress: number }) {
  const pct = Math.round(progress * 100);
  return (
    <div className="w-full bg-zinc-800 rounded-full h-1.5 mt-1">
      <div
        className="bg-blue-500 h-1.5 rounded-full transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function StatCard({
  label,
  value,
  color = "text-zinc-100",
  sub,
}: {
  label: string;
  value: string | number;
  color?: string;
  sub?: string;
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 min-w-0">
      <div className="text-xs text-zinc-500 mb-1 truncate">{label}</div>
      <div className={`text-lg font-medium ${color} tabular-nums`}>{value}</div>
      {sub && <div className="text-[11px] text-zinc-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function ConfirmDialog({
  message,
  confirmLabel,
  confirmColor = "bg-red-900/60 text-red-300 hover:bg-red-800/70",
  onConfirm,
  onCancel,
  loading,
}: {
  message: string;
  confirmLabel: string;
  confirmColor?: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-[380px]">
        <p className="text-zinc-200 text-sm mb-5">{message}</p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Отмена
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`px-4 py-2 text-sm rounded-lg transition-colors disabled:opacity-50 ${confirmColor}`}
          >
            {loading ? "..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────

export function AdminJobs() {
  const navigate = useNavigate();

  // Stats
  const [stats, setStats] = useState<AdminJobStats | null>(null);

  // List
  const [jobs, setJobs] = useState<AdminJob[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  // Filters
  const [statusFilter, setStatusFilter] = useState("");
  const [platformFilter, setPlatformFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [dateRange, setDateRange] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  // Actions
  const [deleteTarget, setDeleteTarget] = useState<AdminJob | null>(null);
  const [retryTarget, setRetryTarget] = useState<AdminJob | null>(null);
  const [cancelTarget, setCancelTarget] = useState<AdminJob | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Auto-refresh
  const [autoRefresh, setAutoRefresh] = useState(true);

  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const perPage = 50;
  const totalPages = Math.ceil(total / perPage);

  // Debounce query
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(query);
      setPage(1);
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [query]);

  const loadData = useCallback(() => {
    // Load stats
    adminGetJobStats().then(setStats).catch(() => {});

    // Load jobs
    setLoading(true);
    adminListJobs({
      status: statusFilter || undefined,
      platform: platformFilter || undefined,
      source: sourceFilter || undefined,
      date_range: dateRange || undefined,
      q: debouncedQuery || undefined,
      page,
      per_page: perPage,
    })
      .then((res) => {
        setJobs(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [statusFilter, platformFilter, sourceFilter, dateRange, debouncedQuery, page]);

  // Initial load + filter changes
  useEffect(() => {
    loadData();
  }, [loadData]);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(loadData, 10_000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadData]);

  // ── Actions ──

  async function handleDelete() {
    if (!deleteTarget) return;
    setActionLoading(true);
    try {
      await adminDeleteJob(deleteTarget.id);
      setJobs((prev) => prev.filter((j) => j.id !== deleteTarget.id));
      setTotal((t) => t - 1);
      setDeleteTarget(null);
    } finally {
      setActionLoading(false);
    }
  }

  async function handleRetry() {
    if (!retryTarget) return;
    setActionLoading(true);
    try {
      await adminRetryJob(retryTarget.id);
      setRetryTarget(null);
      loadData();
    } finally {
      setActionLoading(false);
    }
  }

  async function handleCancel() {
    if (!cancelTarget) return;
    setActionLoading(true);
    try {
      await adminCancelJob(cancelTarget.id);
      setCancelTarget(null);
      loadData();
    } finally {
      setActionLoading(false);
    }
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-serif font-medium text-zinc-100">Задачи</h1>
        <button
          onClick={() => setAutoRefresh((v) => !v)}
          className={`flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg border transition-colors ${
            autoRefresh
              ? "border-green-800 text-green-400 bg-green-950/30"
              : "border-zinc-700 text-zinc-500 bg-zinc-900"
          }`}
          title={autoRefresh ? "Автообновление включено" : "Автообновление выключено"}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              autoRefresh ? "bg-green-400 animate-pulse" : "bg-zinc-600"
            }`}
          />
          Live
        </button>
      </div>

      {/* Stats Dashboard */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <StatCard
            label="В очереди"
            value={stats.queued}
            color={stats.queued > 10 ? "text-yellow-300" : "text-zinc-100"}
          />
          <StatCard
            label="Выполняется"
            value={stats.running}
            color={stats.running > 0 ? "text-blue-300" : "text-zinc-100"}
          />
          <StatCard
            label="Сегодня"
            value={stats.completed_today}
            color="text-green-300"
            sub={`За неделю: ${stats.completed_week}`}
          />
          <StatCard
            label="Ошибки сегодня"
            value={stats.failed_today}
            color={stats.failed_today > 0 ? "text-red-300" : "text-zinc-100"}
            sub={`Error rate: ${stats.error_rate_pct}%`}
          />
        </div>
      )}

      {/* Secondary stats */}
      {stats && (
        <div className="flex items-center gap-6 mb-4 text-xs text-zinc-500">
          <span>
            Ср. длительность:{" "}
            <span className="text-zinc-300">{formatDuration(stats.avg_duration_seconds)}</span>
          </span>
          <span>
            Всего завершено:{" "}
            <span className="text-zinc-300">{stats.completed_total.toLocaleString()}</span>
          </span>
          <span>
            Всего ошибок:{" "}
            <span className="text-zinc-300">{stats.failed_total.toLocaleString()}</span>
          </span>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 pb-4 border-b border-zinc-800 flex-wrap">
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
        >
          <option value="">Все статусы</option>
          <option value="pending">В очереди</option>
          <option value="running">Выполняется</option>
          <option value="completed">Завершено</option>
          <option value="failed">Ошибка</option>
        </select>

        <select
          value={platformFilter}
          onChange={(e) => {
            setPlatformFilter(e.target.value);
            setPage(1);
          }}
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
        >
          <option value="">Все платформы</option>
          <option value="instagram">Instagram</option>
          <option value="youtube">YouTube</option>
          <option value="tiktok">TikTok</option>
        </select>

        <select
          value={sourceFilter}
          onChange={(e) => {
            setSourceFilter(e.target.value);
            setPage(1);
          }}
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
        >
          <option value="">Все источники</option>
          <option value="web">Web</option>
          <option value="telegram">Telegram</option>
          <option value="radar">Radar</option>
        </select>

        <select
          value={dateRange}
          onChange={(e) => {
            setDateRange(e.target.value);
            setPage(1);
          }}
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
        >
          <option value="">Всё время</option>
          <option value="today">Сегодня</option>
          <option value="week">Неделя</option>
          <option value="month">Месяц</option>
        </select>

        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="URL, email, имя..."
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500 w-64 placeholder:text-zinc-600"
        />

        <span className="ml-auto text-xs text-zinc-500">{total} задач</span>
      </div>

      {/* Table */}
      {loading && jobs.length === 0 ? (
        <div className="text-zinc-500 text-sm py-8">Загрузка...</div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  {[
                    "Пользователь",
                    "URL / Название",
                    "Платформа",
                    "Источник",
                    "Статус",
                    "Длительность",
                    "Дата",
                    "",
                  ].map((h) => (
                    <th
                      key={h}
                      className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr
                    key={job.id}
                    className={`border-b border-zinc-800/50 hover:bg-zinc-800/20 ${
                      isRunning(job.status) ? "bg-blue-950/10" : ""
                    }`}
                  >
                    {/* User */}
                    <td className="px-4 py-3 text-xs max-w-[180px]">
                      <button
                        onClick={() => navigate(`/admin/users/${job.user_id}`)}
                        className="truncate block text-left text-zinc-400 hover:text-zinc-100 transition-colors"
                        title={job.user_email || job.user_name || job.user_id}
                      >
                        {job.user_email || job.user_name || (
                          <span className="text-zinc-600">Аноним</span>
                        )}
                      </button>
                      {job.user_tier && (
                        <span
                          className={`inline-block mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide ${
                            TIER_COLORS[job.user_tier] ?? "bg-zinc-800/60 text-zinc-500"
                          }`}
                        >
                          {job.user_tier}
                        </span>
                      )}
                    </td>

                    {/* URL / Title */}
                    <td className="px-4 py-3 max-w-[260px]">
                      {job.video_title ? (
                        <span
                          className="text-zinc-300 text-xs truncate block"
                          title={job.video_title}
                        >
                          {truncate(job.video_title, 50)}
                        </span>
                      ) : (
                        <span
                          className="text-zinc-400 font-mono text-xs truncate block"
                          title={job.url}
                        >
                          {truncate(job.url, 45)}
                        </span>
                      )}
                    </td>

                    {/* Platform */}
                    <td className="px-4 py-3">
                      <PlatformBadge platform={job.video_platform} />
                    </td>

                    {/* Source */}
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs ${
                          SOURCE_COLORS[job.source ?? "web"] ?? "text-zinc-400"
                        }`}
                      >
                        {SOURCE_LABELS[job.source ?? "web"] ?? job.source ?? "web"}
                      </span>
                    </td>

                    {/* Status */}
                    <td className="px-4 py-3 min-w-[140px]">
                      <StatusBadge status={job.status} />
                      {isRunning(job.status) && <ProgressBar progress={job.progress} />}
                      {job.progress_message && isRunning(job.status) && (
                        <p className="mt-0.5 text-[10px] text-zinc-500 truncate max-w-[140px]">
                          {job.progress_message}
                        </p>
                      )}
                      {job.status === "failed" && job.error && (
                        <p
                          className="mt-1 text-[11px] text-red-400/70 leading-tight max-w-[200px] truncate"
                          title={job.error}
                        >
                          {job.error}
                        </p>
                      )}
                      {job.retry_count > 0 && (
                        <span className="text-[10px] text-zinc-600 ml-1">
                          retry: {job.retry_count}
                        </span>
                      )}
                    </td>

                    {/* Duration */}
                    <td className="px-4 py-3 text-zinc-500 text-xs whitespace-nowrap">
                      {formatDuration(job.duration_seconds)}
                    </td>

                    {/* Date */}
                    <td className="px-4 py-3 text-zinc-500 text-xs whitespace-nowrap">
                      {formatDate(job.created_at)}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {job.status === "completed" && (
                          <button
                            onClick={() => navigate(`/admin/library/${job.id}`)}
                            className="text-xs text-zinc-500 hover:text-zinc-200 transition-colors"
                            title="Открыть результат"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                              <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                            </svg>
                          </button>
                        )}
                        {job.share_token && (
                          <a
                            href={`/share/${job.share_token}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-zinc-500 hover:text-zinc-200 transition-colors"
                            title="Share-страница"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                            </svg>
                          </a>
                        )}
                        {job.status === "failed" && (
                          <button
                            onClick={() => setRetryTarget(job)}
                            className="text-xs text-zinc-500 hover:text-amber-300 transition-colors"
                            title="Повторить"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                          </button>
                        )}
                        {(isRunning(job.status) || job.status === "pending") && (
                          <button
                            onClick={() => setCancelTarget(job)}
                            className="text-xs text-zinc-500 hover:text-orange-400 transition-colors"
                            title="Отменить"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          </button>
                        )}
                        <button
                          onClick={() => setDeleteTarget(job)}
                          className="text-xs text-zinc-600 hover:text-red-400 transition-colors"
                          title="Удалить"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}

                {jobs.length === 0 && (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-4 py-8 text-center text-zinc-600 text-sm"
                    >
                      Нет задач
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center gap-4 mt-4 pt-4 border-t border-zinc-800">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-40 transition-colors"
              >
                ← Назад
              </button>
              <span className="text-xs text-zinc-500">
                Страница {page} из {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-40 transition-colors"
              >
                Вперёд →
              </button>
            </div>
          )}
        </>
      )}

      {/* Delete dialog */}
      {deleteTarget && (
        <ConfirmDialog
          message={`Удалить задачу?\n${truncate(deleteTarget.url, 60)}`}
          confirmLabel="Удалить"
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          loading={actionLoading}
        />
      )}

      {/* Retry dialog */}
      {retryTarget && (
        <ConfirmDialog
          message={`Повторить задачу?\n${truncate(retryTarget.url, 60)}\n\nОшибка: ${retryTarget.error ?? "—"}`}
          confirmLabel="Повторить"
          confirmColor="bg-amber-900/60 text-amber-300 hover:bg-amber-800/70"
          onConfirm={handleRetry}
          onCancel={() => setRetryTarget(null)}
          loading={actionLoading}
        />
      )}

      {/* Cancel dialog */}
      {cancelTarget && (
        <ConfirmDialog
          message={`Отменить задачу?\n${truncate(cancelTarget.url, 60)}`}
          confirmLabel="Отменить задачу"
          confirmColor="bg-orange-900/60 text-orange-300 hover:bg-orange-800/70"
          onConfirm={handleCancel}
          onCancel={() => setCancelTarget(null)}
          loading={actionLoading}
        />
      )}
    </div>
  );
}
