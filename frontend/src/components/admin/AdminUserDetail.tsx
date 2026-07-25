import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { adminDeleteUser, adminGetUser, adminUpdateUserTier } from "../../api/client";
import MaskedPII from "./MaskedPII";
import type {
  AdminJob,
  AdminUserDetail as AdminUserDetailType,
  AdminUserScript,
  AdminUserSubscription,
  AdminUserPayment,
  AdminUserSettings,
} from "../../types";

const TIERS = ["ANONYMOUS", "REGISTERED", "FREE", "START", "PRO", "UNLIMITED"];
const PAID_TIERS = ["START", "PRO", "UNLIMITED"];

const DURATION_OPTIONS = [
  { value: 1, label: "1 месяц" },
  { value: 3, label: "3 месяца" },
  { value: 6, label: "6 месяцев" },
  { value: 12, label: "12 месяцев" },
  { value: 0, label: "Бессрочно" },
];

const TIER_COLORS: Record<string, string> = {
  ANONYMOUS: "bg-zinc-700 text-zinc-300",
  REGISTERED: "bg-blue-900/50 text-blue-300",
  FREE: "bg-green-900/50 text-green-300",
  START: "bg-purple-900/50 text-purple-300",
  PRO: "bg-amber-900/50 text-amber-300",
  UNLIMITED: "bg-rose-900/50 text-rose-300",
};

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-green-900/50 text-green-300",
  failed: "bg-red-900/50 text-red-300",
  pending: "bg-zinc-700/50 text-zinc-400",
  active: "bg-green-900/50 text-green-300",
  cancelled: "bg-red-900/50 text-red-300",
  succeeded: "bg-green-900/50 text-green-300",
};

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "bg-yellow-900/50 text-yellow-300";
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}

