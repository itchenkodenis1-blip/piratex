import { useCallback, useEffect, useRef, useState } from "react";
import type { PipelineComment } from "../../types";
import { COLUMN_CONFIG } from "./constants";
import type { ProductionStatus } from "../../types";

interface CommentThreadProps {
  comments: PipelineComment[];
  onSubmit: (text: string) => Promise<void>;
  loading?: boolean;
}

export function CommentThread({ comments, onSubmit, loading }: CommentThreadProps) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll when new comments arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [comments.length]);

  const handleSubmit = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed || sending) return;

    setSending(true);
    try {
      await onSubmit(trimmed);
      setText("");
    } finally {
      setSending(false);
    }
  }, [text, sending, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleDateString("ru-RU", {
      day: "numeric",
      month: "short",
    }) + " " + d.toLocaleTimeString("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getStageBadge = (stage: string) => {
    const config = COLUMN_CONFIG[stage as ProductionStatus];
    if (!config) return null;
    return (
      <span className="text-[10px] bg-white/5 text-cream-muted px-1.5 py-0.5 rounded-full">
        {config.emoji} {config.label}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-cream-muted text-sm">
        Loading comments...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Comment list */}
      <div className="flex-1 overflow-y-auto space-y-3 min-h-0">
        {comments.length === 0 && (
          <p className="text-sm text-cream-muted/50 text-center py-8">
            No comments yet
          </p>
        )}

        {comments.map((c) => (
          <div key={c.id} className="bg-white/[0.03] rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1.5">
              {/* Avatar circle */}
              <div className="w-6 h-6 rounded-full bg-violet-500/20 flex items-center justify-center text-[10px] text-violet-300 font-medium shrink-0">
                {(c.author_name || "U")[0].toUpperCase()}
              </div>
              <span className="text-xs font-medium text-cream truncate">
                {c.author_name || "User"}
              </span>
              {getStageBadge(c.stage)}
              <span className="text-[10px] text-cream-muted/60 ml-auto whitespace-nowrap">
                {formatDate(c.created_at)}
              </span>
            </div>
            <p className="text-sm text-cream/80 whitespace-pre-wrap pl-8">
              {c.text}
            </p>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="mt-3 flex gap-2 shrink-0">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Add a comment..."
          rows={1}
          className="flex-1 bg-white/[0.04] border border-white/10 rounded-lg px-3 py-2 text-sm text-cream placeholder:text-cream-muted/40 resize-none focus:outline-none focus:border-violet-500/50"
        />
        <button
          onClick={handleSubmit}
          disabled={!text.trim() || sending}
          className="px-3 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm rounded-lg transition-colors shrink-0"
        >
          {sending ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}
