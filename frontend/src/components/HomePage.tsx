import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createJob, getJob, updateJobFields } from "../api/client";
import { useTranslation } from "../i18n";
import { LiveResults } from "./LiveResults";
import { ResultsView } from "./ResultsView";
import { UrlInput } from "./UrlInput";
import { useJobPolling } from "../hooks/useJobPolling";
import { useJobWebSocket } from "../hooks/useJobWebSocket";
import type { AuthUser, JobResult, UsageInfo } from "../types";

type PageState = "input" | "processing" | "results" | "error";

interface HomePageProps {
  user: AuthUser | null;
  usage: UsageInfo | null;
  refreshUser: () => Promise<void>;
}

export function HomePage({ user, usage, refreshUser }: HomePageProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [state, setState] = useState<PageState>("input");
  const [jobId, setJobId] = useState<string | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  const [shareToken, setShareToken] = useState<string | null>(null);

  const initialUrl = searchParams.get("url") || "";
  const resumeJobId = searchParams.get("job_id");

  const { progress, liveData } = useJobWebSocket(
    state === "processing" ? jobId : null
  );

  const pollingResult = useJobPolling(state === "processing" ? jobId : null);

  // Resume a job when navigating with ?job_id=xxx (e.g. after auth redirect)
  useEffect(() => {
    if (!resumeJobId || jobId === resumeJobId) return;
    setJobId(resumeJobId);
    setError(null);
    setResult(null);
    // Try to fetch immediately — if completed, show results; otherwise start polling
    getJob(resumeJobId).then((data) => {
      if (data.status === "completed") {
        setResult(data);
        setState("results");
        refreshUser();
      } else if (data.status === "failed") {
        setError(data.error || t.home_error_processing);
        setState("error");
      } else {
        setState("processing");
      }
    }).catch((err: unknown) => {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404 || status === 403) {
        // Job not found or belongs to different user — show error
        setError(t.home_error_fetch);
        setState("error");
      } else {
        setState("processing");
      }
    });
  }, [resumeJobId, jobId, refreshUser, t.home_error_processing]);

  const fetchResult = useCallback(async (id: string) => {
    try {
      const data = await getJob(id);
      setResult(data);
      setState("results");
      refreshUser();
      window.dispatchEvent(new CustomEvent("piratex:job-completed"));
    } catch {
      setError(t.home_error_fetch);
      setState("error");
    }
  }, [refreshUser, t.home_error_fetch]);

  // Watch for completion via WebSocket
  useEffect(() => {
    if (progress?.status === "completed" && state === "processing" && jobId) {
      fetchResult(jobId);
    }
  }, [progress?.status, state, jobId, fetchResult]);

  // Watch for completion via polling
  useEffect(() => {
    if (
      pollingResult?.status === "completed" &&
      state === "processing" &&
      !result
    ) {
      setResult(pollingResult);
      setState("results");
      refreshUser();
      window.dispatchEvent(new CustomEvent("piratex:job-completed"));
    }
  }, [pollingResult, state, result, refreshUser]);

  // Watch for failure
  useEffect(() => {
    if (
      (progress?.status === "failed" || pollingResult?.status === "failed") &&
      state === "processing"
    ) {
      setError(
        progress?.message || pollingResult?.error || t.home_error_processing
      );
      setState("error");
    }
  }, [progress?.status, progress?.message, pollingResult, state, t.home_error_processing]);

  // Reset to input when navigating to clean "/" (logo click, nav link)
  const prevHadParamsRef = useRef(!!resumeJobId || !!initialUrl);
  useEffect(() => {
    const hasParams = !!resumeJobId || !!initialUrl;
    const hadParams = prevHadParamsRef.current;
    prevHadParamsRef.current = hasParams;

    if (hadParams && !hasParams) {
      setState("input");
      setJobId(null);
      setResult(null);
      setError(null);
      setShareToken(null);
      setLinkCopied(false);
    }
  }, [resumeJobId, initialUrl]);

  // Re-fetch results after user registers (anonymous → registered)
  // so teaser gets replaced with full data without page reload
  const wasAnonymousRef = useRef(user?.is_anonymous);
  useEffect(() => {
    const wasAnon = wasAnonymousRef.current;
    wasAnonymousRef.current = user?.is_anonymous;
    if (wasAnon && !user?.is_anonymous && state === "results" && jobId) {
      fetchResult(jobId);
    }
  }, [user?.is_anonymous, state, jobId, fetchResult]);

  const submittingRef = useRef(false);

  const handleSubmit = async (url: string, turnstileToken?: string) => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    try {
      setState("processing");
      setError(null);
      setResult(null);
      const resp = await createJob(url, turnstileToken);

      // Fast-path: URL already in library — redirect to library reel
      if (resp.status === "completed" && resp.library_reel_id && !resp.job_id) {
        setState("input");
        navigate(`/library/${resp.library_reel_id}`);
        return;
      }

      // Fast-path: own completed job — fetch result immediately
      if (resp.status === "completed" && resp.job_id) {
        setJobId(resp.job_id);
        if (resp.share_token) setShareToken(resp.share_token);
        navigate(`/?job_id=${resp.job_id}`, { replace: true });
        fetchResult(resp.job_id);
        return;
      }

      setJobId(resp.job_id);
      if (resp.share_token) setShareToken(resp.share_token);
      // Put job_id in URL so auth redirect can return to this result
      navigate(`/?job_id=${resp.job_id}`, { replace: true });
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: unknown } } };
      if (axiosErr.response?.status === 429) {
        // 429 is handled globally by the interceptor → AuthGateModal
        setState("input");
        return;
      }
      let msg = t.home_error_submit;
      if (axiosErr.response?.data?.detail && typeof axiosErr.response.data.detail === "string") {
        msg = axiosErr.response.data.detail;
      }
      setError(msg);
      setState("error");
    } finally {
      submittingRef.current = false;
    }
  };

  const handleReset = () => {
    setState("input");
    setJobId(null);
    setResult(null);
    setError(null);
    setShareToken(null);
    setLinkCopied(false);
    if (searchParams.has("job_id") || searchParams.has("url")) {
      navigate("/", { replace: true });
    }
  };

  const handleCopyShareLink = async () => {
    const token = shareToken || result?.share_token;
    if (!token) return;
    const url = `${window.location.origin}/share/${token}`;
    await navigator.clipboard.writeText(url);
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 2000);
  };

  // Usage display logic
  const showUsage =
    usage && user && user.tier !== "UNLIMITED" && usage.limit > 0 && usage.used > 0;
  const usageText = showUsage
    ? user.is_anonymous
      ? (t.usage_display as string)
          .replace("{used}", String(usage.used))
          .replace("{limit}", String(usage.limit))
      : (t.usage_display_month as string)
          .replace("{used}", String(usage.used))
          .replace("{limit}", String(usage.limit))
    : null;

  return (
    <>
      {state === "input" && (
        <div className="space-y-20 sm:space-y-28 pb-10">
          {/* HERO */}
          <section className="flex flex-col items-center text-center justify-center min-h-[55vh] sm:min-h-[60vh] mt-2 sm:-mt-12 space-y-6">
            <p className="px-4 py-1.5 rounded-full border border-border-subtle text-xs tracking-[0.25em] uppercase text-cream-muted font-medium">
              {t.app_tagline}
            </p>
            <h1 className="text-5xl md:text-6xl lg:text-7xl font-serif font-medium leading-[1.05] text-cream max-w-3xl">
              {t.home_title}
            </h1>
            <p className="text-lg text-cream-dim max-w-xl leading-relaxed">
              {t.home_subtitle}
            </p>
            <div id="reel-input" className="w-full flex justify-center pt-2 scroll-mt-24">
              <UrlInput
                onSubmit={handleSubmit}
                loading={false}
                initialValue={initialUrl}
                requireCaptcha={!user || user.is_anonymous}
              />
            </div>
            {usageText && (
              <p className="text-center text-sm text-cream-muted">{usageText}</p>
            )}
          </section>

          {/* BENEFITS */}
          <section className="max-w-6xl mx-auto px-4 space-y-8 sm:space-y-10">
            <h2 className="text-center text-3xl md:text-4xl font-serif font-medium text-cream">
              {t.home_benefits_title}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                {
                  icon: (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <circle cx="9" cy="9" r="6" /><path d="M13.5 13.5L17 17" /><path d="M6.5 9h5M9 6.5v5" />
                    </svg>
                  ),
                  title: t.home_feat_hooks_t,
                  desc: t.home_feat_hooks_d,
                },
                {
                  icon: (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <rect x="4" y="3" width="12" height="14" rx="1.5" /><path d="M7 7h6M7 10h6M7 13h3" />
                    </svg>
                  ),
                  title: t.home_feat_struct_t,
                  desc: t.home_feat_struct_d,
                },
                {
                  icon: (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M3 15l4-5 3 3 4-6 3 4" /><circle cx="16.5" cy="4.5" r="0.5" fill="currentColor" />
                    </svg>
                  ),
                  title: t.home_feat_retain_t,
                  desc: t.home_feat_retain_d,
                },
                {
                  icon: (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M6 3h8v14H6z" /><path d="M8.5 6h3M8.5 9h3M8.5 12h2" />
                    </svg>
                  ),
                  title: t.home_feat_script_t,
                  desc: t.home_feat_script_d,
                },
              ].map((f) => (
                <div
                  key={f.title as string}
                  className="rounded-2xl bg-surface-light border border-border-subtle p-6 space-y-3 hover:border-green-400/40 transition-colors"
                >
                  <div className="w-10 h-10 rounded-xl bg-green-400/10 border border-green-400/30 flex items-center justify-center text-green-400">
                    {f.icon}
                  </div>
                  <h3 className="font-serif text-lg text-cream">{f.title}</h3>
                  <p className="text-sm text-cream-muted leading-relaxed">{f.desc}</p>
                </div>
              ))}
            </div>
          </section>

          {/* HOW IT WORKS */}
          <section className="max-w-4xl mx-auto px-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 sm:gap-6">
              {[
                { n: "01", label: t.home_step_link },
                { n: "02", label: t.home_step_ai },
                { n: "03", label: t.home_step_script },
              ].map((s, i) => (
                <div key={s.n} className="flex items-start gap-4 sm:flex-col sm:items-center sm:text-center sm:gap-2">
                  <span className="font-serif text-4xl text-green-400/70 leading-none">{s.n}</span>
                  <div className="sm:space-y-1">
                    <p className="text-cream font-medium">{s.label}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* FINAL CTA */}
          <section className="max-w-3xl mx-auto px-4">
            <div className="rounded-3xl border border-green-400/25 bg-gradient-to-b from-surface-light to-transparent p-8 sm:p-12 text-center space-y-5">
              <h2 className="text-3xl md:text-4xl font-serif font-medium text-cream">
                {t.home_cta_title}
              </h2>
              <p className="text-cream-dim">{t.home_cta_sub}</p>
              <button
                onClick={() => document.getElementById("reel-input")?.scrollIntoView({ behavior: "smooth", block: "center" })}
                className="px-7 py-3 bg-green-400 hover:bg-green-300 text-[#0C0C0C] rounded-full text-sm font-semibold transition-colors"
              >
                {t.home_cta_btn}
              </button>
            </div>
          </section>
        </div>
      )}

      {state === "processing" && jobId && (
        <LiveResults
          jobId={jobId}
          liveData={liveData}
          progress={progress}
        />
      )}

      {state === "results" && result && (
        <div className="space-y-6">
          <div className="flex justify-center gap-3">
            <button
              onClick={handleReset}
              className="px-5 py-2.5 bg-surface-light hover:bg-border-subtle border border-border-subtle rounded-full text-sm text-cream-dim hover:text-cream transition-colors"
            >
              {t.home_new_analysis}
            </button>
            {(shareToken || result.share_token) && (
              <button
                onClick={handleCopyShareLink}
                className="px-5 py-2.5 bg-cream text-[#0C0C0C] hover:bg-cream-dim rounded-full text-sm font-medium transition-colors"
              >
                {linkCopied ? t.share_link_copied : t.share_copy_link}
              </button>
            )}
          </div>
          <ResultsView
            result={result}
            onFieldRefined={(field, value) => {
              setResult((prev) => {
                if (!prev?.adaptation_summary) return prev;
                return {
                  ...prev,
                  adaptation_summary: { ...prev.adaptation_summary, [field]: value },
                };
              });
              if (result?.job_id) {
                updateJobFields(result.job_id, { [field]: value }).catch(() => {});
              }
            }}
          />
        </div>
      )}

      {state === "error" && (
        <div className="text-center space-y-4">
          <p className="text-red-400">{error}</p>
          <button
            onClick={handleReset}
            className="px-5 py-2.5 bg-surface-light hover:bg-border-subtle border border-border-subtle rounded-full text-sm text-cream-dim hover:text-cream transition-colors"
          >
            {t.home_try_again}
          </button>
        </div>
      )}
    </>
  );
}
