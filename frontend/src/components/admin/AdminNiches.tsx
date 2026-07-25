import { useEffect, useState } from "react";
import {
  adminListNiches,
  adminCreateNiche,
  adminUpdateNiche,
  adminDeactivateNiche,
  adminActivateNiche,
} from "../../api/client";
import type { AdminNiche, AdminNicheGroup, AdminNicheStats, AdminNichesResponse } from "../../types";

const GROUP_COLORS: Record<string, string> = {
  tech_ai: "border-blue-800/60 bg-blue-950/20",
  business_money: "border-emerald-800/60 bg-emerald-950/20",
  marketing_growth: "border-purple-800/60 bg-purple-950/20",
  creative: "border-pink-800/60 bg-pink-950/20",
  education_career: "border-amber-800/60 bg-amber-950/20",
  health_wellness: "border-green-800/60 bg-green-950/20",
  lifestyle: "border-cyan-800/60 bg-cyan-950/20",
  entertainment: "border-orange-800/60 bg-orange-950/20",
  other: "border-zinc-700/60 bg-zinc-900/20",
};

const GROUP_BADGE: Record<string, string> = {
  tech_ai: "bg-blue-900/50 text-blue-300",
  business_money: "bg-emerald-900/50 text-emerald-300",
  marketing_growth: "bg-purple-900/50 text-purple-300",
  creative: "bg-pink-900/50 text-pink-300",
  education_career: "bg-amber-900/50 text-amber-300",
  health_wellness: "bg-green-900/50 text-green-300",
  lifestyle: "bg-cyan-900/50 text-cyan-300",
  entertainment: "bg-orange-900/50 text-orange-300",
  other: "bg-zinc-700/50 text-zinc-300",
};

interface NicheFormData {
  slug: string;
  display_name: string;
  display_name_en: string;
  description: string;
  keywords: string;
  group_key: string;
  sort_order: number;
}

const EMPTY_FORM: NicheFormData = {
  slug: "",
  display_name: "",
  display_name_en: "",
  description: "",
  keywords: "",
  group_key: "other",
  sort_order: 0,
};

