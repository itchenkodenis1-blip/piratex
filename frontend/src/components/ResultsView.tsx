import { useMemo, useState } from "react";
import { updateJobFields } from "../api/client";
import { useTranslation } from "../i18n";
import type { JobResult } from "../types";
import { AdaptationSummary } from "./AdaptationSummary";
import { FrameCard } from "./FrameCard";
import { ScriptRatingWidget } from "./ScriptRatingWidget";

import { TeaserOverlay } from "./TeaserOverlay";
import { TelegramPromo } from "./TelegramPromo";
import { TranscriptPanel } from "./TranscriptPanel";

interface Props {
  result: JobResult;
  onFieldRefined?: (field: "script" | "description" | "editor_instructions", value: string) => void;
}

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

export function ResultsView({ result, onFieldRefined }: Props) {
  const { t } = useTranslation();
  const [activeHook, setActiveHook] = useState(0);
  const [localScript, setLocalScript] = useState<string | null>(null);
  const [localDescription, setLocalDescription] = useState<string | null>(null);
  const [localEditorInstructions, setLocalEditorInstructions] = useState<string | null>(null);

  // Stable original primary hook — never changes when user swaps hooks
  const originalPrimaryHook = useMemo(() => {
    const script = result.adaptation_summary?.script ?? "";
    const idx = script.indexOf("\n\n");
    return idx > 0 ? script.slice(0, idx) : script;
  }, [result.adaptation_summary?.script]);

  return (
    <div className="w-full max-w-6xl mx-auto space-y-12">
      {/* ── Section 1: Video metadata ── */}
      <div className="text-center space-y-4">
        <div className="flex flex-wrap items-center justify-center gap-3 text-sm text-cream-dim">
          {result.video_platform && (
            <span className="px-3 py-1 bg-surface-light border border-border-subtle text-cream-dim rounded-full text-xs font-medium uppercase tracking-wide">
              {result.video_platform}
            </span>
          )}
          {result.video_author && (
            <span className="text-cream">{result.video_author}</span>
          )}
          {result.video_duration != null && (
            <span className="font-mono">
              {formatDuration(result.video_duration)}
            </span>
          )}
          {result.video_views != null && result.video_views > 0 && (
            <span>{formatNumber(result.video_views)} {t.results_views}</span>
          )}
          {result.video_likes != null && result.video_likes > 0 && (
            <span>{formatNumber(result.video_likes)} {t.results_likes}</span>
          )}
        </div>

      </div>

      {/* Telegram promo — after seeing results */}
      {!result.is_teaser && <TelegramPromo variant="results" />}

      {/* ── Section 2: Ready-made adaptation — the main value ── */}
      {result.adaptation_summary && (
        <section className="space-y-5">
          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
            <h2 className="text-sm font-medium text-cream uppercase tracking-widest shrink-0">
              {t.results_final}
            </h2>
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
          </div>

          {/* Script rating — compact, right after heading */}
          {!result.is_teaser && result.status === "completed" && result.job_id && (
            <ScriptRatingWidget jobId={result.job_id} initialRating={result.my_rating} compact />
          )}

          <AdaptationSummary
            summary={{
              ...result.adaptation_summary,
              ...(localScript != null && { script: localScript }),
              ...(localDescription != null && { description: localDescription }),
              ...(localEditorInstructions != null && { editor_instructions: localEditorInstructions }),
            }}
            jobId={result.job_id}
            isTeaser={result.is_teaser}
            onFieldRefined={result.is_teaser ? undefined : (field, value) => {
              if (field === "script") setLocalScript(null);
              else if (field === "description") setLocalDescription(null);
              else if (field === "editor_instructions") setLocalEditorInstructions(null);
              onFieldRefined?.(field, value);
            }}
            onFieldSave={result.is_teaser ? undefined : async (field, value) => {
              if (field === "script") setLocalScript(value);
              else if (field === "description") setLocalDescription(value);
              else if (field === "editor_instructions") setLocalEditorInstructions(value);
              if (result.job_id) {
                await updateJobFields(result.job_id, { [field]: value });
              }
            }}
            activeHookIndex={activeHook}
            onHookSwap={result.is_teaser ? undefined : (idx, newScript) => {
              setActiveHook(idx);
              setLocalScript(newScript);
              if (result.job_id) {
                updateJobFields(result.job_id, { script: newScript }).catch(() => {});
              }
            }}
            originalPrimaryHook={originalPrimaryHook}
          />
        </section>
      )}

      {/* ── Section 3: Frame-by-frame breakdown ── */}
      {result.frames && result.frames.length > 0 && (
        <section className="space-y-5">
          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
            <h2 className="text-sm font-medium text-cream-muted uppercase tracking-widest shrink-0">
              {t.results_frame_breakdown} &middot; {result.is_teaser && result.teaser_limits ? result.teaser_limits.frames_total : result.frames.length}
            </h2>
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
            {result.frames.map((frame) => (
              <FrameCard
                key={frame.frame_index}
                frame={frame}
                jobId={result.job_id}
              />
            ))}
            {/* All frames shown — they showcase the product */}
          </div>

          {/* teaser_frames_hint removed — all frames are visible */}
        </section>
      )}

      {/* ── Section 4: Original transcript ── */}
      {result.transcript && result.transcript.length > 0 && (
        <section className="space-y-5">
          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
            <h2 className="text-sm font-medium text-cream-muted uppercase tracking-widest shrink-0">
              {t.results_transcript}
            </h2>
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
          </div>

          {result.is_teaser ? (
            <TeaserOverlay
              hint={result.teaser_limits
                ? (t.teaser_transcript_hint as string).replace("{pct}", String(result.teaser_limits.transcript_pct))
                : undefined}
            >
              <TranscriptPanel segments={result.transcript} />
            </TeaserOverlay>
          ) : (
            <TranscriptPanel segments={result.transcript} />
          )}
        </section>
      )}

    </div>
  );
}
