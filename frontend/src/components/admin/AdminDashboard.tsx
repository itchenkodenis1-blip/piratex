import { useEffect, useRef, useState } from "react";
import { adminCleanupGhosts, adminReextractFrames, adminGetFounderAvatar, adminUploadFounderAvatar, getAdminAnalytics, getAdminStats, getAdminCostAnalytics, repairThumbnails, getDemoMode, setDemoMode as apiSetDemoMode } from "../../api/client";
import type { AdminAnalytics, AdminStats, CostAnalytics, CostPeriod, CostDayStats, JobDayStats, PlatformHealth, RecentError, UserDayStats } from "../../types";

// ── Helpers ──────────────────────────────────────────────────────────────

function formatUsd(value: number): string {
  if (value >= 1) return `$${value.toFixed(2)}`;
  if (value >= 0.01) return `$${value.toFixed(3)}`;
  return `$${value.toFixed(4)}`;
}

function formatRub(kopecks: number): string {
  const rub = kopecks / 100;
  if (rub >= 1000) return `${(rub / 1000).toFixed(1)}K ₽`;
  return `${rub.toFixed(0)} ₽`;
}

function formatEur(cents: number): string {
  const eur = cents / 100;
  return `€${eur.toFixed(0)}`;
}

function pctChange(current: number, previous: number): { text: string; color: string } | null {
  if (previous === 0 && current === 0) return null;
  if (previous === 0) return { text: "+∞", color: "text-red-400" };
  const pct = ((current - previous) / previous) * 100;
  if (Math.abs(pct) < 0.5) return null;
  const sign = pct > 0 ? "+" : "";
  // For costs: up is bad (red), down is good (green)
  const color = pct > 0 ? "text-red-400" : "text-emerald-400";
  return { text: `${sign}${pct.toFixed(0)}%`, color };
}

function pctChangeRevenue(current: number, previous: number): { text: string; color: string } | null {
  if (previous === 0 && current === 0) return null;
  if (previous === 0) return { text: "+∞", color: "text-emerald-400" };
  const pct = ((current - previous) / previous) * 100;
  if (Math.abs(pct) < 0.5) return null;
  const sign = pct > 0 ? "+" : "";
  // For revenue: up is good (green), down is bad (red)
  const color = pct > 0 ? "text-emerald-400" : "text-red-400";
  return { text: `${sign}${pct.toFixed(0)}%`, color };
}

// ── Financial Card ──────────────────────────────────────────────────────

function FinanceCard({ label, value, subtitle, change, accent = "text-zinc-100" }: {
  label: string;
  value: string;
  subtitle?: string;
  change?: { text: string; color: string } | null;
  accent?: string;
}) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-zinc-800/60 bg-gradient-to-br from-zinc-900 via-zinc-900 to-zinc-800/30 p-5">
      <div className="text-[11px] text-zinc-500 uppercase tracking-wider font-medium mb-2">{label}</div>
      <div className="flex items-baseline gap-2">
        <span className={`text-2xl font-mono font-semibold ${accent}`}>{value}</span>
        {change && <span className={`text-xs font-medium ${change.color}`}>{change.text}</span>}
      </div>
      {subtitle && <div className="text-xs text-zinc-500 mt-1.5">{subtitle}</div>}
    </div>
  );
}

// ── Cost Breakdown Bar ──────────────────────────────────────────────────

