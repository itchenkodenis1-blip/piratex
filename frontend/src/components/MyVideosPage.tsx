import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { hideJob, listJobs, toggleJobFilmed } from "../api/client";
import { useLikes } from "../hooks/useLikes";
import { useTranslation } from "../i18n";
import type { JobCard as JobCardType } from "../types";
import { jobToCard } from "../utils/cardAdapters";
import { UnifiedReelCard } from "./UnifiedReelCard";

export function MyVideosPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { isLiked, toggleLike } = useLikes();

  const [jobs, setJobs] = useState<JobCardType[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showLikedOnly, setShowLikedOnly] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const statusFilter = searchParams.get("status") || "";
  const page = parseInt(searchParams.get("page") || "1", 10);
  const perPage = 20;

  const fetchData = useCallback(async () => {
    try {
      const res = await listJobs({
        status_filter: statusFilter || undefined,
        page,
        per_page: perPage,
      });
      setJobs(res.items);
      setTotal(res.total);
    } catch (err) {
      console.error("Failed to load jobs:", err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, page]);

  // Initial load + refetch on filter/page change
  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 5s while any job is still processing
  useEffect(() => {
    const hasProcessing = jobs.some(
      (j) => j.status !== "completed" && j.status !== "failed"
    );

    if (hasProcessing) {
      pollRef.current = setInterval(fetchData, 5000);
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [jobs, fetchData]);

  const updateParams = (updates: Record<string, string>) => {
    const next = new URLSearchParams(searchParams);
    for (const [k, v] of Object.entries(updates)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!("page" in updates)) next.delete("page");
    setSearchParams(next);
  };

  const handleCardClick = (job: JobCardType) => {
    if (job.status === "completed" && job.library_reel_id) {
      navigate(`/library/${job.library_reel_id}`);
    } else if (job.status !== "failed") {
      navigate(`/?job_id=${job.job_id}`);
    }
  };

  const handleHideJob = async (job: JobCardType, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await hideJob(job.job_id);
      setJobs((prev) => prev.filter((j) => j.job_id !== job.job_id));
      setTotal((prev) => prev - 1);
    } catch (err) {
      console.error("Failed to hide job:", err);
    }
  };

  const handleToggleFilmed = async (job: JobCardType, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const result = await toggleJobFilmed(job.job_id);
      setJobs((prev) =>
        prev.map((j) =>
          j.job_id === job.job_id ? { ...j, is_filmed: result.is_filmed } : j
        )
      );
    } catch (err) {
      console.error("Failed to toggle filmed:", err);
    }
  };


  const totalPages = Math.ceil(total / perPage);

  const filters = [
    { key: "", label: t.my_videos_filter_all },
    { key: "processing", label: t.my_videos_filter_processing },
    { key: "completed", label: t.my_videos_filter_completed },
    { key: "failed", label: t.my_videos_filter_failed },
  ];

  return (
    <div className="w-full max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div className="text-center space-y-3">
        <h2 className="text-2xl sm:text-4xl font-serif font-medium text-cream">{t.my_videos_title}</h2>
        <p className="text-cream-muted">
          {total} {t.my_videos_count}
        </p>
      </div>

      {/* Status filters */}
      <div className="flex flex-wrap justify-center gap-2">
        {filters.map((f) => (
          <button
            key={f.key}
            onClick={() => updateParams({ status: f.key })}
            className={`px-4 py-2 text-sm rounded-full transition-colors ${
              statusFilter === f.key
                ? "bg-cream text-[#0C0C0C] font-medium"
                : "bg-surface text-cream-dim border border-border-subtle hover:border-cream-muted/30"
            }`}
          >
            {f.label}
          </button>
        ))}
        <div className="hidden sm:block w-px bg-border-subtle" />
        <button
          onClick={() => setShowLikedOnly((v) => !v)}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm rounded-full transition-colors ${
            showLikedOnly
              ? "bg-red-500/20 text-red-400 border border-red-500/30 font-medium"
              : "bg-surface text-cream-dim border border-border-subtle hover:border-cream-muted/30"
          }`}
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill={showLikedOnly ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
          </svg>
          {t.filter_liked}
        </button>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="text-center py-16">
          <div className="inline-flex items-center gap-3 px-5 py-3 bg-surface border border-border-subtle rounded-full">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cream opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cream-dim" />
            </span>
            <span className="text-sm text-cream-muted">{t.my_videos_loading}</span>
          </div>
        </div>
      ) : jobs.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-cream-muted text-sm">{t.my_videos_empty}</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 sm:gap-3">
          {jobs.filter((job) => !showLikedOnly || isLiked(job.url)).map((job) => (
            <UnifiedReelCard
              key={job.job_id}
              data={jobToCard(job)}
              variant="job"
              onClick={() => handleCardClick(job)}
              onToggleFilmed={(e) => handleToggleFilmed(job, e)}
              onHide={(e) => handleHideJob(job, e)}
              isLiked={isLiked(job.url)}
              onToggleLike={(e) => { e.stopPropagation(); toggleLike(job.url); }}
              t={t}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => updateParams({ page: String(page - 1) })}
            disabled={page <= 1}
            className="px-4 py-2.5 sm:py-1.5 text-sm bg-surface border border-border-subtle rounded-full text-cream-dim hover:text-cream disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            {t.library_prev}
          </button>
          <span className="text-sm text-cream-muted">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => updateParams({ page: String(page + 1) })}
            disabled={page >= totalPages}
            className="px-4 py-2.5 sm:py-1.5 text-sm bg-surface border border-border-subtle rounded-full text-cream-dim hover:text-cream disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            {t.library_next}
          </button>
        </div>
      )}
    </div>
  );
}
