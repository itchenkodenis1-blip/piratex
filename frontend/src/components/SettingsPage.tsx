import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { getSettings, updateSettings, getDefaultPrompts, getProfilePresets, getSettingsInterests, getRadarSettings, deepAnalyzeInstagram, deleteAccount, getTelegramStatus, disconnectTelegram, createTelegramConnectCode, checkTelegramCode } from "../api/client";
import { NICHES } from "../constants/niches";
import { extractInstagramUsername } from "../utils/instagram";
import { useAuth } from "../hooks/useAuth";
import { useTranslation, LANGUAGE_LABELS, LANGUAGE_FLAGS, SUPPORTED_LANGUAGES } from "../i18n";
import type { SupportedLanguage, Translations } from "../i18n";
import { DEEP_ANALYSIS_KEY } from "../types";
import type { UserProfile, ProfilePresets, SuggestedInterest, RadarSettings, DeepAnalysisCache } from "../types";
import { SubscriptionSettings } from "./SubscriptionSettings";
import { QRCodeSVG } from "qrcode.react";

interface Props {
  onClose?: () => void;
}

/* ------------------------------------------------------------------ */
/*  PresetSelector — card-style radio for tone / video format          */
/* ------------------------------------------------------------------ */
interface PresetSelectorProps {
  presets: Record<string, { text: string; labels: Record<string, string> }>;
  value: string | null | undefined;
  onChange: (value: string) => void;
  lang: string;
  customLabel: string;
  customPlaceholder: string;
}

