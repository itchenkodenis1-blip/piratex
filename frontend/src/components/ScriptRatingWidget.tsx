import { useEffect, useState } from "react";
import { rateJob } from "../api/client";
import { useTranslation } from "../i18n";

interface Props {
  jobId: string;
  initialRating?: number | null;
  compact?: boolean;
  onRated?: (rating: number) => void;
}

function StarIcon({ filled, size }: { filled: boolean; size: string }) {
  return (
    <svg viewBox="0 0 24 24" className={size} fill="none">
      <path
        d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function ScriptRatingWidget({ jobId, initialRating, compact, onRated }: Props) {
  const { t } = useTranslation();
  const [rating, setRating] = useState<number>(initialRating || 0);
  const [hoveredStar, setHoveredStar] = useState(0);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(!!initialRating);
  const [showComment, setShowComment] = useState(false);
  const [sending, setSending] = useState(false);
  const [thanksFade, setThanksFade] = useState(false);

  // Auto-fetch rating if not provided (e.g. on library page)
  useEffect(() => {
    if (initialRating != null) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    fetch(`/api/jobs/${jobId}/rating`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data?.rating) {
          setRating(data.rating);
          setSubmitted(true);
        }
      })
      .catch(() => {});
  }, [jobId, initialRating]);

  const starSize = compact ? "w-4.5 h-4.5" : "w-7 h-7";

  const handleStarClick = async (star: number) => {
    setRating(star);
    if (star === 5) {
      setSending(true);
      try {
        await rateJob(jobId, star);
        setSubmitted(true);
        setThanksFade(true);
        setTimeout(() => setThanksFade(false), 3000);
        onRated?.(star);
      } catch { /* ignore */ }
      setSending(false);
    } else {
      setShowComment(true);
    }
  };

  const handleSubmit = async () => {
    if (!rating) return;
    setSending(true);
    try {
      await rateJob(jobId, rating, comment || undefined);
      setSubmitted(true);
      setShowComment(false);
      setThanksFade(true);
      setTimeout(() => setThanksFade(false), 3000);
      onRated?.(rating);
    } catch { /* ignore */ }
    setSending(false);
  };

  return (
    <div className={compact ? "flex flex-col items-center gap-2" : "py-6"}>
      {/* Label — only in non-compact mode */}
      {!compact && (
        <div className="flex items-center gap-3 mb-4">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
          <span className="text-sm font-medium text-cream-muted uppercase tracking-widest shrink-0">
            {t.rating_title}
          </span>
          <div className="h-px flex-1 bg-gradient-to-r from-border-subtle via-transparent to-transparent" />
        </div>
      )}

      {/* Stars + thanks inline */}
      <div className={`flex items-center gap-${compact ? "2" : "3"} ${compact ? "" : "flex-col"}`}>
        <div className={`flex items-center gap-${compact ? "1.5" : "1"}`}>
          {compact && !submitted && !thanksFade && (
            <span className="text-xs text-cream-muted/60 mr-1">{t.rating_title}</span>
          )}
          {[1, 2, 3, 4, 5].map((star) => (
            <button
              key={star}
              type="button"
              className={`transition-colors duration-150 ${
                star <= (hoveredStar || rating)
                  ? "text-amber-400"
                  : "text-zinc-600 hover:text-zinc-400"
              } ${submitted && !showComment ? "pointer-events-none" : "cursor-pointer"}`}
              onMouseEnter={() => !submitted && setHoveredStar(star)}
              onMouseLeave={() => setHoveredStar(0)}
              onClick={() => !submitted && handleStarClick(star)}
              disabled={sending}
            >
              <StarIcon filled={star <= (hoveredStar || rating)} size={starSize} />
            </button>
          ))}
          {thanksFade && (
            <span className="text-xs text-cream-muted/60 ml-1 animate-in fade-in duration-300">
              {t.rating_thanks}
            </span>
          )}
        </div>
      </div>

      {/* Comment textarea (shown if rating < 5) */}
      {showComment && !submitted && (
        <div className={`space-y-2 animate-in fade-in slide-in-from-top-2 duration-200 ${compact ? "w-full" : "w-full max-w-md"}`}>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={t.rating_comment_placeholder}
            rows={2}
            className="w-full bg-white/[0.03] border border-border-subtle rounded-lg px-3 py-2 text-sm text-cream placeholder:text-cream-muted/50 resize-none focus:outline-none focus:border-cream-muted/40"
          />
          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleSubmit}
              disabled={sending}
              className="px-4 py-1.5 text-xs font-medium bg-cream text-[#0C0C0C] rounded-full hover:bg-cream-dim transition-colors disabled:opacity-40"
            >
              {sending ? "..." : t.rating_submit}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
