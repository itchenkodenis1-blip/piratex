import { getFrameUrl } from "../api/client";
import { SCENE_TYPE_COLORS } from "../constants/sceneTypes";
import { useTranslation } from "../i18n";
import type { Translations } from "../i18n/types";
import type { FrameAnalysis } from "../types";

interface Props {
  frame: FrameAnalysis;
  jobId: string;
}

export function FrameCard({ frame, jobId }: Props) {
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
            className={`px-2 py-0.5 text-xs rounded-full ${
              SCENE_TYPE_COLORS[frame.scene_type] || SCENE_TYPE_COLORS.b_roll
            }`}
          >
            {t[`scene_${frame.scene_type}` as keyof Translations] || frame.scene_type}
          </span>
        </div>
      </div>

      <div className="p-4 space-y-3">
        {frame.transcript_segment && (
          <div>
            <p className="text-xs text-cream-muted uppercase tracking-wide mb-1">
              {t.frame_speech}
            </p>
            <p className="text-sm text-cream italic">
              "{frame.transcript_segment}"
            </p>
          </div>
        )}

        {frame.screen_text && frame.screen_text.length > 0 && (
          <div>
            <p className="text-xs text-cream-muted uppercase tracking-wide mb-1">
              {t.frame_text_on_screen}
            </p>
            <p className="text-sm text-cream-dim">
              {frame.screen_text.join(" | ")}
            </p>
          </div>
        )}

        <div>
          <p className="text-xs text-cream-muted uppercase tracking-wide mb-1">
            {t.frame_visual}
          </p>
          <p className="text-sm text-cream-muted">{frame.visual_description}</p>
        </div>

        {frame.ui_elements && frame.ui_elements.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {frame.ui_elements.map((el, i) => (
              <span
                key={i}
                className="px-2 py-0.5 bg-surface-light text-cream-muted text-xs rounded-full"
              >
                {el}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
