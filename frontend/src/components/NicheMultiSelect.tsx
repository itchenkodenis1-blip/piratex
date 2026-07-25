import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Translations } from "../i18n/types";
import type { NicheTreeResponse } from "../types";

interface FlatNiche {
  slug: string;
  label: string;
  groupKey: string;
  groupLabel: string;
  keywords: string[];
  trendingCount: number;
}

interface NicheMultiSelectProps {
  nicheTree: NicheTreeResponse | null;
  selected: string[];
  onChange: (slugs: string[]) => void;
  disabled?: boolean;
  t: Translations;
}

function getNicheLabel(slug: string, t: Translations): string | null {
  const key = `niche_${slug}` as keyof Translations;
  return (t[key] as string) || null;
}

function getGroupLabel(key: string, t: Translations): string | null {
  const tKey = `niche_group_${key}` as keyof Translations;
  return (t[tKey] as string) || null;
}

export function NicheMultiSelect({ nicheTree, selected, onChange, disabled, t }: NicheMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Flatten tree into searchable list
  const flatNiches = useMemo<FlatNiche[]>(() => {
    if (!nicheTree) return [];
    const result: FlatNiche[] = [];
    for (const group of nicheTree.groups) {
      const gLabel = getGroupLabel(group.key, t) || group.label;
      for (const child of group.children) {
        result.push({
          slug: child.slug,
          label: getNicheLabel(child.slug, t) || child.display_name,
          groupKey: group.key,
          groupLabel: gLabel,
          keywords: child.keywords || [],
          trendingCount: child.trending_count,
        });
      }
    }
    return result;
  }, [nicheTree, t]);

  // Filter by search query
  const filtered = useMemo(() => {
    if (!search.trim()) return flatNiches;
    const q = search.toLowerCase().trim();
    return flatNiches.filter(
      (n) =>
        n.label.toLowerCase().includes(q) ||
        n.slug.toLowerCase().includes(q) ||
        n.groupLabel.toLowerCase().includes(q) ||
        n.keywords.some((kw) => kw.toLowerCase().includes(q))
    );
  }, [flatNiches, search]);

  // Group filtered results for display
  const groupedFiltered = useMemo(() => {
    const groups: { key: string; label: string; niches: FlatNiche[] }[] = [];
    const map = new Map<string, FlatNiche[]>();
    const order: string[] = [];
    for (const n of filtered) {
      if (!map.has(n.groupKey)) {
        map.set(n.groupKey, []);
        order.push(n.groupKey);
      }
      map.get(n.groupKey)!.push(n);
    }
    for (const key of order) {
      const niches = map.get(key)!;
      groups.push({ key, label: niches[0].groupLabel, niches });
    }
    return groups;
  }, [filtered]);

  // Selected niches with labels
  const selectedWithLabels = useMemo(() => {
    return selected.map((slug) => {
      const found = flatNiches.find((n) => n.slug === slug);
      return { slug, label: found?.label || slug };
    });
  }, [selected, flatNiches]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on ESC
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const toggleNiche = useCallback(
    (slug: string) => {
      if (selected.includes(slug)) {
        onChange(selected.filter((s) => s !== slug));
      } else {
        onChange([...selected, slug]);
      }
    },
    [selected, onChange]
  );

  const removeNiche = useCallback(
    (slug: string, e: React.MouseEvent) => {
      e.stopPropagation();
      onChange(selected.filter((s) => s !== slug));
    },
    [selected, onChange]
  );

  const handleOpen = () => {
    if (disabled) return;
    setOpen(true);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  return (
    <div ref={containerRef} className="relative">
      {/* Trigger area */}
      <button
        type="button"
        onClick={handleOpen}
        disabled={disabled}
        className={`flex items-center gap-1.5 bg-surface border border-border-subtle rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-cream-muted min-w-0 max-w-[280px] sm:max-w-[360px] ${
          disabled ? "text-cream-muted/50 cursor-not-allowed" : "text-cream cursor-pointer"
        }`}
      >
        {selectedWithLabels.length === 0 ? (
          <span className="text-cream-muted truncate">{t.trends_all_niches}</span>
        ) : (
          <div className="flex items-center gap-1 overflow-hidden">
            {selectedWithLabels.slice(0, 3).map((n) => (
              <span
                key={n.slug}
                className="inline-flex items-center gap-1 bg-cream/10 text-cream text-xs px-2 py-0.5 rounded-md whitespace-nowrap max-w-[120px]"
              >
                <span className="truncate">{n.label}</span>
                <button
                  type="button"
                  onClick={(e) => removeNiche(n.slug, e)}
                  className="text-cream-muted hover:text-cream flex-shrink-0"
                >
                  ×
                </button>
              </span>
            ))}
            {selectedWithLabels.length > 3 && (
              <span className="text-xs text-cream-muted whitespace-nowrap">
                +{selectedWithLabels.length - 3}
              </span>
            )}
          </div>
        )}
        <svg
          className={`w-3.5 h-3.5 text-cream-muted flex-shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 w-[280px] sm:w-[320px] bg-surface border border-border-subtle rounded-lg shadow-xl overflow-hidden">
          {/* Search input */}
          <div className="p-2 border-b border-border-subtle">
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t.trends_search_niches}
              className="w-full bg-surface-light rounded-md px-3 py-1.5 text-sm text-cream placeholder:text-cream-muted/50 focus:outline-none"
            />
          </div>

          {/* Clear all if selected */}
          {selected.length > 0 && (
            <button
              type="button"
              onClick={() => { onChange([]); setSearch(""); }}
              className="w-full px-3 py-1.5 text-xs text-cream-muted hover:text-cream hover:bg-surface-light transition-colors text-left border-b border-border-subtle"
            >
              ✕ {t.trends_all_niches}
            </button>
          )}

          {/* Niche list */}
          <div className="max-h-[300px] overflow-y-auto overscroll-contain">
            {groupedFiltered.length === 0 && (
              <div className="px-3 py-4 text-sm text-cream-muted text-center">
                {t.trends_no_niches_found}
              </div>
            )}
            {groupedFiltered.map((group) => (
              <div key={group.key}>
                <div className="px-3 py-1.5 text-[10px] font-medium text-cream-muted/60 uppercase tracking-wider bg-surface-light/30 sticky top-0">
                  {group.label}
                </div>
                {group.niches.map((n) => {
                  const isSelected = selected.includes(n.slug);
                  return (
                    <button
                      key={n.slug}
                      type="button"
                      onClick={() => toggleNiche(n.slug)}
                      className={`w-full flex items-center justify-between px-3 py-2 text-sm transition-colors ${
                        isSelected
                          ? "bg-cream/5 text-cream"
                          : "text-cream-muted hover:text-cream hover:bg-surface-light"
                      }`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <div
                          className={`w-3.5 h-3.5 rounded border flex-shrink-0 flex items-center justify-center transition-colors ${
                            isSelected
                              ? "bg-cream border-cream"
                              : "border-border-subtle"
                          }`}
                        >
                          {isSelected && (
                            <svg className="w-2.5 h-2.5 text-surface" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                            </svg>
                          )}
                        </div>
                        <span className="truncate">{n.label}</span>
                      </div>
                      {n.trendingCount > 0 && (
                        <span className="text-xs text-cream-muted/50 flex-shrink-0 ml-2">
                          {n.trendingCount}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
