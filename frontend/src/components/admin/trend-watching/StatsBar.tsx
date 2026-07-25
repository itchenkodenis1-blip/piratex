import { useEffect, useRef, useState } from "react";
import type { TrendWatchingStats, TrendWatchingSparklines } from "../../../types";

function useAnimatedNumber(target: number, duration = 1500): number {
  const [current, setCurrent] = useState(0);
  const startTime = useRef<number | null>(null);
  const startValue = useRef(0);
  const raf = useRef(0);

  useEffect(() => {
    startValue.current = current;
    startTime.current = null;
    cancelAnimationFrame(raf.current);
    const step = (ts: number) => {
      if (!startTime.current) startTime.current = ts;
      const elapsed = ts - startTime.current;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setCurrent(Math.round(startValue.current + (target - startValue.current) * eased));
      if (progress < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, duration]);
  return current;
}

function MiniSparkline({ data, color = "#A78BFA" }: { data: number[]; color?: string }) {
  if (data.length === 0 || data.every((v) => v === 0)) return <div className="h-8 w-full" />;
  const max = Math.max(...data, 1);
  const w = 200, h = 32, pad = 1;
  const pts = data.map((v, i) => ({
    x: pad + (i / (data.length - 1)) * (w - pad * 2),
    y: h - pad - (v / max) * (h - pad * 2),
  }));
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const area = `${line} L ${pts[pts.length - 1].x} ${h} L ${pts[0].x} ${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-8" preserveAspectRatio="none">
      <defs>
        <linearGradient id={`ms-${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#ms-${color.replace("#", "")})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function StatCard({
  label,
  value,
  sparkline,
  color,
  suffix,
}: {
  label: string;
  value: number;
  sparkline?: number[];
  color?: string;
  suffix?: string;
}) {
  const animated = useAnimatedNumber(value);
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 min-w-[140px] flex-1">
      <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">{label}</div>
      <div className="text-2xl font-mono font-semibold text-zinc-100">
        {animated.toLocaleString("ru-RU")}
        {suffix && <span className="text-sm text-zinc-500 ml-1">{suffix}</span>}
      </div>
      {sparkline && <MiniSparkline data={sparkline} color={color || "#A78BFA"} />}
    </div>
  );
}

function BudgetBar({ pct, usedUsd, remainingUsd }: { pct: number | null; usedUsd: number | null; remainingUsd: number | null }) {
  const val = pct ?? 0;
  const barColor = val > 50 ? "bg-emerald-500" : val > 20 ? "bg-amber-500" : "bg-red-500";
  const hasUsd = usedUsd != null && remainingUsd != null;
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 min-w-[140px] flex-1">
      <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">Apify</div>
      <div className="text-2xl font-mono font-semibold text-zinc-100">
        {hasUsd ? `$${usedUsd!.toFixed(1)}` : pct != null ? `${Math.round(pct)}%` : "—"}
      </div>
      {hasUsd && (
        <div className="text-[10px] text-zinc-500 font-mono">
          осталось ${remainingUsd!.toFixed(1)}
        </div>
      )}
      <div className="mt-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700 ${barColor}`} style={{ width: `${val}%` }} />
      </div>
    </div>
  );
}

export function StatsBar({
  stats,
  sparklines,
}: {
  stats: TrendWatchingStats | null;
  sparklines: TrendWatchingSparklines | null;
}) {
  if (!stats) {
    return (
      <div className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4 lg:mx-0 lg:px-0">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 min-w-[140px] flex-1 h-24 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4 lg:mx-0 lg:px-0">
      <StatCard label="Профили" value={stats.total_profiles} color="#8B5CF6" />
      <StatCard label="Сегодня" value={stats.checked_today} sparkline={sparklines?.checks_per_hour} color="#3B82F6" />
      <StatCard label="Очередь" value={stats.queue_size} color="#F59E0B" />
      <StatCard
        label="Обработка"
        value={stats.currently_scraping + stats.currently_analyzing}
        color="#6366F1"
      />
      <StatCard label="Тренды" value={stats.trends_found_today} sparkline={sparklines?.trends_per_hour} color="#F59E0B" />
      <StatCard
        label="Уведомления"
        value={stats.notifications_sent_today}
        sparkline={sparklines?.notifications_per_hour}
        color="#06B6D4"
      />
      <BudgetBar pct={stats.apify_balance_pct} usedUsd={stats.apify_used_usd} remainingUsd={stats.apify_remaining_usd} />
    </div>
  );
}
