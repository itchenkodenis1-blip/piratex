import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getPricing } from "../api/client";
import { useTranslation } from "../i18n";
import type { PricingTier, UsageInfo } from "../types";

interface UpgradeModalProps {
  isOpen: boolean;
  onClose: () => void;
  usage: UsageInfo | null;
  currentTier: string;
  reason?: string;
}

// Tier upgrade order: FREE → START → PRO → UNLIMITED
const TIER_ORDER = ["FREE", "START", "PRO", "UNLIMITED"];

function getNextTierKey(current: string): string | null {
  const idx = TIER_ORDER.indexOf(current);
  if (idx < 0 || idx >= TIER_ORDER.length - 1) return null;
  return TIER_ORDER[idx + 1];
}

export function UpgradeModal({
  isOpen,
  onClose,
  usage,
  currentTier,
  reason,
}: UpgradeModalProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [pricingTiers, setPricingTiers] = useState<PricingTier[]>([]);

  useEffect(() => {
    if (isOpen && pricingTiers.length === 0) {
      getPricing("RUB").then((res) => setPricingTiers(res.tiers)).catch(() => {});
    }
  }, [isOpen, pricingTiers.length]);

  if (!isOpen) return null;
  if (!usage && reason !== "upgrade_required_authors") return null;

  const nextKey = getNextTierKey(currentTier);
  if (!nextKey) return null;

  const nextTier = pricingTiers.find((t) => t.tier === nextKey);
  const nextName = nextTier?.name ?? nextKey.charAt(0) + nextKey.slice(1).toLowerCase();
  const nextLimit = nextTier?.limit_monthly;
  const nextPrice = nextTier?.price_monthly;

  const isTrendsReason = reason === "upgrade_required_trends" || reason === "upgrade_required_search";
  const isAuthorsReason = reason === "upgrade_required_authors";
  const pct = usage && usage.limit > 0 ? Math.round((usage.used / usage.limit) * 100) : 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative bg-surface border border-border-subtle rounded-2xl p-6 sm:p-8 max-w-sm w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-cream-muted hover:text-cream text-lg"
        >
          &times;
        </button>

        {isAuthorsReason ? (
          <>
            <h3 className="text-lg font-serif font-bold text-cream mb-2">
              {t.upgrade_authors_title}
            </h3>
            <p className="text-sm text-cream-dim mb-6">
              {t.upgrade_authors_desc}{" "}
              <span className="text-cream font-medium">{nextName}</span>
              {nextPrice != null && <>{" — "}{nextPrice.toLocaleString()} {t.upgrade_price_monthly}</>}
            </p>
          </>
        ) : isTrendsReason ? (
          <>
            <h3 className="text-lg font-serif font-bold text-cream mb-2">
              {t.upgrade_trends_title}
            </h3>
            <p className="text-sm text-cream-dim mb-6">
              {reason === "upgrade_required_search"
                ? `${t.upgrade_trends_search} `
                : `${t.upgrade_trends_pages} `}
              <span className="text-cream font-medium">{nextName}</span>
              {nextPrice != null && <>{" — "}{nextPrice.toLocaleString()} {t.upgrade_price_monthly}</>}
            </p>
          </>
        ) : (
          <>
            {/* Progress bar */}
            <div className="mb-5">
              <div className="flex justify-between text-xs text-cream-muted mb-2">
                <span>{t.upgrade_used_label}</span>
                <span>
                  {usage?.used ?? 0} / {usage?.limit ?? 0}
                </span>
              </div>
              <div className="w-full h-2 bg-surface-light rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    pct >= 100
                      ? "bg-red-400"
                      : pct >= 80
                        ? "bg-yellow-400"
                        : "bg-cream"
                  }`}
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </div>
            </div>

            <h3 className="text-lg font-serif font-bold text-cream mb-2">
              {pct >= 100
                ? t.upgrade_limit_reached
                : t.upgrade_used_pct.replace("{pct}", String(pct))}
            </h3>

            <p className="text-sm text-cream-dim mb-6">
              {t.upgrade_switch_to}{" "}
              <span className="text-cream font-medium">{nextName}</span>
              {nextLimit != null && nextPrice != null
                ? <> — {nextLimit} {t.upgrade_analyses_for} {nextPrice.toLocaleString()} {t.upgrade_price_monthly}</>
                : nextPrice != null
                  ? <> — {nextPrice.toLocaleString()} {t.upgrade_price_monthly}</>
                  : null}
            </p>
          </>
        )}

        <div className="flex flex-col gap-3">
          <button
            onClick={() => {
              onClose();
              navigate("/pricing");
            }}
            className="w-full py-3 bg-cream text-[#0C0C0C] hover:bg-cream-dim font-medium rounded-full text-sm transition-colors"
          >
            {t.upgrade_go_to} {nextName}
          </button>
          <button
            onClick={onClose}
            className="w-full py-2.5 text-cream-muted hover:text-cream text-sm transition-colors"
          >
            {t.upgrade_later}
          </button>
        </div>
      </div>
    </div>
  );
}
