import { useState } from "react";
import { useTranslation } from "../i18n";
import type { TranscriptSegment } from "../types";

interface Props {
  segments: TranscriptSegment[];
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function TranscriptPanel({ segments }: Props) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const fullText = segments.map((s) => s.text).join(" ");

  const handleCopy = async () => {
    await navigator.clipboard.writeText(fullText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-surface border border-border-subtle rounded-2xl overflow-hidden">
      <div className="flex items-center justify-between px-3 sm:px-5 py-3 sm:py-3.5 border-b border-border-subtle">
        <h3 className="text-sm font-medium text-cream">
          {t.transcript_title} ({segments.length})
        </h3>
        <button
          onClick={handleCopy}
          className="px-3 py-1 text-xs font-medium rounded-full transition-colors cursor-pointer
            bg-surface-light border border-border-subtle text-cream-dim hover:text-cream hover:border-cream-muted"
        >
          {copied ? t.transcript_copied : t.transcript_copy}
        </button>
      </div>

      <div className="p-3 sm:p-5 space-y-1.5 max-h-80 overflow-y-auto">
        {segments.map((seg, i) => (
          <div key={i} className="flex gap-3 text-sm leading-relaxed">
            <span className="text-cream-muted font-mono shrink-0 select-none w-10 text-right">
              {formatTime(seg.start)}
            </span>
            <span className="text-cream-dim">{seg.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
