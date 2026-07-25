import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getShootingQueue,
  removeFromShootingQueue,
  shootingQueueMarkDone,
  getFrameUrl,
} from "../api/client";
import type { ShootingQueueItem } from "../api/client";
import { Teleprompter } from "./Teleprompter";

// ── Queue Card ──────────────────────────────────────────────────

function QueueCard({
  item,
  onRemove,
  filmed,
}: {
  item: ShootingQueueItem;
  onRemove: (id: string) => void;
  filmed?: boolean;
}) {
  const navigate = useNavigate();
  const thumbUrl = getFrameUrl(item.job_id, 0);

  return (
    <div className={`flex items-center gap-4 bg-surface border rounded-2xl p-4 group ${
      filmed ? "border-emerald-500/30 opacity-80" : "border-border-subtle"
    }`}>
      {/* Filmed badge */}
      {filmed && (
        <div className="w-6 shrink-0 flex items-center justify-center">
          <svg className="w-5 h-5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6L9 17l-5-5" />
          </svg>
        </div>
      )}

      {/* Thumbnail */}
      <div
        className="w-16 h-16 rounded-xl overflow-hidden bg-surface-light shrink-0 cursor-pointer"
        onClick={() => navigate(`/library/${item.library_reel_id}`)}
      >
        <img
          src={thumbUrl}
          alt={item.video_title || ""}
          className="w-full h-full object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = "none";
          }}
        />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-cream truncate">
          {item.video_title || item.url}
        </p>
        {item.video_author && (
          <p className="text-xs text-cream-muted mt-0.5">@{item.video_author}</p>
        )}
      </div>

      {/* Remove button */}
      <button
        onClick={() => onRemove(item.id)}
        className="w-8 h-8 flex items-center justify-center rounded-full text-cream-muted hover:text-red-400 hover:bg-red-500/10 transition-colors shrink-0 sm:opacity-0 sm:group-hover:opacity-100"
        title="Убрать"
      >
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 6L6 18" /><path d="M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// ── Filming Mode ────────────────────────────────────────────────

function FilmingInterstitial({
  item,
  current,
  total,
  onStart,
  onSkip,
  onExit,
}: {
  item: ShootingQueueItem;
  current: number;
  total: number;
  onStart: () => void;
  onSkip: () => void;
  onExit: () => void;
}) {
  const shortTitle = (item.video_title || "Без названия").split("\n")[0].slice(0, 80) + ((item.video_title || "").length > 80 ? "…" : "");

  return (
    <div className="fixed inset-0 z-[9999] bg-[#0a0a0a] flex flex-col items-center justify-center text-center px-6">
      <div className="absolute top-6 left-0 right-0 flex items-center justify-center gap-3">
        <span className="text-cream-muted text-sm font-mono">
          {current} из {total}
        </span>
        <div className="w-32 h-1 bg-surface-light rounded-full overflow-hidden">
          <div
            className="h-full bg-cream rounded-full transition-all duration-300"
            style={{ width: `${(current / total) * 100}%` }}
          />
        </div>
      </div>

      <button
        onClick={onExit}
        className="absolute top-5 right-5 w-10 h-10 flex items-center justify-center rounded-full text-cream-muted hover:text-cream hover:bg-surface-light transition-colors"
      >
        <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 6L6 18" /><path d="M6 6l12 12" />
        </svg>
      </button>

      <div className="space-y-2 mb-8 max-w-sm">
        <div className="text-5xl">🎬</div>
        {item.video_author && (
          <p className="text-cream-muted text-sm">@{item.video_author}</p>
        )}
        <p className="text-base text-cream/70 line-clamp-2">
          {shortTitle}
        </p>
      </div>

      <div className="flex items-center gap-4">
        <button
          onClick={onStart}
          className="px-8 py-3 bg-cream text-[#0C0C0C] hover:bg-cream-dim font-semibold rounded-full text-base transition-colors"
        >
          ▶ Начать
        </button>
        <button
          onClick={onSkip}
          className="px-6 py-3 text-cream-muted hover:text-cream text-sm transition-colors"
        >
          Пропустить →
        </button>
      </div>
    </div>
  );
}