export function AdminNiches() {
  const [data, setData] = useState<AdminNichesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  // Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editingNiche, setEditingNiche] = useState<AdminNiche | null>(null);
  const [form, setForm] = useState<NicheFormData>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [confirmSlug, setConfirmSlug] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      setData(await adminListNiches());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadData(); }, []);

  // Group niches by group_key
  const groups: AdminNicheGroup[] = data?.groups ?? [];
  const allItems = data?.items ?? [];

  const nichesByGroup: Record<string, AdminNiche[]> = {};
  for (const n of allItems) {
    if (!showInactive && !n.is_active) continue;
    if (search) {
      const q = search.toLowerCase();
      if (!n.slug.includes(q) && !n.display_name.toLowerCase().includes(q) && !(n.description ?? "").toLowerCase().includes(q)) continue;
    }
    (nichesByGroup[n.group_key] ??= []).push(n);
  }

  const stats: AdminNicheStats = data?.stats ?? { total_niches: 0, active_niches: 0, videos_without_niche: 0, authors_without_niche: 0 };

  function toggleCollapse(gk: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(gk)) next.delete(gk);
      else next.add(gk);
      return next;
    });
  }

  function openCreate(groupKey?: string) {
    setEditingNiche(null);
    setForm({ ...EMPTY_FORM, group_key: groupKey ?? "other" });
    setFormError(null);
    setModalOpen(true);
  }

  function openEdit(n: AdminNiche) {
    setEditingNiche(n);
    setForm({
      slug: n.slug,
      display_name: n.display_name,
      display_name_en: n.display_name_en ?? "",
      description: n.description ?? "",
      keywords: (n.keywords ?? []).join(", "),
      group_key: n.group_key,
      sort_order: n.sort_order,
    });
    setFormError(null);
    setModalOpen(true);
  }

  async function handleSave() {
    setSaving(true);
    setFormError(null);
    try {
      const keywords = form.keywords.split(",").map((k) => k.trim()).filter(Boolean);
      if (editingNiche) {
        await adminUpdateNiche(editingNiche.slug, {
          display_name: form.display_name,
          display_name_en: form.display_name_en || undefined,
          description: form.description || undefined,
          keywords, group_key: form.group_key, sort_order: form.sort_order,
        });
      } else {
        if (!form.slug) { setFormError("Slug обязателен"); setSaving(false); return; }
        await adminCreateNiche({
          slug: form.slug, display_name: form.display_name,
          display_name_en: form.display_name_en || undefined,
          description: form.description || undefined,
          keywords, group_key: form.group_key, sort_order: form.sort_order,
        });
      }
      setModalOpen(false);
      await loadData();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? (e instanceof Error ? e.message : "Ошибка");
      setFormError(msg);
    } finally { setSaving(false); }
  }

  async function handleDeactivate(slug: string) {
    await adminDeactivateNiche(slug).catch(() => {});
    setConfirmSlug(null);
    await loadData();
  }

  async function handleActivate(slug: string) {
    await adminActivateNiche(slug).catch(() => {});
    await loadData();
  }

  if (loading && !data) return <div className="text-zinc-500 py-20 text-center">Загрузка ниш...</div>;
  if (error) return <div className="text-red-400 py-20 text-center">{error}<button onClick={loadData} className="ml-3 underline">Повторить</button></div>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Ниши</h1>
          <p className="text-sm text-zinc-500 mt-1">Управление нишами для классификации контента</p>
        </div>
        <button onClick={() => openCreate()} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg transition-colors whitespace-nowrap">
          + Добавить нишу
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div className="text-2xl font-bold text-zinc-100">{stats.total_niches}</div>
          <div className="text-xs text-zinc-500 mt-1">Всего ниш</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div className="text-2xl font-bold text-green-400">{stats.active_niches}</div>
          <div className="text-xs text-zinc-500 mt-1">Активных</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div className="text-2xl font-bold text-amber-400">{stats.videos_without_niche.toLocaleString()}</div>
          <div className="text-xs text-zinc-500 mt-1">Видео без ниши</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div className="text-2xl font-bold text-amber-400">{stats.authors_without_niche.toLocaleString()}</div>
          <div className="text-xs text-zinc-500 mt-1">Авторы без ниши</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <input type="text" placeholder="Поиск по нишам..." value={search} onChange={(e) => setSearch(e.target.value)}
          className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 w-64" />
        <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} className="rounded border-zinc-600" />
          Показать неактивные
        </label>
        <span className="text-xs text-zinc-500 ml-auto">
          {Object.values(nichesByGroup).flat().length} из {allItems.length}
        </span>
      </div>

      {/* Grouped tree */}
      <div className="space-y-3">
        {groups.map((g) => {
          const groupNiches = nichesByGroup[g.key] ?? [];
          if (search && groupNiches.length === 0) return null;
          const isCollapsed = collapsed.has(g.key);
          const groupVideos = groupNiches.reduce((s, n) => s + n.videos_count, 0);
          const groupAuthors = groupNiches.reduce((s, n) => s + n.authors_count, 0);

          return (
            <div key={g.key} className={`border rounded-xl overflow-hidden ${GROUP_COLORS[g.key] ?? GROUP_COLORS.other}`}>
              {/* Group header */}
              <button
                onClick={() => toggleCollapse(g.key)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <svg className={`w-4 h-4 text-zinc-400 transition-transform ${isCollapsed ? "" : "rotate-90"}`}
                    viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                  <span className="font-medium text-zinc-100">{g.label}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${GROUP_BADGE[g.key] ?? GROUP_BADGE.other}`}>
                    {groupNiches.length}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-xs text-zinc-500">
                  <span>{groupVideos.toLocaleString()} видео</span>
                  <span>{groupAuthors.toLocaleString()} авторов</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); openCreate(g.key); }}
                    className="text-blue-400 hover:text-blue-300"
                  >+ Добавить</button>
                </div>
              </button>

              {/* Niches in group */}
              {!isCollapsed && groupNiches.length > 0 && (
                <div className="border-t border-zinc-800/50">
                  <table className="w-full text-sm">
                    <tbody>
                      {groupNiches.map((n) => (
                        <tr key={n.slug} className={`border-b border-zinc-800/30 hover:bg-white/5 transition-colors ${!n.is_active ? "opacity-40" : ""}`}>
                          <td className="px-4 py-2.5 pl-11">
                            <div className="text-zinc-200">{n.display_name}</div>
                            {n.description && <div className="text-xs text-zinc-500 mt-0.5 max-w-xs truncate">{n.description}</div>}
                          </td>
                          <td className="px-3 py-2.5">
                            <code className="text-xs bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-400">{n.slug}</code>
                          </td>
                          <td className="px-3 py-2.5 text-right text-zinc-400 tabular-nums text-xs">{n.videos_count.toLocaleString()}</td>
                          <td className="px-3 py-2.5 text-right text-zinc-400 tabular-nums text-xs">{n.authors_count.toLocaleString()}</td>
                          <td className="px-3 py-2.5 text-center">
                            {n.is_active
                              ? <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-900/40 text-green-400">ON</span>
                              : <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-zinc-700/40 text-zinc-500">OFF</span>}
                          </td>
                          <td className="px-3 py-2.5 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <button onClick={() => openEdit(n)} className="text-xs text-blue-400 hover:text-blue-300">Ред.</button>
                              {n.is_active
                                ? <button onClick={() => setConfirmSlug(n.slug)} className="text-xs text-red-400 hover:text-red-300">Выкл.</button>
                                : <button onClick={() => handleActivate(n.slug)} className="text-xs text-green-400 hover:text-green-300">Вкл.</button>}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Confirm deactivate */}
      {confirmSlug && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 max-w-sm mx-4">
            <h3 className="text-zinc-100 font-medium mb-2">Деактивировать нишу?</h3>
            <p className="text-sm text-zinc-400 mb-4">
              Ниша <code className="bg-zinc-800 px-1 rounded">{confirmSlug}</code> будет скрыта из классификации, но данные сохранятся.
            </p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setConfirmSlug(null)} className="px-3 py-1.5 text-sm text-zinc-400 hover:text-zinc-200">Отмена</button>
              <button onClick={() => handleDeactivate(confirmSlug)} className="px-3 py-1.5 text-sm bg-red-900/60 text-red-300 hover:bg-red-800/70 rounded-lg">Деактивировать</button>
            </div>
          </div>
        </div>
      )}

      {/* Create/Edit modal */}
      {modalOpen && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 max-w-md w-full mx-4">
            <h3 className="text-zinc-100 font-medium mb-4">
              {editingNiche ? `Редактирование: ${editingNiche.display_name}` : "Новая ниша"}
            </h3>
            <div className="space-y-3">
              {!editingNiche && (
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Slug (латиница, дефисы)</label>
                  <input type="text" value={form.slug}
                    onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "") })}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200" placeholder="my-niche" />
                </div>
              )}
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Название (RU)</label>
                <input type="text" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200" placeholder="Отношения" />
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Название (EN)</label>
                <input type="text" value={form.display_name_en} onChange={(e) => setForm({ ...form, display_name_en: e.target.value })}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200" placeholder="Relationships" />
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Описание (для LLM-классификации)</label>
                <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 h-20 resize-none"
                  placeholder="Краткое описание ниши — LLM использует это для классификации рилсов" />
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Ключевые слова (через запятую) — сигналы для LLM</label>
                <input type="text" value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200"
                  placeholder="dating, love, couples, breakup" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Группа</label>
                  <select value={form.group_key} onChange={(e) => setForm({ ...form, group_key: e.target.value })}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200">
                    {groups.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Порядок</label>
                  <input type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: parseInt(e.target.value) || 0 })}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200" />
                </div>
              </div>
            </div>
            {formError && (
              <div className="mt-3 text-sm text-red-400 bg-red-900/20 border border-red-800/30 rounded-lg px-3 py-2">{formError}</div>
            )}
            <div className="flex gap-3 justify-end mt-5">
              <button onClick={() => setModalOpen(false)} className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200">Отмена</button>
              <button onClick={handleSave} disabled={saving || !form.display_name}
                className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white rounded-lg">
                {saving ? "Сохранение..." : editingNiche ? "Сохранить" : "Создать"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
