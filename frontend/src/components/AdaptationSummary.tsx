import { useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";
import { LANGUAGE_LABELS, type SupportedLanguage } from "../i18n/types";
import type {
  AdaptationSummary as SummaryType,
  Hashtags,
  HookVariant,
  ScriptTranslation,
  StrategyData,
} from "../types";
import { LockedSection } from "./LockedSection";
import { TeaserOverlay } from "./TeaserOverlay";
import { ScriptRefiner } from "./ScriptRefiner";
import { Teleprompter } from "./Teleprompter";

function languageLabel(code: string): string {
  return LANGUAGE_LABELS[code as SupportedLanguage] ?? code.toUpperCase();
}

export interface EditData {
  script: string;
  description: string;
  editor_instructions: string;
}

interface Props {
  summary: SummaryType;
  strategy?: StrategyData | null;
  activeHookIndex?: number;
  onHookSwap?: (index: number, newScript: string) => void;
  primaryHookScore?: number;
  primaryHookWhy?: string;
  originalPrimaryHook?: string;
  jobId?: string;
  isTeaser?: boolean;
  onFieldRefined?: (field: keyof EditData, value: string) => void;
  onFieldSave?: (field: keyof EditData, value: string) => Promise<void>;
  // ── Second-language (translated) version ──
  secondLanguage?: string | null;            // configured target language, e.g. "en"
  translation?: ScriptTranslation | null;    // existing translation for secondLanguage
  isTranslating?: boolean;
  translationError?: string | null;
  onTranslate?: () => void;                  // generate or refresh the translation
  onTranslationFieldRefined?: (field: keyof EditData, value: string) => void;
  onTranslationFieldSave?: (field: keyof EditData, value: string) => Promise<void>;
}

interface DisplayHook {
  text: string;
  score: number;
  why: string;
}

function normalizeHook(v: HookVariant | string): DisplayHook {
  if (typeof v === "string") return { text: v, score: 50, why: "" };
  return { text: v.text, score: v.score ?? 50, why: v.why ?? "" };
}

function AutoResizeTextarea({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = "auto";
      ref.current.style.height = ref.current.scrollHeight + "px";
    }
  }, [value]);

  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full p-4 sm:p-5 text-sm text-cream leading-relaxed whitespace-pre-wrap break-words font-sans
        bg-surface-light/30 border-none outline-none resize-none focus:ring-1 focus:ring-cream-muted/40 rounded-b-2xl"
      rows={3}
    />
  );
}

