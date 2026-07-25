import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminGetRatingDetail, adminListRatings } from "../../api/client";
import type { AdminRatingDetail, AdminRatingItem } from "../../types";
import MaskedPII from "./MaskedPII";

function StarDisplay({ rating }: { rating: number }) {
  return (
    <span className="inline-flex gap-0.5">
      {[1, 2, 3, 4, 5].map((s) => (
        <span key={s} className={s <= rating ? "text-amber-400" : "text-zinc-700"}>
          ★
        </span>
      ))}
    </span>
  );
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <span className="text-zinc-500 shrink-0 w-40">{label}</span>
      <span className="text-zinc-200">{children}</span>
    </div>
  );
}

function RatingDetailPanel({ detail: d, navigate }: { detail: AdminRatingDetail; navigate: ReturnType<typeof useNavigate> }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-5 bg-zinc-900/50 border border-zinc-800 rounded-lg text-sm">
      {/* Left column: Video + User */}
      <div className="space-y-5">
        {/* Video info */}
        <div>
          <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">Видео</h4>
          <div className="space-y-1">
            <InfoRow label="Название">{d.video_title || "—"}</InfoRow>
            <InfoRow label="Платформа">{d.video_platform || "—"}</InfoRow>
            <InfoRow label="Автор">{d.video_author || "—"}</InfoRow>
            <InfoRow label="Длительность">
              {d.video_duration ? `${Math.round(d.video_duration)}с` : "—"}
            </InfoRow>
            <InfoRow label="Статистика">
              {fmt(d.video_views)} просм. / {fmt(d.video_likes)} лайк. / {fmt(d.video_comments)} комм.
            </InfoRow>
            {d.job_url && (
              <InfoRow label="URL">
                <a href={d.job_url} target="_blank" rel="noreferrer" className="text-blue-400 hover:text-blue-300 break-all">
                  {d.job_url}
                </a>
              </InfoRow>
            )}
          </div>
        </div>

        {/* User info */}
        <div>
          <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">Пользователь</h4>
          <div className="space-y-1">
            <InfoRow label="Email / TG">
              <button onClick={() => navigate(`/admin/users/${d.user_id}`)} className="text-blue-400 hover:text-blue-300">
                {d.user_email ? <MaskedPII type="email" value={d.user_email} /> : d.user_telegram ? <MaskedPII type="telegram" value={d.user_telegram} /> : d.user_name ? <MaskedPII type="name" value={d.user_name} /> : d.user_id.slice(0, 8)}
              </button>
            </InfoRow>
            <InfoRow label="Тариф">{d.user_tier || "—"}</InfoRow>
            <InfoRow label="Регистрация">
              {d.user_registered_at ? new Date(d.user_registered_at).toLocaleDateString("ru-RU") : "—"}
            </InfoRow>
          </div>
        </div>

        {/* User presets */}
        {d.user_profile && Object.keys(d.user_profile).length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">Пресеты пользователя</h4>
            <div className="space-y-1">
              {d.user_profile.about_me ? (
                <InfoRow label="О себе">
                  <span className="line-clamp-3">{String(d.user_profile.about_me)}</span>
                </InfoRow>
              ) : null}
              {d.user_profile.tone ? <InfoRow label="Тон">{String(d.user_profile.tone)}</InfoRow> : null}
              {d.user_profile.niches ? (
                <InfoRow label="Ниши">{(d.user_profile.niches as string[]).join(", ")}</InfoRow>
              ) : null}
              {d.user_profile.forbidden_words ? (
                <InfoRow label="Запрещённые слова">{String(d.user_profile.forbidden_words)}</InfoRow>
              ) : null}
              {d.user_profile.script_cta ? <InfoRow label="CTA скрипта">{String(d.user_profile.script_cta)}</InfoRow> : null}
              {d.user_profile.video_format ? <InfoRow label="Формат видео">{String(d.user_profile.video_format)}</InfoRow> : null}
              {d.user_profile.content_prompt_additions ? (
                <InfoRow label="Доп. инструкции">
                  <span className="line-clamp-3">{String(d.user_profile.content_prompt_additions)}</span>
                </InfoRow>
              ) : null}
            </div>
          </div>
        )}

        {/* Timing */}
        <div>
          <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">Обработка</h4>
          <div className="space-y-1">
            <InfoRow label="Создан">
              {d.job_created_at ? new Date(d.job_created_at).toLocaleString("ru-RU") : "—"}
            </InfoRow>
            <InfoRow label="Завершён">
              {d.job_completed_at ? new Date(d.job_completed_at).toLocaleString("ru-RU") : "—"}
            </InfoRow>
            <InfoRow label="Время обработки">
              {d.processing_seconds != null ? (
                <span className={d.processing_seconds > 120 ? "text-amber-400" : ""}>
                  {Math.round(d.processing_seconds)}с
                  {d.processing_seconds > 120 && " (долго!)"}
                </span>
              ) : "—"}
            </InfoRow>
          </div>
        </div>

        {/* Reel stats */}
        <div>
          <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">Популярность рила</h4>
          <div className="space-y-1">
            <InfoRow label="Первый разбор">
              {d.reel_first_parsed_at ? new Date(d.reel_first_parsed_at).toLocaleDateString("ru-RU") : "—"}
            </InfoRow>
            <InfoRow label="Кем впервые">{d.reel_submitted_by_email || "—"}</InfoRow>
            <InfoRow label="Всего разборов">{d.total_jobs_for_reel}</InfoRow>
            <InfoRow label="Всего сценариев">{d.total_scripts_for_reel}</InfoRow>
            {d.library_reel_id && (
              <InfoRow label="Библиотека">
                <button
                  onClick={() => navigate(`/admin/library/${d.library_reel_id}`)}
                  className="text-blue-400 hover:text-blue-300"
                >
                  Открыть рил
                </button>
              </InfoRow>
            )}
          </div>
        </div>
      </div>

      {/* Right column: Script + Others */}
      <div className="space-y-5">
        {/* The script user rated */}
        {d.adaptation_summary && (
          <div>
            <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">Сценарий (оценённый)</h4>
            {d.adaptation_summary.script && (
              <div className="bg-zinc-800/50 rounded-lg p-3 mb-2 max-h-64 overflow-y-auto">
                <pre className="whitespace-pre-wrap text-zinc-200 text-xs leading-relaxed font-sans">
                  {d.adaptation_summary.script}
                </pre>
              </div>
            )}
            {d.adaptation_summary.description && (
              <div className="mt-2">
                <span className="text-zinc-500 text-xs">Описание: </span>
                <span className="text-zinc-300 text-xs">{d.adaptation_summary.description}</span>
              </div>
            )}
            {d.adaptation_summary.hook_variants && d.adaptation_summary.hook_variants.length > 0 && (
              <div className="mt-2">
                <span className="text-zinc-500 text-xs block mb-1">Варианты хуков:</span>
                <div className="space-y-1">
                  {d.adaptation_summary.hook_variants.map((h, i) => (
                    <div key={i} className="text-xs flex gap-2">
                      <span className="text-amber-400 shrink-0">{h.score}%</span>
                      <span className="text-zinc-300">{h.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Other ratings for same reel */}
        {d.other_ratings.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">
              Другие оценки этого рила ({d.other_ratings.length})
            </h4>
            <div className="space-y-1.5">
              {d.other_ratings.map((r, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <StarDisplay rating={r.rating} />
                  <span className="text-zinc-400">{r.user_email ? <MaskedPII type="email" value={r.user_email} /> : r.user_name ? <MaskedPII type="name" value={r.user_name} /> : "—"}</span>
                  {r.comment && <span className="text-zinc-500 truncate max-w-[200px]">"{r.comment}"</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Other scripts */}
        {d.other_scripts.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">
              Сценарии других пользователей ({d.other_scripts.length})
            </h4>
            <div className="space-y-2">
              {d.other_scripts.map((s, i) => (
                <div key={i} className="bg-zinc-800/30 rounded p-2">
                  <div className="text-xs text-zinc-500 mb-1">{s.user_email ? <MaskedPII type="email" value={s.user_email} /> : s.user_name ? <MaskedPII type="name" value={s.user_name} /> : "—"}</div>
                  <div className="text-xs text-zinc-300 line-clamp-3">{s.script_preview}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Comment (full) */}
        {d.comment && (
          <div>
            <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">Комментарий пользователя</h4>
            <div className="bg-zinc-800/50 rounded-lg p-3 text-zinc-200 text-sm">{d.comment}</div>
          </div>
        )}
      </div>
    </div>
  );
}

export function AdminRatings() {
  const navigate = useNavigate();
  const [items, setItems] = useState<AdminRatingItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [filterRating, setFilterRating] = useState<number | "">("");
  const [filterComments, setFilterComments] = useState(false);

  // Expandable detail
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailCache, setDetailCache] = useState<Record<string, AdminRatingDetail>>({});

  const perPage = 50;

  useEffect(() => {
    let cancelled = false;
    adminListRatings({
      rating: filterRating || undefined,
      has_comment: filterComments || undefined,
      page,
      per_page: perPage,
    })
      .then((res) => {
        if (!cancelled) {
          setItems(res.items);
          setTotal(res.total);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [page, filterRating, filterComments]);

  const toggleExpand = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    // Mark as viewed locally immediately
    setItems((prev) =>
      prev.map((it) => (it.id === id && !it.viewed_at ? { ...it, viewed_at: new Date().toISOString() } : it))
    );
    if (detailCache[id]) return;
    setDetailLoading(true);
    try {
      const detail = await adminGetRatingDetail(id);
      setDetailCache((prev) => ({ ...prev, [id]: detail }));
    } catch {
      // ignore
    } finally {
      setDetailLoading(false);
    }
  };

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1 className="text-xl font-semibold text-zinc-100">Оценки ({total})</h1>
        <div className="flex gap-3 items-center">
          <select
            value={filterRating}
            onChange={(e) => { setFilterRating(e.target.value ? Number(e.target.value) : ""); setPage(1); }}
            className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200"
          >
            <option value="">Все оценки</option>
            {[1, 2, 3, 4, 5].map((r) => (
              <option key={r} value={r}>{"★".repeat(r)} ({r})</option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
            <input
              type="checkbox"
              checked={filterComments}
              onChange={(e) => { setFilterComments(e.target.checked); setPage(1); }}
              className="accent-cream"
            />
            С комментариями
          </label>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-zinc-500 py-10">Загрузка...</div>
      ) : items.length === 0 ? (
        <div className="text-center text-zinc-500 py-10">Оценок пока нет</div>
      ) : (
        <div className="space-y-1">
          {/* Header */}
          <div className="grid grid-cols-[100px_1fr_1fr_100px_1fr] gap-2 px-3 py-2 text-xs text-zinc-500 border-b border-zinc-800">
            <div>Дата</div>
            <div>Пользователь</div>
            <div>Видео</div>
            <div>Оценка</div>
            <div>Комментарий</div>
          </div>

          {items.map((item) => (
            <div key={item.id}>
              {/* Row */}
              <button
                onClick={() => toggleExpand(item.id)}
                className={`w-full grid grid-cols-[100px_1fr_1fr_100px_1fr] gap-2 px-3 py-2.5 text-sm text-left rounded-lg transition-colors ${
                  expandedId === item.id ? "bg-zinc-800/60" : "hover:bg-zinc-800/30"
                } ${!item.viewed_at ? "border-l-2 border-l-amber-400/70" : ""}`}
              >
                <div className={`whitespace-nowrap ${!item.viewed_at ? "text-zinc-200 font-medium" : "text-zinc-400"}`}>
                  {new Date(item.created_at).toLocaleDateString("ru-RU")}
                  {!item.viewed_at && <span className="ml-1.5 inline-block w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />}
                </div>
                <div
                  className="text-blue-400 truncate"
                  onClick={(e) => { e.stopPropagation(); navigate(`/admin/users/${item.user_id}`); }}
                >
                  {item.user_email ? <MaskedPII type="email" value={item.user_email} /> : item.user_telegram ? <MaskedPII type="telegram" value={item.user_telegram} /> : item.user_name ? <MaskedPII type="name" value={item.user_name} /> : item.user_id.slice(0, 8)}
                </div>
                <div className="text-zinc-300 truncate">
                  {item.video_title || item.job_url || "—"}
                </div>
                <div>
                  <StarDisplay rating={item.rating} />
                </div>
                <div className="text-zinc-400 truncate">
                  {item.comment || <span className="text-zinc-600">—</span>}
                </div>
              </button>

              {/* Expandable detail */}
              {expandedId === item.id && (
                <div className="mt-1 mb-3 ml-3">
                  {detailLoading && !detailCache[item.id] ? (
                    <div className="text-zinc-500 text-sm py-4">Загрузка деталей...</div>
                  ) : detailCache[item.id] ? (
                    <RatingDetailPanel detail={detailCache[item.id]} navigate={navigate} />
                  ) : null}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 pt-4">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="px-3 py-1 text-sm bg-zinc-800 text-zinc-300 rounded hover:bg-zinc-700 disabled:opacity-30"
          >
            ←
          </button>
          <span className="px-3 py-1 text-sm text-zinc-400">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="px-3 py-1 text-sm bg-zinc-800 text-zinc-300 rounded hover:bg-zinc-700 disabled:opacity-30"
          >
            →
          </button>
        </div>
      )}
    </div>
  );
}
