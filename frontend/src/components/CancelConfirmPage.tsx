import { useCallback, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { cancelSubscriptionByToken } from "../api/client";
import { useRegion } from "../region";
import type { Region } from "../region";

const TEXT: Record<Region, {
  title: string;
  description: string;
  confirm: string;
  keep: string;
  cancelling: string;
  successTitle: string;
  successMessage: string;
  errorTitle: string;
  errorMessage: string;
  goHome: string;
  goSettings: string;
}> = {
  ru: {
    title: "Отмена подписки",
    description: "Вы уверены, что хотите отменить подписку? Доступ сохранится до конца оплаченного периода.",
    confirm: "Да, отменить",
    keep: "Нет, оставить",
    cancelling: "Отмена...",
    successTitle: "Подписка отменена",
    successMessage: "Доступ сохранится до",
    errorTitle: "Ошибка",
    errorMessage: "Не удалось отменить подписку. Ссылка могла истечь. Попробуйте отменить в настройках аккаунта.",
    goHome: "На главную",
    goSettings: "Настройки",
  },
  int: {
    title: "Cancel subscription",
    description: "Are you sure you want to cancel your subscription? Access continues until the end of your paid period.",
    confirm: "Yes, cancel",
    keep: "No, keep it",
    cancelling: "Cancelling...",
    successTitle: "Subscription cancelled",
    successMessage: "Access continues until",
    errorTitle: "Error",
    errorMessage: "Could not cancel subscription. The link may have expired. Try cancelling in account settings.",
    goHome: "Home",
    goSettings: "Settings",
  },
};

export function CancelConfirmPage() {
  const [searchParams] = useSearchParams();
  const regionConfig = useRegion();
  const t = TEXT[regionConfig.region];
  const token = searchParams.get("token") || "";

  const [state, setState] = useState<"confirm" | "loading" | "success" | "error">("confirm");
  const [activeUntil, setActiveUntil] = useState<string | null>(null);

  const handleCancel = useCallback(async () => {
    setState("loading");
    try {
      const res = await cancelSubscriptionByToken(token);
      if (res.ok) {
        setState("success");
        setActiveUntil(res.active_until);
      } else {
        setState("error");
      }
    } catch {
      setState("error");
    }
  }, [token]);

  const formatDate = (iso: string | null) => {
    if (!iso) return "";
    const locale = regionConfig.region === "ru" ? "ru-RU" : "en-US";
    return new Date(iso).toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" });
  };

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-4">
      <div className="w-full max-w-sm text-center">
        {state === "confirm" && (
          <div className="space-y-6">
            <h1 className="text-2xl font-serif font-bold text-cream">{t.title}</h1>
            <p className="text-cream-dim text-sm">{t.description}</p>
            <div className="flex flex-col gap-3">
              <button
                onClick={handleCancel}
                className="w-full py-3 rounded-full text-sm font-medium bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-colors"
              >
                {t.confirm}
              </button>
              <Link
                to="/"
                className="w-full py-3 rounded-full text-sm font-medium border border-cream/20 text-cream hover:bg-surface-light transition-colors inline-block"
              >
                {t.keep}
              </Link>
            </div>
          </div>
        )}

        {state === "loading" && (
          <p className="text-cream-muted text-sm">{t.cancelling}</p>
        )}

        {state === "success" && (
          <div className="space-y-6">
            <h1 className="text-2xl font-serif font-bold text-cream">{t.successTitle}</h1>
            {activeUntil && (
              <p className="text-cream-dim text-sm">
                {t.successMessage} {formatDate(activeUntil)}
              </p>
            )}
            <div className="flex flex-col gap-3">
              <Link
                to="/"
                className="w-full py-3 rounded-full text-sm font-medium bg-cream text-[#0C0C0C] hover:bg-cream-dim transition-colors inline-block"
              >
                {t.goHome}
              </Link>
            </div>
          </div>
        )}

        {state === "error" && (
          <div className="space-y-6">
            <h1 className="text-2xl font-serif font-bold text-red-400">{t.errorTitle}</h1>
            <p className="text-cream-dim text-sm">{t.errorMessage}</p>
            <div className="flex flex-col gap-3">
              <Link
                to="/settings"
                className="w-full py-3 rounded-full text-sm font-medium bg-cream text-[#0C0C0C] hover:bg-cream-dim transition-colors inline-block"
              >
                {t.goSettings}
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
