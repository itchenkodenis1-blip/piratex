import { useState } from "react";
import { addMyAuthor } from "../api/client";
import { useTranslation } from "../i18n";

interface AddAuthorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdded: () => void;
}

export function AddAuthorModal({ isOpen, onClose, onAdded }: AddAuthorModalProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);
    try {
      await addMyAuthor(trimmed);
      setInput("");
      onAdded();
      onClose();
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      if (status === 404) {
        setError(t.trends_author_not_found);
      } else if (status === 400 && detail?.includes("limit")) {
        setError(t.trends_author_limit_reached);
      } else if (status === 400) {
        setError(detail || t.trends_error);
      } else {
        setError(t.trends_error);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-md mx-4 bg-surface border border-border-subtle rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-0">
          <h3 className="text-lg font-serif font-medium text-cream">{t.trends_add_author}</h3>
          <button
            onClick={onClose}
            className="text-cream-muted hover:text-cream transition-colors p-1"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="px-6 pb-6 pt-4 space-y-4">
          <div>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t.trends_add_author_placeholder}
              disabled={loading}
              className="w-full bg-surface border border-border-subtle rounded-lg px-4 py-2.5 text-sm text-cream placeholder:text-cream-dim focus:outline-none focus:ring-1 focus:ring-cream-muted disabled:opacity-50"
              autoFocus
            />
            {error && (
              <p className="text-red-400 text-xs mt-2">{error}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="w-full py-2.5 bg-cream text-[#0C0C0C] hover:bg-cream-dim disabled:bg-surface-light disabled:text-cream-muted font-medium rounded-full text-sm transition-colors"
          >
            {loading ? t.trends_add_author_checking : t.trends_add_author}
          </button>
        </form>
      </div>
    </div>
  );
}
