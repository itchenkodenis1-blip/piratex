import { type ReactNode, useEffect, useState } from "react";
import { getPricing } from "../api/client";
import { useTranslation } from "../i18n";

interface Props {
  children: ReactNode;
  hint?: string;
}

export function TeaserOverlay({ children, hint }: Props) {
  const { t } = useTranslation();
  const [freeLimit, setFreeLimit] = useState<number | null>(null);

  useEffect(() => {
    getPricing("RUB")
      .then((res) => {
        if (res.free_limit != null && res.free_limit > 0) setFreeLimit(res.free_limit);
      })
      .catch(() => {});
  }, []);

  const handleClick = () => {
    window.dispatchEvent(
      new CustomEvent("piratex:limit-reached", {
        detail: { reason: "teaser_unlock" },
      })
    );
  };

  const subtitle = freeLimit
    ? (t.teaser_cta_subtitle as string).replace("{limit}", String(freeLimit))
    : (t.teaser_cta_subtitle as string).replace("{limit}", "");

  return (
    <div className="relative">
      {children}
      <div className="absolute inset-0 top-1/3 flex flex-col items-center justify-end pb-8 bg-gradient-to-b from-transparent via-surface/80 to-surface">
        <div className="flex flex-col items-center gap-3 text-center px-4">
          {hint && (
            <p className="text-xs text-cream-dim">{hint}</p>
          )}
          <div className="backdrop-blur-sm bg-surface-light/60 border border-border-subtle rounded-2xl px-6 py-5 flex flex-col items-center gap-2 max-w-sm">
            <svg className="w-5 h-5 text-cream-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            <p className="text-sm font-medium text-cream">{t.teaser_cta_title}</p>
            <p className="text-xs text-cream-dim">{subtitle}</p>
            <button
              onClick={handleClick}
              className="mt-1 px-5 py-2 bg-accent hover:bg-accent-hover text-white text-sm font-medium rounded-full transition-colors"
            >
              {t.teaser_cta_button}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
