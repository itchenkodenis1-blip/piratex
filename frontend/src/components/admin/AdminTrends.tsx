import { useEffect, useState } from "react";
import {
  adminBlockProfile,
  adminDeleteTrackedProfile,
  adminListTrackedProfiles,
  adminToggleTrackedProfile,
  adminUnblockProfile,
} from "../../api/client";
import type { AdminTrackedProfile, AdminTrackedProfileStats } from "../../types";

function formatNumber(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toString();
}

function timeAgo(dt: string | null): string {
  if (!dt) return "никогда";
  const diff = Date.now() - new Date(dt).getTime();
  const hours = Math.floor(diff / 3_600_000);
  if (hours < 1) return "< 1ч назад";
  if (hours < 24) return `${hours}ч назад`;
  const days = Math.floor(hours / 24);
  return `${days}д назад`;
}

function formatDate(dt: string): string {
  const d = new Date(dt);
  const day = d.getDate().toString().padStart(2, "0");
  const mon = (d.getMonth() + 1).toString().padStart(2, "0");
  const year = d.getFullYear().toString().slice(2);
  return `${day}.${mon}.${year}`;
}

interface ConfirmDialogProps {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
  confirmLabel?: string;
  loadingLabel?: string;
}

function ConfirmDialog({ message, onConfirm, onCancel, loading, confirmLabel = "Удалить", loadingLabel = "Удаление..." }: ConfirmDialogProps) {
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
            className="px-4 py-2 text-sm bg-red-900/60 text-red-300 hover:bg-red-800/70 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading ? loadingLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

interface BlockDialogProps {
  profile: AdminTrackedProfile;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
  loading?: boolean;
}

function BlockDialog({ profile, onConfirm, onCancel, loading }: BlockDialogProps) {
  const [reason, setReason] = useState("");
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-[420px]">
        <h3 className="text-zinc-100 font-medium mb-2">Заблокировать @{profile.username}</h3>
        <p className="text-zinc-400 text-sm mb-4">
          Автор будет скрыт из трендов, парсинг остановлен, никто не сможет его добавить.
        </p>
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Причина блокировки (необязательно)"
          className="w-full bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-2 mb-4 focus:outline-none focus:border-zinc-500"
        />
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Отмена
          </button>
          <button
            onClick={() => onConfirm(reason)}
            disabled={loading}
            className="px-4 py-2 text-sm bg-red-900/60 text-red-300 hover:bg-red-800/70 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading ? "Блокировка..." : "Заблокировать"}
          </button>
        </div>
      </div>
    </div>
  );
}

const SOURCE_OPTIONS = [
  { value: "", label: "Все источники" },
  { value: "user", label: "Добавлены пользователями" },
  { value: "auto", label: "Авто (парсер)" },
];

const ACTIVE_OPTIONS = [
  { value: "", label: "Все статусы" },
  { value: "active", label: "Активные" },
  { value: "inactive", label: "Неактивные" },
];

const BLOCKED_OPTIONS = [
  { value: "", label: "Все" },
  { value: "blocked", label: "Заблокированные" },
  { value: "not_blocked", label: "Не заблокированные" },
];

