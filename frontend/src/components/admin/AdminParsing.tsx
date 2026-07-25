import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminListParsings, adminGetParsingStats } from "../../api/client";
import type { AdminParsingItem, AdminParsingStats } from "../../types";

// ── Helpers ────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  running: "bg-blue-900/50 text-blue-300",
  completed: "bg-green-900/50 text-green-300",
  failed: "bg-red-900/50 text-red-300",
};

const STATUS_LABELS: Record<string, string> = {
  running: "В процессе",
  completed: "Готово",
  failed: "Ошибка",
};

const PLATFORM_COLORS: Record<string, string> = {
  instagram: "text-pink-400",
  youtube: "text-red-400",
  tiktok: "text-cyan-400",
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

// Expandable result detail
function ResultDetail({ result }: { result: Record<string, unknown> }) {
  const fields = [
    { key: "about_me", label: "О себе" },
    { key: "tone", label: "Тон" },
    { key: "niches", label: "Ниши" },
    { key: "interests", label: "Интересы" },
    { key: "video_format", label: "Формат видео" },
    { key: "script_cta", label: "CTA (сценарий)" },
    { key: "description_cta", label: "CTA (описание)" },
    { key: "forbidden_words", label: "Запрещённые слова" },
    { key: "content_prompt_additions", label: "Дополнения к промту" },
  ];

  return (
    <div className="px-4 py-3 bg-zinc-900/50 border-t border-zinc-800/50 space-y-3">
      {fields.map(({ key, label }) => {
        const val = result[key];
        if (val === null || val === undefined || val === "") return null;

        let display: React.ReactNode;
        if (Array.isArray(val)) {
          display = (
            <div className="flex flex-wrap gap-1.5 mt-1">
              {val.map((item, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 bg-zinc-800 text-zinc-300 rounded text-xs"
                >
                  {String(item)}
                </span>
              ))}
            </div>
          );
        } else {
          display = (
            <p className="text-zinc-300 text-xs leading-relaxed mt-0.5 whitespace-pre-wrap">
              {String(val)}
            </p>
          );
        }

        return (
          <div key={key}>
            <div className="text-[11px] text-zinc-500 uppercase tracking-wide font-medium">
              {label}
            </div>
            {display}
          </div>
        );
      })}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────

export function AdminParsing() {
  const navigate = useNavigate();

  const [stats, setStats] = useState<AdminParsingStats | null>(null);
  const [items, setItems] = useState<AdminParsingItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  // Filters
  const [statusFilter, setStatusFilter] = useState("");
  const [platformFilter, setPlatformFilter] = useState("");
  const [dateRange, setDateRange] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  // Expanded rows
  const [expandedId, setExpandedId] = useState<string | null>(null);

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
    adminGetParsingStats().then(setStats).catch(() => {});

    setLoading(true);
    adminListParsings({
      status: statusFilter || undefined,
      platform: platformFilter || undefined,
      date_range: dateRange || undefined,
      q: debouncedQuery || undefined,
      page,
      per_page: perPage,
    })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [statusFilter, platformFilter, dateRange, debouncedQuery, page]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(loadData, 10_000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadData]);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-serif font-medium text-zinc-100">
          Парсинг профилей
        </h1>
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

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
          <StatCard
            label="В процессе"
            value={stats.running}
            color={stats.running > 0 ? "text-blue-300" : "text-zinc-100"}
          />
          <StatCard
            label="Сегодня"
            value={stats.completed_today}
            color="text-green-300"
          />
          <StatCard
            label="Ошибки сегодня"
            value={stats.failed_today}
            color={stats.failed_today > 0 ? "text-red-300" : "text-zinc-100"}
          />
          <StatCard
            label="Всего завершено"
            value={stats.completed_total}
            color="text-zinc-100"
          />
          <StatCard
            label="Всего ошибок"
            value={stats.failed_total}
            color="text-zinc-100"
          />
          <StatCard
            label="Ср. длительность"
            value={formatDuration(stats.avg_duration_seconds)}
            color="text-zinc-100"
          />
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
          <option value="running">В процессе</option>
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
          value={dateRange}
          onChange={(e) => {
            setDateRange(e.target.value);
            setPage(1);
          }}
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
        >
          <option value="">Все время</option>
          <option value="today">Сегодня</option>
          <option value="week">Неделя</option>
          <option value="month">Месяц</option>
        </select>

        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Username, email, имя..."
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500 w-64 placeholder:text-zinc-600"
        />

        <span className="ml-auto text-xs text-zinc-500">{total} записей</span>
      </div>

      {/* Table */}
      {loading && items.length === 0 ? (
        <div className="text-zinc-500 text-sm py-8">Загрузка...</div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  {[
                    "Пользователь",
                    "Аккаунт",
                    "Платформа",
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
                {items.map((item) => (
                  <>
                    <tr
                      key={item.id}
                      className={`border-b border-zinc-800/50 hover:bg-zinc-800/20 cursor-pointer ${
                        item.status === "running" ? "bg-blue-950/10" : ""
                      } ${expandedId === item.id ? "bg-zinc-800/30" : ""}`}
                      onClick={() =>
                        setExpandedId(expandedId === item.id ? null : item.id)
                      }
                    >
                      {/* User */}
                      <td className="px-4 py-3 text-xs max-w-[180px]">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/admin/users/${item.user_id}`);
                          }}
                          className="truncate block text-left text-zinc-400 hover:text-zinc-100 transition-colors"
                          title={item.user_email || item.user_name || item.user_id}
                        >
                          {item.user_email || item.user_name || (
                            <span className="text-zinc-600">Аноним</span>
                          )}
                        </button>
                        {item.user_tier && (
                          <span
                            className={`inline-block mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide ${
                              TIER_COLORS[item.user_tier] ??
                              "bg-zinc-800/60 text-zinc-500"
                            }`}
                          >
                            {item.user_tier}
                          </span>
                        )}
                      </td>

                      {/* Account */}
                      <td className="px-4 py-3">
                        <span className="text-zinc-300 text-xs font-mono">
                          @{item.username}
                        </span>
                      </td>

                      {/* Platform */}
                      <td className="px-4 py-3">
                        <span
                          className={`text-xs capitalize ${
                            PLATFORM_COLORS[item.platform] ?? "text-zinc-400"
                          }`}
                        >
                          {item.platform}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3 min-w-[140px]">
                        <StatusBadge status={item.status} />
                        {item.status === "running" && (
                          <div className="w-full bg-zinc-800 rounded-full h-1.5 mt-1">
                            <div className="bg-blue-500 h-1.5 rounded-full animate-pulse w-2/3" />
                          </div>
                        )}
                        {item.status === "failed" && item.error && (
                          <p
                            className="mt-1 text-[11px] text-red-400/70 leading-tight max-w-[200px] truncate"
                            title={item.error}
                          >
                            {item.error}
                          </p>
                        )}
                      </td>

                      {/* Duration */}
                      <td className="px-4 py-3 text-zinc-500 text-xs whitespace-nowrap">
                        {formatDuration(item.duration_seconds)}
                      </td>

                      {/* Date */}
                      <td className="px-4 py-3 text-zinc-500 text-xs whitespace-nowrap">
                        {formatDate(item.created_at)}
                      </td>

                      {/* Expand icon */}
                      <td className="px-4 py-3">
                        {item.result_json && (
                          <svg
                            className={`w-4 h-4 text-zinc-500 transition-transform ${
                              expandedId === item.id ? "rotate-180" : ""
                            }`}
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M19 9l-7 7-7-7"
                            />
                          </svg>
                        )}
                      </td>
                    </tr>

                    {/* Expanded detail */}
                    {expandedId === item.id && item.result_json && (
                      <tr key={`${item.id}-detail`}>
                        <td colSpan={7}>
                          <ResultDetail result={item.result_json} />
                        </td>
                      </tr>
                    )}
                  </>
                ))}

                {items.length === 0 && (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-8 text-center text-zinc-600 text-sm"
                    >
                      Нет записей
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
                Вперед →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