function FilmingComplete({
  total,
  onClose,
}: {
  total: number;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[9999] bg-[#0a0a0a] flex flex-col items-center justify-center text-center px-6">
      <div className="space-y-4 mb-8">
        <div className="text-6xl">✅</div>
        <h2 className="text-2xl font-bold text-cream">Все снято!</h2>
        <p className="text-cream-muted">
          {total} {total === 1 ? "ролик" : total < 5 ? "ролика" : "роликов"} готово
        </p>
      </div>
      <button
        onClick={onClose}
        className="px-8 py-3 bg-cream text-[#0C0C0C] hover:bg-cream-dim font-semibold rounded-full text-base transition-colors"
      >
        Готово
      </button>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────

type FilmingState =
  | { mode: "list" }
  | { mode: "interstitial"; index: number }
  | { mode: "teleprompter"; index: number }
  | { mode: "complete"; filmed: number };

export function ShootingQueuePage() {
  const [items, setItems] = useState<ShootingQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filming, setFilming] = useState<FilmingState>({ mode: "list" });

  const pending = useMemo(() => items.filter((i) => !i.filmed_at), [items]);
  const filmed = useMemo(() => items.filter((i) => !!i.filmed_at), [items]);

  const fetchQueue = useCallback(async () => {
    try {
      const data = await getShootingQueue();
      setItems(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  const handleRemove = async (itemId: string) => {
    setItems((prev) => prev.filter((i) => i.id !== itemId));
    try {
      await removeFromShootingQueue(itemId);
    } catch {
      fetchQueue();
    }
  };

  const handleStartFilming = () => {
    if (pending.length === 0) return;
    setFilming({ mode: "interstitial", index: 0 });
  };

  const handleTeleprompterStart = (index: number) => {
    setFilming({ mode: "teleprompter", index });
  };

  const handleShot = async (index: number) => {
    const item = pending[index];
    // Mark done on backend (sets filmed_at)
    try {
      await shootingQueueMarkDone(item.id);
    } catch {
      // ignore
    }

    // Move item to filmed locally
    setItems((prev) =>
      prev.map((i) =>
        i.id === item.id ? { ...i, filmed_at: new Date().toISOString() } : i
      )
    );

    const nextIndex = index + 1;

    if (nextIndex >= pending.length) {
      setFilming({ mode: "complete", filmed: pending.length });
    } else {
      // Next pending item is now at `index` (since current was just filmed)
      setFilming({ mode: "interstitial", index });
    }
  };

  const handleSkip = (index: number) => {
    const nextIndex = index + 1;
    if (nextIndex >= pending.length) {
      setFilming({ mode: "list" });
    } else {
      setFilming({ mode: "interstitial", index: nextIndex });
    }
  };

  const handleExitFilming = () => {
    setFilming({ mode: "list" });
    fetchQueue();
  };

  // ── Filming modes ──────────────────────────────────────────
  if (filming.mode === "interstitial") {
    const item = pending[filming.index];
    if (!item) {
      setFilming({ mode: "complete", filmed: pending.length });
      return null;
    }
    return (
      <FilmingInterstitial
        item={item}
        current={filming.index + 1}
        total={pending.length}
        onStart={() => handleTeleprompterStart(filming.index)}
        onSkip={() => handleSkip(filming.index)}
        onExit={handleExitFilming}
      />
    );
  }

  if (filming.mode === "teleprompter") {
    const item = pending[filming.index];
    if (!item) {
      setFilming({ mode: "list" });
      return null;
    }
    return (
      <>
        <Teleprompter
          text={item.script_text}
          onClose={() => setFilming({ mode: "interstitial", index: filming.index })}
        />
        {/* Floats top-center, below the progress bar and clear of the
            teleprompter's bottom playback controls (Play/Pause is centered there).
            Left of the top-right close button — no collision on narrow screens. */}
        <div
          className="fixed top-0 left-0 right-0 z-[10000] flex justify-center pointer-events-none"
          style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top))" }}
        >
          <button
            onClick={() => handleShot(filming.index)}
            className="px-8 py-3 bg-emerald-500 hover:bg-emerald-400 text-white font-semibold rounded-full text-base transition-colors shadow-2xl pointer-events-auto"
          >
            ✓ Снято
          </button>
        </div>
      </>
    );
  }

  if (filming.mode === "complete") {
    return (
      <FilmingComplete
        total={filming.filmed}
        onClose={handleExitFilming}
      />
    );
  }

  // ── Queue list ─────────────────────────────────────────────
  return (
    <div className="max-w-2xl mx-auto py-8 px-4 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-cream">Очередь съёмки</h1>
          <p className="text-sm text-cream-muted mt-1">
            {pending.length === 0 && filmed.length === 0
              ? "Пусто — добавьте ролики через «В работу»"
              : pending.length > 0
                ? `${pending.length} к съёмке${filmed.length > 0 ? `, ${filmed.length} снято` : ""}`
                : `${filmed.length} снято`}
          </p>
        </div>
        {pending.length > 0 && (
          <button
            onClick={handleStartFilming}
            className="px-6 py-2.5 bg-cream text-[#0C0C0C] hover:bg-cream-dim font-semibold rounded-full text-sm transition-colors"
          >
            🎬 Погнали
          </button>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="text-cream-muted text-sm">Загрузка...</div>
        </div>
      )}

      {/* Empty state */}
      {!loading && items.length === 0 && (
        <div className="text-center py-16 space-y-3">
          <div className="text-5xl">📋</div>
          <p className="text-cream-muted text-sm">
            Зайдите в анализ любого ролика и нажмите «В работу»
          </p>
        </div>
      )}

      {/* Pending items */}
      {!loading && pending.length > 0 && (
        <div className="space-y-3">
          {pending.map((item) => (
            <QueueCard key={item.id} item={item} onRemove={handleRemove} />
          ))}
        </div>
      )}

      {/* Filmed items */}
      {!loading && filmed.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-3 pt-4">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-emerald-500/30 to-transparent" />
            <span className="text-xs font-medium text-emerald-400 uppercase tracking-widest shrink-0">
              Снято ({filmed.length})
            </span>
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-emerald-500/30 to-transparent" />
          </div>
          {filmed.map((item) => (
            <QueueCard key={item.id} item={item} onRemove={handleRemove} filmed />
          ))}
        </div>
      )}
    </div>
  );
}

export default ShootingQueuePage;
