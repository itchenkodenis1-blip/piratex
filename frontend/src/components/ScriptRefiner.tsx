import { useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";
import type { RefineField } from "../hooks/useStreamRefine";
import { useStreamRefine } from "../hooks/useStreamRefine";

interface QuickAction {
  key: string;
  labelKey: string;
  primary?: boolean;
}

const QUICK_ACTIONS: Record<RefineField, QuickAction[]> = {
  script: [
    { key: "improve", labelKey: "refine_improve", primary: true },
    { key: "strengthen_hook", labelKey: "refine_strengthen_hook" },
    { key: "shorten", labelKey: "refine_shorten" },
    { key: "add_specifics", labelKey: "refine_add_specifics" },
    { key: "rewrite_opening", labelKey: "refine_rewrite_opening" },
    { key: "simplify", labelKey: "refine_simplify" },
  ],
  description: [
    { key: "improve", labelKey: "refine_improve", primary: true },
    { key: "stronger_cta", labelKey: "refine_stronger_cta" },
    { key: "shorten", labelKey: "refine_shorten" },
    { key: "add_emojis", labelKey: "refine_add_emojis" },
  ],
  editor_instructions: [
    { key: "improve", labelKey: "refine_improve", primary: true },
    { key: "more_detail", labelKey: "refine_more_detail" },
    { key: "simplify", labelKey: "refine_simplify" },
  ],
  hook_variant: [
    { key: "strengthen", labelKey: "hook_refine_strengthen", primary: true },
    { key: "shorten", labelKey: "hook_refine_shorter" },
    { key: "audience", labelKey: "hook_refine_audience" },
  ],
};

interface Props {
  jobId: string;
  field: RefineField;
  currentText: string;
  onTextRefined: (newText: string) => void;
  language?: string;
}

export function ScriptRefiner({
  jobId,
  field,
  currentText,
  onTextRefined,
  language,
}: Props) {
  const { t } = useTranslation();
  const [inputValue, setInputValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const streamRef = useRef<HTMLPreElement>(null);

  const { state, streamedText, error, quota, startRefine, accept, reject, retry, cancel } =
    useStreamRefine({
      jobId,
      field,
      onAccept: onTextRefined,
      language,
    });

  const isLimitReached = error?.includes("Daily edit limit");

  // Auto-scroll streaming area
  useEffect(() => {
    if (streamRef.current && state === "streaming") {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [streamedText, state]);

  const handleQuickAction = (action: QuickAction) => {
    startRefine({ actionKey: action.key }, currentText);
  };

  const handleSubmit = () => {
    const trimmed = inputValue.trim();
    if (!trimmed) return;
    startRefine({ instruction: trimmed }, currentText);
    setInputValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const actions = QUICK_ACTIONS[field];

  // ---- IDLE: chips + input ----
  if (state === "idle") {
    return (
      <div className="space-y-2.5 pt-2">
        {/* Limit reached banner */}
        {isLimitReached && (
          <div className="text-xs text-amber-400/80 bg-amber-400/10 rounded-lg px-3 py-2">
            {t.refine_daily_limit_reached}
          </div>
        )}

        {/* Quick action chips */}
        <div className="flex flex-wrap gap-1.5 items-center">
          {actions.map((action) => (
            <button
              key={action.key}
              onClick={() => handleQuickAction(action)}
              disabled={isLimitReached}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed ${
                action.primary
                  ? "bg-cream text-[#0C0C0C] hover:bg-cream-dim"
                  : "text-cream-dim bg-surface-light border border-border-subtle hover:border-cream-muted/40 hover:text-cream"
              }`}
            >
              {action.primary ? "✦ " : ""}
              {t[action.labelKey as keyof typeof t] || action.key}
            </button>
          ))}
          {/* Remaining edits counter */}
          {quota && !isLimitReached && (
            <span className="text-[11px] text-cream-muted/50 ml-1">
              {quota.limit - quota.used}/{quota.limit}
            </span>
          )}
        </div>

        {/* Custom instruction input */}
        {!isLimitReached && (
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t.refine_input_placeholder}
              className="flex-1 px-3.5 py-2 text-sm text-cream bg-surface border border-border-subtle
                rounded-xl placeholder:text-cream-muted/50 focus:border-cream-muted/40 focus:outline-none
                transition-colors"
            />
            {inputValue.trim() && (
              <button
                onClick={handleSubmit}
                className="px-4 py-2 text-sm font-medium text-[#0C0C0C] bg-cream hover:bg-cream-dim
                  rounded-xl transition-colors cursor-pointer shrink-0"
              >
                {t.refine_send}
              </button>
            )}
          </div>
        )}
      </div>
    );
  }

  // ---- STREAMING / REVIEW ----
  return (
    <div className="space-y-3 pt-2">
      {/* Streaming text display */}
      <div className="bg-surface border border-cream-muted/20 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 border-b border-border-subtle">
          <span className="text-xs text-cream-muted flex items-center gap-2">
            {state === "streaming" ? (
              <>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cream opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-cream-dim" />
                </span>
                {t.refine_generating}
              </>
            ) : (
              t.refine_result
            )}
          </span>
          {state === "streaming" && (
            <button
              onClick={cancel}
              className="text-xs text-cream-muted hover:text-cream transition-colors cursor-pointer"
            >
              {t.refine_stop}
            </button>
          )}
        </div>
        <pre
          ref={streamRef}
          className="p-4 text-sm text-cream leading-relaxed whitespace-pre-wrap break-words
            font-sans max-h-80 overflow-y-auto"
        >
          {streamedText || "\u00A0"}
        </pre>
      </div>

      {/* Error */}
      {error && <p className="text-xs text-red-400 px-1">{error}</p>}

      {/* Review actions */}
      {state === "review" && (
        <div className="flex items-center gap-2">
          <button
            onClick={accept}
            disabled={!streamedText}
            className="px-4 py-2 text-sm font-medium text-[#0C0C0C] bg-cream hover:bg-cream-dim
              rounded-full transition-colors disabled:opacity-30 cursor-pointer"
          >
            {t.refine_accept}
          </button>
          <button
            onClick={reject}
            className="px-4 py-2 text-sm text-cream-dim hover:text-cream bg-surface-light
              border border-border-subtle rounded-full transition-colors cursor-pointer"
          >
            {t.refine_reject}
          </button>
          <button
            onClick={retry}
            className="px-4 py-2 text-sm text-cream-muted hover:text-cream transition-colors cursor-pointer"
          >
            {t.refine_try_again}
          </button>
        </div>
      )}
    </div>
  );
}
