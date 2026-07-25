import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createJob, getTrends, getNicheTree, getMyAuthors, adminHideReel, adminBlockProfile } from "../api/client";
import { useLikes } from "../hooks/useLikes";
import { useTranslation } from "../i18n";
import type { AuthUser, TrendItem, NicheTreeResponse } from "../types";
import { trendToCard } from "../utils/cardAdapters";
import { AddAuthorModal } from "./AddAuthorModal";
import { UnifiedReelCard } from "./UnifiedReelCard";
import { TelegramPromo } from "./TelegramPromo";
import { NicheMultiSelect } from "./NicheMultiSelect";

const SORT_OPTIONS = ["hot_score", "x_factor", "views", "recent"] as const;
const DAYS_OPTIONS = [
  { value: "", label: "trends_period_all" },
  { value: "1", label: "trends_period_today" },
  { value: "7", label: "trends_period_week" },
  { value: "30", label: "trends_period_month" },
  { value: "365", label: "trends_period_year" },
] as const;

interface TrendsPageProps {
  user: AuthUser | null;
  onLoginClick: () => void;
  onOpenOnboarding?: (step?: "instagram" | "from_scratch") => void;
}

/* ─── Main page ─── */
export function TrendsPage({ user, onLoginClick, onOpenOnboarding }: TrendsPageProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { isLiked, toggleLike } = useLikes();

  const isAuthenticated = !!user && !user.is_anonymous;
  const isPaidTier = isAuthenticated && !["FREE", "REGISTERED"].includes(user!.tier);

  // Smart default tab: authenticated → for_you, anonymous → global
  const defaultTab = isAuthenticated ? "for_you" : "global";
  const tab = searchParams.get("tab") || defaultTab;
  const niche = searchParams.get("niche") || "";
  const platform = searchParams.get("platform") || "";
  const sort = (searchParams.get("sort") || "hot_score") as typeof SORT_OPTIONS[number];
  const days = searchParams.get("days") || "";
  const page = parseInt(searchParams.get("page") || "1", 10);
  const q = searchParams.get("q") || "";

  const [items, setItems] = useState<TrendItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nicheTree, setNicheTree] = useState<NicheTreeResponse | null>(null);
  const [showAddAuthor, setShowAddAuthor] = useState(false);
  const [parsingId, setParsingId] = useState<string | null>(null);
  const [showLikedOnly, setShowLikedOnly] = useState(false);
  const [forYouEmpty, setForYouEmpty] = useState(false);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [authorCount, setAuthorCount] = useState(0);
  const [authorLimit, setAuthorLimit] = useState(0);
  // Search input with debounce
  const [searchInput, setSearchInput] = useState(q);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setSearchInput(searchParams.get("q") || "");
  }, [searchParams]);

  // Cleanup debounce on unmount
  useEffect(() => () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, []);

  const perPage = 20;

  // ── Tier gating helpers ──────────────────────────────────────
  const canFilter = isAuthenticated;
  const canSearch = isPaidTier;
  const canPaginate = (targetPage: number) => {
    if (!isAuthenticated) return targetPage <= 1;
    if (!isPaidTier && (tab === "global" || tab === "for_you")) return targetPage <= 3;
    return true;
  };

  const showUpgradeModal = (reason = "upgrade_required_trends") => {
    window.dispatchEvent(
      new CustomEvent("piratex:limit-reached", {
        detail: { detail: reason },
      })
    );
  };

  const updateParams = useCallback(
    (updates: Record<string, string>) => {
      const newParams = new URLSearchParams(searchParams);
      for (const [key, val] of Object.entries(updates)) {
        if (val) newParams.set(key, val);
        else newParams.delete(key);
      }
      if (!("page" in updates)) newParams.delete("page");
      setSearchParams(newParams, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getTrends({
        tab,
        niche,
        platform,
        sort,
        days: days ? parseInt(days, 10) : undefined,
        page,
        per_page: perPage,
        q: q || undefined,
      });
      setItems(res.items);
      setTotal(res.total);
      setForYouEmpty(tab === "for_you" && res.interest_source === "none" && res.niche_source === "none");
    } catch {
      setError(t.trends_error);
    } finally {
      setLoading(false);
    }
  }, [tab, niche, platform, sort, days, page, q, t]);

  useEffect(() => {
    getNicheTree().then(setNicheTree).catch(() => {});
  }, []);

  // Fetch author count/limit for authenticated users
  const refreshAuthorCount = useCallback(() => {
    if (isPaidTier) {
      getMyAuthors().then((res) => {
        setAuthorCount(res.count);
        setAuthorLimit(res.limit);
      }).catch(() => {});
    }
  }, [isPaidTier]);

  useEffect(() => {
    refreshAuthorCount();
  }, [refreshAuthorCount]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleParse = async (e: React.MouseEvent, item: TrendItem) => {
    e.stopPropagation();
    setParsingId(item.id);
    try {
      const result = await createJob(item.url);
      if (result.status === "completed" && result.library_reel_id) {
        navigate(`/library/${result.library_reel_id}`);
      } else if (result.job_id) {
        navigate(`/?job_id=${result.job_id}`);
      }
    } catch {
      // 429 handled by interceptor → AuthGateModal
    } finally {
      setParsingId(null);
    }
  };

  const handleCardClick = (item: TrendItem) => {
    window.open(item.url, "_blank");
  };

  const handleTabClick = (newTab: string) => {
    if ((newTab === "my_authors" || newTab === "for_you") && !isAuthenticated) {
      onLoginClick();
      return;
    }
    // Reset filters on tab switch
    const newParams = new URLSearchParams();
    if (newTab !== defaultTab) newParams.set("tab", newTab);
    setSearchParams(newParams, { replace: true });
    setShowLikedOnly(false);
    setSearchInput("");
    setBannerDismissed(false);
  };

  const handleFilterClick = (updater: () => void) => {
    if (!canFilter) {
      onLoginClick();
      return;
    }
    updater();
  };

  const handleSearchInput = (value: string) => {
    setSearchInput(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      updateParams({ q: value });
    }, 400);
  };

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="space-y-5 sm:space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-xl sm:text-2xl font-serif font-medium text-cream">{t.trends_title}</h2>
          <p className="text-xs sm:text-sm text-cream-muted mt-0.5 sm:mt-1">{t.trends_subtitle}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {isPaidTier && authorLimit > 0 && (
            <span className="text-xs text-cream-muted whitespace-nowrap">
              {authorCount}/{authorLimit}
            </span>
          )}
          <button
            onClick={() => {
              if (!isAuthenticated) { onLoginClick(); return; }
              if (!isPaidTier) { showUpgradeModal("upgrade_required_authors"); return; }
              if (authorCount >= authorLimit) { showUpgradeModal("upgrade_required_authors"); return; }
              setShowAddAuthor(true);
            }}
            className="px-3 sm:px-4 py-2 text-xs sm:text-sm bg-cream/10 text-cream rounded-full hover:bg-cream/20 active:bg-cream/25 transition-colors whitespace-nowrap"
          >
            + {t.trends_add_author}
          </button>
        </div>
      </div>

      {/* ─── Filters — horizontal scroll on mobile, wrap on desktop ─── */}
      <div className="relative">
        <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-[#0C0C0C] to-transparent pointer-events-none z-10 sm:hidden" />
        <div className="-mx-4 px-4 sm:mx-0 sm:px-0 overflow-x-auto scrollbar-hide">
          <div className="flex items-center gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
          {/* Tab toggle — 3 tabs */}
          <div className="flex items-center gap-0.5 bg-surface border border-border-subtle rounded-lg p-0.5">
            <button
              onClick={() => handleTabClick("for_you")}
              className={`px-2.5 sm:px-3 py-1.5 rounded-md text-xs sm:text-sm transition-colors whitespace-nowrap ${
                tab === "for_you"
                  ? "bg-surface-light text-cream"
                  : "text-cream-muted hover:text-cream"
              }`}
            >
              {t.trends_tab_for_you}
            </button>
            <button
              onClick={() => handleTabClick("my_authors")}
              className={`px-2.5 sm:px-3 py-1.5 rounded-md text-xs sm:text-sm transition-colors whitespace-nowrap ${
                tab === "my_authors"
                  ? "bg-surface-light text-cream"
                  : "text-cream-muted hover:text-cream"
              }`}
            >
              {t.trends_tab_my_authors}
            </button>
            <button
              onClick={() => handleTabClick("global")}
              className={`px-2.5 sm:px-3 py-1.5 rounded-md text-xs sm:text-sm transition-colors whitespace-nowrap ${
                tab === "global"
                  ? "bg-surface-light text-cream"
                  : "text-cream-muted hover:text-cream"
              }`}
            >
              {t.trends_tab_all}
            </button>
          </div>

          {/* Niche filter — multi-select with search */}
          <NicheMultiSelect
            nicheTree={nicheTree}
            selected={niche ? niche.split(",") : []}
            onChange={(slugs) => handleFilterClick(() => updateParams({ niche: slugs.join(","), page: "1" }))}
            disabled={!canFilter}
            t={t}
          />

          {/* Platform filter — icons */}
          <div className="flex items-center gap-0.5 bg-surface border border-border-subtle rounded-lg p-0.5">
            {[
              { value: "", label: t.trends_all_platforms },
              { value: "instagram", icon: (
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>
              )},
              { value: "youtube", icon: (
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
              )},
              { value: "tiktok", icon: (
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M16.6 5.82A4.28 4.28 0 0 1 15.54 3h-3.09v12.4a2.59 2.59 0 0 1-2.59 2.5c-1.42 0-2.6-1.16-2.6-2.6a2.6 2.6 0 0 1 2.6-2.55c.27 0 .52.04.77.11V9.65a5.74 5.74 0 0 0-.77-.05A5.76 5.76 0 0 0 4.1 15.34 5.76 5.76 0 0 0 9.86 21.1a5.76 5.76 0 0 0 5.76-5.76V9.38a7.54 7.54 0 0 0 5.07 1.95V8.24a4.28 4.28 0 0 1-4.09-2.42z"/></svg>
              )},
            ].map((p) => (
              <button
                key={p.value}
                onClick={() => handleFilterClick(() => updateParams({ platform: p.value }))}
                title={p.value || t.trends_all_platforms}
                className={`px-2.5 py-1.5 rounded-md text-sm transition-colors whitespace-nowrap ${
                  !canFilter
                    ? "text-cream-muted/50 cursor-not-allowed"
                    : platform === p.value
                      ? "bg-surface-light text-cream"
                      : "text-cream-muted hover:text-cream"
                }`}
              >
                {p.icon || p.label}
              </button>
            ))}
          </div>

          {/* Liked filter — icon only */}
          <button
            onClick={() => handleFilterClick(() => setShowLikedOnly((v) => !v))}
            title={t.filter_liked}
            className={`flex items-center justify-center w-9 h-9 rounded-lg transition-colors ${
              !canFilter
                ? "bg-surface text-cream-muted/50 border border-border-subtle cursor-not-allowed"
                : showLikedOnly
                  ? "bg-red-500/20 text-red-400 border border-red-500/30"
                  : "bg-surface text-cream-muted border border-border-subtle hover:border-cream-muted/30"
            }`}
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill={showLikedOnly ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
            </svg>
          </button>

          {/* Period filter */}
          <div className="flex items-center gap-0.5 bg-surface border border-border-subtle rounded-lg p-0.5 sm:flex-1">
            {DAYS_OPTIONS.map((d) => {
              const isToday = d.value === "1";
              const isActive = days === d.value;
              return (
                <button
                  key={d.value}
                  onClick={() => handleFilterClick(() => updateParams({ days: d.value }))}
                  className={`flex-1 px-2.5 py-1.5 rounded-md text-xs sm:text-sm transition-colors whitespace-nowrap text-center ${
                    !canFilter
                      ? "text-cream-muted/50 cursor-not-allowed"
                      : isActive && isToday
                        ? "bg-cyan-500/20 text-cyan-300 ring-1 ring-cyan-500/30"
                        : isActive
                          ? "bg-surface-light text-cream"
                          : isToday
                            ? "text-cyan-400/70 hover:text-cyan-300"
                            : "text-cream-muted hover:text-cream"
                  }`}
                >
                  {t[d.label as keyof typeof t]}
                </button>
              );
            })}
          </div>

          {/* Search */}
          <div className="relative min-w-[160px] sm:min-w-[200px] sm:flex-1">
            <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-cream-muted/50 pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
            </svg>
            <input
              type="text"
              placeholder={canSearch ? t.trends_search_placeholder : t.trends_search_upgrade}
              value={searchInput}
              onChange={(e) => handleSearchInput(e.target.value)}
              disabled={!canSearch}
              onFocus={() => {
                if (!isAuthenticated) onLoginClick();
                else if (!canSearch) showUpgradeModal();
              }}
              className={`w-full bg-surface border border-border-subtle rounded-lg pl-8 pr-3 py-2 text-sm placeholder-cream-muted/50 focus:outline-none focus:ring-1 focus:ring-cream-muted ${
                canSearch ? "text-cream" : "text-cream-muted/50 cursor-not-allowed"
              }`}
            />
            {searchInput && canSearch && (
              <button
                onClick={() => { setSearchInput(""); updateParams({ q: "" }); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-cream-muted hover:text-cream text-xs p-1"
              >
                &times;
              </button>
            )}
          </div>

          {/* Sort */}
          <div className="flex items-center gap-0.5 bg-surface border border-border-subtle rounded-lg p-0.5 sm:ml-auto">
            {SORT_OPTIONS.map((s) => (
              <button
                key={s}
                onClick={() => handleFilterClick(() => updateParams({ sort: s }))}
                className={`px-3 py-1.5 rounded-md text-sm transition-colors whitespace-nowrap ${
                  !canFilter
                    ? "text-cream-muted/50 cursor-not-allowed"
                    : sort === s
                      ? "bg-surface-light text-cream"
                      : "text-cream-muted hover:text-cream"
                }`}
              >
                {s === "hot_score" ? t.trends_sort_hot_score : s === "x_factor" ? "X-factor" : s === "views" ? t.trends_sort_views : t.trends_sort_recent}
              </button>
            ))}
          </div>
          </div>
        </div>
      </div>

      {/* ─── For You onboarding banner ─── */}
      {forYouEmpty && !loading && !bannerDismissed && isAuthenticated && (
        <div className="rounded-[20px] p-px bg-gradient-to-br from-cream/15 via-cream/[0.03] to-cream/[0.08]">
          <div className="relative bg-gradient-to-br from-surface to-[#111111] rounded-[19px] px-5 py-7 sm:px-8 sm:py-9 overflow-hidden">
            {/* Decorative glow */}
            <div className="absolute -top-16 -right-10 w-64 h-64 bg-[radial-gradient(circle,rgba(235,235,235,0.04)_0%,transparent_70%)] pointer-events-none" />
            {/* Eyebrow */}
            <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-cream/[0.06] border border-cream/10 rounded-full text-[11px] font-medium text-cream-dim uppercase tracking-wide mb-4">
              <span className="w-1.5 h-1.5 rounded-full bg-cream/50 animate-pulse" />
              {t.for_you_onboarding_eyebrow}
            </div>
            {/* Title & subtitle */}
            <h3 className="font-serif text-xl sm:text-2xl font-semibold text-cream leading-tight mb-2.5">
              {t.for_you_onboarding_title}
            </h3>
            <p className="text-sm text-cream-dim leading-relaxed max-w-xl mb-6">
              {t.for_you_onboarding_subtitle}
            </p>
            {/* Two CTA cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
              {/* Instagram card */}
              <button
                onClick={() => onOpenOnboarding?.("instagram")}
                className="group text-left bg-cream/[0.03] border border-cream/10 hover:border-cream/20 hover:bg-cream/[0.06] rounded-xl p-5 transition-all"
              >
                <div className="w-10 h-10 rounded-[10px] bg-cream/[0.08] flex items-center justify-center text-cream-dim mb-3">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
                    <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
                    <line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
                  </svg>
                </div>
                <div className="text-[15px] font-semibold text-cream mb-1">{t.for_you_onboarding_ig_title}</div>
                <div className="text-[13px] text-cream-muted leading-snug mb-3">{t.for_you_onboarding_ig_desc}</div>
                <div className="flex items-center gap-1 text-[11px] text-cream-muted">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>
                  {t.for_you_onboarding_ig_time}
                  <span className="ml-auto text-cream-muted opacity-0 group-hover:opacity-100 transition-opacity text-lg">&rarr;</span>
                </div>
              </button>
              {/* Manual card */}
              <button
                onClick={() => onOpenOnboarding?.("from_scratch")}
                className="group text-left bg-cream/[0.03] border border-border-subtle hover:border-cream/[0.12] hover:bg-cream/[0.05] rounded-xl p-5 transition-all"
              >
                <div className="w-10 h-10 rounded-[10px] bg-cream/[0.06] flex items-center justify-center text-cream-dim mb-3">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                  </svg>
                </div>
                <div className="text-[15px] font-semibold text-cream mb-1">{t.for_you_onboarding_manual_title}</div>
                <div className="text-[13px] text-cream-muted leading-snug mb-3">{t.for_you_onboarding_manual_desc}</div>
                <div className="flex items-center gap-1 text-[11px] text-cream-muted">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>
                  {t.for_you_onboarding_manual_time}
                  <span className="ml-auto text-cream-muted opacity-0 group-hover:opacity-100 transition-opacity text-lg">&rarr;</span>
                </div>
              </button>
            </div>
            {/* Dismiss */}
            <button
              onClick={() => setBannerDismissed(true)}
              className="text-xs text-cream-muted opacity-70 hover:opacity-100 transition-opacity"
            >
              {t.for_you_onboarding_dismiss}
            </button>
          </div>
        </div>
      )}

      {/* Global trends label when banner is showing */}
      {forYouEmpty && !loading && !bannerDismissed && isAuthenticated && items.length > 0 && (
        <div className="flex items-center gap-3">
          <span className="text-xs text-cream-muted uppercase tracking-wider">{t.for_you_onboarding_global_label}</span>
          <div className="flex-1 h-px bg-border-subtle" />
        </div>
      )}

      {/* ─── Content ─── */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5 sm:gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-surface border border-border-subtle rounded-2xl overflow-hidden animate-pulse">
              <div className="aspect-[3/4] bg-surface-light" />
              <div className="p-2 sm:p-2.5 space-y-1.5">
                <div className="h-3.5 bg-surface-light rounded w-3/4" />
                <div className="h-3 bg-surface-light rounded w-1/2" />
                <div className="h-7 bg-surface-light rounded mt-1" />
              </div>
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="text-center py-16 text-red-400">{error}</div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 space-y-4">
          <p className="text-cream-muted">{tab === "my_authors" ? t.trends_my_authors_empty : t.trends_empty}</p>
          {tab === "my_authors" && (
            <button
              onClick={() => {
                if (!isPaidTier) { showUpgradeModal("upgrade_required_authors"); return; }
                setShowAddAuthor(true);
              }}
              className="px-5 py-2.5 bg-cream text-[#0C0C0C] hover:bg-cream-dim font-medium rounded-full text-sm transition-colors"
            >
              + {t.trends_my_authors_empty_cta}
            </button>
          )}
        </div>
      ) : (
        <>
          {/* Telegram promo — on trends page (hook handles auth/display logic) */}
          <TelegramPromo variant="trends" />

          {/* ─── Grid of trend cards ─── */}
          <div className={`grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5 sm:gap-3${forYouEmpty && !bannerDismissed && isAuthenticated ? " opacity-50" : ""}`}>
            {items.filter((item) => !showLikedOnly || isLiked(item.url)).map((item, index) => {
              const rank = page === 1 ? index + 1 : perPage * (page - 1) + index + 1;
              return (
                <UnifiedReelCard
                  key={item.id}
                  data={trendToCard(item, rank)}
                  variant="trend"
                  onClick={() => handleCardClick(item)}
                  onParse={(e) => handleParse(e, item)}
                  isLiked={isAuthenticated ? isLiked(item.url) : false}
                  onToggleLike={(e) => { e.stopPropagation(); if (!isAuthenticated) { onLoginClick(); return; } toggleLike(item.url); }}
                  onAdminHide={user?.is_admin ? (e) => { e.stopPropagation(); adminHideReel(item.id).then(() => setItems(prev => prev.filter(i => i.id !== item.id))); } : undefined}
                  onAdminBlock={user?.is_admin ? (e) => { e.stopPropagation(); if (confirm(`Заблокировать автора @${item.author.username}?`)) { adminBlockProfile(item.author.profile_id).then(() => setItems(prev => prev.filter(i => i.author.profile_id !== item.author.profile_id))); } } : undefined}
                  parsingId={parsingId}
                  t={t}
                />
              );
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 sm:gap-4 pt-4">
              <button
                onClick={() => {
                  if (canPaginate(page - 1)) {
                    updateParams({ page: String(page - 1) });
                  }
                }}
                disabled={page <= 1}
                className="px-4 py-2.5 sm:py-2 text-sm rounded-lg border border-border-subtle text-cream-muted hover:text-cream active:bg-surface-light disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                {t.library_prev}
              </button>
              <span className="text-sm text-cream-muted tabular-nums">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => {
                  const next = page + 1;
                  if (!canPaginate(next)) {
                    if (!isAuthenticated) onLoginClick();
                    else showUpgradeModal();
                    return;
                  }
                  updateParams({ page: String(next) });
                }}
                disabled={page >= totalPages}
                className={`px-4 py-2.5 sm:py-2 text-sm rounded-lg border transition-colors ${
                  page < totalPages && !canPaginate(page + 1)
                    ? "border-amber-500/30 text-amber-400 hover:bg-amber-500/10"
                    : "border-border-subtle text-cream-muted hover:text-cream active:bg-surface-light disabled:opacity-30 disabled:cursor-not-allowed"
                }`}
              >
                {page < totalPages && !canPaginate(page + 1) ? (
                  <span className="flex items-center gap-1.5">
                    {t.library_next}
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </svg>
                  </span>
                ) : (
                  t.library_next
                )}
              </button>
            </div>
          )}
        </>
      )}

      <AddAuthorModal
        isOpen={showAddAuthor}
        onClose={() => setShowAddAuthor(false)}
        onAdded={() => { fetchData(); refreshAuthorCount(); }}
      />
    </div>
  );
}
