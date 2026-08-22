import { useEffect, useState, useCallback } from "react";
import {
  adminListTrendingReels,
  adminHideReel,
  adminBlockProfile,
} from "../../api/client";
import type { AdminTrendingReel, AdminTrendingReelsResponse } from "../../types";

function formatNumber(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toString();
}

function timeAgo(dt: string | null): string {
  if (!dt) return "—";
  const diff = Date.now() - new Date(dt).getTime();
  if (diff < 0) return "только что";
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins} мин назад`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}ч назад`;
  const days = Math.floor(hours / 24);
  return `${days}д назад`;
}

function platformIcon(platform: string): string {
  switch (platform) {
    case "instagram": return "📸";
    case "tiktok": return "🎵";
    case "youtube": return "▶️";
    default: return "🌐";
  }
}

const DATE_RANGES = [
  { value: "today", label: "Сегодня" },
  { value: "yesterday", label: "Вчера" },
  { value: "2days", label: "2 дня назад" },
  { value: "week", label: "Неделя" },
  { value: "all", label: "Все" },
];

const SORT_OPTIONS = [
  { value: "hot_score", label: "Hot Score" },
  { value: "x_factor", label: "Виральность" },
  { value: "views", label: "Просмотры" },
  { value: "recent", label: "Новые" },
];

