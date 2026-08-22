import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getSharedJob, getSharedFrameUrl } from "../api/client";
import type { FrameAnalysis, SharedJobResult } from "../types";
import { AdaptationSummary } from "./AdaptationSummary";
import { useTranslation } from "../i18n";

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}


function KeyframesGallery({
  frames,
  token,
}: {
  frames: FrameAnalysis[];
  token: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-border-subtle rounded-2xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-3.5
          bg-surface hover:bg-surface-light transition-colors cursor-pointer"
      >
        <h3 className="text-sm font-medium text-cream flex items-center gap-2">
          <span
            className="inline-block transition-transform duration-200"
            style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}
          >
            ▸
          </span>
          {t.shared_page_keyframes}
          <span className="text-cream-muted font-normal">({frames.length})</span>
        </h3>
        <span className="text-xs text-cream-muted">
          {open ? t.strategy_show_less : t.strategy_show_more}
        </span>
      </button>
      {open && (
        <div className="px-5 py-4 border-t border-border-subtle bg-surface space-y-4">
          {frames.map((frame) => (
            <div
              key={frame.frame_index}
              className="flex gap-4 items-start"
            >
              <div className="shrink-0 w-36 sm:w-44">
                <img
                  src={getSharedFrameUrl(token, frame.frame_index)}
                  alt={`Frame ${frame.timecode}`}
                  className="w-full rounded-lg border border-border-subtle"
                  loading="lazy"
                />
              </div>
              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-cream-muted">
                    {frame.timecode}
                  </span>
                  <span className="px-2 py-0.5 bg-surface-light border border-border-subtle rounded-full text-[10px] font-medium text-cream-muted uppercase tracking-wide">
                    {t[`scene_${frame.scene_type}` as keyof typeof t] || frame.scene_type}
                  </span>
                </div>
                {frame.visual_description && (
                  <p className="text-sm text-cream-dim leading-relaxed">
                    {frame.visual_description}
                  </p>
                )}
                {frame.screen_text.length > 0 && (
                  <p className="text-xs text-cream-muted italic">
                    {frame.screen_text.join(" · ")}
                  </p>
                )}
                {frame.transcript_segment && (
                  <p className="text-xs text-cream-muted/70 leading-relaxed">
                    &ldquo;{frame.transcript_segment}&rdquo;
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function SharedScriptPage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [data, setData] = useState<SharedJobResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    getSharedJob(token)
      .then((result) => {
        // If the viewer is the owner, redirect to full library page
        if (result.library_reel_id) {
          navigate(`/library/${result.library_reel_id}`, { replace: true });
          return;
        }
        setData(result);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [token, navigate]);

  return (
    <div className="min-h-screen bg-[#0C0C0C] text-cream">
      {/* Header */}
      <header className="border-b border-border-subtle px-4 sm:px-6 md:px-8 py-3 sm:py-5">
        <a href="/" className="flex items-center gap-2 text-lg font-serif font-medium text-cream hover:text-cream-dim transition-colors">
          <img src="/logo.png" alt="ВидеоРентген" className="h-7 w-7" />
          ВидеоРентген
        </a>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 md:px-8 py-8 sm:py-12 md:py-16">
        {loading && (
          <div className="text-center py-20 text-cream-muted">
            {t.shared_page_loading}
          </div>
        )}

        {error && (
          <div className="text-center py-20 text-cream-dim">
            {t.shared_page_not_found}
          </div>
        )}

        {data && (
          <div className="space-y-10">
            {/* Video metadata */}
            <div className="text-center space-y-4">
              <div className="flex flex-wrap items-center justify-center gap-3 text-sm text-cream-dim">
                {data.video_platform && (
                  <span className="px-3 py-1 bg-surface-light border border-border-subtle text-cream-dim rounded-full text-xs font-medium uppercase tracking-wide">
                    {data.video_platform}
                  </span>
                )}
                {data.video_author && (
                  <span className="text-cream">{data.video_author}</span>
                )}
                {data.video_duration != null && (
                  <span className="font-mono">
                    {formatDuration(data.video_duration)}
                  </span>
                )}
              </div>
              {data.video_title && (
                <h1 className="text-3xl font-serif font-medium text-cream line-clamp-2">
                  {data.video_title}
                </h1>
              )}
              {/* Link to original reel */}
              {data.video_url && (
                <a
                  href={data.video_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-4 py-2 mt-2
                    bg-surface-light border border-border-subtle rounded-full
                    text-sm font-medium text-cream-dim hover:text-cream hover:border-cream-muted transition-colors"
                >
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                    <polyline points="15 3 21 3 21 9" />
                    <line x1="10" y1="14" x2="21" y2="3" />
                  </svg>
                  {t.shared_page_open_reference}
                </a>
              )}
            </div>

            {/* Script content — reuse AdaptationSummary */}
            <AdaptationSummary
              summary={{
                script: data.script,
                description: data.description,
                editor_instructions: data.editor_instructions,
              }}
            />

            {/* Keyframes gallery — collapsible */}
            {token && data.frames && data.frames.length > 0 && (
              <KeyframesGallery frames={data.frames} token={token} />
            )}

            {/* CTA block */}
            <div className="bg-surface border border-border-subtle rounded-2xl p-6 sm:p-8 text-center space-y-4">
              <h3 className="text-lg font-serif font-bold text-cream">
                Хотите такой же разбор для своего рилса?
              </h3>
              <p className="text-sm text-cream-dim max-w-md mx-auto">
                ВидеоРентген анализирует вирусные рилсы и создаёт готовые сценарии адаптации.
                Попробуйте бесплатно — без регистрации.
              </p>
              <a
                href="/"
                className="inline-block px-8 py-3 bg-cream text-[#0C0C0C] hover:bg-cream-dim text-sm font-semibold rounded-full transition-colors"
              >
                Проанализировать рилс бесплатно
              </a>
              <p className="text-xs text-cream-muted">
                3 бесплатных анализа в месяц для всех пользователей
              </p>
            </div>
          </div>
        )}
      </main>

      {/* Sticky bottom CTA bar */}
      {data && (
        <div className="sticky bottom-0 border-t border-border-subtle bg-[#0C0C0C]/95 backdrop-blur-sm px-4 py-3 text-center">
          <a
            href="/"
            className="inline-flex items-center gap-2 px-5 py-2 bg-cream text-[#0C0C0C] hover:bg-cream-dim text-sm font-medium rounded-full transition-colors"
          >
            Сделано в ВидеоРентген — попробуйте бесплатно
          </a>
        </div>
      )}
    </div>
  );
}
