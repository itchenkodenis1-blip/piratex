import { useCallback, useEffect, useRef, useState } from "react";

interface RejectModalProps {
  isOpen: boolean;
  onConfirm: (comment: string) => void;
  onCancel: () => void;
}

export function RejectModal({ isOpen, onConfirm, onCancel }: RejectModalProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Reset & autofocus on open
  useEffect(() => {
    if (isOpen) {
      setText("");
      setTimeout(() => textareaRef.current?.focus(), 0);
    }
  }, [isOpen]);

  // Escape → cancel
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onCancel]);

  const isValid = text.trim().length >= 10;

  const handleConfirm = useCallback(() => {
    if (isValid) onConfirm(text.trim());
  }, [isValid, text, onConfirm]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md mx-4 bg-surface border border-border-subtle rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-0">
          <h3 className="text-base font-medium text-cream">
            Причина отклонения
          </h3>
          <button
            onClick={onCancel}
            className="text-cream-muted hover:text-cream transition-colors p-1"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-5 pt-4 pb-5 space-y-4">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Опишите причину отклонения (мин. 10 символов)..."
            rows={4}
            className="w-full bg-white/[0.04] border border-white/10 rounded-lg px-3 py-2.5 text-sm text-cream placeholder:text-cream-muted/40 resize-none focus:outline-none focus:border-red-500/50 transition-colors"
          />

          <div className="flex items-center justify-between">
            <span className={`text-xs ${isValid ? "text-cream-muted" : "text-cream-muted/50"}`}>
              {text.trim().length}/10 символов
            </span>
            <div className="flex gap-2">
              <button
                onClick={onCancel}
                className="px-4 py-2 text-sm text-cream-muted hover:text-cream bg-white/[0.04] hover:bg-white/[0.08] rounded-lg transition-colors"
              >
                Отмена
              </button>
              <button
                onClick={handleConfirm}
                disabled={!isValid}
                className="px-4 py-2 text-sm text-white bg-red-600 hover:bg-red-500 disabled:bg-red-600/30 disabled:text-white/40 rounded-lg transition-colors"
              >
                Отклонить
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
