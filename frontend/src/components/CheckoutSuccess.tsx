import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useRegion } from "../region";
import type { Region } from "../region";

interface CheckoutSuccessProps {
  refreshUser: () => Promise<void>;
}

const TEXT: Record<Region, {
  title: string;
  subtitle: string;
  startAnalysis: string;
  subscriptionSettings: string;
}> = {
  ru: {
    title: "Оплата прошла успешно!",
    subtitle: "Ваша подписка активирована. Теперь вам доступны все возможности тарифа.",
    startAnalysis: "Начать анализ",
    subscriptionSettings: "Настройки подписки",
  },
  int: {
    title: "Payment successful!",
    subtitle: "Your subscription is now active. You have full access to all plan features.",
    startAnalysis: "Start analyzing",
    subscriptionSettings: "Subscription settings",
  },
};

export function CheckoutSuccess({ refreshUser }: CheckoutSuccessProps) {
  const navigate = useNavigate();
  const regionConfig = useRegion();
  const t = TEXT[regionConfig.region];

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  return (
    <div className="max-w-md mx-auto text-center py-16">
      <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-green-500/10 border border-green-500/20 flex items-center justify-center">
        <span className="text-green-400 text-2xl">&#10003;</span>
      </div>

      <h1 className="text-2xl font-serif font-bold text-cream mb-3">
        {t.title}
      </h1>
      <p className="text-cream-dim mb-8">
        {t.subtitle}
      </p>

      <div className="flex flex-col sm:flex-row gap-3 justify-center">
        <button
          onClick={() => navigate("/")}
          className="px-6 py-2.5 bg-cream text-[#0C0C0C] hover:bg-cream-dim font-medium rounded-full text-sm transition-colors"
        >
          {t.startAnalysis}
        </button>
        <button
          onClick={() => navigate("/settings")}
          className="px-6 py-2.5 border border-border-subtle hover:border-cream-muted rounded-full text-cream-muted hover:text-cream text-sm transition-colors"
        >
          {t.subscriptionSettings}
        </button>
      </div>
    </div>
  );
}