export function AdminTrendingReels() {
  const [data, setData] = useState<AdminTrendingReelsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dateRange, setDateRange] = useState("today");
  const [niche, setNiche] = useState("");
  const [platform, setPlatform] = useState("");
  const [sort, setSort] = useState("hot_score");
  const [page, setPage] = useState(1);
  const perPage = 30;

  // Cached niches — populated once on initial load (before niche filter applied)
  const [cachedNiches, setCachedNiches] = useState<string[]>([]);

  // Modal state for hide action
  const [hideModal, setHideModal] = useState<{ reel: AdminTrendingReel } | null>(null);
  const [hideReason, setHideReason] = useState("");
  const [blockConfirm, setBlockConfirm] = useState<{ reel: AdminTrendingReel } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await adminListTrendingReels({
        date_range: dateRange,
        niche: niche || undefined,
        platform: platform || undefined,
        sort,
        page,
        per_page: perPage,
      });
      setData(result);
      // Cache niches on first load or when no niche filter is active
      if (!niche && result.summary.top_niches.length > 0) {
        setCachedNiches(result.summary.top_niches.map((n) => n.niche));
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [dateRange, niche, platform, sort, page]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [dateRange, niche, platform, sort]);

  const handleHide = async () => {
    if (!hideModal) return;
    try {
      await adminHideReel(hideModal.reel.id, hideReason);
      setHideModal(null);
      setHideReason("");
      load();
    } catch (e) {
      setError(`Ошибка скрытия: ${e}`);
      setHideModal(null);
    }
  };

  const handleBlock = async () => {
    if (!blockConfirm) return;
    try {
      await adminBlockProfile(blockConfirm.reel.author_id);
      setBlockConfirm(null);
      load();
    } catch (e) {
      setError(`Ошибка блокировки: ${e}`);
      setBlockConfirm(null);
    }
  };

  const totalPages = data ? Math.ceil(data.total / perPage) : 0;

  // Use cached niches (populated before any niche filter is applied)
  const availableNiches = cachedNiches;

  return (
    <div className="px-4 sm:px-6 py-6 max-w-[1400px]">
      <h1 className="text-2xl font-serif font-medium text-zinc-100 mb-6">
        Тренды — Рилсы
      </h1>

      {/* Summary */}
      {data?.summary && (
        <div className="flex flex-wrap gap-3 mb-6">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2.5">
            <div className="text-xs text-zinc-500">Найдено</div>
            <div className="text-lg font-medium text-zinc-100">{data.summary.total_trending}</div>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2.5">
            <div className="text-xs text-zinc-500">Ср. Hot Score</div>
            <div className="text-lg font-medium text-zinc-100">
              {data.summary.avg_hot_score != null ? data.summary.avg_hot_score.toFixed(3) : "—"}
            </div>
          </div>
          {data.summary.top_niches.slice(0, 3).map((ns) => (
            <div key={ns.niche} className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2.5">
              <div className="text-xs text-zinc-500">{ns.niche}</div>
              <div className="text-lg font-medium text-zinc-100">{ns.count}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* Date range */}
        <div className="flex bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
          {DATE_RANGES.map((d) => (
            <button
              key={d.value}
              onClick={() => setDateRange(d.value)}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                dateRange === d.value
                  ? "bg-zinc-100 text-zinc-900"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>

        {/* Niche filter */}
        <select
          value={niche}
          onChange={(e) => setNiche(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:ring-1 focus:ring-zinc-600"
        >
          <option value="">Все ниши</option>
          {availableNiches.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>

        {/* Platform filter */}
        <select
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:ring-1 focus:ring-zinc-600"
        >
          <option value="">Все платформы</option>
          <option value="instagram">Instagram</option>
          <option value="tiktok">TikTok</option>
          <option value="youtube">YouTube</option>
        </select>

        {/* Sort */}
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:ring-1 focus:ring-zinc-600"
        >
          {SORT_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="text-center py-10 text-red-400 text-sm border border-red-900/50 rounded-lg mb-4">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-center py-20 text-zinc-500">Загрузка...</div>
      )}

      {/* Empty state */}
      {!loading && data && data.items.length === 0 && (
        <div className="text-center py-20 text-zinc-500">
          Нет трендов за выбранный период
        </div>
      )}

      {/* Grid */}
      {!loading && data && data.items.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5 sm:gap-3">
            {data.items.map((reel) => (
              <TrendCard
                key={reel.id}
                reel={reel}
                onHide={() => setHideModal({ reel })}
                onBlock={() => setBlockConfirm({ reel })}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-6">
              <div className="text-xs text-zinc-500">
                Стр. {page} из {totalPages} ({data.total} всего)
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-800 rounded text-zinc-300 disabled:opacity-30 hover:bg-zinc-800"
                >
                  ←
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-800 rounded text-zinc-300 disabled:opacity-30 hover:bg-zinc-800"
                >
                  →
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Hide modal */}
      {hideModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setHideModal(null)}>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-zinc-100 font-medium mb-3">Скрыть тренд</h3>
            <p className="text-xs text-zinc-400 mb-4">
              Рилс @{hideModal.reel.author_username} будет скрыт из выдачи трендов.
            </p>
            <input
              type="text"
              placeholder="Причина (необязательно)"
              value={hideReason}
              onChange={(e) => setHideReason(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 mb-4 focus:outline-none focus:ring-1 focus:ring-zinc-600"
            />
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setHideModal(null)}
                className="px-4 py-2 text-xs text-zinc-400 hover:text-zinc-200"
              >
                Отмена
              </button>
              <button
                onClick={handleHide}
                className="px-4 py-2 text-xs bg-amber-600 hover:bg-amber-500 text-white rounded-lg"
              >
                Скрыть
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Block confirm */}
      {blockConfirm && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setBlockConfirm(null)}>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-zinc-100 font-medium mb-3">Заблокировать автора</h3>
            <p className="text-xs text-zinc-400 mb-4">
              Автор @{blockConfirm.reel.author_username} ({blockConfirm.reel.author_platform}) будет заблокирован.
              Все его рилсы перестанут отображаться в трендах.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setBlockConfirm(null)}
                className="px-4 py-2 text-xs text-zinc-400 hover:text-zinc-200"
              >
                Отмена
              </button>
              <button
                onClick={handleBlock}
                className="px-4 py-2 text-xs bg-red-600 hover:bg-red-500 text-white rounded-lg"
              >
                Заблокировать
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TrendCard({
  reel,
  onHide,
  onBlock,
}: {
  reel: AdminTrendingReel;
  onHide: () => void;
  onBlock: () => void;
}) {
  const [imgError, setImgError] = useState(false);
  const hotScorePercent = reel.hot_score != null ? Math.round(reel.hot_score * 100) : 0;
  const hotScoreColor =
    hotScorePercent >= 80 ? "bg-red-500" :
    hotScorePercent >= 50 ? "bg-amber-500" :
    "bg-zinc-500";

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden hover:border-zinc-700 transition-colors group">
      {/* Thumbnail */}
      <div className="relative aspect-[3/4] bg-zinc-800 overflow-hidden">
        {reel.thumbnail_url && !imgError ? (
          <img
            src={`/api/trends/thumbnail/${reel.id}`}
            alt=""
            className="w-full h-full object-cover"
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-zinc-600 text-3xl">
            🎬
          </div>
        )}
        {/* Hot score badge */}
        <div className="absolute top-2 right-2 bg-black/70 backdrop-blur-sm rounded-lg px-2 py-1">
          <span className="text-xs font-mono font-bold text-zinc-100">
            {reel.hot_score != null ? reel.hot_score.toFixed(3) : "—"}
          </span>
        </div>
        {/* X-factor badge */}
        {reel.x_factor != null && (
          <div className="absolute top-2 left-2 bg-amber-500/90 backdrop-blur-sm rounded-lg px-2 py-1">
            <span className="text-xs font-mono font-bold text-black">
              {reel.x_factor.toFixed(1)}×
            </span>
          </div>
        )}
        {/* Platform */}
        <div className="absolute bottom-2 left-2 bg-black/70 backdrop-blur-sm rounded-full px-2 py-0.5">
          <span className="text-xs">{platformIcon(reel.author_platform)}</span>
        </div>
      </div>

      {/* Content */}
      <div className="p-3">
        {/* Author */}
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-medium text-zinc-200 truncate">
            @{reel.author_username}
          </span>
          {reel.author_followers != null && (
            <span className="text-[10px] text-zinc-500">
              {formatNumber(reel.author_followers)} подп.
            </span>
          )}
        </div>

        {/* Caption */}
        {reel.caption && (
          <p className="text-[11px] text-zinc-400 line-clamp-2 mb-2 leading-relaxed">
            {reel.caption}
          </p>
        )}

        {/* Metrics row */}
        <div className="flex items-center gap-3 text-[11px] text-zinc-400 mb-2">
          <span title="Просмотры">👁 {formatNumber(reel.views)}</span>
          <span title="Лайки">❤️ {formatNumber(reel.likes)}</span>
          <span title="Комментарии">💬 {formatNumber(reel.comments)}</span>
        </div>

        {/* Trend metrics */}
        <div className="space-y-1.5 mb-3">
          {/* Hot Score bar */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-zinc-500 w-12">Hot</span>
            <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${hotScoreColor}`}
                style={{ width: `${hotScorePercent}%` }}
              />
            </div>
            <span className="text-[10px] text-zinc-400 font-mono w-8 text-right">
              {hotScorePercent}%
            </span>
          </div>
          {/* Velocity */}
          {reel.velocity != null && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-zinc-500 w-12">Скор.</span>
              <span className="text-[10px] text-zinc-300 font-mono">
                {formatNumber(Math.round(reel.velocity))}/ч
              </span>
            </div>
          )}
        </div>

        {/* Niche */}
        {reel.niche && (
          <div className="mb-2">
            <span className="inline-block text-[10px] bg-zinc-800 text-zinc-400 rounded-full px-2 py-0.5">
              {reel.niche}
            </span>
          </div>
        )}

        {/* Dates */}
        <div className="flex items-center justify-between text-[10px] text-zinc-500 mb-3">
          <span title="Опубликовано">{timeAgo(reel.published_at)}</span>
          {reel.trending_since && (
            <span title="Обнаружен как тренд" className="text-amber-500/70">
              🔥 {timeAgo(reel.trending_since)}
            </span>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <a
            href={reel.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 text-center text-[11px] py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg transition-colors"
          >
            Открыть
          </a>
          <button
            onClick={onHide}
            title="Скрыть тренд"
            className="px-2.5 py-1.5 text-[11px] bg-zinc-800 hover:bg-amber-900/50 text-zinc-400 hover:text-amber-400 rounded-lg transition-colors"
          >
            🙈
          </button>
          <button
            onClick={onBlock}
            title="Заблокировать автора"
            className="px-2.5 py-1.5 text-[11px] bg-zinc-800 hover:bg-red-900/50 text-zinc-400 hover:text-red-400 rounded-lg transition-colors"
          >
            🚫
          </button>
        </div>
      </div>
    </div>
  );
}
