import { useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";
import type { TagInfo } from "../types";

interface TagDropdownProps {
  tags: TagInfo[];
  activeTags: string;
  onToggle: (tagName: string) => void;
}

export function TagDropdown({ tags, activeTags, onToggle }: TagDropdownProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const activeSet = new Set(activeTags ? activeTags.split(",").filter(Boolean) : []);
  const activeCount = activeSet.size;

  const filtered = search
    ? tags.filter((tag) =>
        tag.display_name.toLowerCase().includes(search.toLowerCase()) ||
        tag.name.toLowerCase().includes(search.toLowerCase())
      )
    : tags;

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Focus search input when opened
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-1.5 px-3 py-1 text-xs rounded-full transition-colors ${
          activeCount > 0
            ? "bg-cream/15 text-cream border border-cream/30"
            : "bg-surface-light text-cream-dim border border-border-subtle hover:border-cream-muted/30"
        }`}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
          <line x1="7" y1="7" x2="7.01" y2="7" />
        </svg>
        {t.library_tags_filter}
        {activeCount > 0 && (
          <span className="bg-cream text-[#0C0C0C] text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
            {activeCount}
          </span>
        )}
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={`transition-transform ${open ? "rotate-180" : ""}`}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-2 w-64 bg-surface border border-border-subtle rounded-2xl shadow-xl z-50 overflow-hidden">
          {/* Search */}
          <div className="p-2 border-b border-border-subtle">
            <input
              ref={inputRef}
              type="text"
              placeholder={t.library_tags_search}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-surface-light rounded-lg px-3 py-1.5 text-xs text-cream placeholder-cream-muted focus:outline-none"
            />
          </div>

          {/* Tag list */}
          <div className="max-h-64 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <div className="px-3 py-4 text-center text-xs text-cream-muted">--</div>
            ) : (
              filtered.map((tag) => {
                const isActive = activeSet.has(tag.name);
                return (
                  <button
                    key={tag.id}
                    onClick={() => onToggle(tag.name)}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-surface-light transition-colors text-left"
                  >
                    <span className={`w-3.5 h-3.5 rounded border flex items-center justify-center flex-shrink-0 ${
                      isActive
                        ? "bg-cream border-cream"
                        : "border-border-subtle"
                    }`}>
                      {isActive && (
                        <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#0C0C0C" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      )}
                    </span>
                    <span className={`flex-1 ${isActive ? "text-cream font-medium" : "text-cream-dim"}`}>
                      {tag.display_name}
                    </span>
                    <span className="text-cream-muted text-[10px]">{tag.reel_count}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
