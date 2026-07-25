import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "../i18n";
import type { SupportedLanguage } from "../i18n";

const STORAGE_KEY = "teleprompter_settings";

interface Settings {
  speed: number; // 0.5–5, step 0.1
  fontSize: number; // 0=S, 1=M, 2=L
  light: boolean; // false=dark, true=light
  voice: boolean; // follow speech instead of timed scroll
}

const FONT_SIZES = [24, 36, 52] as const;
const FONT_LABELS = ["S", "M", "L"] as const;
const DEFAULT_SETTINGS: Settings = { speed: 1.5, fontSize: 1, light: false, voice: false };

// Web Speech API recognition language per UI language (best-effort guess).
const RECOG_LANG: Record<SupportedLanguage, string> = {
  ru: "ru-RU",
  en: "en-US",
  fr: "fr-FR",
  pt: "pt-BR",
  de: "de-DE",
};

const SPEECH_SUPPORTED =
  typeof window !== "undefined" && !!(window.SpeechRecognition || window.webkitSpeechRecognition);

// Matches a "word" (letters/digits, with internal apostrophes/hyphens).
const WORD_RE = /[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu;

function normWord(w: string): string {
  return w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
}

function splitWords(s: string): string[] {
  const out: string[] = [];
  const matches = s.matchAll(WORD_RE);
  for (const m of matches) {
    const n = normWord(m[0]);
    if (n) out.push(n);
  }
  return out;
}

// Fuzzy word equality — tolerant of inflections (shared prefix) and minor ASR errors.
function wordsMatch(a: string, b: string): boolean {
  if (a === b) return true;
  const min = Math.min(a.length, b.length);
  if (min < 3) return false;
  let c = 0;
  while (c < min && a[c] === b[c]) c++;
  // Share at least 3 leading chars and all but ≤2 trailing chars of the shorter word.
  return c >= 3 && c >= min - 2;
}

// Find where the recently spoken `tail` aligns in the script, near `cursor`.
// Returns the script word index of the last spoken word, or -1 if no confident match.
function findMatch(scriptWords: string[], tail: string[], cursor: number): number {
  if (tail.length === 0 || scriptWords.length === 0) return -1;
  const lo = Math.max(0, cursor - 30);
  const hi = Math.min(scriptWords.length - 1, cursor + 60);
  let best = -1;
  let bestScore = 0;
  let bestDist = Infinity;

  for (let p = lo; p <= hi; p++) {
    let score = 0;
    for (let k = 0; k < tail.length; k++) {
      const s = p - k;
      const ti = tail.length - 1 - k;
      if (s < 0) break;
      if (wordsMatch(scriptWords[s], tail[ti])) score++;
      else break; // require a contiguous trailing run
    }
    if (score === 0) continue;
    const dist = Math.abs(p - cursor);
    if (score > bestScore || (score === bestScore && dist < bestDist)) {
      best = p;
      bestScore = score;
      bestDist = dist;
    }
  }

  if (best < 0) return -1;
  const fwd = best - cursor;
  // ≥2 matching words → trust any jump (incl. backward re-takes).
  if (bestScore >= 2) return best;
  // Single-word match → only a gentle forward creep, to avoid jitter.
  if (bestScore === 1 && fwd >= 0 && fwd <= 4) return best;
  return -1;
}

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw);
    return {
      speed: Math.min(5, Math.max(0.5, parsed.speed ?? DEFAULT_SETTINGS.speed)),
      fontSize: Math.min(2, Math.max(0, parsed.fontSize ?? DEFAULT_SETTINGS.fontSize)),
      light: typeof parsed.light === "boolean" ? parsed.light : DEFAULT_SETTINGS.light,
      voice: typeof parsed.voice === "boolean" ? parsed.voice : DEFAULT_SETTINGS.voice,
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function saveSettings(s: Settings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
}

interface Props {
  text: string;
  onClose: () => void;
}

export function Teleprompter({ text, onClose }: Props) {
  const { t, lang } = useTranslation();
  const [settings, setSettings] = useState(loadSettings);
  const [isPlaying, setIsPlaying] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [progress, setProgress] = useState(0);
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const [micDenied, setMicDenied] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const animRef = useRef<number>(0);
  const wakeLockRef = useRef<WakeLockSentinel | null>(null);
  const touchScrollingRef = useRef(false);
  const touchEndTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const cursorRef = useRef(-1); // last matched script-word index
  const targetScrollRef = useRef(0); // desired scrollTop in voice mode

  const voiceMode = settings.voice && SPEECH_SUPPORTED;

  // Split text into render segments (words carry a `wi` index; gaps carry null).
  const segments = useMemo(() => {
    const segs: { text: string; wi: number | null }[] = [];
    let last = 0;
    let wi = 0;
    for (const m of text.matchAll(WORD_RE)) {
      const idx = m.index ?? 0;
      if (idx > last) segs.push({ text: text.slice(last, idx), wi: null });
      segs.push({ text: m[0], wi });
      wi++;
      last = idx + m[0].length;
    }
    if (last < text.length) segs.push({ text: text.slice(last), wi: null });
    return segs;
  }, [text]);

  // Normalized script words, indexed to match each segment's `wi`.
  const scriptWords = useMemo(
    () => segments.filter((s) => s.wi !== null).map((s) => normWord(s.text)),
    [segments],
  );
  const scriptWordsRef = useRef(scriptWords);
  useEffect(() => {
    scriptWordsRef.current = scriptWords;
  }, [scriptWords]);

  // Center the matched word in view (sets the easing target; RAF animates toward it).
  const setTargetForWord = useCallback((idx: number) => {
    const el = scrollRef.current;
    if (!el) return;
    const span = el.querySelector<HTMLElement>(`[data-wi="${idx}"]`);
    if (!span) return;
    const elRect = el.getBoundingClientRect();
    const spanRect = span.getBoundingClientRect();
    const target = el.scrollTop + (spanRect.top - elRect.top) - el.clientHeight * 0.42;
    targetScrollRef.current = Math.max(0, target);
  }, []);

  // Persist settings on change
  useEffect(() => {
    saveSettings(settings);
  }, [settings]);

  // Wake Lock — keep screen on while playing
  useEffect(() => {
    if (!isPlaying) {
      wakeLockRef.current?.release().catch(() => {});
      wakeLockRef.current = null;
      return;
    }
    let released = false;
    navigator.wakeLock?.request("screen").then((lock) => {
      if (released) { lock.release(); return; }
      wakeLockRef.current = lock;
    }).catch(() => {});
    return () => { released = true; wakeLockRef.current?.release().catch(() => {}); };
  }, [isPlaying]);

  // Cleanup wake lock on unmount
  useEffect(() => () => { wakeLockRef.current?.release().catch(() => {}); }, []);

  // Scroll animation loop — timed scroll, or eased follow in voice mode.
  useEffect(() => {
    if (!isPlaying || countdown !== null) {
      cancelAnimationFrame(animRef.current);
      return;
    }
    const el = scrollRef.current;
    if (!el) return;

    if (voiceMode) {
      // Sync target with current position so we don't lurch on start.
      if (cursorRef.current < 0) targetScrollRef.current = el.scrollTop;
      const tick = () => {
        if (!touchScrollingRef.current) {
          const cur = el.scrollTop;
          const target = targetScrollRef.current;
          if (Math.abs(target - cur) > 0.5) {
            el.scrollTop = cur + (target - cur) * 0.12; // ease toward target
          }
          const maxScroll = el.scrollHeight - el.clientHeight;
          setProgress(maxScroll > 0 ? Math.min(1, el.scrollTop / maxScroll) : 1);
        }
        animRef.current = requestAnimationFrame(tick);
      };
      animRef.current = requestAnimationFrame(tick);
      return () => cancelAnimationFrame(animRef.current);
    }

    // Exponential curve: speed 0.5 → 0.15 px/frame, 1.5 → 0.6, 3 → 2.1, 5 → 5.5
    const pxPerFrame = 0.2 * Math.pow(settings.speed, 1.7);
    const tick = () => {
      if (touchScrollingRef.current) {
        animRef.current = requestAnimationFrame(tick);
        return;
      }
      el.scrollTop += pxPerFrame;
      const maxScroll = el.scrollHeight - el.clientHeight;
      setProgress(maxScroll > 0 ? Math.min(1, el.scrollTop / maxScroll) : 1);
      if (el.scrollTop >= maxScroll) {
        setIsPlaying(false);
        setProgress(1);
        return;
      }
      animRef.current = requestAnimationFrame(tick);
    };
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, [isPlaying, countdown, settings.speed, voiceMode]);

  // Speech recognition — drives highlight + scroll target while playing in voice mode.
  useEffect(() => {
    if (!voiceMode || !isPlaying || countdown !== null) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    const recog = new SR();
    recog.continuous = true;
    recog.interimResults = true;
    recog.lang = RECOG_LANG[lang] ?? "en-US";
    let stopped = false;
    const finalWords: string[] = [];

    recog.onresult = (e: SpeechRecognitionEvent) => {
      let interim: string[] = [];
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        const ws = splitWords(res[0].transcript);
        if (res.isFinal) finalWords.push(...ws);
        else interim = ws;
      }
      if (finalWords.length > 60) finalWords.splice(0, finalWords.length - 60);
      const tail = finalWords.concat(interim).slice(-6);
      const m = findMatch(scriptWordsRef.current, tail, cursorRef.current);
      if (m >= 0 && m !== cursorRef.current) {
        cursorRef.current = m;
        setHighlightIdx(m);
        setTargetForWord(m);
      }
    };
    recog.onerror = (e: SpeechRecognitionErrorEvent) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        stopped = true;
        setMicDenied(true);
        setSettings((s) => ({ ...s, voice: false }));
      }
    };
    recog.onend = () => {
      // Recognition stops itself periodically — restart while still active.
      if (!stopped) { try { recog.start(); } catch { /* already started */ } }
    };

    try { recog.start(); } catch { /* ignore */ }
    return () => {
      stopped = true;
      recog.onresult = null;
      recog.onend = null;
      recog.onerror = null;
      try { recog.stop(); } catch { /* ignore */ }
    };
  }, [voiceMode, isPlaying, countdown, lang, setTargetForWord]);

  // Touch detection — pause auto-scroll while finger is on screen
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const onTouchStart = () => {
      touchScrollingRef.current = true;
      clearTimeout(touchEndTimerRef.current);
    };
    const onTouchEnd = () => {
      touchEndTimerRef.current = setTimeout(() => {
        touchScrollingRef.current = false;
        // In voice mode, follow the user's manual scroll as the new target.
        if (voiceMode) targetScrollRef.current = el.scrollTop;
        const maxScroll = el.scrollHeight - el.clientHeight;
        if (maxScroll > 0) setProgress(el.scrollTop / maxScroll);
      }, 300);
    };

    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchend", onTouchEnd, { passive: true });
    el.addEventListener("touchcancel", onTouchEnd, { passive: true });
    return () => {
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchend", onTouchEnd);
      el.removeEventListener("touchcancel", onTouchEnd);
      clearTimeout(touchEndTimerRef.current);
    };
  }, [voiceMode]);

  // Countdown logic
  useEffect(() => {
    if (countdown === null) return;
    if (countdown === 0) {
      setCountdown(null);
      setIsPlaying(true);
      return;
    }
    const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const handlePlay = useCallback(() => {
    if (isPlaying) {
      setIsPlaying(false);
    } else {
      setCountdown(3);
    }
  }, [isPlaying]);

  const handleRestart = useCallback(() => {
    setIsPlaying(false);
    setCountdown(null);
    setProgress(0);
    setHighlightIdx(-1);
    cursorRef.current = -1;
    targetScrollRef.current = 0;
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }, []);

  const updateSpeed = useCallback((speed: number) => {
    setSettings((s) => ({ ...s, speed }));
  }, []);

  const cycleFontSize = useCallback(() => {
    setSettings((s) => ({ ...s, fontSize: (s.fontSize + 1) % 3 }));
  }, []);

  const toggleTheme = useCallback(() => {
    setSettings((s) => ({ ...s, light: !s.light }));
  }, []);

  const toggleVoice = useCallback(() => {
    setMicDenied(false);
    setHighlightIdx(-1);
    cursorRef.current = -1;
    setSettings((s) => ({ ...s, voice: !s.voice }));
  }, []);

  // Escape key to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === " ") { e.preventDefault(); handlePlay(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, handlePlay]);

  const fontSize = FONT_SIZES[settings.fontSize];
  const light = settings.light;

  // Theme-dependent classes
  const bg = light ? "bg-white" : "bg-black";
  const fg = light ? "text-black" : "text-white";
  const fgDim = light ? "text-black/70" : "text-white/70";
  const fgMuted = light ? "text-black/50" : "text-white/50";
  const fgCountdown = light ? "text-black/80" : "text-white/80";
  const barBg = light ? "bg-black/10" : "bg-white/10";
  const barFill = light ? "bg-black/60" : "bg-white/60";
  const btnBg = light ? "bg-black/10" : "bg-white/10";
  const btnHover = light ? "hover:bg-black/20 hover:text-black" : "hover:bg-white/20 hover:text-white";
  const playBg = light ? "bg-black/15 hover:bg-black/25" : "bg-white/20 hover:bg-white/30";
  const controlsBg = light ? "bg-white/90" : "bg-black/90";
  const controlsBorder = light ? "border-black/10" : "border-white/10";
  const sliderTrack = light ? "bg-black/20" : "bg-white/20";
  const sliderThumb = light ? "[&::-webkit-slider-thumb]:bg-black" : "[&::-webkit-slider-thumb]:bg-white";
  const sliderAccent = light ? "accent-black" : "accent-white";
  const voiceActiveBg = light ? "bg-emerald-500/20 text-emerald-700" : "bg-emerald-400/20 text-emerald-300";

  // Per-word highlight (voice mode only, once reading has started).
  const wordClass = (wi: number): string => {
    if (highlightIdx < 0) return "";
    if (wi === highlightIdx) {
      return light
        ? "text-emerald-600 bg-emerald-500/10 rounded"
        : "text-emerald-400 bg-emerald-400/15 rounded";
    }
    if (wi < highlightIdx) return light ? "text-black/40" : "text-white/40";
    return "";
  };

  return createPortal(
    <div className={`fixed inset-0 z-[9999] ${bg} flex flex-col select-none transition-colors duration-300`}>
      {/* Progress bar */}
      <div className={`h-1 w-full ${barBg} shrink-0`}>
        <div
          className={`h-full ${barFill} transition-[width] duration-100`}
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      {/* Close button */}
      <button
        onClick={onClose}
        className={`absolute top-3 right-3 z-10 w-10 h-10 flex items-center justify-center
          rounded-full ${btnBg} ${fgDim} ${btnHover} transition-colors cursor-pointer`}
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
          <path d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Countdown overlay */}
      {countdown !== null && (
        <div className="absolute inset-0 z-20 flex items-center justify-center">
          <span className={`${fgCountdown} text-8xl font-light tabular-nums animate-pulse`}>
            {countdown}
          </span>
        </div>
      )}

      {/* Script text */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-6 sm:px-10 py-20"
        style={{ WebkitOverflowScrolling: "touch" }}
      >
        <pre
          className={`${fg} leading-relaxed whitespace-pre-wrap break-words font-sans max-w-2xl mx-auto`}
          style={{ fontSize: `${fontSize}px`, lineHeight: 1.6 }}
        >
          {voiceMode
            ? segments.map((s, i) =>
                s.wi === null ? (
                  s.text
                ) : (
                  <span
                    key={i}
                    data-wi={s.wi}
                    className={`transition-colors duration-150 ${wordClass(s.wi)}`}
                  >
                    {s.text}
                  </span>
                ),
              )
            : text}
        </pre>
        {/* Extra space at bottom so text can scroll fully */}
        <div className="h-[70vh]" />
      </div>

      {/* Controls */}
      <div className={`shrink-0 ${controlsBg} backdrop-blur-sm border-t ${controlsBorder} px-4 py-3 safe-area-pb`}>
        {micDenied && (
          <p className="text-xs text-red-500 text-center mb-2 max-w-2xl mx-auto">
            {t.teleprompter_voice_denied}
          </p>
        )}
        <div className="flex items-center justify-between gap-3 max-w-2xl mx-auto">
          {/* Restart */}
          <button
            onClick={handleRestart}
            className={`w-11 h-11 flex items-center justify-center rounded-full ${btnBg}
              ${fgDim} ${btnHover} transition-colors cursor-pointer`}
            title={t.teleprompter_restart}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
              <path d="M1 4v6h6" />
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
            </svg>
          </button>

          {/* Play / Pause */}
          <button
            onClick={handlePlay}
            className={`w-14 h-14 flex items-center justify-center rounded-full ${playBg}
              ${fg} transition-colors cursor-pointer`}
          >
            {isPlaying ? (
              <svg className="w-7 h-7" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
            ) : (
              <svg className="w-7 h-7" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            )}
          </button>

          {/* Voice follow + Font size + Theme */}
          <div className="flex items-center gap-1.5">
            {SPEECH_SUPPORTED && (
              <button
                onClick={toggleVoice}
                className={`w-11 h-11 flex items-center justify-center rounded-full transition-colors cursor-pointer
                  ${settings.voice ? voiceActiveBg : `${btnBg} ${fgDim} ${btnHover}`}`}
                title={t.teleprompter_voice}
                aria-pressed={settings.voice}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                  <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
                </svg>
              </button>
            )}
            <button
              onClick={cycleFontSize}
              className={`w-11 h-11 flex items-center justify-center rounded-full ${btnBg}
                ${fgDim} ${btnHover} transition-colors cursor-pointer
                text-sm font-bold`}
              title={t.teleprompter_font_size}
            >
              {FONT_LABELS[settings.fontSize]}
            </button>
            <button
              onClick={toggleTheme}
              className={`w-11 h-11 flex items-center justify-center rounded-full ${btnBg}
                ${fgDim} ${btnHover} transition-colors cursor-pointer`}
              title={t.teleprompter_theme}
            >
              {light ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                  <circle cx="12" cy="12" r="5" />
                  <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Speed slider — hidden in voice mode (scroll follows speech) */}
        {voiceMode ? (
          <div className="flex items-center justify-center gap-2 mt-3 max-w-2xl mx-auto">
            <svg className={`w-4 h-4 ${fgMuted}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
            </svg>
            <span className={`${fgMuted} text-xs`}>{t.teleprompter_voice}</span>
          </div>
        ) : (
          <div className="flex items-center gap-3 mt-3 max-w-2xl mx-auto">
            <span className={`${fgMuted} text-xs w-8 text-right shrink-0 tabular-nums`}>
              {settings.speed.toFixed(1)}×
            </span>
            <input
              type="range"
              min={0.5}
              max={5}
              step={0.1}
              value={settings.speed}
              onChange={(e) => updateSpeed(Math.round(Number(e.target.value) * 10) / 10)}
              className={`flex-1 h-1 ${sliderAccent} appearance-none ${sliderTrack} rounded-full
                [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5
                [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:rounded-full
                ${sliderThumb} [&::-webkit-slider-thumb]:cursor-pointer`}
            />
            <svg className={`w-4 h-4 ${fgMuted} shrink-0`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