function formatDate(dt: string) {
  return new Date(dt).toLocaleDateString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function truncateUrl(url: string, len = 50) {
  if (url.length <= len) return url;
  return url.slice(0, len) + "...";
}

function formatMoney(kopecks: number, currency: string) {
  if (currency === "EUR") return `€${(kopecks / 100).toFixed(2)}`;
  return `${(kopecks / 100).toFixed(0)} ₽`;
}

function SectionHeader({ title, count, open, onToggle }: {
  title: string; count?: number; open: boolean; onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between py-3 text-left group"
    >
      <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wide">
        {title}{count !== undefined ? ` (${count})` : ""}
      </h2>
      <span className="text-zinc-600 group-hover:text-zinc-400 transition-colors text-lg">
        {open ? "−" : "+"}
      </span>
    </button>
  );
}

function InfoField({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">{label}</div>
      <div className="text-zinc-300 text-sm">{value || <span className="text-zinc-600">—</span>}</div>
    </div>
  );
}

function ConfirmDialog({
  message, onConfirm, onCancel, loading,
}: {
  message: string; onConfirm: () => void; onCancel: () => void; loading?: boolean;
}) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-[340px]">
        <p className="text-zinc-200 text-sm mb-5">{message}</p>
        <div className="flex gap-3 justify-end">
          <button onClick={onCancel} className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors">
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

/* ─── Settings Section ─── */
function SettingsSection({ settings }: { settings: AdminUserSettings }) {
  const flags = [
    settings.onboarding_completed && "Onboarding пройден",
    settings.has_custom_content_prompt && "Кастомный промпт контента",
    settings.has_custom_strategy_prompt && "Кастомный промпт стратегии",
    settings.has_api_keys && "Свои API ключи",
    settings.radar_enabled && `Радар: ${settings.radar_mode || "on"}`,
  ].filter(Boolean);

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-x-8 gap-y-4 text-sm">
      <InfoField label="Язык" value={settings.language} />
      <InfoField label="Ниши" value={settings.niches.length > 0 ? settings.niches.join(", ") : null} />
      <InfoField label="Формат видео" value={settings.video_format} />
      <InfoField label="Тон" value={settings.tone} />
      <InfoField label="CTA (скрипт)" value={settings.script_cta} />
      <InfoField label="CTA (описание)" value={settings.description_cta} />
      <InfoField label="Запрещённые слова" value={settings.forbidden_words} />
      <InfoField
        label="Интересы"
        value={settings.interests.length > 0 ? settings.interests.slice(0, 10).join(", ") + (settings.interests.length > 10 ? ` +${settings.interests.length - 10}` : "") : null}
      />
      {settings.about_me && (
        <div className="col-span-2 md:col-span-3">
          <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">О себе</div>
          <div className="text-zinc-300 text-sm whitespace-pre-wrap max-h-32 overflow-y-auto bg-zinc-800/50 rounded-lg p-3">
            {settings.about_me}
          </div>
        </div>
      )}
      {flags.length > 0 && (
        <div className="col-span-2 md:col-span-3 flex flex-wrap gap-2 mt-1">
          {flags.map((f) => (
            <span key={f as string} className="px-2 py-0.5 rounded-full text-xs bg-zinc-800 text-zinc-400">
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Subscription Section ─── */
function SubscriptionSection({ subscription, payments }: {
  subscription: AdminUserSubscription | null;
  payments: AdminUserPayment[];
}) {
  return (
    <div className="space-y-4">
      {subscription ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-3 text-sm">
          <InfoField label="Тариф" value={<StatusBadge status={subscription.tier} />} />
          <InfoField label="Статус" value={<StatusBadge status={subscription.status} />} />
          <InfoField label="Провайдер" value={subscription.payment_provider} />
          <InfoField label="Интервал" value={subscription.billing_interval === "yearly" ? "Годовая" : "Месячная"} />
          <InfoField label="Сумма" value={formatMoney(subscription.amount_kopecks, subscription.currency)} />
          <InfoField label="Период до" value={subscription.current_period_end ? formatDate(subscription.current_period_end) : null} />
          {subscription.scheduled_tier && (
            <InfoField label="Запланировано" value={`${subscription.scheduled_tier} (${subscription.scheduled_interval})`} />
          )}
        </div>
      ) : (
        <div className="text-zinc-600 text-sm">Нет активной подписки</div>
      )}

      {payments.length > 0 && (
        <div className="mt-4">
          <div className="text-xs text-zinc-500 uppercase tracking-wide mb-2">Платежи</div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  {["Сумма", "Статус", "Провайдер", "Метод", "Дата"].map((h) => (
                    <th key={h} className="text-left px-3 py-2 text-xs text-zinc-500 uppercase tracking-wide font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id} className="border-b border-zinc-800/50">
                    <td className="px-3 py-2 text-zinc-300">{formatMoney(p.amount_kopecks, p.currency)}</td>
                    <td className="px-3 py-2"><StatusBadge status={p.status} /></td>
                    <td className="px-3 py-2 text-zinc-500">{p.payment_provider || "—"}</td>
                    <td className="px-3 py-2 text-zinc-500">{p.payment_method || "—"}</td>
                    <td className="px-3 py-2 text-zinc-500 whitespace-nowrap">{p.paid_at ? formatDate(p.paid_at) : formatDate(p.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Script Card with Diff ─── */
function ScriptCard({ script }: { script: AdminUserScript }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"current" | "original" | "diff">("current");

  const hasOriginal = !!(script.original_script || script.original_description || script.original_editor_instructions);
  const isChanged = hasOriginal && (
    script.script !== script.original_script ||
    script.description !== script.original_description ||
    script.editor_instructions !== script.original_editor_instructions
  );

  return (
    <div className="border border-zinc-800 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 bg-zinc-900 hover:bg-zinc-800/70 transition-colors text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-xs text-zinc-500 uppercase">{script.reel_platform || "?"}</span>
          <span className="text-sm text-zinc-300 truncate">
            {script.reel_title || truncateUrl(script.reel_url || "—", 60)}
          </span>
          {isChanged && (
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-900/40 text-amber-400 whitespace-nowrap">
              изменён
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs text-zinc-600">{script.updated_at ? formatDate(script.updated_at) : ""}</span>
          <span className="text-zinc-600">{open ? "−" : "+"}</span>
        </div>
      </button>

      {open && (
        <div className="px-4 py-4 space-y-4 bg-zinc-950/50">
          {/* Tabs */}
          {hasOriginal && (
            <div className="flex gap-1 border-b border-zinc-800 pb-2">
              {(["current", "original", ...(isChanged ? ["diff"] : [])] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t as "current" | "original" | "diff")}
                  className={`px-3 py-1 text-xs rounded-t transition-colors ${
                    tab === t ? "bg-zinc-800 text-zinc-200" : "text-zinc-500 hover:text-zinc-400"
                  }`}
                >
                  {t === "current" ? "Текущий" : t === "original" ? "Оригинал" : "Сравнение"}
                </button>
              ))}
            </div>
          )}

          {tab === "diff" && isChanged ? (
            <DiffView script={script} />
          ) : (
            <div className="space-y-3">
              <ScriptField
                label="Сценарий"
                value={tab === "original" ? script.original_script : script.script}
              />
              <ScriptField
                label="Описание"
                value={tab === "original" ? script.original_description : script.description}
              />
              <ScriptField
                label="Инструкции монтажёру"
                value={tab === "original" ? script.original_editor_instructions : script.editor_instructions}
              />
            </div>
          )}

          {script.reel_url && (
            <a
              href={script.reel_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block text-xs text-zinc-500 hover:text-zinc-400 transition-colors mt-2"
            >
              Открыть оригинал
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function ScriptField({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div>
      <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">{label}</div>
      <div className="text-zinc-300 text-sm whitespace-pre-wrap bg-zinc-900 rounded-lg p-3 max-h-48 overflow-y-auto leading-relaxed">
        {value}
      </div>
    </div>
  );
}

function DiffView({ script }: { script: AdminUserScript }) {
  return (
    <div className="space-y-4">
      {[
        { label: "Сценарий", current: script.script, original: script.original_script },
        { label: "Описание", current: script.description, original: script.original_description },
        { label: "Инструкции монтажёру", current: script.editor_instructions, original: script.original_editor_instructions },
      ].map(({ label, current, original }) => {
        if (current === original) return null;
        if (!current && !original) return null;
        return (
          <div key={label}>
            <div className="text-xs text-zinc-500 uppercase tracking-wide mb-2">{label}</div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-[10px] text-zinc-600 mb-1">ОРИГИНАЛ</div>
                <div className="text-sm whitespace-pre-wrap bg-red-950/20 border border-red-900/30 rounded-lg p-3 max-h-48 overflow-y-auto text-zinc-400 leading-relaxed">
                  {original || <span className="text-zinc-600 italic">пусто</span>}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-zinc-600 mb-1">ТЕКУЩИЙ</div>
                <div className="text-sm whitespace-pre-wrap bg-green-950/20 border border-green-900/30 rounded-lg p-3 max-h-48 overflow-y-auto text-zinc-300 leading-relaxed">
                  {current || <span className="text-zinc-600 italic">пусто</span>}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ─── Main Component ─── */
export function AdminUserDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<AdminUserDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [editTier, setEditTier] = useState("");
  const [durationMonths, setDurationMonths] = useState<number>(1);
  const [reason, setReason] = useState("");
  const [savingTier, setSavingTier] = useState(false);
  const [tierError, setTierError] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [jobsPage, setJobsPage] = useState(1);
  const [loadingMore, setLoadingMore] = useState(false);
  const [allJobs, setAllJobs] = useState<AdminJob[]>([]);

  // Collapsible sections
  const [openSections, setOpenSections] = useState({
    settings: true,
    subscription: false,
    jobs: true,
    scripts: true,
  });

  const toggleSection = (key: keyof typeof openSections) =>
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));

  useEffect(() => {
    if (!id) return;
    adminGetUser(id, 1, 20)
      .then((u) => {
        setUser(u);
        setEditTier(u.tier);
        setAllJobs(u.recent_jobs);
      })
      .finally(() => setLoading(false));
  }, [id]);

  async function loadMoreJobs() {
    if (!id || !user) return;
    setLoadingMore(true);
    try {
      const nextPage = jobsPage + 1;
      const data = await adminGetUser(id, nextPage, 20);
      setAllJobs((prev) => [...prev, ...data.recent_jobs]);
      setJobsPage(nextPage);
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleTierSave() {
    if (!user || editTier === user.tier) return;
    setSavingTier(true);
    setTierError("");
    try {
      const isPaid = PAID_TIERS.includes(editTier);
      await adminUpdateUserTier(
        user.id,
        editTier,
        isPaid ? (durationMonths === 0 ? null : durationMonths) : null,
        isPaid ? reason || null : null,
      );
      setUser((prev) => prev ? { ...prev, tier: editTier } : prev);
      setReason("");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setTierError(msg || "Ошибка при изменении тиера");
    } finally {
      setSavingTier(false);
    }
  }

  async function handleDelete() {
    if (!user) return;
    setDeleting(true);
    try {
      await adminDeleteUser(user.id);
      navigate("/admin/users");
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return <div className="text-zinc-500 text-sm py-8">Загрузка...</div>;
  }

  if (!user) {
    return <div className="text-zinc-500 text-sm py-8">Пользователь не найден</div>;
  }

  const displayName = user.email || user.name || null;

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <button
          onClick={() => navigate("/admin/users")}
          className="hover:text-zinc-300 transition-colors"
        >
          Пользователи
        </button>
        <span>/</span>
        <span className="text-zinc-300 truncate max-w-[300px]">
          {displayName ? <MaskedPII type={user.email ? "email" : "name"} value={displayName} /> : `Аноним #${user.id.slice(0, 8)}`}
        </span>
      </div>

      {/* ── User Info ── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-8 gap-y-4 text-sm">
          <InfoField label="Email" value={user.email ? <MaskedPII type="email" value={user.email} /> : null} />
          <InfoField label="Имя" value={user.name ? <MaskedPII type="name" value={user.name} /> : null} />
          <InfoField label="Авторизация" value={user.auth_provider} />
          <InfoField label="ID" value={<span className="font-mono text-xs text-zinc-500">{user.id}</span>} />
          <InfoField label="Создан" value={user.created_at ? formatDate(user.created_at) : null} />
          <InfoField
            label="Telegram"
            value={
              user.telegram_username ? (
                <span className={user.telegram_subscribed ? "text-green-400" : ""}>
                  <MaskedPII type="telegram" value={user.telegram_username} />
                  {user.telegram_subscribed ? " ✓" : " (не подписан)"}
                </span>
              ) : null
            }
          />
          <div>
            <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">Тир</div>
            <div className="flex items-center gap-3 mt-1">
              <select
                value={editTier}
                onChange={(e) => setEditTier(e.target.value)}
                className="bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none"
              >
                {TIERS.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              {editTier !== user.tier && (
                <button
                  onClick={handleTierSave}
                  disabled={savingTier}
                  className="px-3 py-1.5 text-sm bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded-lg transition-colors disabled:opacity-50"
                >
                  {savingTier ? "..." : "Сохранить"}
                </button>
              )}
              {editTier === user.tier && (
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${TIER_COLORS[user.tier] ?? ""}`}>
                  {user.tier}
                </span>
              )}
            </div>
            {editTier !== user.tier && PAID_TIERS.includes(editTier) && (
              <div className="flex items-center gap-3 mt-2">
                <select
                  value={durationMonths}
                  onChange={(e) => setDurationMonths(Number(e.target.value))}
                  className="bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none"
                >
                  {DURATION_OPTIONS.map((d) => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </select>
                <input
                  type="text"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Причина (промо, партнёр...)"
                  className="bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none flex-1"
                />
              </div>
            )}
            {tierError && <div className="text-red-400 text-xs mt-1">{tierError}</div>}
          </div>
        </div>

        <div className="mt-6 pt-4 border-t border-zinc-800">
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="px-4 py-2 text-sm border border-red-900/50 text-red-400 hover:bg-red-900/20 rounded-lg transition-colors"
          >
            Удалить пользователя
          </button>
        </div>
      </div>

      {/* ── Settings & Profile ── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-6">
        <SectionHeader title="Настройки профиля" open={openSections.settings} onToggle={() => toggleSection("settings")} />
        {openSections.settings && (
          <div className="pb-5">
            {user.settings ? (
              <SettingsSection settings={user.settings} />
            ) : (
              <div className="text-zinc-600 text-sm">Настройки не заполнены</div>
            )}
          </div>
        )}
      </div>

      {/* ── Subscription & Payments ── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-6">
        <SectionHeader
          title="Подписка и платежи"
          count={user.payments?.length}
          open={openSections.subscription}
          onToggle={() => toggleSection("subscription")}
        />
        {openSections.subscription && (
          <div className="pb-5">
            <SubscriptionSection
              subscription={user.subscription ?? null}
              payments={user.payments ?? []}
            />
          </div>
        )}
      </div>

      {/* ── Jobs ── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-6">
        <SectionHeader
          title="Джобы"
          count={user.jobs_total ?? user.jobs_count}
          open={openSections.jobs}
          onToggle={() => toggleSection("jobs")}
        />
        {openSections.jobs && (
          <div className="pb-5">
            {allJobs.length === 0 ? (
              <div className="text-zinc-600 text-sm">Нет джобов</div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-800">
                        {["URL", "Платформа", "Статус", "Ошибка", "Дата"].map((h) => (
                          <th key={h} className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {allJobs.map((job: AdminJob) => (
                        <tr key={job.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                          <td className="px-4 py-2.5">
                            <a
                              href={job.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-zinc-400 hover:text-zinc-300 font-mono text-xs transition-colors"
                            >
                              {truncateUrl(job.url, 55)}
                            </a>
                          </td>
                          <td className="px-4 py-2.5 text-zinc-500 text-xs">{job.video_platform || "—"}</td>
                          <td className="px-4 py-2.5"><StatusBadge status={job.status} /></td>
                          <td className="px-4 py-2.5 text-red-400/70 text-xs max-w-[200px] truncate">{job.error || ""}</td>
                          <td className="px-4 py-2.5 text-zinc-500 text-xs whitespace-nowrap">
                            {new Date(job.created_at).toLocaleDateString("ru-RU")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {allJobs.length < (user.jobs_total ?? user.jobs_count) && (
                  <button
                    onClick={loadMoreJobs}
                    disabled={loadingMore}
                    className="mt-3 px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {loadingMore ? "Загрузка..." : `Показать ещё (${(user.jobs_total ?? user.jobs_count) - allJobs.length} осталось)`}
                  </button>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* ── Scripts / Scenarios ── */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-6">
        <SectionHeader
          title="Сценарии"
          count={user.scripts?.length}
          open={openSections.scripts}
          onToggle={() => toggleSection("scripts")}
        />
        {openSections.scripts && (
          <div className="pb-5 space-y-2">
            {!user.scripts || user.scripts.length === 0 ? (
              <div className="text-zinc-600 text-sm">Нет сценариев</div>
            ) : (
              user.scripts.map((s) => <ScriptCard key={s.id} script={s} />)
            )}
          </div>
        )}
      </div>

      {showDeleteConfirm && (
        <ConfirmDialog
          message={`Удалить пользователя ${displayName}? Все его данные (джобы, скрипты, закладки) будут удалены безвозвратно.`}
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteConfirm(false)}
          loading={deleting}
        />
      )}
    </div>
  );
}
