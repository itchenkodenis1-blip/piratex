import { useEffect, useState } from "react";
import { adminListHiddenReels, adminUnhideReel } from "../../api/client";
import type { AdminHiddenReel } from "../../types";

function timeAgo(dt: string | null): string {
  if (!dt) return "—";
  const diff = Date.now() - new Date(dt).getTime();
  const hours = Math.floor(diff / 3_600_000);
  if (hours < 1) return "< 1ч назад";
  if (hours < 24) return `${hours}ч назад`;
  const days = Math.floor(hours / 24);
  return `${days}д назад`;
}

function formatViews(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toString();
}

export function AdminHiddenReels() {
  const [reels, setReels] = useState<AdminHiddenReel[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [unhiding, setUnhiding] = useState<string | null>(null);

  const perPage = 50;
  const totalPages = Math.ceil(total / perPage);

  function load() {
    setLoading(true);
    adminListHiddenReels({
      q: search || undefined,
      page,
      per_page: perPage,
    })
      .then((res) => {
        setReels(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, [page]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (page === 1) {
      load();
    } else {
      setPage(1);
    }
  }

  async function handleUnhide(reel: AdminHiddenReel) {
    setUnhiding(reel.id);
    try {
      await adminUnhideReel(reel.id);
      setReels((prev) => prev.filter((r) => r.id !== reel.id));
      setTotal((t) => t - 1);
    } finally {
      setUnhiding(null);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-serif font-medium text-zinc-100 mb-6">Скрытые рилсы</h1>

      <div className="flex flex-wrap items-center gap-4 mb-4 pb-4 border-b border-zinc-800">
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по URL, автору, описанию..."
            className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-1.5 w-[280px] focus:outline-none focus:border-zinc-500"
          />
          <button
            type="submit"
            className="text-sm px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg transition-colors"
          >
            Найти
          </button>
        </form>

        <span className="ml-auto text-xs text-zinc-500">
          {total} скрытых рилсов
        </span>
      </div>

      {loading ? (
        <div className="text-zinc-500 text-sm py-8">Загрузка...</div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  {["Автор", "Платформа", "Просмотры", "Описание", "Причина", "Скрыт", ""].map((h) => (
                    <th key={h} className="text-left px-3 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {reels.map((r) => (
                  <tr key={r.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                    <td className="px-3 py-3 text-zinc-200 text-xs">
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 hover:underline"
                      >
                        @{r.profile_username}
                      </a>
                    </td>
                    <td className="px-3 py-3 text-zinc-400 text-xs">
                      {r.profile_platform === "instagram" ? "IG" : r.profile_platform === "youtube" ? "YT" : r.profile_platform}
                    </td>
                    <td className="px-3 py-3 text-zinc-400 text-xs">{formatViews(r.views)}</td>
                    <td className="px-3 py-3 text-zinc-400 text-xs max-w-[300px]">
                      <span className="truncate block">{r.caption || "—"}</span>
                    </td>
                    <td className="px-3 py-3 text-zinc-400 text-xs max-w-[200px]">
                      <span className="truncate block">{r.hidden_reason || "—"}</span>
                    </td>
                    <td className="px-3 py-3 text-zinc-500 text-xs whitespace-nowrap">
                      {timeAgo(r.hidden_at)}
                    </td>
                    <td className="px-3 py-3">
                      <button
                        onClick={() => handleUnhide(r)}
                        disabled={unhiding === r.id}
                        className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-400 hover:bg-green-900/40 hover:text-green-400 transition-colors disabled:opacity-50"
                      >
                        {unhiding === r.id ? "..." : "Вернуть"}
                      </button>
                    </td>
                  </tr>
                ))}
                {reels.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-3 py-8 text-center text-zinc-500 text-sm">
                      Нет скрытых рилсов
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center gap-4 mt-4 pt-4 border-t border-zinc-800">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-40 transition-colors"
              >
                ← Назад
              </button>
              <span className="text-xs text-zinc-500">
                Страница {page} из {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-40 transition-colors"
              >
                Вперёд →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