function CostBreakdownBar({ period, label }: { period: CostPeriod; label: string }) {
  const total = period.total_usd || 1;
  const segments = [
    { key: "apify", label: "Apify", value: period.apify_usd, color: "bg-violet-500" },
    { key: "whisper", label: "Whisper", value: period.whisper_usd, color: "bg-blue-500" },
    { key: "vision", label: "Vision", value: period.vision_usd, color: "bg-cyan-500" },
    { key: "sonnet", label: "Sonnet", value: period.sonnet_usd, color: "bg-amber-500" },
    { key: "haiku", label: "Haiku", value: period.haiku_usd, color: "bg-emerald-500" },
  ].filter(s => s.value > 0);

  return (
    <div className="rounded-2xl border border-zinc-800/60 bg-zinc-900 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs text-zinc-500 uppercase tracking-wider font-medium">{label}</h3>
        <span className="text-sm font-mono text-zinc-300">{formatUsd(period.total_usd)}</span>
      </div>

      {/* Stacked bar */}
      <div className="h-3 rounded-full bg-zinc-800 overflow-hidden flex">
        {segments.map(s => (
          <div
            key={s.key}
            className={`${s.color} transition-all duration-500`}
            style={{ width: `${(s.value / total) * 100}%` }}
            title={`${s.label}: ${formatUsd(s.value)} (${((s.value / total) * 100).toFixed(0)}%)`}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3">
        {segments.map(s => (
          <div key={s.key} className="flex items-center gap-1.5 text-xs text-zinc-400">
            <span className={`w-2 h-2 rounded-full ${s.color}`} />
            <span>{s.label}</span>
            <span className="text-zinc-600 font-mono">{formatUsd(s.value)}</span>
          </div>
        ))}
      </div>

      {period.jobs_count > 0 && (
        <div className="text-xs text-zinc-600 mt-2">
          {period.jobs_count} анализ{period.jobs_count === 1 ? "" : period.jobs_count < 5 ? "а" : "ов"}
        </div>
      )}
    </div>
  );
}

// ── Cost Sparkline (14 days) ────────────────────────────────────────────

function CostSparkline({ data }: { data: CostDayStats[] }) {
  const maxCost = Math.max(...data.map(d => d.total_usd), 0.01);

  return (
    <div className="rounded-2xl border border-zinc-800/60 bg-zinc-900 p-5">
      <h3 className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-4">
        Затраты за 14 дней
      </h3>
      <div className="flex items-end gap-1 h-24">
        {data.map((day) => {
          const h = (day.total_usd / maxCost) * 100;
          const label = day.date.slice(5);
          return (
            <div key={day.date} className="flex-1 flex flex-col items-center gap-1">
              <div
                className="w-full bg-gradient-to-t from-red-500/60 to-red-400/30 rounded-t-sm transition-all"
                style={{ height: `${h}%`, minHeight: day.total_usd > 0 ? "3px" : "0" }}
                title={`${label}: ${formatUsd(day.total_usd)} (${day.jobs_count} jobs)`}
              />
              <span className="text-[9px] text-zinc-600 tabular-nums">{label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Apify Budget Gauge ──────────────────────────────────────────────────

function ApifyBudgetGauge({ budget }: { budget: { max_monthly_usd: number; used_monthly_usd: number; remaining_usd: number } }) {
  const pct = budget.max_monthly_usd > 0
    ? (budget.used_monthly_usd / budget.max_monthly_usd) * 100
    : 0;
  const color = pct > 80 ? "text-red-400" : pct > 50 ? "text-amber-400" : "text-emerald-400";
  const barColor = pct > 80 ? "bg-red-500" : pct > 50 ? "bg-amber-500" : "bg-emerald-500";

  return (
    <div className="rounded-2xl border border-zinc-800/60 bg-zinc-900 p-5">
      <div className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-3">Бюджет Apify</div>
      <div className="flex items-baseline gap-2 mb-3">
        <span className={`text-2xl font-mono font-semibold ${color}`}>
          ${budget.remaining_usd.toFixed(2)}
        </span>
        <span className="text-xs text-zinc-600">осталось</span>
      </div>
      <div className="h-2 rounded-full bg-zinc-800 overflow-hidden mb-2">
        <div
          className={`h-full ${barColor} rounded-full transition-all duration-500`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-zinc-600">
        <span>Израсходовано: ${budget.used_monthly_usd.toFixed(2)}</span>
        <span>Лимит: ${budget.max_monthly_usd.toFixed(0)}</span>
      </div>
    </div>
  );
}

// ── Stat Card (improved) ────────────────────────────────────────────────

function StatCard({ title, value, accent = "text-zinc-100" }: { title: string; value: number | undefined; accent?: string }) {
  return (
    <div className="rounded-2xl border border-zinc-800/60 bg-zinc-900 p-4">
      <div className="text-[11px] text-zinc-500 uppercase tracking-wider font-medium">{title}</div>
      <div className={`text-2xl font-mono mt-1.5 ${accent}`}>
        {value ?? "—"}
      </div>
    </div>
  );
}

// ── Charts ──────────────────────────────────────────────────────────────

function JobsChart({ data }: { data: JobDayStats[] }) {
  const maxTotal = Math.max(...data.map(d => d.total), 1);

  return (
    <div className="rounded-2xl border border-zinc-800/60 bg-zinc-900 p-5">
      <h3 className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-4">
        Джобы за 14 дней
      </h3>
      <div className="flex items-end gap-1.5 h-32">
        {data.map((day) => {
          const totalH = (day.total / maxTotal) * 100;
          const completedH = day.total > 0 ? (day.completed / day.total) * 100 : 0;
          const failedH = day.total > 0 ? (day.failed / day.total) * 100 : 0;
          const otherH = 100 - completedH - failedH;
          const label = day.date.slice(5);

          return (
            <div key={day.date} className="flex-1 flex flex-col items-center gap-1">
              <div
                className="w-full rounded-t-sm flex flex-col justify-end overflow-hidden"
                style={{ height: `${totalH}%`, minHeight: day.total > 0 ? "4px" : "0" }}
                title={`${label}: всего ${day.total}, OK ${day.completed}, ошибок ${day.failed}`}
              >
                {day.failed > 0 && (
                  <div className="w-full bg-red-500/70" style={{ height: `${failedH}%`, minHeight: "2px" }} />
                )}
                {otherH > 0 && day.total - day.completed - day.failed > 0 && (
                  <div className="w-full bg-zinc-600" style={{ height: `${otherH}%`, minHeight: "2px" }} />
                )}
                {day.completed > 0 && (
                  <div className="w-full bg-emerald-500/70 rounded-b-sm" style={{ height: `${completedH}%`, minHeight: "2px" }} />
                )}
              </div>
              <span className="text-[9px] text-zinc-600 tabular-nums">{label}</span>
            </div>
          );
        })}
      </div>
      <div className="flex gap-4 mt-3 text-[10px] text-zinc-500">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500/70" /> Завершено</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500/70" /> Ошибки</span>
      </div>
    </div>
  );
}

function UsersChart({ data }: { data: UserDayStats[] }) {
  const maxUsers = Math.max(...data.map(d => d.new_users), 1);

  return (
    <div className="rounded-2xl border border-zinc-800/60 bg-zinc-900 p-5">
      <h3 className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-4">
        Новые пользователи за 14 дней
      </h3>
      <div className="flex items-end gap-1.5 h-32">
        {data.map((day) => {
          const h = (day.new_users / maxUsers) * 100;
          const label = day.date.slice(5);
          return (
            <div key={day.date} className="flex-1 flex flex-col items-center gap-1">
              <div
                className="w-full bg-blue-500/50 rounded-t-sm"
                style={{ height: `${h}%`, minHeight: day.new_users > 0 ? "4px" : "0" }}
                title={`${label}: ${day.new_users} новых`}
              />
              <span className="text-[9px] text-zinc-600 tabular-nums">{label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const PLATFORM_COLORS: Record<string, string> = {
  instagram: "text-pink-400",
  youtube: "text-red-400",
  tiktok: "text-cyan-400",
};

const PLATFORM_NAMES: Record<string, string> = {
  instagram: "Instagram",
  youtube: "YouTube",
  tiktok: "TikTok",
};

function rateColor(rate: number): string {
  if (rate >= 90) return "text-emerald-400";
  if (rate >= 70) return "text-amber-400";
  return "text-red-400";
}

function PlatformHealthCards({ data }: { data: PlatformHealth[] }) {
  return (
    <div className="grid grid-cols-3 gap-3">
      {["instagram", "youtube", "tiktok"].map((p) => {
        const entry = data.find(d => d.platform === p);
        const rate = entry?.success_rate ?? 0;
        return (
          <div key={p} className="rounded-2xl border border-zinc-800/60 bg-zinc-900 p-4">
            <div className={`text-sm font-medium mb-2 ${PLATFORM_COLORS[p] ?? "text-zinc-400"}`}>
              {PLATFORM_NAMES[p] ?? p}
            </div>
            <div className={`text-2xl font-mono ${entry && entry.total_jobs > 0 ? rateColor(rate) : "text-zinc-600"}`}>
              {entry && entry.total_jobs > 0 ? `${rate.toFixed(0)}%` : "—"}
            </div>
            <div className="flex gap-3 mt-2 text-xs text-zinc-500">
              <span>Всего: <span className="text-zinc-400">{entry?.total_jobs ?? 0}</span></span>
              <span>Ошибок: <span className="text-red-400">{entry?.failed ?? 0}</span></span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function timeAgo(dt: string): string {
  const diff = Date.now() - new Date(dt).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins} мин. назад`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} ч. назад`;
  const days = Math.floor(hours / 24);
  return `${days} дн. назад`;
}

function RecentErrorsTable({ errors }: { errors: RecentError[] }) {
  return (
    <div className="rounded-2xl border border-zinc-800/60 bg-zinc-900 p-5">
      <h3 className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-4">
        Последние ошибки
      </h3>
      {errors.length === 0 ? (
        <div className="text-sm text-zinc-600 py-4">Нет ошибок</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800">
                <th className="text-left px-3 py-2 text-[10px] text-zinc-500 uppercase tracking-wider font-medium">URL</th>
                <th className="text-left px-3 py-2 text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Платформа</th>
                <th className="text-left px-3 py-2 text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Ошибка</th>
                <th className="text-left px-3 py-2 text-[10px] text-zinc-500 uppercase tracking-wider font-medium">Когда</th>
              </tr>
            </thead>
            <tbody>
              {errors.map((err, i) => (
                <tr key={i} className="border-b border-zinc-800/30 hover:bg-zinc-800/20 transition-colors">
                  <td className="px-3 py-2 max-w-[200px]">
                    {err.share_token ? (
                      <a href={`/share/${err.share_token}`} target="_blank" rel="noopener noreferrer"
                        className="text-zinc-400 font-mono text-xs truncate block hover:text-zinc-200 transition-colors"
                        title={err.url}>{err.url.length > 40 ? err.url.slice(0, 40) + "…" : err.url}</a>
                    ) : (
                      <span className="text-zinc-400 font-mono text-xs truncate block" title={err.url}>
                        {err.url.length > 40 ? err.url.slice(0, 40) + "…" : err.url}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-xs ${PLATFORM_COLORS[err.platform ?? ""] ?? "text-zinc-500"}`}>
                      {err.platform ?? "—"}
                    </span>
                  </td>
                  <td className="px-3 py-2 max-w-[300px]">
                    <span className="text-xs text-red-400/80 truncate block" title={err.error ?? ""}>
                      {err.error ? (err.error.length > 60 ? err.error.slice(0, 60) + "…" : err.error) : "—"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-zinc-500 whitespace-nowrap">{timeAgo(err.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Main Dashboard ──────────────────────────────────────────────────────

export function AdminDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [analytics, setAnalytics] = useState<AdminAnalytics | null>(null);
  const [costs, setCosts] = useState<CostAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<number | null>(null);
  const [reextracting, setReextracting] = useState(false);
  const [reextractResult, setReextractResult] = useState<{ missing: number; total: number } | null>(null);
  const [repairingThumbs, setRepairingThumbs] = useState(false);
  const [thumbRepairResult, setThumbRepairResult] = useState<{ fixed: number; still_broken: number } | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [avatarUploading, setAvatarUploading] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const [demoMode, setDemoMode] = useState(false);
  const [demoToggling, setDemoToggling] = useState(false);

  function reloadFinancials() {
    setError(null);
    getAdminStats()
      .then(setStats)
      .catch((e) => setError(e?.response?.data?.detail ?? e.message ?? "Ошибка загрузки"));
    getAdminCostAnalytics()
      .then(setCosts)
      .catch((e) => console.warn("cost-analytics not available:", e));
  }

  useEffect(() => {
    let done = 0;
    const total = 3;
    const check = () => { if (++done === total) setLoading(false); };

    getAdminStats()
      .then(setStats)
      .catch((e) => setError(e?.response?.data?.detail ?? e.message ?? "Ошибка загрузки"))
      .finally(check);

    getAdminAnalytics()
      .then(setAnalytics)
      .catch((e) => setError(e?.response?.data?.detail ?? e.message ?? "Ошибка загрузки"))
      .finally(check);

    getAdminCostAnalytics()
      .then(setCosts)
      .catch((e) => console.warn("cost-analytics not available:", e))
      .finally(check);

    getDemoMode().then((r) => setDemoMode(r.enabled)).catch(() => {});
  }, []);

  async function handleToggleDemo() {
    setDemoToggling(true);
    try {
      const res = await apiSetDemoMode(!demoMode);
      setDemoMode(res.enabled);
      reloadFinancials();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e?.response?.data?.detail ?? e?.message ?? "Не удалось переключить демо-режим");
    } finally {
      setDemoToggling(false);
    }
  }

  useEffect(() => {
    adminGetFounderAvatar().then((res) => setAvatarUrl(res.url)).catch(() => {});
  }, []);

  async function handleAvatarUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarUploading(true);
    try {
      await adminUploadFounderAvatar(file);
      const res = await adminGetFounderAvatar();
      setAvatarUrl(res.url);
    } catch (err) { console.error("Avatar upload failed:", err); }
    setAvatarUploading(false);
    if (avatarInputRef.current) avatarInputRef.current.value = "";
  }

  async function handleCleanup() {
    setCleaning(true);
    setCleanupResult(null);
    try { const res = await adminCleanupGhosts(); setCleanupResult(res.deleted); }
    finally { setCleaning(false); }
  }

  async function handleReextractFrames() {
    setReextracting(true);
    setReextractResult(null);
    try { const res = await adminReextractFrames(); setReextractResult({ missing: res.missing_frames, total: res.total_completed }); }
    finally { setReextracting(false); }
  }

  async function handleRepairThumbnails() {
    setRepairingThumbs(true);
    setThumbRepairResult(null);
    try { const res = await repairThumbnails(); setThumbRepairResult({ fixed: res.thumbnails_fixed, still_broken: res.still_broken }); }
    finally { setRepairingThumbs(false); }
  }

  return (
    <div className="max-w-6xl">
      <div className="flex items-center justify-between gap-4 mb-8 flex-wrap">
        <h1 className="text-2xl font-serif font-medium text-zinc-100 flex items-center gap-3">
          Панель управления
          {demoMode && (
            <span className="px-2 py-0.5 rounded-md bg-amber-500/15 border border-amber-500/40 text-amber-400 text-[11px] font-semibold uppercase tracking-wider">
              Demo
            </span>
          )}
        </h1>
        <button
          onClick={handleToggleDemo}
          disabled={demoToggling}
          title="Демо-режим: показывает синтетические цифры (≈500K ₽/мес) для презентации. Данные генерируются на лету, в БД ничего не пишется."
          className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors disabled:opacity-50 ${
            demoMode
              ? "bg-amber-500/15 border-amber-500/40 text-amber-300 hover:bg-amber-500/25"
              : "bg-zinc-800/60 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
          }`}
        >
          <span className={`w-2 h-2 rounded-full ${demoMode ? "bg-amber-400 animate-pulse" : "bg-zinc-600"}`} />
          Демо-режим: {demoMode ? "вкл" : "выкл"}
        </button>
      </div>

      {loading ? (
        <div className="text-zinc-500 text-sm">Загрузка...</div>
      ) : (
        <>
          {error && (
            <div className="mb-6 px-4 py-3 rounded-xl border border-red-800/40 bg-red-900/10 text-red-400 text-sm">
              {error}
            </div>
          )}

          {/* ═══ SECTION: Финансы ═══ */}
          {costs && (
            <>
              <div className="mb-10">
                <h2 className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-4 flex items-center gap-2">
                  <span className="w-1 h-4 bg-emerald-500 rounded-full" />
                  Финансы
                </h2>

                {/* Revenue row */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
                  <FinanceCard
                    label="Доход сегодня"
                    value={formatRub(costs.revenue_today_rub)}
                    subtitle={costs.revenue_today_eur > 0 ? `+ ${formatEur(costs.revenue_today_eur)}` : undefined}
                    change={pctChangeRevenue(costs.revenue_today_rub, costs.revenue_yesterday_rub)}
                    accent="text-emerald-400"
                  />
                  <FinanceCard
                    label="Доход вчера"
                    value={formatRub(costs.revenue_yesterday_rub)}
                    accent="text-zinc-300"
                  />
                  <FinanceCard
                    label="Доход за месяц"
                    value={formatRub(costs.revenue_month_rub)}
                    subtitle={costs.revenue_month_eur > 0 ? `+ ${formatEur(costs.revenue_month_eur)}` : undefined}
                    accent="text-emerald-400"
                  />
                  <FinanceCard
                    label="MRR"
                    value={formatRub(costs.mrr_rub)}
                    subtitle={costs.mrr_eur > 0 ? `+ ${formatEur(costs.mrr_eur)}` : undefined}
                    accent="text-blue-400"
                  />
                </div>

                {/* Costs row */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
                  <FinanceCard
                    label="Расход сегодня"
                    value={formatUsd(costs.today.total_usd)}
                    subtitle={`${costs.today.jobs_count} анализов`}
                    change={pctChange(costs.today.total_usd, costs.yesterday.total_usd)}
                  />
                  <FinanceCard
                    label="Расход вчера"
                    value={formatUsd(costs.yesterday.total_usd)}
                    subtitle={`${costs.yesterday.jobs_count} анализов`}
                  />
                  <FinanceCard
                    label="Расход за месяц"
                    value={formatUsd(costs.month.total_usd)}
                    subtitle={`${costs.month.jobs_count} анализов`}
                  />
                  <FinanceCard
                    label="Себестоимость рилса"
                    value={costs.avg_per_reel_usd > 0 ? formatUsd(costs.avg_per_reel_usd) : "—"}
                    subtitle={costs.paid_users > 0 ? `${formatUsd(costs.cost_per_paid_user_usd)}/платящий` : undefined}
                    accent="text-amber-400"
                  />
                </div>

                {/* Cost breakdown + Apify budget */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-4">
                  <CostBreakdownBar period={costs.today} label="Структура затрат — сегодня" />
                  {costs.apify_budget ? (
                    <ApifyBudgetGauge budget={costs.apify_budget} />
                  ) : (
                    <CostBreakdownBar period={costs.month} label="Структура затрат — месяц" />
                  )}
                </div>

                {/* Cost sparkline */}
                {costs.daily_costs.length > 0 && (
                  <CostSparkline data={costs.daily_costs} />
                )}
              </div>
            </>
          )}

          {/* ═══ SECTION: Пользователи ═══ */}
          <div className="mb-8">
            <h2 className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-4 flex items-center gap-2">
              <span className="w-1 h-4 bg-blue-500 rounded-full" />
              Пользователи
            </h2>
            <div className="grid grid-cols-4 lg:grid-cols-7 gap-3">
              <StatCard title="Всего" value={stats?.total_users} />
              <StatCard title="Анонимных" value={stats?.anonymous_users} accent="text-zinc-400" />
              <StatCard title="REGISTERED" value={stats?.registered_users} accent="text-blue-400" />
              <StatCard title="FREE" value={stats?.free_users} accent="text-emerald-400" />
              <StatCard title="START" value={stats?.start_users} accent="text-violet-400" />
              <StatCard title="PRO" value={stats?.pro_users} accent="text-amber-400" />
              <StatCard title="UNLIMITED" value={stats?.unlimited_users} accent="text-rose-400" />
            </div>
          </div>

          {/* ═══ SECTION: Джобы ═══ */}
          <div className="mb-8">
            <h2 className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-4 flex items-center gap-2">
              <span className="w-1 h-4 bg-amber-500 rounded-full" />
              Джобы
            </h2>
            <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
              <StatCard title="Всего" value={stats?.total_jobs} />
              <StatCard title="Сегодня" value={stats?.jobs_today} />
              <StatCard title="В процессе" value={stats?.jobs_running} accent="text-amber-400" />
              <StatCard title="Завершено" value={stats?.jobs_completed} accent="text-emerald-400" />
              <StatCard title="Упало" value={stats?.jobs_failed} accent="text-red-400" />
              <StatCard title="Упало сегодня" value={stats?.jobs_failed_today} accent="text-orange-400" />
            </div>
          </div>

          {/* ═══ SECTION: Библиотека ═══ */}
          <div className="mb-8">
            <div className="grid grid-cols-3 gap-3">
              <StatCard title="Рилсов в библиотеке" value={stats?.library_reels} />
              {costs && <StatCard title="Платящих пользователей" value={costs.paid_users} accent="text-emerald-400" />}
              {costs && costs.all_time.jobs_count > 0 && (
                <FinanceCard
                  label="Все расходы"
                  value={formatUsd(costs.all_time.total_usd)}
                  subtitle={`${costs.all_time.jobs_count} анализов за всё время`}
                />
              )}
            </div>
          </div>

          {/* ═══ SECTION: Аналитика ═══ */}
          {analytics && (
            <>
              <div className="mb-8">
                <h2 className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-4 flex items-center gap-2">
                  <span className="w-1 h-4 bg-violet-500 rounded-full" />
                  Аналитика
                </h2>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  <JobsChart data={analytics.jobs_per_day} />
                  <UsersChart data={analytics.users_per_day} />
                </div>
              </div>

              <div className="mb-8">
                <h2 className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-4">Здоровье платформ (14 дней)</h2>
                <PlatformHealthCards data={analytics.platform_health} />
              </div>

              <div className="mb-8">
                <RecentErrorsTable errors={analytics.recent_errors} />
              </div>
            </>
          )}

          {/* ═══ SECTION: Обслуживание ═══ */}
          <div className="border-t border-zinc-800/50 pt-8 mt-8">
            <h2 className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-4 flex items-center gap-2">
              <span className="w-1 h-4 bg-zinc-600 rounded-full" />
              Обслуживание
            </h2>

            {/* Founder Avatar */}
            <div className="flex items-center gap-4 mb-6">
              {avatarUrl ? (
                <img src={avatarUrl} alt="Founder" className="w-12 h-12 rounded-full object-cover border border-zinc-700" />
              ) : (
                <div className="w-12 h-12 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center text-zinc-600 text-xs">—</div>
              )}
              <div>
                <input ref={avatarInputRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={handleAvatarUpload} />
                <button onClick={() => avatarInputRef.current?.click()} disabled={avatarUploading}
                  className="px-3 py-1.5 text-xs border border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 rounded-lg transition-colors disabled:opacity-50">
                  {avatarUploading ? "Загрузка..." : avatarUrl ? "Заменить аватар" : "Загрузить аватар"}
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button onClick={handleCleanup} disabled={cleaning}
                className="px-3 py-1.5 text-xs border border-zinc-700 text-zinc-400 hover:border-red-800/70 hover:text-red-400 rounded-lg transition-colors disabled:opacity-50">
                {cleaning ? "Удаление..." : "Очистить ghost-пользователей"}
              </button>
              {cleanupResult !== null && <span className="text-xs text-emerald-400">Удалено: {cleanupResult}</span>}

              <button onClick={handleReextractFrames} disabled={reextracting}
                className="px-3 py-1.5 text-xs border border-zinc-700 text-zinc-400 hover:border-blue-800/70 hover:text-blue-400 rounded-lg transition-colors disabled:opacity-50">
                {reextracting ? "Запуск..." : "Восстановить кадры"}
              </button>
              {reextractResult !== null && (
                <span className="text-xs text-emerald-400">
                  {reextractResult.missing === 0 ? `Все на месте (${reextractResult.total})` : `Запущено: ${reextractResult.missing}/${reextractResult.total}`}
                </span>
              )}

              <button onClick={handleRepairThumbnails} disabled={repairingThumbs}
                className="px-3 py-1.5 text-xs border border-zinc-700 text-zinc-400 hover:border-violet-800/70 hover:text-violet-400 rounded-lg transition-colors disabled:opacity-50">
                {repairingThumbs ? "Ремонт..." : "Починить картинки трендов"}
              </button>
              {thumbRepairResult !== null && (
                <span className="text-xs text-emerald-400">
                  {thumbRepairResult.still_broken === 0 ? `Все ОК (${thumbRepairResult.fixed})` : `${thumbRepairResult.fixed} / ещё ${thumbRepairResult.still_broken}`}
                </span>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
