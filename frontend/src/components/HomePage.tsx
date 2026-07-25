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
        <div className="flex flex-col items-center justify-center min-h-[60vh] sm:min-h-[70vh] mt-2 sm:-mt-12 space-y-8 sm:space-y-10">
          <div className="text-center space-y-5">
            <p className="text-xs tracking-[0.25em] uppercase text-cream-muted font-medium">
              {t.app_tagline}
            </p>
            <h2 className="text-5xl md:text-6xl lg:text-7xl font-serif font-medium leading-[1.1] text-cream">
              {t.home_title}
            </h2>
            <p className="text-lg text-cream-dim max-w-xl mx-auto leading-relaxed">
              {t.home_subtitle}
            </p>
          </div>
          <UrlInput
            onSubmit={handleSubmit}
            loading={false}
            initialValue={initialUrl}
            requireCaptcha={!user || user.is_anonymous}
          />
          {/* Usage display */}
          {usageText && (
            <p className="text-center text-sm text-cream-muted">{usageText}</p>
          )}
          {/* 3-step visual */}
          <div className="flex items-center gap-4 sm:gap-6 md:gap-10 pt-4">
            <div className="flex flex-col items-center gap-2 text-center">
              <div className="w-12 h-12 rounded-full bg-surface-light border border-border-subtle flex items-center justify-center text-xl">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-cream-dim">
                  <path d="M8 4H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2" />
                  <path d="M16 4l-4-2v4l4-2z" />
                  <path d="M10 10h6" />
                </svg>
              </div>
              <span className="text-xs text-cream-muted max-w-[100px]">{t.home_step_link}</span>
            </div>
            <div className="h-px w-6 bg-border-subtle" />
            <div className="flex flex-col items-center gap-2 text-center">
              <div className="w-12 h-12 rounded-full bg-surface-light border border-border-subtle flex items-center justify-center text-xl">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-cream-dim">
                  <circle cx="10" cy="10" r="7" />
                  <path d="M10 7v3l2 2" />
                </svg>
              </div>
              <span className="text-xs text-cream-muted max-w-[100px]">{t.home_step_ai}</span>
            </div>
            <div className="h-px w-6 bg-border-subtle" />
            <div className="flex flex-col items-center gap-2 text-center">
              <div className="w-12 h-12 rounded-full bg-surface-light border border-border-subtle flex items-center justify-center text-xl">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-cream-dim">
                  <path d="M4 4h12v12H4z" />
                  <path d="M7 8h6M7 11h4" />
                </svg>
              </div>
              <span className="text-xs text-cream-muted max-w-[100px]">{t.home_step_script}</span>
            </div>
          </div>
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
