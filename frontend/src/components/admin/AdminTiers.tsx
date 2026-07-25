import { useEffect, useState } from "react";
import { adminListTiers, adminUpdateTierConfig } from "../../api/client";
import type { AdminTierConfig } from "../../types";

type LimitType = "monthly" | "total" | "unlimited";

function getLimitType(tier: AdminTierConfig): LimitType {
  if (tier.max_monthly !== null) return "monthly";
  if (tier.max_total !== null) return "total";
  return "unlimited";
}

function getLimitValue(tier: AdminTierConfig): number {
  if (tier.max_monthly !== null) return tier.max_monthly;
  if (tier.max_total !== null) return tier.max_total;
  return 0;
}

function formatDate(dt: string | null) {
  if (!dt) return "—";
  return new Date(dt).toLocaleDateString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

const TIER_LABELS: Record<string, string> = {
  ANONYMOUS: "Анонимный",
  REGISTERED: "Зарегистрированный",
  FREE: "Бесплатный",
  START: "Start",
  PRO: "Pro",
  UNLIMITED: "Unlimited",
};

const TIER_COLORS: Record<string, string> = {
  ANONYMOUS: "text-zinc-400",
  REGISTERED: "text-blue-400",
  FREE: "text-green-400",
  START: "text-purple-400",
  PRO: "text-amber-400",
  UNLIMITED: "text-rose-400",
};

interface EditState {
  limitType: LimitType;
  limitValue: number;
  refinesDaily: number | null;
}

export function AdminTiers() {
  const [tiers, setTiers] = useState<AdminTierConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [edits, setEdits] = useState<Record<string, EditState>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  function loadTiers() {
    setLoading(true);
    adminListTiers()
      .then(setTiers)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadTiers();
  }, []);

  function isChanged(tier: AdminTierConfig): boolean {
    const edit = edits[tier.name];
    if (!edit) return false;
    const origType = getLimitType(tier);
    const origValue = getLimitValue(tier);
    return (
      edit.limitType !== origType ||
      edit.limitValue !== origValue ||
      edit.refinesDaily !== (tier.max_refines_daily ?? null)
    );
  }

  function getEdit(tier: AdminTierConfig): EditState {
    return edits[tier.name] ?? {
      limitType: getLimitType(tier),
      limitValue: getLimitValue(tier),
      refinesDaily: tier.max_refines_daily ?? null,
    };
  }

  function setEdit(name: string, partial: Partial<EditState>) {
    setEdits((prev) => {
      const tier = tiers.find((t) => t.name === name);
      const base = prev[name] ?? {
        limitType: tier ? getLimitType(tier) : "monthly",
        limitValue: tier ? getLimitValue(tier) : 0,
        refinesDaily: tier?.max_refines_daily ?? null,
      };
      return { ...prev, [name]: { ...base, ...partial } };
    });
  }

  async function handleSave(tier: AdminTierConfig) {
    const edit = getEdit(tier);
    setSaving(tier.name);
    try {
      let max_monthly: number | null = null;
      let max_total: number | null = null;

      if (edit.limitType === "monthly") {
        max_monthly = edit.limitValue;
      } else if (edit.limitType === "total") {
        max_total = edit.limitValue;
      }
      // unlimited → both null

      const updated = await adminUpdateTierConfig(tier.name, {
        max_monthly,
        max_total,
        max_refines_daily: edit.refinesDaily,
      });
      setTiers((prev) => prev.map((t) => (t.name === tier.name ? updated : t)));
      setEdits((prev) => {
        const next = { ...prev };
        delete next[tier.name];
        return next;
      });
      setSuccessMsg(`Тариф ${TIER_LABELS[tier.name] ?? tier.name} обновлён`);
      setTimeout(() => setSuccessMsg(null), 2000);
    } finally {
      setSaving(null);
    }
  }

  function handleReset(name: string) {
    setEdits((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
  }

  return (
    <div>
      <h1 className="text-2xl font-serif font-medium text-zinc-100 mb-6">Тарифы</h1>

      {successMsg && (
        <div className="mb-4 px-4 py-2 bg-green-900/30 border border-green-800/50 rounded-lg text-green-300 text-sm">
          {successMsg}
        </div>
      )}

      {loading ? (
        <div className="text-zinc-500 text-sm py-8">Загрузка...</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800">
                {["Тариф", "Тип лимита", "Значение", "Рефайнов/день", "Обновлён", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tiers.map((tier) => {
                const edit = getEdit(tier);
                const changed = isChanged(tier);
                const isSaving = saving === tier.name;

                return (
                  <tr key={tier.name} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                    {/* Tier name */}
                    <td className="px-4 py-3">
                      <span className={`font-medium ${TIER_COLORS[tier.name] ?? "text-zinc-300"}`}>
                        {TIER_LABELS[tier.name] ?? tier.name}
                      </span>
                      <span className="text-zinc-600 text-xs ml-2">{tier.name}</span>
                    </td>

                    {/* Limit type dropdown */}
                    <td className="px-4 py-3">
                      <select
                        value={edit.limitType}
                        onChange={(e) => {
                          const lt = e.target.value as LimitType;
                          setEdit(tier.name, {
                            limitType: lt,
                            limitValue: lt === "unlimited" ? 0 : edit.limitValue,
                          });
                        }}
                        className="bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded-lg px-2 py-1.5 focus:outline-none focus:border-zinc-500"
                      >
                        <option value="monthly">По месяцу</option>
                        <option value="total">За всё время</option>
                        <option value="unlimited">Безлимит</option>
                      </select>
                    </td>

                    {/* Limit value */}
                    <td className="px-4 py-3">
                      {edit.limitType === "unlimited" ? (
                        <span className="text-zinc-500 text-xs">—</span>
                      ) : (
                        <input
                          type="number"
                          min={0}
                          value={edit.limitValue}
                          onChange={(e) => setEdit(tier.name, { limitValue: parseInt(e.target.value) || 0 })}
                          className="bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded-lg px-2 py-1.5 w-20 focus:outline-none focus:border-zinc-500"
                        />
                      )}
                    </td>

                    {/* Refines daily */}
                    <td className="px-4 py-3">
                      <input
                        type="number"
                        min={0}
                        value={edit.refinesDaily ?? ""}
                        placeholder="—"
                        onChange={(e) => {
                          const v = e.target.value;
                          setEdit(tier.name, { refinesDaily: v === "" ? null : parseInt(v) || 0 });
                        }}
                        className="bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded-lg px-2 py-1.5 w-20 focus:outline-none focus:border-zinc-500"
                      />
                    </td>

                    {/* Updated at */}
                    <td className="px-4 py-3 text-zinc-500 text-xs whitespace-nowrap">
                      {formatDate(tier.updated_at)}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      {changed && (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleSave(tier)}
                            disabled={isSaving}
                            className="px-3 py-1 text-xs bg-green-900/50 text-green-300 hover:bg-green-800/60 rounded-lg transition-colors disabled:opacity-50"
                          >
                            {isSaving ? "..." : "Сохранить"}
                          </button>
                          <button
                            onClick={() => handleReset(tier.name)}
                            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                          >
                            Отмена
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Help text */}
      <div className="mt-6 p-4 bg-zinc-900/50 border border-zinc-800 rounded-xl text-xs text-zinc-500 space-y-1">
        <p><strong className="text-zinc-400">По месяцу</strong> — лимит генераций в месяц (0 = заблокирован)</p>
        <p><strong className="text-zinc-400">За всё время</strong> — лимит генераций за всё время использования</p>
        <p><strong className="text-zinc-400">Безлимит</strong> — без ограничений</p>
        <p><strong className="text-zinc-400">Рефайнов/день</strong> — лимит AI-редактирований сценария в день (пусто = нет доступа)</p>
      </div>
    </div>
  );
}
