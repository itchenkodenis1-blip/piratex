import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  addToShootingQueue,
  bookmarkReel,
  checkInShootingQueue,
  generateScript,
  getFrameUrl,
  getLibraryReel,
  getSettings,
  removeFromShootingQueue,
  rewriteScript,
  translateScript,
  unbookmarkReel,
  updateScript,
  updateTranslation,
} from "../api/client";
import type {
  FrameAnalysis,
  LibraryReelDetail as ReelDetail,
  ScriptTranslation,
  UserScript,
} from "../types";
import { AdaptationSummary } from "./AdaptationSummary";
import { ScriptGenerationProgress } from "./ScriptGenerationProgress";
import { ScriptRatingWidget } from "./ScriptRatingWidget";
import { TranscriptPanel } from "./TranscriptPanel";
import { useTranslation } from "../i18n";
import { useAuth } from "../hooks/useAuth";
import { useLikes } from "../hooks/useLikes";
import { SCENE_TYPE_COLORS } from "../constants/sceneTypes";
import type { Translations } from "../i18n/types";

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function LibraryFrameCard({
  frame,
  jobId,
}: {
  frame: FrameAnalysis;
  jobId: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="bg-surface border border-border-subtle rounded-2xl overflow-hidden">
      <div className="relative">
        <img
          src={getFrameUrl(jobId, frame.frame_index)}
          alt={`Frame ${frame.frame_index}`}
          className="w-full aspect-[9/16] object-contain bg-black"
          loading="lazy"
        />
        <div className="absolute top-2 left-2 flex gap-2">
          <span className="px-2 py-0.5 bg-black/70 text-cream text-xs rounded-full font-mono">
            {frame.timecode}
          </span>
          <span
            className={`px-2 py-0.5 text-xs rounded ${
              SCENE_TYPE_COLORS[frame.scene_type] || SCENE_TYPE_COLORS.b_roll
            }`}
          >
            {t[`scene_${frame.scene_type}` as keyof Translations] || frame.scene_type}
          </span>
        </div>
      </div>

      <div className="p-3 space-y-2">
        {frame.transcript_segment && (
          <div>
            <p className="text-[10px] text-cream-muted uppercase tracking-wider">
              {t.frame_speech}
            </p>
            <p className="text-xs text-cream italic leading-relaxed">
              &ldquo;{frame.transcript_segment}&rdquo;
            </p>
          </div>
        )}
        {frame.screen_text.length > 0 && (
          <div>
            <p className="text-[10px] text-cream-muted uppercase tracking-wider">
              {t.frame_text_on_screen}
            </p>
            <p className="text-xs text-cream-dim">
              {frame.screen_text.join(" | ")}
            </p>
          </div>
        )}
        <div>
          <p className="text-[10px] text-cream-muted uppercase tracking-wider">
            {t.frame_visual}
          </p>
          <p className="text-xs text-cream-muted leading-relaxed">
            {frame.visual_description}
          </p>
        </div>
      </div>
    </div>
  );
}