function PresetSelector({ presets, value, onChange, lang, customLabel, customPlaceholder }: PresetSelectorProps) {
  const presetKeys = Object.keys(presets);
  const isPreset = value != null && presetKeys.includes(value);
  const isCustom = value != null && !isPreset && value !== "";

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {presetKeys.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            className={`text-left px-4 py-3 rounded-xl transition-colors border ${
              value === key
                ? "bg-cream text-[#0C0C0C] border-cream"
                : "bg-surface-light text-cream-dim border-border-subtle hover:border-cream-muted/30"
            }`}
          >
            <span className="text-sm font-medium block">{presets[key].labels[lang] || key}</span>
            <span className={`text-xs mt-1 block leading-snug ${value === key ? "text-[#0C0C0C]/60" : "text-cream-muted"}`}>
              {presets[key].text.slice(0, 60)}…
            </span>
          </button>
        ))}
        <button
          type="button"
          onClick={() => onChange(isCustom && value ? value : "")}
          className={`text-left px-4 py-3 rounded-xl transition-colors border ${
            isCustom || (value != null && value === "")
              ? "bg-cream text-[#0C0C0C] border-cream"
              : "bg-surface-light text-cream-dim border-border-subtle hover:border-cream-muted/30"
          }`}
        >
          <span className="text-sm font-medium">{customLabel}</span>
        </button>
      </div>
      {(isCustom || (value != null && !isPreset)) && (
        <textarea
          value={isCustom ? value : ""}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          placeholder={customPlaceholder}
          className="w-full px-3 py-2.5 bg-surface-light border border-border-subtle rounded-xl text-sm text-cream-dim placeholder-cream-muted focus:outline-none focus:border-cream-muted resize-y leading-relaxed transition-colors"
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PromptEditor — advanced mode raw prompt textarea (kept as-is)     */
/* ------------------------------------------------------------------ */
interface PromptEditorProps {
  label: string;
  hint: string;
  value: string;
  isCustom: boolean;
  defaultPrompt: string;
  onSave: (value: string) => Promise<void>;
  t: Translations;
}

function PromptEditor({ label, hint, value, isCustom, defaultPrompt, onSave, t }: PromptEditorProps) {
  const [expanded, setExpanded] = useState(false);
  const [text, setText] = useState(value);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setText(value);
    setDirty(false);
  }, [value]);

  const handleChange = (newText: string) => {
    setText(newText);
    setDirty(newText !== value);
    setMessage(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await onSave(text);
      setDirty(false);
      setMessage(t.settings_prompt_saved);
    } catch {
      setMessage(t.settings_save_error);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm(t.settings_prompt_reset_confirm)) return;
    setSaving(true);
    setMessage(null);
    try {
      await onSave("");
      setText(defaultPrompt);
      setDirty(false);
      setMessage(t.settings_prompt_saved);
    } catch {
      setMessage(t.settings_save_error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-border-subtle rounded-2xl overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-surface-light/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <svg
            className={`w-4 h-4 text-cream-muted transition-transform ${expanded ? "rotate-90" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
          <span className="text-sm font-medium text-cream">{label}</span>
        </div>
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${
            isCustom
              ? "bg-cream/10 text-cream"
              : "bg-surface-light text-cream-muted"
          }`}
        >
          {isCustom ? t.settings_prompt_custom : t.settings_prompt_using_default}
        </span>
      </button>

      {expanded && (
        <div className="px-5 pb-5 space-y-3 border-t border-border-subtle">
          <p className="text-xs text-cream-muted pt-3">{hint}</p>
          <textarea
            value={text}
            onChange={(e) => handleChange(e.target.value)}
            rows={8}
            className="w-full px-3 py-2.5 bg-surface-light border border-border-subtle rounded-xl text-sm text-cream-dim placeholder-cream-muted focus:outline-none focus:border-cream-muted resize-y font-mono leading-relaxed transition-colors"
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <button
                onClick={handleSave}
                disabled={saving || !dirty}
                className="px-4 py-2 text-sm bg-cream text-[#0C0C0C] hover:bg-cream-dim disabled:bg-surface-light disabled:text-cream-muted disabled:cursor-not-allowed font-medium rounded-full transition-colors"
              >
                {saving ? "..." : t.settings_save}
              </button>
              {isCustom && (
                <button
                  onClick={handleReset}
                  disabled={saving}
                  className="px-4 py-2 text-sm text-cream-dim hover:text-cream border border-border-subtle hover:border-cream-muted rounded-full transition-colors"
                >
                  {t.settings_prompt_reset}
                </button>
              )}
            </div>
            {message && (
              <span
                className={`text-xs ${
                  message === t.settings_save_error ? "text-red-400" : "text-green-400"
                }`}
              >
                {message}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  SettingsPage                                                       */
/* ------------------------------------------------------------------ */
export function SettingsPage({ onClose }: Props) {
  const navigate = useNavigate();
  const { t, lang, setLang } = useTranslation();

  // Profile state
  const [profile, setProfile] = useState<UserProfile>({});
  const [initialProfile, setInitialProfile] = useState<UserProfile>({});
  const [presets, setPresets] = useState<ProfilePresets | null>(null);
  const [profileDirty, setProfileDirty] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);

  // Interests (auto-detected from parsed reels)
  const [suggestedInterests, setSuggestedInterests] = useState<SuggestedInterest[]>([]);

  // Deep analysis
  const [onboardingCompleted, setOnboardingCompleted] = useState(false);
  const [deepUsername, setDeepUsername] = useState("");
  const [deepAnalyzing, setDeepAnalyzing] = useState(false);
  const [deepProgress, setDeepProgress] = useState(0);
  const [deepMessage, setDeepMessage] = useState("");
  const [deepError, setDeepError] = useState("");
  const [deepDone, setDeepDone] = useState(false);
  const deepWsRef = useRef<WebSocket | null>(null);

  // Content Radar
  const [radar, setRadar] = useState<RadarSettings | null>(null);

  // Advanced mode (raw prompts)
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [contentPrompt, setContentPrompt] = useState("");
  const [strategyPrompt, setStrategyPrompt] = useState("");
  const [contentIsCustom, setContentIsCustom] = useState(false);
  const [strategyIsCustom, setStrategyIsCustom] = useState(false);
  const [defaultContentPrompt, setDefaultContentPrompt] = useState("");
  const [defaultStrategyPrompt, setDefaultStrategyPrompt] = useState("");

  const hasAdvancedOverride = contentIsCustom || strategyIsCustom;
  const mountedRef = useRef(true);

  // Telegram connection state (shared by Hero + LinkedAccounts)
  const { refreshUser: refreshUserAuth } = useAuth();
  const heroRef = useRef<HTMLDivElement>(null);
  const [tgLinked, setTgLinked] = useState(false);
  const [tgUsername, setTgUsername] = useState<string | null>(null);
  const [tgLoading, setTgLoading] = useState(true);
  const [tgDisconnecting, setTgDisconnecting] = useState(false);

  useEffect(() => {
    getTelegramStatus()
      .then((s) => { setTgLinked(s.linked); setTgUsername(s.telegram_username); })
      .catch(() => {})
      .finally(() => setTgLoading(false));
  }, []);

  const handleTgDisconnect = async () => {
    setTgDisconnecting(true);
    try {
      await disconnectTelegram();
      setTgLinked(false);
      setTgUsername(null);
      await refreshUserAuth();
    } catch { /* disconnect failed — non-critical */ }
    setTgDisconnecting(false);
  };

  // Cleanup deep analysis WebSocket on unmount; track mounted state
  useEffect(() => {
    return () => {
      mountedRef.current = false;
      if (deepWsRef.current) {
        deepWsRef.current.close();
        deepWsRef.current = null;
      }
    };
  }, []);

  // Poll localStorage for analysis completion (handles background async handler finishing)
  useEffect(() => {
    if (!deepAnalyzing) return;
    const interval = setInterval(() => {
      try {
        const raw = localStorage.getItem(DEEP_ANALYSIS_KEY);
        if (!raw) { setDeepAnalyzing(false); return; }
        const cached: DeepAnalysisCache = JSON.parse(raw);
        if (cached.status === "done") {
          localStorage.removeItem(DEEP_ANALYSIS_KEY);
          // Reload fresh profile from backend
          getSettings().then((settings) => {
            const p = settings.profile || {};
            setProfile(p);
            setInitialProfile(p);
            setProfileDirty(false);
          }).catch(() => {});
          getSettingsInterests()
            .then((data) => setSuggestedInterests(data.suggested))
            .catch(() => {});
          setDeepAnalyzing(false);
          setDeepDone(true);
          setOnboardingCompleted(true);
        } else if (cached.status === "error") {
          localStorage.removeItem(DEEP_ANALYSIS_KEY);
          setDeepAnalyzing(false);
          setDeepError(cached.error || t.onboarding_da_error);
        }
      } catch {
        setDeepAnalyzing(false);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [deepAnalyzing]);

  useEffect(() => {
    // Load interests suggestions (non-blocking)
    getSettingsInterests()
      .then((data) => {
        setSuggestedInterests(data.suggested);
      })
      .catch(() => {});

    // Load radar settings (non-blocking)
    getRadarSettings()
      .then((data) => setRadar(data))
      .catch(() => {});

    Promise.all([getSettings(), getDefaultPrompts(), getProfilePresets()])
      .then(([settings, defaults, presetsData]) => {
        setPresets(presetsData);

        // Profile
        const p = settings.profile || {};
        setProfile(p);
        setInitialProfile(p);
        setOnboardingCompleted(settings.onboarding_completed || false);

        // Advanced mode prompts (only meaningful for paid tiers)
        setDefaultContentPrompt(defaults.content_prompt);
        setDefaultStrategyPrompt(defaults.strategy_prompt);

        const hasCustomContent = !!settings.custom_content_prompt;
        const hasCustomStrategy = !!settings.custom_strategy_prompt;
        setContentIsCustom(hasCustomContent);
        setStrategyIsCustom(hasCustomStrategy);
        setContentPrompt(hasCustomContent ? settings.custom_content_prompt! : defaults.content_prompt);
        setStrategyPrompt(hasCustomStrategy ? settings.custom_strategy_prompt! : defaults.strategy_prompt);

        // Auto-open advanced if user has custom prompts but no profile
        if ((hasCustomContent || hasCustomStrategy) && !settings.profile) {
          setAdvancedOpen(true);
        }

        // Restore deep analysis state from localStorage (survives navigation)
        try {
          const raw = localStorage.getItem(DEEP_ANALYSIS_KEY);
          if (raw) {
            const cached: DeepAnalysisCache = JSON.parse(raw);
            if (cached.status === "done") {
              // Analysis finished while user was away — profile already loaded above
              setDeepDone(true);
              setOnboardingCompleted(true);
              localStorage.removeItem(DEEP_ANALYSIS_KEY);
            } else if (cached.status === "error") {
              setDeepError(cached.error || t.onboarding_da_error);
              localStorage.removeItem(DEEP_ANALYSIS_KEY);
            } else if (cached.status === "analyzing") {
              const elapsed = Date.now() - cached.startedAt;
              if (elapsed < 10 * 60 * 1000) {
                // Analysis likely still running in background — show progress UI
                setDeepAnalyzing(true);
                setDeepUsername(cached.username);
                setDeepMessage(t.onboarding_da_continues);
                // Try reconnecting to WebSocket for live progress
                connectDeepWs(cached.analysisId);
              } else if (settings.onboarding_completed) {
                // Took too long but backend saved results
                setDeepDone(true);
                localStorage.removeItem(DEEP_ANALYSIS_KEY);
              } else {
                // Stale analysis — clean up
                setDeepError(t.onboarding_da_interrupted);
                localStorage.removeItem(DEEP_ANALYSIS_KEY);
              }
            }
          }
        } catch { localStorage.removeItem(DEEP_ANALYSIS_KEY); }
      })
      .catch((e) => {
        console.error("Settings load error:", e);
        setProfileMessage("error");
      });
  }, []);

  // Track dirty state
  const updateProfile = (patch: Partial<UserProfile>) => {
    const next = { ...profile, ...patch };
    setProfile(next);
    setProfileDirty(JSON.stringify(next) !== JSON.stringify(initialProfile));
    setProfileMessage(null);
  };

  const handleLanguageChange = (newLang: SupportedLanguage) => {
    setLang(newLang);
    updateSettings({ language: newLang }).catch(() => {});
  };

  const handleSaveProfile = async () => {
    setProfileSaving(true);
    setProfileMessage(null);
    try {
      const result = await updateSettings({ profile });
      const p = result.profile || {};
      setProfile(p);
      setInitialProfile(p);
      setProfileDirty(false);
      setProfileMessage(t.settings_profile_saved);
    } catch {
      setProfileMessage(t.settings_save_error);
    } finally {
      setProfileSaving(false);
    }
  };

  const handleResetProfile = async () => {
    if (!confirm(t.settings_profile_reset_confirm)) return;
    setProfileSaving(true);
    setProfileMessage(null);
    try {
      // Preserve radar settings when resetting profile fields
      const radarFields: Partial<UserProfile> = {};
      if (profile.radar_enabled !== undefined) radarFields.radar_enabled = profile.radar_enabled;
      if (profile.radar_mode) radarFields.radar_mode = profile.radar_mode;
      if (profile.radar_min_x_factor !== undefined) radarFields.radar_min_x_factor = profile.radar_min_x_factor;
      if (profile.radar_niches) radarFields.radar_niches = profile.radar_niches;
      if (profile.radar_quiet_hours !== undefined) radarFields.radar_quiet_hours = profile.radar_quiet_hours;

      await updateSettings({ profile: radarFields as UserProfile });
      setProfile(radarFields);
      setInitialProfile(radarFields);
      setProfileDirty(false);
      setProfileMessage(t.settings_profile_saved);
    } catch {
      setProfileMessage(t.settings_save_error);
    } finally {
      setProfileSaving(false);
    }
  };

  const handleSaveContentPrompt = async (value: string) => {
    const result = await updateSettings({ custom_content_prompt: value });
    const isCustom = !!result.custom_content_prompt;
    setContentIsCustom(isCustom);
    setContentPrompt(isCustom ? result.custom_content_prompt! : defaultContentPrompt);
  };

  const handleSaveStrategyPrompt = async (value: string) => {
    const result = await updateSettings({ custom_strategy_prompt: value });
    const isCustom = !!result.custom_strategy_prompt;
    setStrategyIsCustom(isCustom);
    setStrategyPrompt(isCustom ? result.custom_strategy_prompt! : defaultStrategyPrompt);
  };

  const handleDeepAnalyze = async () => {
    if (deepAnalyzing) return; // prevent double-invocation
    const clean = extractInstagramUsername(deepUsername);
    if (!clean) return;
    const analysisId = crypto.randomUUID();
    setDeepAnalyzing(true);
    setDeepError("");
    setDeepDone(false);
    setDeepProgress(0);
    setDeepMessage(t.onboarding_da_starting);

    // Persist analysis state so it survives page navigation
    const cache: DeepAnalysisCache = { status: "analyzing", username: clean, analysisId, startedAt: Date.now() };
    localStorage.setItem(DEEP_ANALYSIS_KEY, JSON.stringify(cache));

    // WebSocket for progress (stored in ref for cleanup on unmount)
    connectDeepWs(analysisId);

    try {
      await deepAnalyzeInstagram(clean, analysisId);
      if (mountedRef.current) {
        // Component still mounted — handle normally, clear localStorage
        localStorage.removeItem(DEEP_ANALYSIS_KEY);
        try {
          const settings = await getSettings();
          const p = settings.profile || {};
          setProfile(p);
          setInitialProfile(p);
          setProfileDirty(false);
        } catch { /* profile reload failed, but analysis result is saved */ }
        setDeepDone(true);
        setOnboardingCompleted(true);
        getSettingsInterests()
          .then((data) => setSuggestedInterests(data.suggested))
          .catch(() => {});
      } else {
        // Component unmounted — persist for next mount to pick up
        localStorage.setItem(DEEP_ANALYSIS_KEY, JSON.stringify({ ...cache, status: "done" }));
      }
    } catch (e: unknown) {
      const axErr = e as { response?: { data?: { detail?: string } } };
      const msg =
        axErr?.response?.data?.detail ||
        (e instanceof Error ? e.message : t.onboarding_da_error);
      if (mountedRef.current) {
        localStorage.removeItem(DEEP_ANALYSIS_KEY);
        setDeepError(msg);
      } else {
        localStorage.setItem(DEEP_ANALYSIS_KEY, JSON.stringify({ ...cache, status: "error", error: msg }));
      }
    } finally {
      setDeepAnalyzing(false);
      if (deepWsRef.current) {
        deepWsRef.current.close();
        deepWsRef.current = null;
      }
    }
  };

  /** Connect (or reconnect) to the progress WebSocket */
  const connectDeepWs = (analysisId: string) => {
    if (deepWsRef.current) { deepWsRef.current.close(); deepWsRef.current = null; }
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    try {
      const authToken = localStorage.getItem("token");
      if (!authToken) return;
      const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/blog-analysis/${analysisId}?token=${encodeURIComponent(authToken)}`);
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "progress") {
            setDeepProgress(Math.round(data.progress * 100));
            setDeepMessage(data.message || "");
          }
        } catch { /* ignore */ }
      };
      deepWsRef.current = ws;
    } catch { /* non-critical */ }
  };

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-serif font-medium text-cream">{t.settings_title}</h2>
        <button
          onClick={onClose || (() => navigate("/"))}
          className="text-sm text-cream-muted hover:text-cream transition-colors"
        >
          {t.settings_back}
        </button>
      </div>

      {/* Telegram Hero — top of settings when not connected */}
      {!tgLoading && !tgLinked && (
        <div ref={heroRef}>
          <TelegramHeroSection
            t={t}
            onConnected={async () => { setTgLinked(true); await refreshUserAuth(); getTelegramStatus().then(s => setTgUsername(s.telegram_username)).catch(() => {}); }}
          />
        </div>
      )}

      {/* Language section */}
      <div className="bg-surface border border-border-subtle rounded-2xl p-6 space-y-4">
        <h3 className="text-lg font-medium text-cream">{t.settings_language}</h3>

        <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
          {SUPPORTED_LANGUAGES.map((code) => (
            <button
              key={code}
              onClick={() => handleLanguageChange(code)}
              className={`flex flex-col items-center gap-1.5 px-3 py-3 rounded-xl transition-colors border ${
                code === lang
                  ? "bg-cream text-[#0C0C0C] border-cream font-medium"
                  : "bg-surface-light text-cream-dim border-border-subtle hover:border-cream-muted/30"
              }`}
            >
              <span className="text-lg">{LANGUAGE_FLAGS[code]}</span>
              <span className="text-xs font-medium">{LANGUAGE_LABELS[code]}</span>
            </button>
          ))}
        </div>

        <p className="text-xs text-cream-muted">
          {t.settings_language_hint}
        </p>
      </div>

      {/* Hero: Auto-analyze blog */}
      <div className="relative rounded-2xl p-[1px] bg-gradient-to-br from-cream/25 via-cream/5 to-cream/25">
        <div className="bg-surface rounded-2xl p-6 sm:p-8 space-y-5">
          <div className="flex items-start gap-3">
            {/* Sparkle icon */}
            <div className="w-10 h-10 rounded-xl bg-cream/10 flex items-center justify-center flex-shrink-0 mt-0.5">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="text-cream">
                <path d="M12 2L14.09 8.26L20 9.27L15.55 13.97L16.91 20L12 16.9L7.09 20L8.45 13.97L4 9.27L9.91 8.26L12 2Z" fill="currentColor" opacity="0.9" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-lg sm:text-xl font-medium text-cream">{t.settings_autoprofile_title}</h3>
              <p className="text-sm text-cream-dim mt-1">
                {t.settings_autoprofile_desc}
              </p>
            </div>
          </div>

          {/* State: Done */}
          {onboardingCompleted && !deepAnalyzing && !deepDone && !deepError && (
            <div className="bg-green-500/8 border border-green-500/15 rounded-xl px-4 py-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="text-green-400 flex-shrink-0">
                  <path d="M20 6L9 17L4 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="text-sm text-green-400">{t.settings_autoprofile_filled}</span>
              </div>
              <button
                onClick={() => setOnboardingCompleted(false)}
                className="text-xs text-cream-muted hover:text-cream transition-colors whitespace-nowrap"
              >
                {t.settings_autoprofile_reanalyze}
              </button>
            </div>
          )}

          {/* State: Just finished */}
          {deepDone && !deepAnalyzing && (
            <div className="bg-green-500/8 border border-green-500/15 rounded-xl px-4 py-3 flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="text-green-400 flex-shrink-0">
                <path d="M20 6L9 17L4 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="text-sm text-green-400">{t.settings_autoprofile_updated}</span>
            </div>
          )}

          {/* State: Input or re-analyze */}
          {(!onboardingCompleted || deepError) && !deepAnalyzing && !deepDone && (
            <>
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-cream-muted text-sm">@</span>
                  <input
                    type="text"
                    placeholder={t.settings_autoprofile_placeholder}
                    value={deepUsername}
                    onChange={(e) => setDeepUsername(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleDeepAnalyze()}
                    className="w-full bg-surface-light border border-border-subtle rounded-xl pl-9 pr-4 py-3 text-sm text-cream placeholder:text-cream-muted/50 focus:outline-none focus:border-cream/30 transition-colors"
                  />
                </div>
                <button
                  onClick={handleDeepAnalyze}
                  disabled={deepAnalyzing || !deepUsername.trim()}
                  className="bg-cream hover:bg-cream-dim text-[#0C0C0C] font-medium rounded-xl px-5 py-3 text-sm disabled:opacity-50 transition-colors whitespace-nowrap"
                >
                  {t.settings_autoprofile_analyze}
                </button>
              </div>
              <p className="text-cream-muted text-xs">{t.settings_autoprofile_hint}</p>
              {deepError && <p className="text-red-400 text-xs">{deepError}</p>}
            </>
          )}

          {/* State: Analyzing */}
          {deepAnalyzing && (
            <div className="space-y-3">
              <div className="w-full bg-surface-light rounded-full h-2 overflow-hidden">
                <div
                  className="h-full bg-cream rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${deepProgress}%` }}
                />
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="animate-spin w-4 h-4 border-2 border-cream/30 border-t-cream rounded-full" />
                  <span className="text-sm text-cream-dim">{deepMessage}</span>
                </div>
                <span className="text-sm text-cream-muted font-mono">{deepProgress}%</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Divider */}
      <div className="flex items-center gap-4 py-1">
        <div className="h-px flex-1 bg-border-subtle" />
        <span className="text-xs text-cream-muted whitespace-nowrap">Детальные настройки</span>
        <div className="h-px flex-1 bg-border-subtle" />
      </div>

      {/* Profile section */}
      <div className="bg-surface border border-border-subtle rounded-2xl p-6 space-y-6">
        <div>
          <h3 className="text-lg font-medium text-cream">{t.settings_profile}</h3>
          <p className="text-xs text-cream-muted mt-1">{t.settings_profile_hint}</p>
        </div>

        {/* Advanced mode warning */}
        {hasAdvancedOverride && (
          <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl px-4 py-3">
            <p className="text-xs text-amber-400">{t.settings_advanced_warning}</p>
          </div>
        )}

        {/* About me & audience */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-cream">{t.settings_about_me}</label>
          <p className="text-xs text-cream-muted">{t.settings_about_me_hint}</p>
          <textarea
            value={profile.about_me || ""}
            onChange={(e) => updateProfile({ about_me: e.target.value })}
            rows={3}
            placeholder={presets?.defaults.about_me || ""}
            className="w-full px-3 py-2.5 bg-surface-light border border-border-subtle rounded-xl text-sm text-cream-dim placeholder-cream-muted/50 focus:outline-none focus:border-cream-muted resize-y leading-relaxed transition-colors"
          />
        </div>

        {/* Interests */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-cream">{t.settings_interests}</label>
          <p className="text-xs text-cream-muted">{t.settings_interests_hint}</p>

          {/* Active interests */}
          {(profile.interests || []).length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {(profile.interests || []).map((topic) => (
                <span
                  key={topic}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm bg-cream text-[#0C0C0C] border border-cream"
                >
                  {topic.replace(/-/g, " ")}
                  <button
                    type="button"
                    onClick={() => {
                      const next = (profile.interests || []).filter((i) => i !== topic);
                      updateProfile({ interests: next.length > 0 ? next : null });
                    }}
                    className="ml-0.5 text-[#0C0C0C]/60 hover:text-[#0C0C0C] transition-colors"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-cream-dim italic">{t.settings_interests_empty}</p>
          )}

          {/* Suggested interests from parsed reels */}
          {suggestedInterests.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {suggestedInterests
                .filter((s) => !(profile.interests || []).includes(s.topic))
                .slice(0, 15)
                .map((s) => (
                  <button
                    key={s.topic}
                    type="button"
                    onClick={() => {
                      const current = profile.interests || [];
                      if (current.length >= 20) return;
                      updateProfile({ interests: [...current, s.topic] });
                    }}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-sm bg-surface-light text-cream-dim border border-border-subtle hover:border-cream-muted/30 transition-colors"
                  >
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    {s.display_name}
                    <span className="text-[10px] text-cream-muted ml-0.5">({s.count})</span>
                  </button>
                ))}
            </div>
          )}

          <p className="text-xs text-cream-dim">{t.settings_interests_auto_hint}</p>
        </div>

        {/* Tone */}
        {presets && (
          <div className="space-y-2">
            <label className="text-sm font-medium text-cream">{t.settings_tone}</label>
            <PresetSelector
              presets={presets.tone_presets}
              value={profile.tone}
              onChange={(v) => updateProfile({ tone: v })}
              lang={lang}
              customLabel={t.settings_custom_format}
              customPlaceholder={t.settings_tone_custom_placeholder}
            />
          </div>
        )}

        {/* CTAs */}
        <div className="grid grid-cols-1 gap-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-cream">{t.settings_script_cta}</label>
            <p className="text-xs text-cream-muted">{t.settings_script_cta_hint}</p>
            <input
              type="text"
              value={profile.script_cta || ""}
              onChange={(e) => updateProfile({ script_cta: e.target.value })}
              placeholder={presets?.defaults.script_cta || ""}
              className="w-full px-3 py-2.5 bg-surface-light border border-border-subtle rounded-xl text-sm text-cream-dim placeholder-cream-muted/50 focus:outline-none focus:border-cream-muted transition-colors"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-cream">{t.settings_description_cta}</label>
            <p className="text-xs text-cream-muted">{t.settings_description_cta_hint}</p>
            <input
              type="text"
              value={profile.description_cta || ""}
              onChange={(e) => updateProfile({ description_cta: e.target.value })}
              placeholder={presets?.defaults.description_cta || ""}
              className="w-full px-3 py-2.5 bg-surface-light border border-border-subtle rounded-xl text-sm text-cream-dim placeholder-cream-muted/50 focus:outline-none focus:border-cream-muted transition-colors"
            />
          </div>
        </div>

        {/* Forbidden words */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-cream">{t.settings_forbidden_words}</label>
          <p className="text-xs text-cream-muted">{t.settings_forbidden_words_hint}</p>
          <textarea
            value={profile.forbidden_words || ""}
            onChange={(e) => updateProfile({ forbidden_words: e.target.value })}
            rows={2}
            placeholder={presets?.defaults.forbidden_words || ""}
            className="w-full px-3 py-2.5 bg-surface-light border border-border-subtle rounded-xl text-sm text-cream-dim placeholder-cream-muted/50 focus:outline-none focus:border-cream-muted resize-y leading-relaxed transition-colors"
          />
        </div>

        {/* Video format */}
        {presets && (
          <div className="space-y-2">
            <label className="text-sm font-medium text-cream">{t.settings_video_format}</label>
            <PresetSelector
              presets={presets.video_format_presets}
              value={profile.video_format}
              onChange={(v) => updateProfile({ video_format: v })}
              lang={lang}
              customLabel={t.settings_custom_format}
              customPlaceholder={t.settings_video_format_custom_placeholder}
            />
          </div>
        )}

        {/* Bilingual scripts — auto second-language version */}
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <label className="text-sm font-medium text-cream">{t.settings_dual_language}</label>
              <p className="text-xs text-cream-muted mt-0.5">{t.settings_dual_language_hint}</p>
            </div>
            <button
              type="button"
              onClick={() => updateProfile({ dual_language_enabled: !(profile.dual_language_enabled ?? false) })}
              className={`relative w-11 h-6 rounded-full transition-colors shrink-0 ${
                (profile.dual_language_enabled ?? false) ? "bg-cream" : "bg-surface-light border border-border-subtle"
              }`}
            >
              <span
                className={`absolute top-0.5 w-5 h-5 rounded-full transition-transform ${
                  (profile.dual_language_enabled ?? false)
                    ? "translate-x-[22px] bg-[#0C0C0C]"
                    : "translate-x-0.5 bg-cream-muted"
                }`}
              />
            </button>
          </div>
          <div className="space-y-2">
            <label className="text-xs font-medium text-cream-muted">{t.settings_second_language}</label>
            <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
              {SUPPORTED_LANGUAGES.map((code) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => updateProfile({ second_language: code })}
                  className={`px-3 py-2.5 rounded-xl border text-sm transition-colors flex items-center justify-center gap-1.5 ${
                    profile.second_language === code
                      ? "bg-cream text-[#0C0C0C] border-cream"
                      : "bg-surface-light text-cream-dim border-border-subtle hover:border-cream-muted/40"
                  }`}
                >
                  <span>{LANGUAGE_FLAGS[code]}</span>
                  <span className="text-xs font-medium">{LANGUAGE_LABELS[code]}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Save / Reset */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
          <div className="flex items-center gap-2">
            <button
              onClick={handleSaveProfile}
              disabled={profileSaving || !profileDirty}
              className="px-5 py-2.5 text-sm bg-cream text-[#0C0C0C] hover:bg-cream-dim disabled:bg-surface-light disabled:text-cream-muted disabled:cursor-not-allowed font-medium rounded-full transition-colors"
            >
              {profileSaving ? "..." : t.settings_save}
            </button>
            {(profile.about_me || profile.tone || profile.script_cta || profile.description_cta || profile.forbidden_words || profile.video_format) && (
              <button
                onClick={handleResetProfile}
                disabled={profileSaving}
                className="px-4 py-2.5 text-sm text-cream-dim hover:text-cream border border-border-subtle hover:border-cream-muted rounded-full transition-colors"
              >
                {t.settings_profile_reset}
              </button>
            )}
          </div>
          {profileMessage && (
            <span
              className={`text-xs ${
                profileMessage === t.settings_save_error ? "text-red-400" : "text-green-400"
              }`}
            >
              {profileMessage}
            </span>
          )}
        </div>
      </div>

      {/* Content Radar */}
      {radar && (
        <div className="bg-surface border border-border-subtle rounded-2xl p-6 space-y-5">
          <div>
            <h3 className="text-lg font-medium text-cream">{t.settings_radar_title}</h3>
            <p className="text-xs text-cream-muted mt-1">{t.settings_radar_hint}</p>
          </div>

          {!radar.has_telegram && (
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl px-4 py-3">
              <p className="text-xs text-amber-400">{t.settings_radar_no_telegram}</p>
            </div>
          )}

          {/* Enable toggle */}
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-cream">{t.settings_radar_enabled}</label>
            <button
              type="button"
              onClick={() => {
                const next = !(profile.radar_enabled ?? true);
                updateProfile({ radar_enabled: next });
              }}
              className={`relative w-11 h-6 rounded-full transition-colors ${
                (profile.radar_enabled ?? true) ? "bg-cream" : "bg-surface-light border border-border-subtle"
              }`}
              disabled={!radar.has_telegram}
            >
              <span
                className={`absolute top-0.5 w-5 h-5 rounded-full transition-transform ${
                  (profile.radar_enabled ?? true)
                    ? "translate-x-[22px] bg-[#0C0C0C]"
                    : "translate-x-0.5 bg-cream-muted"
                }`}
              />
            </button>
          </div>

          {(profile.radar_enabled ?? true) && radar.has_telegram && (
            <>
              {/* Mode selector */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-cream">{t.settings_radar_mode}</label>
                <div className="grid grid-cols-3 gap-2">
                  {(["instant", "digest", "both"] as const).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => updateProfile({ radar_mode: mode })}
                      className={`px-3 py-2 rounded-xl text-sm transition-colors border ${
                        (profile.radar_mode ?? "instant") === mode
                          ? "bg-cream text-[#0C0C0C] border-cream font-medium"
                          : "bg-surface-light text-cream-dim border-border-subtle hover:border-cream-muted/30"
                      }`}
                    >
                      {t[`settings_radar_mode_${mode}` as keyof typeof t]}
                    </button>
                  ))}
                </div>
              </div>

              {/* Min X-factor slider */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-cream">{t.settings_radar_min_x}</label>
                  <span className="text-sm font-mono text-cream-dim">×{profile.radar_min_x_factor ?? 3.0}</span>
                </div>
                <input
                  type="range"
                  min={2}
                  max={10}
                  step={0.5}
                  value={profile.radar_min_x_factor ?? 3.0}
                  onChange={(e) => updateProfile({ radar_min_x_factor: parseFloat(e.target.value) })}
                  className="w-full accent-cream"
                />
                <p className="text-xs text-cream-muted">{t.settings_radar_min_x_hint}</p>
              </div>

              {/* Radar niches */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-cream">{t.settings_radar_niches}</label>
                <p className="text-xs text-cream-muted">{t.settings_radar_niches_hint}</p>
                <div className="flex flex-wrap gap-2">
                  {NICHES.map((niche) => {
                    const active = (profile.radar_niches || profile.niches || []).includes(niche);
                    return (
                      <button
                        key={niche}
                        type="button"
                        onClick={() => {
                          const current = profile.radar_niches || profile.niches || [];
                          const next = active
                            ? current.filter((n) => n !== niche)
                            : [...current, niche];
                          updateProfile({ radar_niches: next.length > 0 ? next.slice(0, 5) : null });
                        }}
                        className={`px-3 py-1.5 rounded-full text-xs transition-colors border ${
                          active
                            ? "bg-cream text-[#0C0C0C] border-cream"
                            : "bg-surface-light text-cream-dim border-border-subtle hover:border-cream-muted/30"
                        }`}
                      >
                        {(t[`niche_${niche}` as keyof typeof t] as string) || niche}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Quiet hours toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-sm font-medium text-cream">{t.settings_radar_quiet_hours}</label>
                  <p className="text-xs text-cream-muted mt-0.5">{t.settings_radar_quiet_hours_hint}</p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    const next = !(profile.radar_quiet_hours ?? true);
                    updateProfile({ radar_quiet_hours: next });
                  }}
                  className={`relative w-11 h-6 rounded-full transition-colors flex-shrink-0 ${
                    (profile.radar_quiet_hours ?? true) ? "bg-cream" : "bg-surface-light border border-border-subtle"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 w-5 h-5 rounded-full transition-transform ${
                      (profile.radar_quiet_hours ?? true)
                        ? "translate-x-[22px] bg-[#0C0C0C]"
                        : "translate-x-0.5 bg-cream-muted"
                    }`}
                  />
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Advanced mode toggle */}
      <div className="bg-surface border border-border-subtle rounded-2xl overflow-hidden">
        <button
          onClick={() => setAdvancedOpen(!advancedOpen)}
          className="w-full flex items-center justify-between px-6 py-4 hover:bg-surface-light/50 transition-colors"
        >
          <div>
            <span className="text-sm font-medium text-cream">{t.settings_advanced_mode}</span>
            <p className="text-xs text-cream-muted mt-0.5">{t.settings_advanced_mode_hint}</p>
          </div>
          <svg
            className={`w-4 h-4 text-cream-muted transition-transform ${advancedOpen ? "rotate-90" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>

        {advancedOpen && (
          <div className="px-6 pb-6 space-y-3 border-t border-border-subtle pt-4">
            <PromptEditor
              label={t.settings_content_prompt}
              hint={t.settings_content_prompt_hint}
              value={contentPrompt}
              isCustom={contentIsCustom}
              defaultPrompt={defaultContentPrompt}
              onSave={handleSaveContentPrompt}
              t={t}
            />

            <PromptEditor
              label={t.settings_strategy_prompt}
              hint={t.settings_strategy_prompt_hint}
              value={strategyPrompt}
              isCustom={strategyIsCustom}
              defaultPrompt={defaultStrategyPrompt}
              onSave={handleSaveStrategyPrompt}
              t={t}
            />
          </div>
        )}
      </div>

      {/* Subscription & Billing */}
      <SubscriptionSettings />


      {/* Linked Accounts (with Telegram management) */}
      <LinkedAccountsSection
        t={t}
        telegramUsername={tgUsername}
        onTelegramConnect={() => heroRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })}
        onTelegramDisconnect={handleTgDisconnect}
        telegramDisconnecting={tgDisconnecting}
      />

      {/* Delete Account — GDPR Article 17 */}
      <DeleteAccountSection t={t} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  TelegramHeroSection — prominent CTA at top of settings             */
/*  Only renders when Telegram is NOT connected                        */
/* ------------------------------------------------------------------ */
function TelegramHeroSection({ t, onConnected }: { t: Translations; onConnected: () => void }) {
  const { refreshUser } = useAuth();
  const [showQR, setShowQR] = useState(false);
  const [deepLink, setDeepLink] = useState("");
  const [qrExpired, setQrExpired] = useState(false);
  const [qrLoading, setQrLoading] = useState(false);
  const [qrError, setQrError] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const isMobile = typeof navigator !== "undefined" &&
    (navigator.maxTouchPoints > 0 || /Mobi|Android/i.test(navigator.userAgent));

  const handleConnect = async () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setShowQR(true);
    setQrLoading(true);
    setQrExpired(false);
    setQrError(false);
    try {
      const result = await createTelegramConnectCode();
      setDeepLink(result.deep_link);

      // On mobile, open deep link directly
      if (isMobile) {
        window.open(result.deep_link, "_blank");
      }

      pollRef.current = setInterval(async () => {
        try {
          const check = await checkTelegramCode(result.code);
          if (check.expired) {
            setQrExpired(true);
            if (pollRef.current) clearInterval(pollRef.current);
            return;
          }
          if (check.confirmed && check.token) {
            if (pollRef.current) clearInterval(pollRef.current);
            localStorage.setItem("token", check.token);
            await refreshUser();
            setShowQR(false);
            onConnected();
          }
        } catch { /* poll failed — retry on next interval */ }
      }, 2000);
    } catch {
      setQrError(true);
    }
    setQrLoading(false);
  };

  const valueProps = [
    t.settings_telegram_hero_vp1,
    t.settings_telegram_hero_vp2,
    t.settings_telegram_hero_vp3,
    t.settings_telegram_hero_vp4,
  ];

  return (
    <div className="bg-gradient-to-br from-[#2AABEE]/10 to-[#2AABEE]/5 border border-[#2AABEE]/30 rounded-2xl p-6 sm:p-8 text-center space-y-5">
      {/* Telegram icon */}
      <div className="flex justify-center">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="#2AABEE"><path d="M11.94 24c6.6 0 11.94-5.37 11.94-12S18.54 0 11.94 0 0 5.37 0 12s5.34 12 11.94 12zm-3.15-8.4l-.3-3.15 7.74-7.05c.33-.3-.08-.45-.54-.18L6.84 11.4l-3.06-.96c-.66-.18-.66-.66.15-.99l11.94-4.62c.54-.24 1.05.12.84.99l-2.04 9.6c-.15.66-.54.81-1.11.51l-3.06-2.25-1.47 1.41c-.18.18-.3.3-.54.3z"/></svg>
      </div>

      {/* Title */}
      <h3 className="text-lg sm:text-xl font-medium text-cream leading-snug">
        {t.settings_telegram_hero_title}
      </h3>

      {/* Value props */}
      <ul className="space-y-2 text-left max-w-sm mx-auto">
        {valueProps.map((vp, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm text-cream-dim">
            <svg className="w-4 h-4 text-[#2AABEE] flex-shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
            <span>{vp}</span>
          </li>
        ))}
      </ul>

      {/* Connect flow */}
      {showQR ? (
        <div className="space-y-4">
          {qrLoading ? (
            <div className="flex justify-center py-4">
              <div className="w-6 h-6 border-2 border-[#2AABEE] border-t-transparent rounded-full animate-spin" />
            </div>
          ) : qrError ? (
            <div className="space-y-2 py-2">
              <p className="text-red-400 text-sm">{t.auth_error_generic}</p>
              <button onClick={handleConnect} className="text-sm text-cream underline underline-offset-4 hover:text-cream-dim transition-colors">
                {t.modal_telegram_retry}
              </button>
            </div>
          ) : qrExpired ? (
            <div className="space-y-2 py-2">
              <p className="text-amber-400 text-sm">{t.modal_telegram_code_expired}</p>
              <button onClick={handleConnect} className="text-sm text-cream underline underline-offset-4 hover:text-cream-dim transition-colors">
                {t.modal_telegram_retry}
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {!isMobile && (
                <div className="flex justify-center">
                  <div className="bg-white p-3 rounded-xl inline-block">
                    <QRCodeSVG value={deepLink} size={160} />
                  </div>
                </div>
              )}
              {!isMobile && (
                <p className="text-cream-muted text-xs">{t.modal_telegram_scan_qr}</p>
              )}
              <a
                href={deepLink}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block px-5 py-2.5 bg-[#2AABEE] hover:bg-[#229ED9] text-white font-medium rounded-full text-sm transition-colors"
              >
                {t.modal_telegram_open_bot}
              </a>
            </div>
          )}
          <button
            onClick={() => { setShowQR(false); if (pollRef.current) clearInterval(pollRef.current); }}
            className="text-xs text-cream-muted hover:text-cream transition-colors"
          >
            {t.modal_back}
          </button>
        </div>
      ) : (
        <button
          onClick={handleConnect}
          className="px-6 py-3 bg-[#2AABEE] hover:bg-[#229ED9] text-white font-medium rounded-full text-sm transition-colors inline-flex items-center gap-2"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M11.94 24c6.6 0 11.94-5.37 11.94-12S18.54 0 11.94 0 0 5.37 0 12s5.34 12 11.94 12zm-3.15-8.4l-.3-3.15 7.74-7.05c.33-.3-.08-.45-.54-.18L6.84 11.4l-3.06-.96c-.66-.18-.66-.66.15-.99l11.94-4.62c.54-.24 1.05.12.84.99l-2.04 9.6c-.15.66-.54.81-1.11.51l-3.06-2.25-1.47 1.41c-.18.18-.3.3-.54.3z"/></svg>
          {t.settings_telegram_connect}
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  LinkedAccountsSection — actionable list of auth providers          */
/* ------------------------------------------------------------------ */
const PROVIDER_LABELS: Record<string, string> = {
  telegram: "Telegram",
  yandex: "Yandex",
  vk: "VK",
  google: "Google",
  email: "Email",
  phone: "Phone",
};

const PROVIDER_ICONS: Record<string, ReactNode> = {
  telegram: <svg width="16" height="16" viewBox="0 0 24 24" fill="#2AABEE"><path d="M11.94 24c6.6 0 11.94-5.37 11.94-12S18.54 0 11.94 0 0 5.37 0 12s5.34 12 11.94 12zm-3.15-8.4l-.3-3.15 7.74-7.05c.33-.3-.08-.45-.54-.18L6.84 11.4l-3.06-.96c-.66-.18-.66-.66.15-.99l11.94-4.62c.54-.24 1.05.12.84.99l-2.04 9.6c-.15.66-.54.81-1.11.51l-3.06-2.25-1.47 1.41c-.18.18-.3.3-.54.3z"/></svg>,
  yandex: <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 24C5.373 24 0 18.627 0 12S5.373 0 12 0s12 5.373 12 12-5.373 12-12 12zm1.252-17.63h-1.21c-2.142 0-3.27 1.27-3.27 2.877 0 1.787.718 2.695 2.217 3.79l1.237.897-3.537 5.558h-2.16l3.2-4.927c-1.807-1.378-2.77-2.7-2.77-4.85 0-2.665 1.83-4.558 5.007-4.558h3.39v14.335h-2.104V6.37z"/></svg>,
  vk: <svg width="16" height="16" viewBox="0 0 24 24" fill="#4680C2"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 13.4c.46.45.946.87 1.36 1.36.184.22.357.447.49.7.19.36.02.76-.3.78h-2.12c-.53.05-1.04-.17-1.43-.52-.32-.28-.61-.59-.91-.89-.12-.13-.25-.24-.4-.33-.3-.18-.56-.1-.72.21-.17.32-.2.67-.22 1.02-.02.52-.18.66-.7.68-1.11.06-2.17-.08-3.15-.58-1.07-.54-1.9-1.33-2.63-2.24C5.77 11.85 4.8 9.93 3.97 7.94c-.18-.44-.05-.68.43-.69.7-.01 1.4-.01 2.1 0 .3.01.51.18.63.46.43 1.03.95 2.02 1.59 2.94.17.25.35.49.6.66.27.19.48.12.6-.19.08-.2.12-.41.14-.62.06-.7.07-1.4-.04-2.1-.07-.44-.32-.72-.76-.8-.22-.04-.19-.13-.08-.24.19-.18.37-.3.73-.3h2.4c.38.08.46.26.51.64l.01 2.73c0 .15.08.59.35.7.22.07.36-.1.49-.24.59-.64 1.01-1.39 1.39-2.16.17-.34.31-.7.45-1.05.1-.26.27-.39.56-.39h2.31c.07 0 .14 0 .2.02.38.06.48.22.37.6-.18.6-.55 1.1-.92 1.59-.4.52-.82 1.03-1.2 1.57-.17.24-.15.48.05.72z"/></svg>,
  google: <svg width="16" height="16" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>,
  email: <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor" className="text-cream-muted"><path d="M2.003 5.884L10 9.882l7.997-3.998A2 2 0 0016 4H4a2 2 0 00-1.997 1.884z"/><path d="M18 8.118l-8 4-8-4V14a2 2 0 002 2h12a2 2 0 002-2V8.118z"/></svg>,
  phone: <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor" className="text-cream-muted"><path d="M2 3a1 1 0 011-1h2.153a1 1 0 01.986.836l.74 4.435a1 1 0 01-.54 1.06l-1.548.773a11.037 11.037 0 006.105 6.105l.774-1.548a1 1 0 011.059-.54l4.435.74a1 1 0 01.836.986V17a1 1 0 01-1 1h-2C7.82 18 2 12.18 2 5V3z"/></svg>,
};

function LinkedAccountsSection({ t, telegramUsername, onTelegramConnect, onTelegramDisconnect, telegramDisconnecting }: {
  t: Translations;
  telegramUsername: string | null;
  onTelegramConnect: () => void;
  onTelegramDisconnect: () => void;
  telegramDisconnecting: boolean;
}) {
  const { user, usage } = useAuth();
  const providers = user?.auth_providers ?? [];
  const hasTelegram = providers.includes("telegram");

  // Providers we can suggest linking (Telegram + Email only for now)
  const suggestableProviders = ["telegram", "email"].filter(p => !providers.includes(p));
  const showWarning = providers.length <= 1 && (usage?.used ?? 0) >= 5;

  return (
    <div className="bg-surface border border-border-subtle rounded-2xl p-6 space-y-3">
      <h3 className="text-lg font-medium text-cream">{t.settings_linked_accounts}</h3>

      {/* Connected providers */}
      {providers.length === 0 ? (
        <p className="text-sm text-cream-muted">{t.settings_linked_accounts_none}</p>
      ) : (
        <ul className="space-y-2">
          {providers.map((provider) => (
            <li key={provider} className="flex items-center justify-between">
              <div className="flex items-center gap-2.5 text-sm text-cream-dim">
                <svg className="w-4 h-4 text-green-400 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                {PROVIDER_ICONS[provider] || null}
                <span>{PROVIDER_LABELS[provider] || provider}</span>
                {provider === "telegram" && telegramUsername && (
                  <span className="text-cream-muted">@{telegramUsername}</span>
                )}
              </div>
              {provider === "telegram" && hasTelegram && (
                <button
                  onClick={onTelegramDisconnect}
                  disabled={telegramDisconnecting}
                  className="px-3 py-1 text-xs border border-border-subtle text-cream-muted hover:text-red-400 hover:border-red-500/30 rounded-full transition-colors"
                >
                  {telegramDisconnecting ? t.settings_telegram_disconnecting : t.settings_telegram_disconnect}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Warning: only 1 provider linked */}
      {showWarning && (
        <div className="flex items-start gap-2.5 bg-amber-900/15 border border-amber-700/25 rounded-xl px-4 py-3">
          <svg className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          <p className="text-sm text-amber-300/90">
            {t.settings_linked_accounts_warning}{" "}
            {(usage?.used ?? 0) >= 5 && (
              <span className="text-amber-400/70">{t.settings_linked_accounts_warning_analyses.replace("{count}", String(usage?.used ?? 0))}</span>
            )}
          </p>
        </div>
      )}

      {/* Unlinked suggestable providers */}
      {suggestableProviders.length > 0 && (
        <ul className="space-y-2 pt-1">
          {suggestableProviders.map((provider) => (
            <li key={provider} className="flex items-center justify-between">
              <div className="flex items-center gap-2.5 text-sm text-cream-muted">
                <svg className="w-4 h-4 text-cream-muted/40 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
                  <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.5" />
                </svg>
                {PROVIDER_ICONS[provider] || null}
                <span>{PROVIDER_LABELS[provider] || provider}</span>
                <span className="text-cream-muted/50">— {t.settings_linked_accounts_not_linked}</span>
              </div>
              {provider === "telegram" && (
                <button
                  onClick={onTelegramConnect}
                  className="px-3 py-1 text-xs bg-[#2AABEE]/15 text-[#2AABEE] hover:bg-[#2AABEE]/25 border border-[#2AABEE]/30 rounded-full transition-colors"
                >
                  {t.settings_linked_accounts_link}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  DeleteAccountSection — danger zone with confirmation dialog        */
/* ------------------------------------------------------------------ */
function DeleteAccountSection({ t }: { t: Translations }) {
  const navigate = useNavigate();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  const handleDelete = async () => {
    setDeleting(true);
    setError("");
    try {
      await deleteAccount();
      localStorage.removeItem("token");
      navigate("/");
      window.location.reload();
    } catch (e: unknown) {
      const axErr = e as { response?: { data?: { detail?: string } } };
      setError(axErr?.response?.data?.detail || "Error");
      setDeleting(false);
    }
  };

  return (
    <>
      <div className="bg-surface border border-red-500/20 rounded-2xl p-6 space-y-3">
        <h3 className="text-lg font-medium text-red-400">{t.settings_delete_account}</h3>
        <p className="text-sm text-cream-muted">{t.settings_delete_account_hint}</p>
        <button
          onClick={() => setConfirmOpen(true)}
          className="px-5 py-2.5 text-sm border border-red-500/30 text-red-400 hover:bg-red-500/10 hover:border-red-500/50 rounded-full transition-colors"
        >
          {t.settings_delete_account_btn}
        </button>
      </div>

      {/* Confirmation dialog */}
      {confirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-surface border border-border-subtle rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <h3 className="text-lg font-medium text-cream">{t.settings_delete_account_confirm_title}</h3>
            <p className="text-sm text-cream-dim leading-relaxed">{t.settings_delete_account_confirm_message}</p>
            {error && <p className="text-sm text-red-400">{error}</p>}
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => setConfirmOpen(false)}
                disabled={deleting}
                className="flex-1 py-2.5 px-4 border border-border-subtle rounded-full text-sm text-cream-dim hover:text-cream hover:border-cream-muted transition-colors"
              >
                {t.settings_delete_account_cancel}
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex-1 py-2.5 px-4 bg-red-600 hover:bg-red-700 disabled:bg-red-900 text-white rounded-full text-sm font-medium transition-colors"
              >
                {deleting ? t.settings_delete_account_deleting : t.settings_delete_account_confirm_btn}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
