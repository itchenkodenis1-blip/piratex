import { useState, useEffect, useCallback, useRef } from "react";
import { deepAnalyzeInstagram, getSettings, updateSettings } from "../api/client";
import { extractInstagramUsername } from "../utils/instagram";
import { NICHES } from "../constants/niches";
import { useTranslation } from "../i18n";
import { useRegion } from "../region";
import { DEEP_ANALYSIS_KEY } from "../types";
import type { DeepAnalyzeResult, DeepAnalysisCache, BlogAnalysisProgress, UserProfile } from "../types";

// TONES and STATUS_LABELS are now inside the component to use translations

interface OnboardingModalProps {
  isOpen: boolean;
  onComplete: () => void;
  onSkip: () => void;
  refreshUser: () => Promise<void>;
  initialStep?: "choice" | "instagram" | "from_scratch";
}

type Step = "choice" | "from_scratch" | "instagram" | "analyzing" | "review";

export function OnboardingModal({ isOpen, onComplete, onSkip, refreshUser, initialStep = "choice" }: OnboardingModalProps) {
  const { t } = useTranslation();
  const regionConfig = useRegion();

  const TONES = [
    { key: "conversational", label: t.onboarding_tone_conversational, desc: t.onboarding_tone_conversational_desc },
    { key: "expert", label: t.onboarding_tone_expert, desc: t.onboarding_tone_expert_desc },
    { key: "energetic", label: t.onboarding_tone_energetic, desc: t.onboarding_tone_energetic_desc },
    { key: "calm", label: t.onboarding_tone_calm, desc: t.onboarding_tone_calm_desc },
  ];

  const STATUS_LABELS: Record<string, string> = {
    scraping: t.onboarding_da_scraping,
    downloading: t.onboarding_da_downloading,
    transcribing: t.onboarding_da_transcribing,
    analyzing_frames: t.onboarding_da_analyzing_frames,
    extracting_patterns: t.onboarding_da_extracting_patterns,
    analyzing_posts: t.onboarding_da_analyzing_posts,
    generating_profile: t.onboarding_da_generating_profile,
    done: t.onboarding_da_done,
  };
  const [step, setStep] = useState<Step>("choice");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // From scratch state
  const [scratchAbout, setScratchAbout] = useState("");
  const [scratchNiches, setScratchNiches] = useState<string[]>([]);
  const [scratchTone, setScratchTone] = useState("conversational");

  // Instagram analysis state
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);
  const [username, setUsername] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState("");
  const [progressStatus, setProgressStatus] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  // Minimized floating indicator state
  const [minimized, setMinimized] = useState(false);
  // Analysis completed but not yet viewed
  const [analysisComplete, setAnalysisComplete] = useState(false);

  // Time estimation
  const analysisStartTimeRef = useRef<number>(0);
  const progressRef = useRef(0); // monotonic progress tracking
  const [estimatedTimeLeft, setEstimatedTimeLeft] = useState<string>("");

  // Keep progress monotonic (parallel reel processing sends out-of-order updates)
  const updateProgress = useCallback((newProgress: number) => {
    if (newProgress > progressRef.current) {
      progressRef.current = newProgress;
      setProgress(newProgress);

      // Calculate time estimation
      if (newProgress > 5 && analysisStartTimeRef.current > 0) {
        const elapsed = (Date.now() - analysisStartTimeRef.current) / 1000;
        const rate = newProgress / elapsed; // percent per second
        const remaining = (100 - newProgress) / rate;

        if (remaining < 60) {
          setEstimatedTimeLeft(`~${Math.max(Math.ceil(remaining), 5)} ${t.onboarding_time_sec}`);
        } else {
          const mins = Math.ceil(remaining / 60);
          setEstimatedTimeLeft(`~${mins} ${t.onboarding_time_min}`);
        }
      }
    }
  }, []);

  // Review state
  const [result, setResult] = useState<DeepAnalyzeResult | null>(null);
  const [editAbout, setEditAbout] = useState("");
  const [editTone, setEditTone] = useState("");
  const [editNiches, setEditNiches] = useState<string[]>([]);
  const [editInterests, setEditInterests] = useState<string[]>([]);
  const [editVideoFormat, setEditVideoFormat] = useState("");
  const [editScriptCta, setEditScriptCta] = useState("");
  const [editDescCta, setEditDescCta] = useState("");
  const [editForbidden, setEditForbidden] = useState("");
  const [editPromptAdditions, setEditPromptAdditions] = useState("");
  const [consentChecked, setConsentChecked] = useState(false);

  // Reset state when modal opens; restore from localStorage if analysis was in progress
  useEffect(() => {
    if (isOpen) {
      // Check if there's a cached analysis state before resetting
      let restored = false;
      try {
        const raw = localStorage.getItem(DEEP_ANALYSIS_KEY);
        if (raw) {
          const cached: DeepAnalysisCache = JSON.parse(raw);
          if (cached.status === "done") {
            // Analysis finished while user was away — load results from backend
            restored = true;
            setUsername(cached.username);
            setError(null);
            setSaving(false);
            setConsentChecked(false);
            setStep("analyzing");
            setAnalyzing(true);
            setProgress(100);
            setProgressMessage(t.onboarding_da_loading);
            setProgressStatus("done");
            localStorage.removeItem(DEEP_ANALYSIS_KEY);
            // Fetch the saved profile and transition to review
            getSettings().then((settings) => {
              const analysis = settings.profile;
              if (analysis) {
                const res: DeepAnalyzeResult = {
                  analysis_id: cached.analysisId,
                  about_me: analysis.about_me || "",
                  tone: analysis.tone || "conversational",
                  niches: analysis.niches || [],
                  interests: analysis.interests || [],
                  video_format: analysis.video_format || "",
                  script_cta: analysis.script_cta || "",
                  description_cta: analysis.description_cta || "",
                  forbidden_words: analysis.forbidden_words || "",
                  content_prompt_additions: analysis.content_prompt_additions || null,
                };
                setResult(res);
                setEditAbout(res.about_me);
                setEditTone(res.tone);
                setEditNiches(res.niches);
                setEditInterests(res.interests);
                setEditVideoFormat(res.video_format);
                setEditScriptCta(res.script_cta);
                setEditDescCta(res.description_cta);
                setEditForbidden(res.forbidden_words);
                setEditPromptAdditions(res.content_prompt_additions || "");
                setAnalysisComplete(true);
              } else {
                setStep("choice");
              }
              setAnalyzing(false);
            }).catch(() => {
              setStep("choice");
              setAnalyzing(false);
            });
          } else if (cached.status === "analyzing") {
            const elapsed = Date.now() - cached.startedAt;
            if (elapsed < 10 * 60 * 1000) {
              // Analysis still running — show progress UI
              restored = true;
              setUsername(cached.username);
              setError(null);
              setSaving(false);
              setConsentChecked(false);
              setAnalyzing(true);
              setProgress(0);
              setProgressMessage(t.onboarding_da_continues);
              setProgressStatus("analyzing_frames");
              setStep("analyzing");
              // Try reconnecting WebSocket
              const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
              try {
                const authToken = localStorage.getItem("token");
                if (authToken) {
                  const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/blog-analysis/${cached.analysisId}?token=${encodeURIComponent(authToken)}`);
                  wsRef.current = ws;
                  ws.onmessage = (event) => {
                    try {
                      const data: BlogAnalysisProgress = JSON.parse(event.data);
                      if (data.type === "progress") {
                        updateProgress(Math.round(data.progress * 100));
                        setProgressMessage(data.message);
                        setProgressStatus(data.status);
                      }
                    } catch { /* ignore */ }
                  };
                }
              } catch { /* non-critical */ }
            } else {
              // Stale (>10 min) — check if backend saved results
              restored = true;
              setStep("analyzing");
              setAnalyzing(true);
              setProgress(100);
              setProgressMessage(t.onboarding_da_checking);
              setProgressStatus("done");
              localStorage.removeItem(DEEP_ANALYSIS_KEY);
              getSettings().then((settings) => {
                if (settings.onboarding_completed && settings.profile) {
                  const p = settings.profile;
                  const res: DeepAnalyzeResult = {
                    analysis_id: cached.analysisId,
                    about_me: p.about_me || "",
                    tone: p.tone || "conversational",
                    niches: p.niches || [],
                    interests: p.interests || [],
                    video_format: p.video_format || "",
                    script_cta: p.script_cta || "",
                    description_cta: p.description_cta || "",
                    forbidden_words: p.forbidden_words || "",
                    content_prompt_additions: p.content_prompt_additions || null,
                  };
                  setResult(res);
                  setEditAbout(res.about_me);
                  setEditTone(res.tone);
                  setEditNiches(res.niches);
                  setEditInterests(res.interests);
                  setEditVideoFormat(res.video_format);
                  setEditScriptCta(res.script_cta);
                  setEditDescCta(res.description_cta);
                  setEditForbidden(res.forbidden_words);
                  setEditPromptAdditions(res.content_prompt_additions || "");
                  setAnalysisComplete(true);
                } else {
                  setError(t.onboarding_da_interrupted);
                  setStep("instagram");
                  setUsername(cached.username);
                }
                setAnalyzing(false);
              }).catch(() => {
                setStep("choice");
                setAnalyzing(false);
              });
            }
          } else if (cached.status === "error") {
            restored = true;
            setUsername(cached.username);
            setError(cached.error || t.onboarding_da_error);
            setStep("instagram");
            setAnalyzing(false);
            localStorage.removeItem(DEEP_ANALYSIS_KEY);
          }
        }
      } catch { localStorage.removeItem(DEEP_ANALYSIS_KEY); }

      if (!restored) {
        setStep(initialStep);
        setError(null);
        setSaving(false);
        setSaveSuccess(false);
        setScratchAbout("");
        setScratchNiches([]);
        setScratchTone("conversational");
        setUsername("");
        setAnalyzing(false);
        setProgress(0);
        progressRef.current = 0;
        analysisStartTimeRef.current = 0;
        setEstimatedTimeLeft("");
        setProgressMessage("");
        setProgressStatus("");
        setMinimized(false);
        setAnalysisComplete(false);
        setResult(null);
        setEditAbout("");
        setEditTone("");
        setEditNiches([]);
        setEditInterests([]);
        setEditVideoFormat("");
        setEditScriptCta("");
        setEditDescCta("");
        setEditForbidden("");
        setEditPromptAdditions("");
        setConsentChecked(false);
      }
    }
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [isOpen, initialStep]);

  // Poll localStorage for analysis completion (handles background async finishing)
  useEffect(() => {
    if (!analyzing) return;
    const interval = setInterval(() => {
      try {
        const raw = localStorage.getItem(DEEP_ANALYSIS_KEY);
        if (!raw) { setAnalyzing(false); return; }
        const cached: DeepAnalysisCache = JSON.parse(raw);
        if (cached.status === "done") {
          localStorage.removeItem(DEEP_ANALYSIS_KEY);
          // Fetch saved profile from backend and show review
          getSettings().then((settings) => {
            const analysis = settings.profile;
            if (analysis) {
              const res: DeepAnalyzeResult = {
                analysis_id: cached.analysisId,
                about_me: analysis.about_me || "",
                tone: analysis.tone || "conversational",
                niches: analysis.niches || [],
                interests: analysis.interests || [],
                video_format: analysis.video_format || "",
                script_cta: analysis.script_cta || "",
                description_cta: analysis.description_cta || "",
                forbidden_words: analysis.forbidden_words || "",
                content_prompt_additions: analysis.content_prompt_additions || null,
              };
              setResult(res);
              setEditAbout(res.about_me);
              setEditTone(res.tone);
              setEditNiches(res.niches);
              setEditInterests(res.interests);
              setEditVideoFormat(res.video_format);
              setEditScriptCta(res.script_cta);
              setEditDescCta(res.description_cta);
              setEditForbidden(res.forbidden_words);
              setEditPromptAdditions(res.content_prompt_additions || "");
              updateProgress(100);
              setProgressStatus("done");
              setProgressMessage(t.onboarding_da_ready);
              setEstimatedTimeLeft("");
              setAnalysisComplete(true);
            }
            setAnalyzing(false);
          }).catch(() => { setAnalyzing(false); });
        } else if (cached.status === "error") {
          localStorage.removeItem(DEEP_ANALYSIS_KEY);
          setAnalyzing(false);
          setError(cached.error || t.onboarding_da_error);
          setStep("instagram");
        }
      } catch { setAnalyzing(false); }
    }, 2000);
    return () => clearInterval(interval);
  }, [analyzing, updateProgress]);

  const handleFromScratchSave = useCallback(async () => {
    if (!scratchAbout.trim()) {
      setError(t.onboarding_tell_blog);
      return;
    }
    if (scratchNiches.length === 0) {
      setError(t.onboarding_select_niche);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const profile: UserProfile = {
        about_me: scratchAbout,
        niches: scratchNiches,
        tone: scratchTone,
      };
      await updateSettings({ profile, onboarding_completed: true });
      await refreshUser();
      setSaving(false);
      setSaveSuccess(true);
      setTimeout(() => onComplete(), 1500);
    } catch {
      setError(t.onboarding_save_error);
      setSaving(false);
    }
  }, [scratchAbout, scratchNiches, scratchTone, refreshUser, onComplete]);

  const handleStartAnalysis = useCallback(async () => {
    if (analyzing) return; // prevent double-invocation via rapid Enter key
    const cleanUsername = extractInstagramUsername(username);
    if (!cleanUsername) {
      setError(t.onboarding_enter_username);
      return;
    }

    const analysisId = crypto.randomUUID();

    setAnalyzing(true);
    setError(null);
    setProgress(0);
    progressRef.current = 0;
    analysisStartTimeRef.current = Date.now();
    setEstimatedTimeLeft(t.onboarding_da_time_estimate);
    setProgressMessage(t.onboarding_da_starting);
    setProgressStatus("scraping");
    setStep("analyzing");
    setMinimized(false);
    setAnalysisComplete(false);

    // Persist analysis state so it survives navigation
    const cache: DeepAnalysisCache = { status: "analyzing", username: cleanUsername, analysisId, startedAt: Date.now() };
    localStorage.setItem(DEEP_ANALYSIS_KEY, JSON.stringify(cache));

    // Connect WebSocket for progress before starting API call
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const authToken = localStorage.getItem("token");
    if (!authToken) throw new Error("No auth token");
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/blog-analysis/${analysisId}?token=${encodeURIComponent(authToken)}`;
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onmessage = (event) => {
        try {
          const data: BlogAnalysisProgress = JSON.parse(event.data);
          if (data.type === "progress") {
            updateProgress(Math.round(data.progress * 100));
            setProgressMessage(data.message);
            setProgressStatus(data.status);
          }
        } catch { /* ignore parse errors */ }
      };
      ws.onerror = () => { /* WebSocket errors are non-critical */ };
    } catch { /* WebSocket connection failure is non-critical */ }

    try {
      const res = await deepAnalyzeInstagram(cleanUsername, analysisId);
      if (mountedRef.current) {
        // Component still mounted — handle normally, clear localStorage
        localStorage.removeItem(DEEP_ANALYSIS_KEY);
        setResult(res);
        setEditAbout(res.about_me);
        setEditTone(res.tone);
        setEditNiches(res.niches);
        setEditInterests(res.interests);
        setEditVideoFormat(res.video_format);
        setEditScriptCta(res.script_cta);
        setEditDescCta(res.description_cta);
        setEditForbidden(res.forbidden_words);
        setEditPromptAdditions(res.content_prompt_additions || "");
        updateProgress(100);
        setProgressStatus("done");
        setProgressMessage(t.onboarding_da_ready);
        setEstimatedTimeLeft("");
        setAnalysisComplete(true);
      } else {
        // Component unmounted — persist for next mount to pick up
        localStorage.setItem(DEEP_ANALYSIS_KEY, JSON.stringify({ ...cache, status: "done" }));
      }
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { detail?: string } } };
      const message =
        axErr?.response?.data?.detail ||
        (err instanceof Error ? err.message : t.onboarding_da_error);
      if (mountedRef.current) {
        localStorage.removeItem(DEEP_ANALYSIS_KEY);
        setError(message);
        setStep("instagram");
      } else {
        localStorage.setItem(DEEP_ANALYSIS_KEY, JSON.stringify({ ...cache, status: "error", error: message }));
      }
    } finally {
      setAnalyzing(false);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    }
  }, [username, updateProgress]);

  const handleReviewSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      const profile: UserProfile = {
        about_me: editAbout,
        tone: editTone,
        niches: editNiches,
        interests: editInterests,
        video_format: editVideoFormat,
        script_cta: editScriptCta,
        description_cta: editDescCta,
        forbidden_words: editForbidden,
        content_prompt_additions: editPromptAdditions || null,
      };
      await updateSettings({ profile, onboarding_completed: true });
      localStorage.removeItem(DEEP_ANALYSIS_KEY);
      await refreshUser();
      setSaving(false);
      setSaveSuccess(true);
      setTimeout(() => onComplete(), 1500);
    } catch {
      setError(t.onboarding_save_error);
      setSaving(false);
    }
  }, [editAbout, editTone, editNiches, editInterests, editVideoFormat, editScriptCta, editDescCta, editForbidden, editPromptAdditions, refreshUser, onComplete]);

  const removeInterest = useCallback((tag: string) => {
    setEditInterests((prev) => prev.filter((t) => t !== tag));
  }, []);

  const toggleNiche = useCallback((niche: string, current: string[], setter: (v: string[]) => void) => {
    if (current.includes(niche)) {
      setter(current.filter((n) => n !== niche));
    } else if (current.length < 3) {
      setter([...current, niche]);
    }
  }, []);

  if (!isOpen) return null;

  // ── Minimized floating indicator ──
  if (step === "analyzing" && minimized) {
    const circumference = 2 * Math.PI * 22;
    const strokeDashoffset = circumference - (progress / 100) * circumference;

    return (
      <button
        onClick={() => setMinimized(false)}
        className="fixed bottom-6 right-6 z-50 group"
        aria-label={t.onboarding_open_analysis}
      >
        <div className="relative w-14 h-14 rounded-full bg-surface border border-border-subtle shadow-lg shadow-black/40 flex items-center justify-center cursor-pointer hover:scale-110 transition-transform active:scale-95">
          {/* Circular progress ring */}
          <svg className="absolute inset-0 w-14 h-14 -rotate-90" viewBox="0 0 48 48">
            <circle cx="24" cy="24" r="22" fill="none" stroke="currentColor" strokeWidth="2" className="text-surface-light" />
            <circle
              cx="24" cy="24" r="22" fill="none"
              stroke="currentColor" strokeWidth="2.5"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              className="text-cream transition-all duration-700 ease-out"
            />
          </svg>
          {/* Center content */}
          {analysisComplete ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-cream">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          ) : (
            <span className="text-cream text-xs font-bold">{progress}%</span>
          )}
        </div>
        {/* Tooltip on hover */}
        <div className="absolute bottom-full right-0 mb-2 px-3 py-1.5 bg-surface border border-border-subtle rounded-lg text-xs text-cream whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-lg">
          {analysisComplete ? t.onboarding_done_tooltip : `${t.onboarding_analyzing_title} ${progress}%${estimatedTimeLeft ? ` · ${estimatedTimeLeft}` : ""}`}
        </div>
      </button>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="relative bg-surface border border-border-subtle rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* Success overlay */}
        {saveSuccess && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-surface rounded-2xl animate-in fade-in duration-300">
            <div className="w-16 h-16 rounded-full bg-emerald-500/20 flex items-center justify-center mb-4">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-400">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <p className="text-cream text-lg font-semibold">{t.onboarding_da_ready}</p>
          </div>
        )}

        {/* Close button — always visible on choice step */}
        {step === "choice" && (
          <button
            onClick={onSkip}
            className="absolute top-4 right-4 text-cream-muted hover:text-cream transition-colors z-10"
            aria-label={t.modal_close}
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        )}

        {/* Step: Choice */}
        {step === "choice" && (
          <div className="p-6 sm:p-8 space-y-6">
            <div className="text-center space-y-3 pr-6">
              <h2 className="text-xl sm:text-2xl font-bold text-cream">{t.onboarding_title}</h2>
              <p className="text-cream-dim text-sm leading-relaxed">{t.onboarding_subtitle}</p>
            </div>

            <div className="space-y-3">
              <button
                onClick={() => { setStep("instagram"); setError(null); }}
                className="w-full p-4 bg-surface-light border border-border-subtle rounded-xl text-left hover:border-cream/30 transition-colors group"
              >
                <div className="text-cream font-medium group-hover:text-cream">{t.onboarding_ig_btn}</div>
                <div className="text-cream-muted text-sm mt-1">{t.onboarding_ig_desc}</div>
              </button>

              <button
                onClick={() => { setStep("from_scratch"); setError(null); }}
                className="w-full p-4 bg-surface-light border border-border-subtle rounded-xl text-left hover:border-cream/30 transition-colors group"
              >
                <div className="text-cream font-medium group-hover:text-cream">{t.onboarding_manual_btn}</div>
                <div className="text-cream-muted text-sm mt-1">{t.onboarding_manual_desc}</div>
              </button>
            </div>

            <button
              onClick={onSkip}
              className="w-full text-center text-sm text-cream-muted hover:text-cream transition-colors py-1"
            >
              {t.onboarding_skip}
            </button>
          </div>
        )}

        {/* Step: From Scratch */}
        {step === "from_scratch" && (
          <div className="p-6 sm:p-8 space-y-5">
            <div className="flex items-center gap-3">
              <button onClick={() => setStep("choice")} className="text-cream-muted hover:text-cream transition-colors">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M12 4L6 10L12 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
              <h2 className="text-lg font-bold text-cream">{t.onboarding_scratch_title}</h2>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm text-cream-dim">{t.onboarding_scratch_blog_label}</label>
              <textarea
                value={scratchAbout}
                onChange={(e) => setScratchAbout(e.target.value)}
                placeholder={t.onboarding_scratch_blog_placeholder}
                className="w-full bg-surface-light border border-border-subtle rounded-xl px-4 py-3 text-cream placeholder:text-cream-muted/50 text-sm resize-none focus:outline-none focus:border-cream/30 transition-colors"
                rows={4}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm text-cream-dim">{t.onboarding_scratch_niche_label}</label>
              <div className="flex flex-wrap gap-2">
                {NICHES.map((niche) => (
                  <button
                    key={niche}
                    onClick={() => toggleNiche(niche, scratchNiches, setScratchNiches)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                      scratchNiches.includes(niche)
                        ? "bg-cream text-[#0C0C0C]"
                        : "bg-surface-light border border-border-subtle text-cream-muted hover:text-cream hover:border-cream/30"
                    }`}
                  >
                    {(t[`niche_${niche}` as keyof typeof t] as string) || niche}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm text-cream-dim">{t.onboarding_scratch_tone_label}</label>
              <div className="grid grid-cols-2 gap-2">
                {TONES.map((tone) => (
                  <button
                    key={tone.key}
                    onClick={() => setScratchTone(tone.key)}
                    className={`p-3 rounded-xl text-left transition-colors ${
                      scratchTone === tone.key
                        ? "bg-cream/10 border border-cream/30"
                        : "bg-surface-light border border-border-subtle hover:border-cream/20"
                    }`}
                  >
                    <div className="text-cream text-sm font-medium">{tone.label}</div>
                    <div className="text-cream-muted text-xs mt-0.5">{tone.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Personal data consent — NOT pre-checked (152-ФЗ / GDPR) */}
            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={consentChecked}
                onChange={(e) => setConsentChecked(e.target.checked)}
                className="mt-0.5 w-4 h-4 rounded border-border-subtle accent-cream shrink-0"
              />
              <span className="text-xs text-cream-muted leading-relaxed">
                {t.consent_personal_data}{" "}
                <a href={regionConfig.privacyUrl} className="text-cream underline underline-offset-2">{t.footer_privacy}</a>
              </span>
            </label>

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <button
              onClick={handleFromScratchSave}
              disabled={saving || !consentChecked}
              className="w-full py-3 bg-cream text-[#0C0C0C] font-medium rounded-full text-sm hover:bg-cream-dim transition-colors disabled:opacity-50"
            >
              {saving ? t.onboarding_scratch_saving : t.onboarding_scratch_save}
            </button>
          </div>
        )}

        {/* Step: Instagram username */}
        {step === "instagram" && (
          <div className="p-6 sm:p-8 space-y-5">
            <div className="flex items-center gap-3">
              <button onClick={() => setStep("choice")} className="text-cream-muted hover:text-cream transition-colors">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M12 4L6 10L12 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
              <h2 className="text-lg font-bold text-cream">{t.onboarding_ig_step_title}</h2>
            </div>

            <p className="text-cream-muted text-sm">
              {t.onboarding_ig_step_desc}
            </p>

            <div className="relative">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-cream-muted text-sm">@</span>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleStartAnalysis()}
                placeholder={t.onboarding_ig_step_placeholder}
                className="w-full bg-surface-light border border-border-subtle rounded-xl pl-8 pr-4 py-3 text-cream placeholder:text-cream-muted/50 text-sm focus:outline-none focus:border-cream/30 transition-colors"
              />
            </div>

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <button
              onClick={handleStartAnalysis}
              disabled={analyzing || !username.trim()}
              className="w-full py-3 bg-cream text-[#0C0C0C] font-medium rounded-full text-sm hover:bg-cream-dim transition-colors disabled:opacity-50"
            >
              {t.onboarding_ig_step_analyze}
            </button>

            <p className="text-cream-muted text-xs text-center">
              {t.onboarding_ig_step_hint}
            </p>
          </div>
        )}

        {/* Step: Analyzing — full modal view */}
        {step === "analyzing" && !minimized && (
          <div className="p-6 sm:p-8 space-y-6">
            {/* Minimize button */}
            <button
              onClick={() => setMinimized(true)}
              className="absolute top-4 right-4 text-cream-muted hover:text-cream transition-colors z-10"
              aria-label={t.onboarding_minimize}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>

            {analysisComplete ? (
              /* ── Completion state ── */
              <div className="space-y-6 py-4">
                <div className="flex justify-center">
                  <div className="w-16 h-16 rounded-full bg-cream/10 border-2 border-cream flex items-center justify-center animate-[scaleIn_0.4s_ease-out]">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-cream">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </div>
                </div>

                <div className="text-center space-y-2">
                  <h2 className="text-xl font-bold text-cream">{t.onboarding_completed_title}</h2>
                  <p className="text-cream-muted text-sm">
                    {t.onboarding_completed_desc}
                  </p>
                </div>

                <div className="bg-surface-light border border-border-subtle rounded-xl p-4 space-y-2">
                  <div className="flex items-center gap-2 text-cream text-sm">
                    <span className="text-cream/60">@</span>
                    <span className="font-medium">{username.replace(/^@/, "")}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {[t.onboarding_tag_tone, t.onboarding_tag_niches, t.onboarding_tag_interests, t.onboarding_tag_video_format, t.onboarding_tag_cta].map((tag) => (
                      <span key={tag} className="px-2 py-0.5 rounded-full text-[10px] bg-cream/10 text-cream/70 border border-cream/10">
                        {tag} ✓
                      </span>
                    ))}
                  </div>
                </div>

                <button
                  onClick={() => {
                    setAnalysisComplete(false);
                    setStep("review");
                  }}
                  className="w-full py-3.5 bg-cream text-[#0C0C0C] font-semibold rounded-full text-sm hover:bg-cream-dim transition-all hover:scale-[1.02] active:scale-[0.98]"
                >
                  {t.onboarding_completed_view}
                </button>
              </div>
            ) : (
              /* ── Progress state ── */
              <>
                <div className="text-center space-y-2">
                  <h2 className="text-lg font-bold text-cream">{t.onboarding_analyzing_title}</h2>
                  <p className="text-cream-muted text-sm">@{username.replace(/^@/, "")}</p>
                </div>

                <div className="space-y-3">
                  <div className="w-full bg-surface-light rounded-full h-2.5 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-cream/80 to-cream rounded-full transition-all duration-700 ease-out"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-cream-muted text-sm">
                      {STATUS_LABELS[progressStatus] || progressStatus}
                    </span>
                    <span className="text-cream-dim text-sm font-medium">{progress}%</span>
                  </div>

                  {/* Time estimation */}
                  <div className="flex justify-between items-center text-xs text-cream-muted/70">
                    <span>{progressMessage}</span>
                    {estimatedTimeLeft && (
                      <span className="shrink-0 ml-2">{t.onboarding_time_remaining} {estimatedTimeLeft}</span>
                    )}
                  </div>
                </div>

                {/* Stages indicator */}
                <div className="flex justify-center gap-1">
                  {Object.keys(STATUS_LABELS).filter(k => k !== "done").map((key) => {
                    const stageKeys = Object.keys(STATUS_LABELS).filter(k => k !== "done");
                    const currentIdx = stageKeys.indexOf(progressStatus);
                    const thisIdx = stageKeys.indexOf(key);
                    const isActive = thisIdx === currentIdx;
                    const isDone = thisIdx < currentIdx;
                    return (
                      <div
                        key={key}
                        className={`h-1 rounded-full transition-all duration-500 ${
                          isDone ? "w-4 bg-cream" : isActive ? "w-6 bg-cream/70" : "w-3 bg-surface-light"
                        }`}
                      />
                    );
                  })}
                </div>

                <div className="flex justify-center">
                  <div className="animate-spin w-5 h-5 border-2 border-cream/20 border-t-cream rounded-full" />
                </div>
              </>
            )}
          </div>
        )}

        {/* Step: Review (edit-only — profile is already auto-saved by backend) */}
        {step === "review" && result && (
          <div className="p-6 sm:p-8 space-y-4">
            {/* Skip button — profile already saved, user can skip editing */}
            <button
              onClick={async () => {
                await refreshUser();
                onComplete();
              }}
              className="absolute top-4 right-4 text-cream-muted hover:text-cream transition-colors z-10"
              aria-label={t.onboarding_skip}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>

            <div className="text-center space-y-1 pr-6">
              <h2 className="text-lg font-bold text-cream">{t.onboarding_review_title}</h2>
              <p className="text-cream-muted text-xs">{t.onboarding_review_desc}</p>
            </div>

            <div className="space-y-3">
              {/* About me */}
              <div className="space-y-1">
                <label className="text-xs text-cream-dim">{t.onboarding_review_about}</label>
                <textarea
                  value={editAbout}
                  onChange={(e) => setEditAbout(e.target.value)}
                  className="w-full bg-surface-light border border-border-subtle rounded-xl px-3 py-2 text-cream text-sm resize-none focus:outline-none focus:border-cream/30 transition-colors"
                  rows={3}
                />
              </div>

              {/* Tone */}
              <div className="space-y-1">
                <label className="text-xs text-cream-dim">{t.onboarding_review_tone}</label>
                <div className="flex flex-wrap gap-1.5">
                  {TONES.map((tone) => (
                    <button
                      key={tone.key}
                      onClick={() => setEditTone(tone.key)}
                      className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                        editTone === tone.key || (editTone.startsWith("custom:") && tone.key === editTone)
                          ? "bg-cream text-[#0C0C0C]"
                          : "bg-surface-light border border-border-subtle text-cream-muted hover:text-cream"
                      }`}
                    >
                      {tone.label}
                    </button>
                  ))}
                  {editTone.startsWith("custom:") && (
                    <span className="px-3 py-1 rounded-full text-xs font-medium bg-cream text-[#0C0C0C]">
                      {editTone.replace("custom:", "")}
                    </span>
                  )}
                </div>
              </div>

              {/* Niches */}
              <div className="space-y-1">
                <label className="text-xs text-cream-dim">{t.onboarding_review_niches}</label>
                <div className="flex flex-wrap gap-1.5">
                  {NICHES.map((niche) => (
                    <button
                      key={niche}
                      onClick={() => toggleNiche(niche, editNiches, setEditNiches)}
                      className={`px-2.5 py-1 rounded-full text-xs transition-colors ${
                        editNiches.includes(niche)
                          ? "bg-cream text-[#0C0C0C] font-medium"
                          : "bg-surface-light border border-border-subtle text-cream-muted hover:text-cream"
                      }`}
                    >
                      {(t[`niche_${niche}` as keyof typeof t] as string) || niche}
                    </button>
                  ))}
                </div>
              </div>

              {/* Interests */}
              <div className="space-y-1">
                <label className="text-xs text-cream-dim">{t.onboarding_review_interests}</label>
                <div className="flex flex-wrap gap-1.5">
                  {editInterests.map((tag) => (
                    <button
                      key={tag}
                      onClick={() => removeInterest(tag)}
                      className="px-2.5 py-1 rounded-full text-xs bg-surface-light border border-border-subtle text-cream-dim hover:text-red-400 hover:border-red-400/30 transition-colors"
                    >
                      {tag} ×
                    </button>
                  ))}
                </div>
              </div>

              {/* Video format */}
              <div className="space-y-1">
                <label className="text-xs text-cream-dim">{t.onboarding_review_video_format}</label>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    { key: "head_plus_visual", label: t.onboarding_format_head_visual },
                    { key: "talking_head_only", label: t.onboarding_format_head_only },
                    { key: "screencast_voiceover", label: t.onboarding_format_screencast },
                  ].map((f) => (
                    <button
                      key={f.key}
                      onClick={() => setEditVideoFormat(f.key)}
                      className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                        editVideoFormat === f.key
                          ? "bg-cream text-[#0C0C0C]"
                          : "bg-surface-light border border-border-subtle text-cream-muted hover:text-cream"
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* CTA */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs text-cream-dim">{t.onboarding_review_script_cta}</label>
                  <input
                    value={editScriptCta}
                    onChange={(e) => setEditScriptCta(e.target.value)}
                    className="w-full bg-surface-light border border-border-subtle rounded-lg px-3 py-1.5 text-cream text-xs focus:outline-none focus:border-cream/30 transition-colors"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-cream-dim">{t.onboarding_review_desc_cta}</label>
                  <input
                    value={editDescCta}
                    onChange={(e) => setEditDescCta(e.target.value)}
                    className="w-full bg-surface-light border border-border-subtle rounded-lg px-3 py-1.5 text-cream text-xs focus:outline-none focus:border-cream/30 transition-colors"
                  />
                </div>
              </div>

              {/* Forbidden words */}
              <div className="space-y-1">
                <label className="text-xs text-cream-dim">{t.onboarding_review_forbidden}</label>
                <input
                  value={editForbidden}
                  onChange={(e) => setEditForbidden(e.target.value)}
                  className="w-full bg-surface-light border border-border-subtle rounded-lg px-3 py-1.5 text-cream text-xs focus:outline-none focus:border-cream/30 transition-colors"
                />
              </div>

              {/* Content prompt additions */}
              {result && (
                <div className="space-y-1">
                  <label className="text-xs text-cream-dim">
                    {t.onboarding_review_patterns}
                  </label>
                  <textarea
                    value={editPromptAdditions}
                    onChange={(e) => setEditPromptAdditions(e.target.value)}
                    className="w-full bg-surface-light border border-border-subtle rounded-xl px-3 py-2 text-cream text-xs resize-none focus:outline-none focus:border-cream/30 transition-colors"
                    rows={2}
                  />
                </div>
              )}
            </div>

            {/* Personal data consent — NOT pre-checked (152-ФЗ / GDPR) */}
            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={consentChecked}
                onChange={(e) => setConsentChecked(e.target.checked)}
                className="mt-0.5 w-4 h-4 rounded border-border-subtle accent-cream shrink-0"
              />
              <span className="text-xs text-cream-muted leading-relaxed">
                {t.consent_personal_data}{" "}
                <a href={regionConfig.privacyUrl} className="text-cream underline underline-offset-2">{t.footer_privacy}</a>
              </span>
            </label>

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <div className="space-y-2">
              <button
                onClick={handleReviewSave}
                disabled={saving || !consentChecked}
                className="w-full py-3 bg-cream text-[#0C0C0C] font-medium rounded-full text-sm hover:bg-cream-dim transition-colors disabled:opacity-50"
              >
                {saving ? t.onboarding_review_saving : t.onboarding_review_save}
              </button>
              <button
                onClick={async () => {
                  await refreshUser();
                  onComplete();
                }}
                className="w-full text-center text-sm text-cream-muted hover:text-cream transition-colors py-1"
              >
                {t.onboarding_review_skip}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