export function LibraryReelDetailPage({ backPath = "/library" }: { backPath?: string } = {}) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [reel, setReel] = useState<ReelDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bookmarked, setBookmarked] = useState(false);
  const [titleExpanded, setTitleExpanded] = useState(false);
  const { user } = useAuth();
  const { isLiked, toggleLike } = useLikes();
  const [inShootingQueue, setInShootingQueue] = useState(false);
  const [shootingQueueItemId, setShootingQueueItemId] = useState<string | null>(null);
  const [queueLoading, setQueueLoading] = useState(false);

  // Script state
  const [userScript, setUserScript] = useState<UserScript | null>(null);
  const [scriptLoading, setScriptLoading] = useState(false);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  const [activeHookIndex, setActiveHookIndex] = useState(0);

  // Second-language translation state
  const [translations, setTranslations] = useState<ScriptTranslation[]>([]);
  const [secondLanguage, setSecondLanguage] = useState<string | null>(null);
  const [isTranslating, setIsTranslating] = useState(false);
  const [translationError, setTranslationError] = useState<string | null>(null);

  const fetchReel = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getLibraryReel(id);
      setReel(data);
      setBookmarked(data.is_bookmarked);
      setUserScript(data.user_script);
      setActiveHookIndex(data.user_script?.active_hook_index ?? 0);
      setTranslations(data.translations ?? []);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      setError(status === 404 ? t.library_reel_not_found : t.library_reel_error);
    } finally {
      setLoading(false);
    }
  }, [id, t]);

  useEffect(() => {
    fetchReel();
  }, [fetchReel]);

  // Resolve the user's configured second language (for the translate button)
  useEffect(() => {
    if (!user) return;
    getSettings()
      .then((s) => setSecondLanguage(s.profile?.second_language ?? null))
      .catch(() => {});
  }, [user]);

  // The translation to display: prefer the configured second language,
  // otherwise fall back to whatever translation already exists (e.g. auto-generated).
  const displayLanguage =
    secondLanguage ?? (translations.length > 0 ? translations[0].language : null);
  const displayTranslation =
    translations.find((tr) => tr.language === displayLanguage) ?? null;

  const upsertTranslation = (tr: ScriptTranslation) => {
    setTranslations((prev) => {
      const next = prev.filter((x) => x.language !== tr.language);
      return [...next, tr];
    });
  };

  const handleTranslate = async () => {
    if (!id || !displayLanguage) return;
    setIsTranslating(true);
    setTranslationError(null);
    try {
      const tr = await translateScript(id, displayLanguage);
      upsertTranslation(tr);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setTranslationError(detail || t.summary_translation_error);
    } finally {
      setIsTranslating(false);
    }
  };

  const persistTranslationField = async (
    field: "script" | "description" | "editor_instructions",
    value: string,
  ) => {
    if (!id || !displayTranslation) return;
    const updated = await updateTranslation(id, displayTranslation.language, { [field]: value });
    upsertTranslation(updated);
  };

  // Check shooting queue status (admin only)
  useEffect(() => {
    if (!reel?.job_id || !user?.is_admin) return;
    checkInShootingQueue(reel.job_id)
      .then((res) => {
        setInShootingQueue(res.in_queue);
        setShootingQueueItemId(res.item_id);
      })
      .catch(() => {});
  }, [reel?.job_id, user?.is_admin]);

  const handleToggleShootingQueue = async () => {
    if (!reel?.job_id) return;
    setQueueLoading(true);
    try {
      if (inShootingQueue && shootingQueueItemId) {
        await removeFromShootingQueue(shootingQueueItemId);
        setInShootingQueue(false);
        setShootingQueueItemId(null);
      } else {
        const res = await addToShootingQueue(reel.job_id);
        setInShootingQueue(true);
        setShootingQueueItemId(res.item_id);
      }
    } catch {
      // ignore
    } finally {
      setQueueLoading(false);
    }
  };

  const handleCopyShareLink = () => {
    if (!reel?.share_token) return;
    const url = `${window.location.origin}/share/${reel.share_token}`;
    navigator.clipboard.writeText(url);
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 2000);
  };

  const handleBookmark = async () => {
    if (!id) return;
    try {
      if (bookmarked) {
        await unbookmarkReel(id);
        setBookmarked(false);
      } else {
        await bookmarkReel(id);
        setBookmarked(true);
      }
    } catch {
      // ignore
    }
  };

  const handleGenerateScript = async () => {
    if (!id) return;
    setScriptLoading(true);
    setScriptError(null);
    try {
      const script = await generateScript(id);
      setUserScript(script);
    } catch (err: unknown) {
      let msg = t.script_generation_error;
      if (err && typeof err === "object" && "response" in err) {
        const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
        if (detail) msg = detail;
      }
      setScriptError(msg);
    } finally {
      setScriptLoading(false);
    }
  };

  const handleRewriteScript = async () => {
    if (!id) return;
    setScriptLoading(true);
    setScriptError(null);
    try {
      const script = await rewriteScript(id);
      setUserScript(script);
    } catch (err: unknown) {
      let msg = t.script_rewrite_error;
      if (err && typeof err === "object" && "response" in err) {
        const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
        if (detail) msg = detail;
      }
      setScriptError(msg);
    } finally {
      setScriptLoading(false);
    }
  };

  const handleHookSwap = async (newIndex: number, newScript: string) => {
    if (!id) return;
    try {
      const updated = await updateScript(id, { script: newScript, active_hook_index: newIndex });
      setUserScript(updated);
      setActiveHookIndex(newIndex);
    } catch {
      // silently fail — user can retry
    }
  };

  if (loading) {
    return (
      <div className="text-center py-20">
        <div className="inline-flex items-center gap-3 px-5 py-3 bg-surface border border-border-subtle rounded-full">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cream opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cream-dim" />
          </span>
          <span className="text-sm text-cream-muted">{t.library_reel_loading}</span>
        </div>
      </div>
    );
  }

  if (error || !reel) {
    return (
      <div className="text-center py-20 space-y-4">
        <p className="text-red-400">{error || t.library_reel_error}</p>
        <button
          onClick={() => navigate(backPath)}
          className="px-4 py-2 bg-surface-light hover:bg-border-subtle rounded-full text-sm border border-border-subtle text-cream-dim hover:text-cream transition-colors"
        >
          {t.library_reel_back}
        </button>
      </div>
    );
  }

  const frames = (reel.frames_json || []) as FrameAnalysis[];

  return (
    <div className="w-full max-w-5xl mx-auto space-y-10">
      {/* Back + actions */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <button
          onClick={() => navigate(backPath)}
          className="text-sm text-cream-muted hover:text-cream transition-colors"
        >
          {`\u2190 ${t.library_reel_back_arrow}`}
        </button>
        <div className="flex items-center gap-2 sm:gap-3">
          {reel?.share_token && (
            <button
              onClick={handleCopyShareLink}
              className="px-4 py-2 text-sm rounded-full transition-colors border bg-surface text-cream-dim border-border-subtle hover:border-cream-muted/30 flex items-center gap-1.5"
            >
              {linkCopied ? (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                  {t.share_link_copied}
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" /><path strokeLinecap="round" strokeLinejoin="round" d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.102 1.101" /></svg>
                  {t.share_copy_link}
                </>
              )}
            </button>
          )}
          <button
            onClick={handleBookmark}
            className={`px-4 py-2 text-sm rounded-full transition-colors border ${
              bookmarked
                ? "bg-cream text-[#0C0C0C] border-cream font-medium"
                : "bg-surface text-cream-dim border-border-subtle hover:border-cream-muted/30"
            }`}
          >
            {bookmarked ? t.library_reel_bookmarked : t.library_reel_save}
          </button>
        </div>
      </div>

      {/* Metadata — compact header */}
      <div className="space-y-3">
        {/* Line 1: platform · author · duration · lang · format */}
        <div className="flex items-center justify-center gap-2 text-sm text-cream-dim flex-wrap">
          {reel.video_platform && (
            <span className="px-2.5 py-0.5 bg-surface-light border border-border-subtle text-cream-dim rounded-full text-[11px] font-medium uppercase tracking-wide">
              {reel.video_platform}
            </span>
          )}
          {reel.video_author && (
            <span className="text-cream font-medium">{reel.video_author}</span>
          )}
          {reel.video_duration != null && (
            <>
              <span className="text-border-subtle">·</span>
              <span className="font-mono text-xs">{formatDuration(reel.video_duration)}</span>
            </>
          )}
          {reel.original_language && (
            <>
              <span className="text-border-subtle">·</span>
              <span className="text-xs text-cream-muted uppercase">{reel.original_language}</span>
            </>
          )}
          {reel.content_format && (
            <>
              <span className="text-border-subtle">·</span>
              <span className="text-xs text-cream-muted">{reel.content_format}</span>
            </>
          )}
          {/* Stats inline */}
          {(reel.video_views ?? 0) > 0 || (reel.video_likes ?? 0) > 0 || (reel.video_comments ?? 0) > 0 ? (
            <>
              <span className="text-border-subtle">·</span>
              <span className="text-xs text-cream-muted">
                {[
                  reel.video_views != null && reel.video_views > 0 && `${formatNumber(reel.video_views)} ${t.results_views}`,
                  reel.video_likes != null && reel.video_likes > 0 && `${formatNumber(reel.video_likes)} ${t.results_likes}`,
                  reel.video_comments != null && reel.video_comments > 0 && `${formatNumber(reel.video_comments)} ${t.results_comments}`,
                ].filter(Boolean).join("  ·  ")}
              </span>
            </>
          ) : null}
          {/* Source link icon */}
          {reel.url && (
            <>
              <span className="text-border-subtle">·</span>
              <a
                href={reel.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-cream-muted hover:text-cream transition-colors"
                title={reel.url}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </a>
            </>
          )}
        </div>

        {/* Title — compact */}
        {reel.video_title && (
          <div className="text-center">
            <h1
              className={`text-lg sm:text-xl font-serif font-medium text-cream leading-snug ${
                !titleExpanded ? "line-clamp-2" : ""
              }`}
            >
              {reel.video_title}
            </h1>
            {reel.video_title.length > 120 && (
              <button
                onClick={() => setTitleExpanded((v) => !v)}
                className="mt-1 text-xs text-cream-muted hover:text-cream transition-colors"
              >
                {titleExpanded ? t.strategy_show_less : t.strategy_show_more}
              </button>
            )}
          </div>
        )}

        {/* Tags — collapsed, max 4 visible */}
        {reel.tags.length > 0 && (
          <div className="flex flex-wrap items-center justify-center gap-1.5">
            {reel.tags.slice(0, 4).map((tag) => (
              <span
                key={tag.id}
                className="px-2 py-0.5 bg-surface-light/50 text-cream-muted text-[11px] rounded-full"
              >
                {tag.display_name}
              </span>
            ))}
            {reel.tags.length > 4 && (
              <span className="px-2 py-0.5 text-cream-muted/50 text-[11px]">
                +{reel.tags.length - 4}
              </span>
            )}
          </div>
        )}
      </div>

      {/* My Script Section */}
      <section className="space-y-5">
        <div className="flex items-center gap-3">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
          <h2 className="text-sm font-medium text-cream uppercase tracking-widest shrink-0">
            {t.library_reel_my_script}
          </h2>
          {reel?.url && (
            <button
              onClick={() => toggleLike(reel.url)}
              className={`w-8 h-8 flex items-center justify-center rounded-full transition-colors shrink-0 ${
                isLiked(reel.url)
                  ? "bg-red-500/20 text-red-400"
                  : "bg-surface text-cream-muted hover:text-cream"
              }`}
              title={isLiked(reel.url) ? "Unlike" : "Like"}
            >
              <svg
                className="w-4 h-4"
                viewBox="0 0 24 24"
                fill={isLiked(reel.url) ? "currentColor" : "none"}
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
              </svg>
            </button>
          )}
          {user?.is_admin && reel?.job_id && (
            <button
              onClick={handleToggleShootingQueue}
              disabled={queueLoading}
              className={`h-8 px-3 flex items-center gap-1.5 rounded-full text-xs font-medium transition-colors shrink-0 ${
                inShootingQueue
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                  : "bg-surface text-cream-muted hover:text-cream border border-border-subtle hover:border-cream-muted/30"
              }`}
              title={inShootingQueue ? "Убрать из очереди" : "В работу"}
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                {inShootingQueue ? (
                  <><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></>
                ) : (
                  <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M12 8v8" /><path d="M8 12h8" /></>
                )}
              </svg>
              {inShootingQueue ? "В очереди" : "В работу"}
            </button>
          )}
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
        </div>

        {/* Script rating */}
        {reel.job_id && (
          <ScriptRatingWidget jobId={reel.job_id} compact />
        )}

        {scriptError && (
          <p className="text-center text-sm text-red-400">{scriptError}</p>
        )}

        {userScript ? (
          <div className="space-y-4">
            <AdaptationSummary
              summary={{
                script: userScript.script,
                description: userScript.description,
                editor_instructions: userScript.editor_instructions,
              }}
              strategy={reel?.hook_variants ? { hook_variants: reel.hook_variants, virality_breakdown: "", comments_strategy: {}, hashtags: reel.hashtags ?? { primary: [], secondary: [] } } : undefined}
              activeHookIndex={activeHookIndex}
              onHookSwap={handleHookSwap}
              primaryHookScore={reel?.primary_hook_score ?? undefined}
              primaryHookWhy={reel?.primary_hook_why ?? undefined}
              originalPrimaryHook={reel?.original_primary_hook ?? undefined}
              jobId={reel.job_id}
              onFieldRefined={async (field, value) => {
                setUserScript((prev) => prev ? { ...prev, [field]: value } : prev);
                if (id) {
                  try {
                    await updateScript(id, { [field]: value });
                  } catch {
                    // persist failed — text is still updated in memory
                  }
                }
              }}
              onFieldSave={async (field, value) => {
                if (!id) return;
                const updated = await updateScript(id, { [field]: value });
                setUserScript(updated);
              }}
              secondLanguage={displayLanguage}
              translation={displayTranslation}
              isTranslating={isTranslating}
              translationError={translationError}
              onTranslate={handleTranslate}
              onTranslationFieldRefined={async (field, value) => {
                if (displayTranslation) {
                  upsertTranslation({ ...displayTranslation, [field]: value, stale: false });
                }
                try {
                  await persistTranslationField(field, value);
                } catch {
                  // persist failed — text is still updated in memory
                }
              }}
              onTranslationFieldSave={persistTranslationField}
            />
            {scriptLoading ? (
              <ScriptGenerationProgress />
            ) : (
              <div className="flex justify-center gap-3">
                <button
                  onClick={() => {
                    if (window.confirm(t.library_reel_rewrite_confirm || "Текущий сценарий будет переписан. Продолжить?")) {
                      handleRewriteScript();
                    }
                  }}
                  className="px-6 py-2.5 text-sm bg-surface-light hover:bg-border-subtle text-cream-dim hover:text-cream rounded-full transition-colors border border-border-subtle"
                >
                  {t.library_reel_rewrite}
                </button>
              </div>
            )}
          </div>
        ) : scriptLoading ? (
          <ScriptGenerationProgress />
        ) : (
          <div className="text-center space-y-3 py-6">
            <p className="text-sm text-cream-muted">{t.library_reel_no_script_yet}</p>
            <button
              onClick={handleGenerateScript}
              className="px-6 py-2.5 text-sm bg-cream text-[#0C0C0C] hover:bg-cream-dim rounded-full font-medium transition-colors"
            >
              {t.library_reel_write_script}
            </button>
          </div>
        )}
      </section>

      {/* Frames */}
      {frames.length > 0 && (
        <section className="space-y-5">
          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
            <h2 className="text-sm font-medium text-cream-muted uppercase tracking-widest shrink-0">
              {t.results_frame_breakdown} &middot; {frames.length}
            </h2>
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
            {frames.map((frame) => (
              <LibraryFrameCard
                key={frame.frame_index}
                frame={frame}
                jobId={reel.job_id}
              />
            ))}
          </div>
        </section>
      )}

      {/* Transcript */}
      {reel.transcript_json && reel.transcript_json.length > 0 && (
        <section className="space-y-5">
          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
            <h2 className="text-sm font-medium text-cream-muted uppercase tracking-widest shrink-0">
              {t.results_transcript}
            </h2>
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
          </div>

          <TranscriptPanel segments={reel.transcript_json} />
        </section>
      )}
    </div>
  );
}
