import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminDeleteLibraryItem, getLibrary, getLibraryTags } from "../../api/client";
import { useTranslation } from "../../i18n";
import type { LibraryReelCard, TagInfo } from "../../types";
import { libraryReelToCard } from "../../utils/cardAdapters";
import { UnifiedReelCard } from "../UnifiedReelCard";
import { TagDropdown } from "../TagDropdown";

function truncate(str: string, len: number) {
  return str.length > len ? str.slice(0, len) + "\u2026" : str;
}

function ConfirmDialog({
  message, onConfirm, onCancel, loading,
}: {
  message: string; onConfirm: () => void; onCancel: () => void; loading?: boolean;
}) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-[340px]">
        <p className="text-zinc-200 text-sm mb-5">{message}</p>
        <div className="flex gap-3 justify-end">
          <button onClick={onCancel} className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors">
            Отмена
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="px-4 py-2 text-sm bg-red-900/60 text-red-300 hover:bg-red-800/70 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading ? "Удаление..." : "Удалить"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function AdminLibrary() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [reels, setReels] = useState<LibraryReelCard[]>([]);
  const [tags, setTags] = useState<TagInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState("");
  const [activeTags, setActiveTags] = useState("");
  const [sort, setSort] = useState("recent");
  const [page, setPage] = useState(1);
  const perPage = 20;

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Delete state
  const [deleteTarget, setDeleteTarget] = useState<LibraryReelCard | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [libraryRes, tagsRes] = await Promise.all([
        getLibrary({ q, tags: activeTags, sort, page, per_page: perPage }),
        tags.length === 0 ? getLibraryTags() : Promise.resolve(null),
      ]);
      setReels(libraryRes.items);
      setTotal(libraryRes.total);
      if (tagsRes) setTags(tagsRes);
    } catch {
      setError("Ошибка загрузки библиотеки");
    } finally {
      setLoading(false);
    }
  }, [q, activeTags, sort, page, tags.length]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSearchInput = (value: string) => {
    setSearchInput(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setQ(value);
      setPage(1);
    }, 400);
  };

  const toggleTag = (tagName: string) => {
    const current = activeTags ? activeTags.split(",") : [];
    const idx = current.indexOf(tagName);
    if (idx >= 0) {
      current.splice(idx, 1);
    } else {
      current.push(tagName);
    }
    setActiveTags(current.join(","));
    setPage(1);
  };

  const handleSortChange = (newSort: string) => {
    setSort(newSort);
    setPage(1);
  };

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await adminDeleteLibraryItem(deleteTarget.id);
      setReels((prev) => prev.filter((r) => r.id !== deleteTarget.id));
      setTotal((t) => t - 1);
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-serif font-medium text-zinc-100">Библиотека</h1>
        <span className="text-xs text-zinc-500">{total} рилсов</span>
      </div>

      {/* Search + Sort */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1 relative">
          <input
            type="text"
            placeholder="Поиск по транскрипту, автору, названию..."
            value={searchInput}
            onChange={(e) => handleSearchInput(e.target.value)}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-full px-5 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-500 transition-colors"
          />
          {searchInput && (
            <button
              onClick={() => { setSearchInput(""); setQ(""); setPage(1); }}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 text-sm"
            >
              x
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => handleSortChange("recent")}
            className={`px-4 py-2 text-sm rounded-full transition-colors ${
              sort === "recent"
                ? "bg-zinc-100 text-zinc-900 font-medium"
                : "bg-zinc-800 text-zinc-400 border border-zinc-700 hover:border-zinc-500"
            }`}
          >
            Новые
          </button>
          <button
            onClick={() => handleSortChange("popular")}
            className={`px-4 py-2 text-sm rounded-full transition-colors ${
              sort === "popular"
                ? "bg-zinc-100 text-zinc-900 font-medium"
                : "bg-zinc-800 text-zinc-400 border border-zinc-700 hover:border-zinc-500"
            }`}
          >
            Популярные
          </button>
        </div>
      </div>

      {/* Tags */}
      {tags.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <TagDropdown tags={tags} activeTags={activeTags} onToggle={toggleTag} />
          {activeTags && activeTags.split(",").filter(Boolean).map((tagName) => {
            const tag = tags.find((t) => t.name === tagName);
            return (
              <button
                key={tagName}
                onClick={() => toggleTag(tagName)}
                className="flex items-center gap-1.5 px-3 py-1 text-xs rounded-full bg-zinc-100 text-zinc-900 font-medium transition-colors hover:bg-zinc-300"
              >
                {tag?.display_name || tagName}
                <span className="text-[10px] opacity-60">&times;</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="text-center py-8">
          <p className="text-red-400 text-sm mb-3">{error}</p>
          <button
            onClick={fetchData}
            className="px-4 py-2 text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-full border border-zinc-700 transition-colors"
          >
            Попробовать снова
          </button>
        </div>
      )}

      {/* Grid */}
      {!error && loading ? (
        <div className="text-center py-16">
          <div className="text-sm text-zinc-500">Загрузка...</div>
        </div>
      ) : !error && reels.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-zinc-500 text-sm">
            {q || activeTags ? "Ничего не найдено" : "Библиотека пуста"}
          </p>
        </div>
      ) : !error ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {reels.map((reel) => (
            <div key={reel.id} className="relative group/card">
              <UnifiedReelCard
                data={libraryReelToCard(reel)}
                variant="library"
                onClick={() => navigate(`/admin/library/${reel.id}`)}
                isLiked={false}
                onToggleLike={() => {}}
                t={t}
              />
              {/* Delete button overlay */}
              <button
                onClick={(e) => { e.stopPropagation(); setDeleteTarget(reel); }}
                className="absolute top-2 right-2 z-20 w-7 h-7 flex items-center justify-center rounded-full bg-red-900/80 text-red-300 text-xs opacity-0 group-hover/card:opacity-100 transition-opacity hover:bg-red-800"
                title="Удалить из библиотеки"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      ) : null}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4 pt-4 border-t border-zinc-800">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-40 transition-colors"
          >
            &larr; Назад
          </button>
          <span className="text-xs text-zinc-500">
            Страница {page} из {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-40 transition-colors"
          >
            Вперёд &rarr;
          </button>
        </div>
      )}

      {/* Delete dialog */}
      {deleteTarget && (
        <ConfirmDialog
          message={`Удалить рилс из библиотеки? "${deleteTarget.video_title || truncate(deleteTarget.url, 50)}"`}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          loading={deleting}
        />
      )}
    </div>
  );
}