function CopyBlock({
  title,
  content,
  onSave,
  onEditingChange,
  showTeleprompter,
}: {
  title: string;
  content: string;
  onSave?: (value: string) => Promise<void>;
  onEditingChange?: (editing: boolean) => void;
  showTeleprompter?: boolean;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [teleprompterOpen, setTeleprompterOpen] = useState(false);
  const prevContentRef = useRef(content);

  // Exit edit mode if content prop changes externally (e.g. hook swap)
  useEffect(() => {
    if (isEditing && content !== prevContentRef.current) {
      setIsEditing(false);
      onEditingChange?.(false);
    }
    prevContentRef.current = content;
  }, [content, isEditing, onEditingChange]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(isEditing ? editValue : content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleStartEdit = () => {
    setEditValue(content);
    setIsEditing(true);
    onEditingChange?.(true);
  };

  const handleCancel = () => {
    setIsEditing(false);
    onEditingChange?.(false);
  };

  const handleSave = async () => {
    if (!onSave) return;
    setIsSaving(true);
    try {
      await onSave(editValue);
      setIsEditing(false);
      onEditingChange?.(false);
    } catch {
      // stay in edit mode on error — user keeps their edits
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className={`bg-surface border rounded-2xl overflow-hidden ${isEditing ? "border-cream-muted/40" : "border-border-subtle"}`}>
      <div className="flex items-center justify-between px-4 sm:px-5 py-3 sm:py-3.5 border-b border-border-subtle">
        <h3 className="text-sm font-medium text-cream">{title}</h3>
        <div className="flex items-center gap-1.5">
          {showTeleprompter && !isEditing && (
            <button
              onClick={() => setTeleprompterOpen(true)}
              className="w-7 h-7 flex items-center justify-center rounded-full transition-colors cursor-pointer
                text-cream-muted hover:text-cream hover:bg-surface-light"
              title={t.teleprompter_open}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <rect x="2" y="3" width="20" height="14" rx="2" />
                <path d="M8 21h8" />
                <path d="M12 17v4" />
                <path d="M7 8h10M7 12h6" />
              </svg>
            </button>
          )}
          {onSave && !isEditing && (
            <button
              onClick={handleStartEdit}
              className="w-7 h-7 flex items-center justify-center rounded-full transition-colors cursor-pointer
                text-cream-muted hover:text-cream hover:bg-surface-light"
              title={t.edit_script}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>
          )}
          <button
            onClick={handleCopy}
            className="px-3 py-1 text-xs font-medium rounded-full transition-colors cursor-pointer
              bg-surface-light border border-border-subtle text-cream-dim hover:text-cream hover:border-cream-muted"
          >
            {copied ? t.summary_copied : t.summary_copy}
          </button>
        </div>
      </div>
      {isEditing ? (
        <>
          <AutoResizeTextarea value={editValue} onChange={setEditValue} />
          <div className="flex justify-end gap-2 px-4 sm:px-5 py-3 border-t border-border-subtle">
            <button
              onClick={handleCancel}
              disabled={isSaving}
              className="px-4 py-1.5 text-xs font-medium rounded-full transition-colors cursor-pointer
                bg-surface-light border border-border-subtle text-cream-dim hover:text-cream hover:border-cream-muted disabled:opacity-50"
            >
              {t.cancel_edit}
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="px-4 py-1.5 text-xs font-medium rounded-full transition-colors cursor-pointer
                bg-cream text-[#0C0C0C] hover:bg-cream-dim disabled:opacity-50"
            >
              {isSaving ? t.save_script_saving : t.save_script}
            </button>
          </div>
        </>
      ) : (
        <pre className="p-4 sm:p-5 text-sm text-cream-dim leading-relaxed whitespace-pre-wrap break-words font-sans overflow-hidden">
          {content}
        </pre>
      )}
      {teleprompterOpen && (
        <Teleprompter text={isEditing ? editValue : content} onClose={() => setTeleprompterOpen(false)} />
      )}
    </div>
  );
}

function CollapsibleSection({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border border-border-subtle rounded-2xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 sm:px-5 py-3 sm:py-3.5
          bg-surface hover:bg-surface-light transition-colors cursor-pointer"
      >
        <h3 className="text-sm font-medium text-cream flex items-center gap-2">
          <span
            className="inline-block transition-transform duration-200"
            style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}
          >
            ▸
          </span>
          {title}
        </h3>
        <span className="text-xs text-cream-muted">
          {open ? t.strategy_show_less : t.strategy_show_more}
        </span>
      </button>
      {open && (
        <div className="px-4 sm:px-5 py-4 border-t border-border-subtle bg-surface">
          {children}
        </div>
      )}
    </div>
  );
}

function estimateHookDuration(text: string): number {
  const words = text.trim().split(/\s+/).length;
  return Math.round((words / 3.07) * 10) / 10;
}

function HookVariantItem({
  label,
  hook,
  isActive,
  onUse,
  rank,
  onRefine,
  isRefining,
  compact,
}: {
  label: string;
  hook: DisplayHook;
  isActive: boolean;
  onUse: () => void;
  rank: number;
  onRefine?: () => void;
  isRefining?: boolean;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const dur = estimateHookDuration(hook.text);
  const isLong = dur > 3;

  const badgeColor = rank === 1
    ? "text-green-400/80 bg-green-400/10 border-green-400/20"
    : rank <= 3
      ? "text-blue-400/80 bg-blue-400/10 border-blue-400/20"
      : "text-cream-muted/70 bg-surface-light border-border-subtle";
  const badgeText = rank === 1 ? t.hook_badge_best : rank <= 3 ? t.hook_badge_strong : t.hook_badge_alternative;

  /* ── Compact card (mobile carousel) ── */
  if (compact) {
    return (
      <div
        className={`w-[280px] shrink-0 snap-center rounded-2xl p-3.5 flex flex-col gap-2.5 transition-all ${
          isActive
            ? "bg-cream/5 border-2 border-cream/30 shadow-[0_0_20px_rgba(255,248,230,0.06)]"
            : "bg-surface-light/40 border border-border-subtle"
        }`}
      >
        {/* Top row: number + badge */}
        <div className="flex items-center gap-2">
          <span
            className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold ${
              isActive
                ? "bg-cream text-[#0C0C0C]"
                : "bg-surface-light border border-border-subtle text-cream-muted"
            }`}
          >
            {label}
          </span>
          {hook.score > 0 && (
            <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full border ${badgeColor}`}>
              {badgeText}
            </span>
          )}
          <span className={`ml-auto text-[10px] font-mono ${isLong ? "text-amber-400/80" : "text-cream-muted/50"}`}>
            ~{dur}{t.hook_timing_sec}
          </span>
        </div>

        {/* Hook text */}
        <p className="text-[13px] text-cream-dim leading-snug line-clamp-4 flex-1">{hook.text}</p>

        {/* Bottom actions */}
        <div className="flex items-center gap-2 mt-auto pt-1 border-t border-border-subtle/50">
          {onRefine && (
            <button
              onClick={onRefine}
              className={`w-8 h-8 flex items-center justify-center rounded-xl transition-colors cursor-pointer ${
                isRefining ? "bg-cream/10 text-cream" : "text-cream-muted hover:text-cream hover:bg-surface-light"
              }`}
              title={t.hook_refine}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>
          )}
          <button
            onClick={isActive ? undefined : onUse}
            disabled={isActive}
            className={`flex-1 py-2 text-xs font-medium rounded-xl transition-colors ${
              isActive
                ? "bg-cream/10 text-cream cursor-default border border-cream/20"
                : "bg-surface border border-border-subtle text-cream-muted hover:text-cream hover:border-cream-muted cursor-pointer"
            }`}
          >
            {isActive ? t.hook_in_use : t.hook_use}
          </button>
        </div>
      </div>
    );
  }

  /* ── Full card (desktop vertical list) ── */
  return (
    <div
      className={`p-3 rounded-xl transition-colors ${
        isActive
          ? "bg-cream/5 border border-cream/20"
          : "bg-surface-light/50 border border-transparent"
      }`}
    >
      <div className="flex items-start gap-3">
        {/* Label circle */}
        <span
          className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-medium mt-0.5 ${
            isActive
              ? "bg-cream text-[#0C0C0C]"
              : "bg-surface-light border border-border-subtle text-cream-muted"
          }`}
        >
          {label}
        </span>

        {/* Text + why + timing + badge */}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-cream-dim leading-relaxed">{hook.text}</p>
          {hook.why && (
            <p className="mt-1 text-xs text-cream-muted/70 italic leading-snug">
              {hook.why}
            </p>
          )}
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            {hook.score > 0 && (
              <span className={`inline-block px-2 py-0.5 text-[10px] font-medium rounded-full border ${badgeColor}`}>
                {badgeText}
              </span>
            )}
            <span className={`text-[10px] font-mono ${isLong ? "text-amber-400/80" : "text-cream-muted/60"}`}>
              ~{dur} {t.hook_timing_sec}{isLong ? ` — ${t.hook_timing_warning}` : ""}
            </span>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 shrink-0 mt-0.5">
          {onRefine && (
            <button
              onClick={onRefine}
              className={`w-7 h-7 flex items-center justify-center rounded-full transition-colors cursor-pointer ${
                isRefining ? "bg-cream/10 text-cream" : "text-cream-muted hover:text-cream hover:bg-surface-light"
              }`}
              title={t.hook_refine}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>
          )}
          <button
            onClick={isActive ? undefined : onUse}
            disabled={isActive}
            className={`px-3 py-1 text-[10px] font-medium rounded-full transition-colors ${
              isActive
                ? "bg-cream/10 text-cream-muted cursor-default border border-cream/20"
                : "bg-surface border border-border-subtle text-cream-muted hover:text-cream hover:border-cream-muted cursor-pointer"
            }`}
          >
            {isActive ? t.hook_in_use : t.hook_use}
          </button>
        </div>
      </div>
    </div>
  );
}

function HashtagBlock({ hashtags }: { hashtags: Hashtags }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const allTags = [...hashtags.primary, ...hashtags.secondary];
  const tagString = allTags.map((h) => (h.startsWith("#") ? h : `#${h}`)).join(" ");

  const handleCopy = async () => {
    await navigator.clipboard.writeText(tagString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-surface border border-border-subtle rounded-2xl overflow-hidden">
      <div className="flex items-center justify-between px-4 sm:px-5 py-3 sm:py-3.5 border-b border-border-subtle">
        <h3 className="text-sm font-medium text-cream">{t.summary_hashtags}</h3>
        <button
          onClick={handleCopy}
          className="px-3 py-1 text-xs font-medium rounded-full transition-colors cursor-pointer
            bg-surface-light border border-border-subtle text-cream-dim hover:text-cream hover:border-cream-muted"
        >
          {copied ? t.summary_copied : t.summary_copy}
        </button>
      </div>
      <div className="p-4 sm:p-5 flex flex-wrap gap-2">
        {hashtags.primary.map((tag, i) => (
          <span
            key={`p-${i}`}
            className="px-2.5 py-1 bg-surface-light rounded-full text-xs text-cream-dim"
          >
            {tag.startsWith("#") ? tag : `#${tag}`}
          </span>
        ))}
        {hashtags.secondary.map((tag, i) => (
          <span
            key={`s-${i}`}
            className="px-2.5 py-1 bg-surface-light/50 rounded-full text-xs text-cream-muted"
          >
            {tag.startsWith("#") ? tag : `#${tag}`}
          </span>
        ))}
      </div>
    </div>
  );
}

export function AdaptationSummary({
  summary,
  strategy,
  activeHookIndex = 0,
  onHookSwap,
  primaryHookScore,
  primaryHookWhy,
  originalPrimaryHook,
  jobId,
  isTeaser,
  onFieldRefined,
  onFieldSave,
  secondLanguage,
  translation,
  isTranslating,
  translationError,
  onTranslate,
  onTranslationFieldRefined,
  onTranslationFieldSave,
}: Props) {
  const { t } = useTranslation();
  const [editingField, setEditingField] = useState<keyof EditData | null>(null);
  const [editingTransField, setEditingTransField] = useState<keyof EditData | null>(null);

  // Merge strategy data: prefer explicit strategy prop, fall back to fields on summary
  const rawHookVariants = strategy?.hook_variants ?? summary.hook_variants ?? [];
  const hashtags = strategy?.hashtags ?? summary.hashtags;
  const virality = strategy?.virality_breakdown ?? summary.virality_breakdown;
  // Resolve primary hook score/why from props or strategy
  const phScore = primaryHookScore ?? strategy?.primary_hook_score ?? summary.primary_hook_score ?? 0;
  const phWhy = primaryHookWhy ?? strategy?.primary_hook_why ?? summary.primary_hook_why ?? "";

  const scriptText = summary.script;

  // Extract primary hook = first paragraph of the script
  const splitIdx = scriptText.indexOf("\n\n");
  const primaryHookText = splitIdx > 0 ? scriptText.slice(0, splitIdx) : scriptText;
  const scriptBody = splitIdx > 0 ? scriptText.slice(splitIdx + 2) : "";

  // Build 5-hook array: [original primary] + [alternatives from strategist]
  // Use originalPrimaryHook prop (stable) to avoid losing the original when script changes
  const stablePrimaryHookText = originalPrimaryHook ?? primaryHookText;
  const alternativeHooks: DisplayHook[] = rawHookVariants.map(normalizeHook);
  const allHooksBase: DisplayHook[] = [
    { text: stablePrimaryHookText, score: phScore, why: phWhy },
    ...alternativeHooks,
  ];

  // Hook refinement overrides
  const [hookOverrides, setHookOverrides] = useState<Map<number, string>>(new Map());
  const [refiningHookIndex, setRefiningHookIndex] = useState<number | null>(null);

  const allHooks: DisplayHook[] = allHooksBase.map((hook, i) => {
    const override = hookOverrides.get(i);
    return override ? { ...hook, text: override } : hook;
  });

  // Compute rank for each hook by score (1 = highest)
  const hookRanks: number[] = allHooks.map((_, i) => {
    const score = allHooks[i].score;
    return allHooks.filter(h => h.score > score).length + 1;
  });

  const hookLabels = ["1", "2", "3", "4", "5"];

  const handleHookSwap = (newIndex: number) => {
    if (!onHookSwap || newIndex === activeHookIndex || newIndex < 0 || newIndex >= allHooks.length) return;
    const newHookText = allHooks[newIndex].text;
    const newScript = scriptBody ? newHookText + "\n\n" + scriptBody : newHookText;
    onHookSwap(newIndex, newScript);
  };

  const handleHookRefined = (index: number, newText: string) => {
    setHookOverrides(prev => new Map(prev).set(index, newText));
    setRefiningHookIndex(null);
    if (index === activeHookIndex && onHookSwap) {
      const newScript = scriptBody ? newText + "\n\n" + scriptBody : newText;
      onHookSwap(index, newScript);
    }
  };

  const hasStrategy = !!virality;

  // ── Teaser mode: show partial script + locked placeholders ──
  if (isTeaser) {
    return (
      <div className="space-y-6">
        {/* 1. Script — truncated with overlay */}
        <TeaserOverlay>
          <div className="bg-surface border border-border-subtle rounded-2xl overflow-hidden">
            <div className="px-4 sm:px-5 py-3 sm:py-3.5 border-b border-border-subtle">
              <h3 className="text-sm font-medium text-cream">{t.summary_script}</h3>
            </div>
            <pre className="p-4 sm:p-5 text-sm text-cream-dim leading-relaxed whitespace-pre-wrap break-words font-sans overflow-hidden">
              {scriptText}
            </pre>
          </div>
        </TeaserOverlay>

        {/* 2–6. Locked sections */}
        <LockedSection title={t.summary_hook_variants} />
        <LockedSection title={t.summary_description} />
        <LockedSection title={t.summary_hashtags} />
        <LockedSection title={t.summary_editor_instructions} />
        <LockedSection title={t.strategy_section_title} />
      </div>
    );
  }

  // ── Full mode (registered users) ──
  return (
    <div className="space-y-6">
      {/* 1. Script */}
      <CopyBlock
        title={t.summary_script}
        content={scriptText}
        onSave={onFieldSave ? (v) => onFieldSave("script", v) : undefined}
        onEditingChange={(e) => setEditingField(e ? "script" : null)}
        showTeleprompter
      />
      {jobId && onFieldRefined && editingField !== "script" && (
        <ScriptRefiner
          jobId={jobId}
          field="script"
          currentText={scriptText}
          onTextRefined={(text) => onFieldRefined("script", text)}
        />
      )}

      {/* 2. Hook variants — carousel on mobile, list on desktop */}
      {allHooks.length > 1 && (
        <div className="border border-border-subtle rounded-2xl overflow-hidden">
          <div className="px-4 sm:px-5 py-3 sm:py-3.5 border-b border-border-subtle bg-surface">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-cream">{t.summary_hook_variants}</h3>
              <span className="text-[10px] text-cream-muted/50 sm:hidden">{activeHookIndex + 1}/{allHooks.length}</span>
            </div>
          </div>

          {/* Mobile: horizontal carousel */}
          <div className="sm:hidden bg-surface p-3">
            <div className="flex gap-3 overflow-x-auto snap-x snap-mandatory pb-2 -mx-3 px-3 scrollbar-hide">
              {allHooks.map((hook, i) => (
                <HookVariantItem
                  key={i}
                  label={hookLabels[i] ?? String(i + 1)}
                  hook={hook}
                  isActive={i === activeHookIndex}
                  onUse={() => handleHookSwap(i)}
                  rank={hookRanks[i]}
                  onRefine={jobId && onFieldRefined && !editingField ? () => setRefiningHookIndex(refiningHookIndex === i ? null : i) : undefined}
                  isRefining={refiningHookIndex === i}
                  compact
                />
              ))}
            </div>
            {/* Dot indicators */}
            <div className="flex items-center justify-center gap-1.5 mt-2">
              {allHooks.map((_, i) => (
                <span
                  key={i}
                  className={`w-1.5 h-1.5 rounded-full transition-colors ${
                    i === activeHookIndex ? "bg-cream" : "bg-cream/20"
                  }`}
                />
              ))}
            </div>
            {refiningHookIndex !== null && jobId && (
              <div className="mt-2">
                <ScriptRefiner
                  jobId={jobId}
                  field="hook_variant"
                  currentText={allHooks[refiningHookIndex].text}
                  onTextRefined={(text) => handleHookRefined(refiningHookIndex!, text)}
                />
              </div>
            )}
          </div>

          {/* Desktop: vertical list */}
          <div className="hidden sm:block p-3 sm:p-4 space-y-2 bg-surface">
            {allHooks.map((hook, i) => (
              <div key={i}>
                <HookVariantItem
                  label={hookLabels[i] ?? String(i + 1)}
                  hook={hook}
                  isActive={i === activeHookIndex}
                  onUse={() => handleHookSwap(i)}
                  rank={hookRanks[i]}
                  onRefine={jobId && onFieldRefined && !editingField ? () => setRefiningHookIndex(refiningHookIndex === i ? null : i) : undefined}
                  isRefining={refiningHookIndex === i}
                />
                {refiningHookIndex === i && jobId && (
                  <div className="ml-9 mt-1 mb-1">
                    <ScriptRefiner
                      jobId={jobId}
                      field="hook_variant"
                      currentText={hook.text}
                      onTextRefined={(text) => handleHookRefined(i, text)}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3. Description */}
      <CopyBlock
        title={t.summary_description}
        content={summary.description}
        onSave={onFieldSave ? (v) => onFieldSave("description", v) : undefined}
        onEditingChange={(e) => setEditingField(e ? "description" : null)}
      />
      {jobId && onFieldRefined && editingField !== "description" && (
        <ScriptRefiner
          jobId={jobId}
          field="description"
          currentText={summary.description}
          onTextRefined={(text) => onFieldRefined("description", text)}
        />
      )}

      {/* 4. Hashtags — right under description */}
      {hashtags &&
        (hashtags.primary.length > 0 || hashtags.secondary.length > 0) && (
          <HashtagBlock hashtags={hashtags} />
        )}

      {/* 5. Editor instructions */}
      <CopyBlock
        title={t.summary_editor_instructions}
        content={summary.editor_instructions}
        onSave={onFieldSave ? (v) => onFieldSave("editor_instructions", v) : undefined}
        onEditingChange={(e) => setEditingField(e ? "editor_instructions" : null)}
      />
      {jobId && onFieldRefined && editingField !== "editor_instructions" && (
        <ScriptRefiner
          jobId={jobId}
          field="editor_instructions"
          currentText={summary.editor_instructions}
          onTextRefined={(text) => onFieldRefined("editor_instructions", text)}
        />
      )}

      {/* 5b. Second-language (translated) version */}
      {(secondLanguage || translation) && (() => {
        const lang = translation?.language ?? secondLanguage!;
        return (
          <div className="space-y-6">
            <div className="flex items-center gap-3 pt-4">
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
              <h2 className="text-sm font-medium text-cream-muted uppercase tracking-widest shrink-0">
                {t.summary_second_language} • {languageLabel(lang)}
              </h2>
              <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
            </div>

            {translation ? (
              <>
                {translation.stale && (
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs bg-amber-400/10 text-amber-300/90 rounded-xl px-3.5 py-2.5">
                    <span>{t.summary_translation_stale}</span>
                    {onTranslate && (
                      <button
                        onClick={onTranslate}
                        disabled={isTranslating}
                        className="px-3 py-1 rounded-full bg-amber-400/20 hover:bg-amber-400/30 text-amber-100 transition-colors disabled:opacity-50 cursor-pointer"
                      >
                        {isTranslating ? t.summary_translating : t.summary_translation_refresh}
                      </button>
                    )}
                  </div>
                )}

                {/* Translated script */}
                <CopyBlock
                  title={t.summary_script}
                  content={translation.script}
                  onSave={onTranslationFieldSave ? (v) => onTranslationFieldSave("script", v) : undefined}
                  onEditingChange={(e) => setEditingTransField(e ? "script" : null)}
                  showTeleprompter
                />
                {jobId && onTranslationFieldRefined && editingTransField !== "script" && (
                  <ScriptRefiner
                    jobId={jobId}
                    field="script"
                    language={lang}
                    currentText={translation.script}
                    onTextRefined={(text) => onTranslationFieldRefined("script", text)}
                  />
                )}

                {/* Translated description */}
                <CopyBlock
                  title={t.summary_description}
                  content={translation.description}
                  onSave={onTranslationFieldSave ? (v) => onTranslationFieldSave("description", v) : undefined}
                  onEditingChange={(e) => setEditingTransField(e ? "description" : null)}
                />
                {jobId && onTranslationFieldRefined && editingTransField !== "description" && (
                  <ScriptRefiner
                    jobId={jobId}
                    field="description"
                    language={lang}
                    currentText={translation.description}
                    onTextRefined={(text) => onTranslationFieldRefined("description", text)}
                  />
                )}

                {/* Translated editor instructions */}
                <CopyBlock
                  title={t.summary_editor_instructions}
                  content={translation.editor_instructions}
                  onSave={onTranslationFieldSave ? (v) => onTranslationFieldSave("editor_instructions", v) : undefined}
                  onEditingChange={(e) => setEditingTransField(e ? "editor_instructions" : null)}
                />
                {jobId && onTranslationFieldRefined && editingTransField !== "editor_instructions" && (
                  <ScriptRefiner
                    jobId={jobId}
                    field="editor_instructions"
                    language={lang}
                    currentText={translation.editor_instructions}
                    onTextRefined={(text) => onTranslationFieldRefined("editor_instructions", text)}
                  />
                )}
              </>
            ) : (
              <div className="flex flex-col items-center gap-3 py-2">
                {onTranslate && (
                  <button
                    onClick={onTranslate}
                    disabled={isTranslating}
                    className="px-6 py-2.5 text-sm font-medium rounded-full transition-colors cursor-pointer
                      bg-cream text-[#0C0C0C] hover:bg-cream-dim disabled:opacity-50"
                  >
                    {isTranslating
                      ? t.summary_translating
                      : `${t.summary_translation_generate} (${languageLabel(lang)})`}
                  </button>
                )}
                {translationError && (
                  <p className="text-xs text-red-400">{translationError}</p>
                )}
              </div>
            )}
          </div>
        );
      })()}

      {/* 6. Strategy section */}
      {hasStrategy && (
        <>
          <div className="flex items-center gap-3 pt-4">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
            <h2 className="text-sm font-medium text-cream-muted uppercase tracking-widest shrink-0">
              {t.strategy_section_title}
            </h2>
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-cream-muted/30 to-transparent" />
          </div>

          <div className="space-y-4">
            {/* Virality breakdown — collapsed by default */}
            {virality && (
              <CollapsibleSection title={t.strategy_virality}>
                <pre className="text-sm text-cream-dim leading-relaxed whitespace-pre-wrap break-words font-sans">
                  {virality}
                </pre>
              </CollapsibleSection>
            )}

          </div>
        </>
      )}
    </div>
  );
}
