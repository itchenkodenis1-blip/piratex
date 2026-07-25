import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminDeleteUser, adminListUsers, adminUpdateUserTier } from "../../api/client";
import type { AdminUser } from "../../types";
import MaskedPII from "./MaskedPII";

const TIERS = ["ANONYMOUS", "REGISTERED", "FREE", "START", "PRO", "UNLIMITED"];
const PAID_TIERS = new Set(["START", "PRO", "UNLIMITED"]);
const DURATION_OPTIONS = [
  { value: 1, label: "1 месяц" },
  { value: 3, label: "3 месяца" },
  { value: 6, label: "6 месяцев" },
  { value: 12, label: "12 месяцев" },
  { value: 0, label: "Бессрочно" },
] as const;

function formatDate(dt: string) {
  const d = new Date(dt);
  const date = d.toLocaleDateString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric",
  });
  const time = d.toLocaleTimeString("ru-RU", {
    hour: "2-digit", minute: "2-digit",
  });
  return `${date} ${time}`;
}

interface ConfirmDialogProps {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

function ConfirmDialog({ message, onConfirm, onCancel, loading }: ConfirmDialogProps) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-[340px]">
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
            {loading ? "Удаление..." : "Удалить"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function AdminUsers() {
  const navigate = useNavigate();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [tierFilter, setTierFilter] = useState("");
  const [showAnon, setShowAnon] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Per-row tier editing
  const [editTier, setEditTier] = useState<Record<string, string>>({});
  const [savingTier, setSavingTier] = useState<string | null>(null);

  // Tier assign dialog (for paid tiers)
  const [tierDialog, setTierDialog] = useState<{ userId: string; tier: string } | null>(null);
  const [tierDuration, setTierDuration] = useState<number>(1);
  const [tierReason, setTierReason] = useState("");
  const [tierError, setTierError] = useState("");

  // Delete confirm
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [deleting, setDeleting] = useState(false);

  const perPage = 50;
  const totalPages = Math.ceil(total / perPage);

  function loadUsers() {
    setLoading(true);
    setError("");
    adminListUsers({
      tier: tierFilter || undefined,
      is_anonymous: showAnon ? undefined : false,
      page,
      per_page: perPage,
    })
      .then((res) => {
        setUsers(res.items);
        setTotal(res.total);
      })
      .catch(() => setError("Ошибка загрузки пользователей"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadUsers();
  }, [tierFilter, showAnon, page]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleTierSave(userId: string) {
    const tier = editTier[userId];
    if (!tier) return;
    if (PAID_TIERS.has(tier)) {
      setTierDuration(1);
      setTierReason("");
      setTierError("");
      setTierDialog({ userId, tier });
    } else {
      doTierUpdate(userId, tier, null, null);
    }
  }

  async function doTierUpdate(userId: string, tier: string, durationMonths: number | null, reason: string | null) {
    setSavingTier(userId);
    setTierError("");
    try {
      await adminUpdateUserTier(userId, tier, durationMonths, reason);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, tier } : u))
      );
      setEditTier((prev) => {
        const next = { ...prev };
        delete next[userId];
        return next;
      });
      setTierDialog(null);
    } catch (err: unknown) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const axErr = err as any;
      const detail = axErr?.response?.data?.detail;
      const status = axErr?.response?.status;
      const msg = detail
        ? `${detail} (${status})`
        : err instanceof Error
          ? err.message
          : "Ошибка сохранения тарифа";
      setTierError(msg);
    } finally {
      setSavingTier(null);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await adminDeleteUser(deleteTarget.id);
      setUsers((prev) => prev.filter((u) => u.id !== deleteTarget.id));
      setTotal((t) => t - 1);
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-serif font-medium text-zinc-100 mb-6">Пользователи</h1>

      {/* Filters */}
      <div className="flex items-center gap-4 mb-4 pb-4 border-b border-zinc-800">
        <select
          value={tierFilter}
          onChange={(e) => { setTierFilter(e.target.value); setPage(1); }}
          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-zinc-500"
        >
          <option value="">Все тиры</option>
          {TIERS.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>

        <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={showAnon}
            onChange={(e) => { setShowAnon(e.target.checked); setPage(1); }}
            className="rounded"
          />
          Показать анонимных
        </label>

        <span className="ml-auto text-xs text-zinc-500">
          {total} пользователей
        </span>
      </div>

      {error ? (
        <div className="text-red-400 text-sm py-8">{error}</div>
      ) : loading ? (
        <div className="text-zinc-500 text-sm py-8">Загрузка...</div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  {["Email", "Имя", "Тир", "Telegram", "Джобов", "Дата", ""].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const currentTier = editTier[u.id] ?? u.tier;
                  const tierChanged = editTier[u.id] && editTier[u.id] !== u.tier;
                  return (
                    <tr key={u.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                      <td className="px-4 py-3 text-zinc-300 max-w-[200px]">
                        <span className="truncate block">
                          <MaskedPII type="email" value={u.email} fallback={<span className="text-zinc-500">Аноним #{u.id.slice(0, 8)}</span>} />
                        </span>
                      </td>
                      <td className="px-4 py-3 text-zinc-400">
                        <MaskedPII type="name" value={u.name} fallback={<span className="text-zinc-600">—</span>} />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <select
                            value={currentTier}
                            onChange={(e) => setEditTier((prev) => ({ ...prev, [u.id]: e.target.value }))}
                            className="bg-zinc-800 border border-zinc-700 text-zinc-300 text-xs rounded px-2 py-1 focus:outline-none"
                          >
                            {TIERS.map((t) => (
                              <option key={t} value={t}>{t}</option>
                            ))}
                          </select>
                          {tierChanged && (
                            <button
                              onClick={() => handleTierSave(u.id)}
                              disabled={savingTier === u.id}
                              className="text-xs px-2 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded transition-colors disabled:opacity-50"
                            >
                              {savingTier === u.id ? "..." : "Сохранить"}
                            </button>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-zinc-400 text-xs">
                        {u.telegram_username ? (
                          <MaskedPII type="telegram" value={u.telegram_username} className={u.telegram_subscribed ? "text-green-400" : "text-zinc-400"} />
                        ) : (
                          <span className="text-zinc-600">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-zinc-400 text-center">{u.jobs_count}</td>
                      <td className="px-4 py-3 text-zinc-500 text-xs whitespace-nowrap">
                        {u.created_at ? formatDate(u.created_at) : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => navigate(`/admin/users/${u.id}`)}
                            className="text-xs text-zinc-500 hover:text-zinc-200 transition-colors"
                            title="Детали"
                          >
                            →
                          </button>
                          <button
                            onClick={() => setDeleteTarget(u)}
                            className="text-xs text-zinc-600 hover:text-red-400 transition-colors"
                            title="Удалить"
                          >
                            ✕
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
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
          message={`Удалить пользователя ${deleteTarget.email || `Аноним #${deleteTarget.id.slice(0, 8)}`}? Все его данные будут удалены безвозвратно.`}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          loading={deleting}
        />
      )}

      {tierDialog && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-[380px]">
            <h3 className="text-zinc-100 font-medium mb-1">
              Назначить {tierDialog.tier}
            </h3>
            <p className="text-zinc-500 text-xs mb-5">
              <MaskedPII type="email" value={users.find((u) => u.id === tierDialog.userId)?.email} fallback={<span>{tierDialog.userId.slice(0, 8)}</span>} />
            </p>

            <label className="block text-xs text-zinc-400 mb-1.5">Срок действия</label>
            <div className="flex flex-wrap gap-2 mb-4">
              {DURATION_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setTierDuration(opt.value)}
                  className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                    tierDuration === opt.value
                      ? "border-blue-500 bg-blue-500/15 text-blue-300"
                      : "border-zinc-700 text-zinc-400 hover:border-zinc-500"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <label className="block text-xs text-zinc-400 mb-1.5">Причина (опционально)</label>
            <input
              type="text"
              value={tierReason}
              onChange={(e) => setTierReason(e.target.value)}
              placeholder="Например: тест, партнёр, промо..."
              className="w-full bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-2 mb-5 focus:outline-none focus:border-zinc-500 placeholder:text-zinc-600"
            />

            {tierError && (
              <p className="text-red-400 text-xs mb-3">{tierError}</p>
            )}

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setTierDialog(null)}
                disabled={savingTier === tierDialog.userId}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-50"
              >
                Отмена
              </button>
              <button
                onClick={() => doTierUpdate(
                  tierDialog.userId,
                  tierDialog.tier,
                  tierDuration === 0 ? null : tierDuration,
                  tierReason || null,
                )}
                disabled={savingTier === tierDialog.userId}
                className="px-4 py-2 text-sm bg-blue-600/80 hover:bg-blue-600 text-blue-100 rounded-lg transition-colors disabled:opacity-50"
              >
                {savingTier === tierDialog.userId ? "Сохранение..." : "Назначить"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