export function AdminTrends() {
  const [profiles, setProfiles] = useState<AdminTrackedProfile[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<AdminTrackedProfileStats | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [blockedFilter, setBlockedFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminTrackedProfile | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [blockTarget, setBlockTarget] = useState<AdminTrackedProfile | null>(null);
  const [blocking, setBlocking] = useState(false);

  const perPage = 50;
  const totalPages = Math.ceil(total / perPage);

  function load() {
    setLoading(true);
    adminListTrackedProfiles({
      q: search || undefined,
      source: sourceFilter || undefined,
      active: activeFilter || undefined,
      blocked: blockedFilter || undefined,
      page,
      per_page: perPage,
    })
      .then((res) => {
        setProfiles(res.items);
        setTotal(res.total);
        if (res.stats) setStats(res.stats);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, [sourceFilter, activeFilter, blockedFilter, page]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (page === 1) {
      load();
    } else {
      setPage(1);
    }
  }

  async function handleToggle(profile: AdminTrackedProfile) {
    setToggling(profile.id);
    try {
      const res = await adminToggleTrackedProfile(profile.id);
      setProfiles((prev) =>
        prev.map((p) => (p.id === profile.id ? { ...p, is_active: res.is_active } : p))
      );
    } finally {
      setToggling(null);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await adminDeleteTrackedProfile(deleteTarget.id);
      setProfiles((prev) => prev.filter((p) => p.id !== deleteTarget.id));
      setTotal((t) => t - 1);
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  async function handleBlock(reason: string) {
    if (!blockTarget) return;
    setBlocking(true);
    try {
      await adminBlockProfile(blockTarget.id, reason);
      setProfiles((prev) =>
        prev.map((p) =>
          p.id === blockTarget.id
            ? { ...p, is_blocked: true, is_active: false, blocked_reason: reason || null, blocked_at: new Date().toISOString() }
            : p
        )
      );
      setBlockTarget(null);
    } finally {
      setBlocking(false);
    }
  }

  async function handleUnblock(profile: AdminTrackedProfile) {
    setToggling(profile.id);
    try {
      await adminUnblockProfile(profile.id);
      setProfiles((prev) =>
        prev.map((p) =>
          p.id === profile.id
            ? { ...p, is_blocked: false, is_active: true, blocked_reason: null, blocked_at: null }
            : p
        )
      );
    } finally {
      setToggling(null);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-serif font-medium text-zinc-100 mb-6">Авторы — Отслеживаемые профили</h1>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-5 gap-3 mb-5">
          {[
            { label: "Всего", value: stats.total, color: "text-zinc-100" },
            { label: "Сегодня", value: stats.today, color: stats.today > 0 ? "text-green-400" : "text-zinc-400" },
            { label: "Вчера", value: stats.yesterday, color: stats.yesterday > 0 ? "text-blue-400" : "text-zinc-400" },
            { label: "За неделю", value: stats.week, color: stats.week > 0 ? "text-orange-400" : "text-zinc-400" },
            { label: "За месяц", value: stats.month, color: stats.month > 0 ? "text-purple-400" : "text-zinc-400" },
          ].map((s) => (
            <div key={s.label} className="bg-zinc-900/60 border border-zinc-800 rounded-lg px-4 py-3">
              <div className="text-xs text-zinc-500 mb-1">{s.label}</div>
              <div className={`text-xl font-medium ${s.color}`}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4 mb-4 pb-4 border-b border-zinc-800">
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по username..."
            className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 w-[200px] focus:outline-none focus:border-zinc-500"
          />
          <button
            type="submit"
            className="text-sm px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg transition-colors"
          >
            Найти
          </button>
        </form>

        <select
          value={sourceFilter}
          onChange={(e) => { setSourceFilter(e.target.value); setPage(1); }}
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
        >
          {SOURCE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <select
          value={activeFilter}
          onChange={(e) => { setActiveFilter(e.target.value); setPage(1); }}
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
        >
          {ACTIVE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <select
          value={blockedFilter}
          onChange={(e) => { setBlockedFilter(e.target.value); setPage(1); }}
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
        >
          {BLOCKED_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <span className="ml-auto text-xs text-zinc-500">
          {total} авторов
        </span>
      </div>

      {loading ? (
        <div className="text-zinc-500 text-sm py-8">Загрузка...</div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  {["Автор", "Платформа", "Ниша", "Подписчики", "Медиана", "Рилсов", "Трендовых", "Пользователей", "Приоритет", "Проверен", "Добавлен", "Статус", "Модерация", ""].map((h) => (
                    <th key={h} className="text-left px-3 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {profiles.map((p) => (
                  <tr
                    key={p.id}
                    className={`border-b border-zinc-800/50 hover:bg-zinc-800/20 ${
                      p.is_blocked ? "bg-red-950/20" : !p.is_active ? "opacity-50" : ""
                    }`}
                  >
                    <td className="px-3 py-3 text-zinc-200 max-w-[180px]">
                      <div className={`truncate font-medium ${p.is_blocked ? "line-through text-red-400/70" : ""}`}>
                        @{p.username}
                      </div>
                      {p.display_name && p.display_name !== p.username && (
                        <div className="text-xs text-zinc-500 truncate">{p.display_name}</div>
                      )}
                      {p.is_blocked && p.blocked_reason && (
                        <div className="text-xs text-red-400/60 truncate" title={p.blocked_reason}>
                          {p.blocked_reason}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-3 text-zinc-400 text-xs">
                      {p.platform === "instagram" ? "IG" : p.platform === "youtube" ? "YT" : p.platform}
                    </td>
                    <td className="px-3 py-3 text-zinc-400 text-xs max-w-[120px]">
                      <span className="truncate block">{p.niche || "—"}</span>
                    </td>
                    <td className="px-3 py-3 text-zinc-400 text-xs">{formatNumber(p.followers_count)}</td>
                    <td className="px-3 py-3 text-zinc-400 text-xs">{formatNumber(p.median_views)}</td>
                    <td className="px-3 py-3 text-zinc-400 text-xs text-center">{p.total_reels}</td>
                    <td className="px-3 py-3 text-xs text-center">
                      {p.trending_reels_count > 0 ? (
                        <span className="text-orange-400 font-medium">{p.trending_reels_count}</span>
                      ) : (
                        <span className="text-zinc-600">0</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-xs text-center">
                      {p.tracking_users_count > 0 ? (
                        <span className="text-blue-400">{p.tracking_users_count}</span>
                      ) : (
                        <span className="text-zinc-600 italic">авто</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-xs">
                      <span className={
                        p.check_priority === "high" ? "text-orange-400" :
                        p.check_priority === "cold" ? "text-zinc-600" :
                        "text-zinc-400"
                      }>
                        {p.check_priority}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-zinc-500 text-xs whitespace-nowrap">
                      {timeAgo(p.last_checked_at)}
                    </td>
                    <td className="px-3 py-3 text-zinc-500 text-xs whitespace-nowrap" title={new Date(p.created_at).toLocaleString()}>
                      {formatDate(p.created_at)}
                    </td>
                    <td className="px-3 py-3">
                      <button
                        onClick={() => handleToggle(p)}
                        disabled={toggling === p.id || p.is_blocked}
                        className={`text-xs px-2 py-1 rounded transition-colors disabled:opacity-50 ${
                          p.is_active
                            ? "bg-green-900/40 text-green-400 hover:bg-green-900/60"
                            : "bg-zinc-800 text-zinc-500 hover:bg-zinc-700"
                        }`}
                      >
                        {p.is_active ? "Активен" : "Выключен"}
                      </button>
                    </td>
                    <td className="px-3 py-3">
                      {p.is_blocked ? (
                        <button
                          onClick={() => handleUnblock(p)}
                          disabled={toggling === p.id}
                          className="text-xs px-2 py-1 rounded bg-red-900/40 text-red-400 hover:bg-red-900/60 transition-colors disabled:opacity-50"
                        >
                          Разблокировать
                        </button>
                      ) : (
                        <button
                          onClick={() => setBlockTarget(p)}
                          className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-400 hover:bg-red-900/40 hover:text-red-400 transition-colors"
                        >
                          Заблокировать
                        </button>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <button
                        onClick={() => setDeleteTarget(p)}
                        className="text-xs text-zinc-600 hover:text-red-400 transition-colors"
                        title="Удалить автора"
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
                {profiles.length === 0 && (
                  <tr>
                    <td colSpan={14} className="px-3 py-8 text-center text-zinc-500 text-sm">
                      Нет отслеживаемых авторов
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

      {deleteTarget && (
        <ConfirmDialog
          message={`Удалить автора @${deleteTarget.username}? Все его рилсы и связи с пользователями будут удалены безвозвратно.`}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          loading={deleting}
        />
      )}

      {blockTarget && (
        <BlockDialog
          profile={blockTarget}
          onConfirm={handleBlock}
          onCancel={() => setBlockTarget(null)}
          loading={blocking}
        />
      )}
    </div>
  );
}
