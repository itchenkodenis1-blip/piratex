import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  cancelSubscription,
  getPayments,
  getPortalUrl,
  getSubscription,
  removePaymentMethod,
} from "../api/client";
import type { PaymentItem, SubscriptionInfo } from "../types";
import { useRegion } from "../region";
import type { Region } from "../region";

const TIER_NAMES: Record<string, string> = {
  START: "Start",
  PRO: "Pro",
  UNLIMITED: "Unlimited",
};

const TEXT: Record<Region, {
  title: string;
  yearly: string;
  monthly: string;
  amount: string;
  activeUntil: string;
  changePlan: string;
  manageSub: string;
  cancelSub: string;
  confirmCancel: string;
  cancelNo: string;
  cancelling: string;
  cancelError: string;
  noSub: string;
  choosePlan: string;
  accessUntil: string;
  paymentHistory: string;
  defaultPaymentDesc: string;
  loading: string;
  autoRenewal: string;
  autoRenewalOn: string;
  autoRenewalOff: string;
  removeCard: string;
  removeCardConfirm: string;
  removeCardDone: string;
  statusLabels: Record<string, string>;
  paymentStatus: Record<string, { label: string; color: string }>;
}> = {
  ru: {
    title: "Подписка",
    yearly: "годовая",
    monthly: "месячная",
    amount: "Сумма",
    activeUntil: "Действует до",
    changePlan: "Сменить тариф",
    manageSub: "Управление подпиской",
    cancelSub: "Отменить подписку",
    confirmCancel: "Подтвердить",
    cancelNo: "Нет",
    cancelling: "Отмена...",
    cancelError: "Ошибка при отмене подписки",
    noSub: "У вас нет активной подписки",
    choosePlan: "Выбрать тариф",
    accessUntil: "Доступ сохранится до",
    paymentHistory: "История платежей",
    defaultPaymentDesc: "Оплата подписки",
    loading: "Загрузка...",
    autoRenewal: "Автопродление",
    autoRenewalOn: "Включено",
    autoRenewalOff: "Отключено",
    removeCard: "Удалить карту",
    removeCardConfirm: "Удалить карту и отключить автопродление?",
    removeCardDone: "Карта удалена. Автопродление отключено.",
    statusLabels: {
      active: "Активна",
      cancelled: "Отменена",
      past_due: "Просрочена",
      expired: "Истекла",
    },
    paymentStatus: {
      succeeded: { label: "Оплачен", color: "text-green-400" },
      pending: { label: "Ожидание", color: "text-yellow-400" },
      cancelled: { label: "Отменён", color: "text-red-400" },
      refunded: { label: "Возврат", color: "text-cream-muted" },
    },
  },
  int: {
    title: "Subscription",
    yearly: "yearly",
    monthly: "monthly",
    amount: "Amount",
    activeUntil: "Active until",
    changePlan: "Change plan",
    manageSub: "Manage subscription",
    cancelSub: "Cancel subscription",
    confirmCancel: "Confirm",
    cancelNo: "No",
    cancelling: "Cancelling...",
    cancelError: "Failed to cancel subscription",
    noSub: "You have no active subscription",
    choosePlan: "Choose a plan",
    accessUntil: "Access continues until",
    paymentHistory: "Payment history",
    defaultPaymentDesc: "Subscription payment",
    loading: "Loading...",
    autoRenewal: "Auto-renewal",
    autoRenewalOn: "Enabled",
    autoRenewalOff: "Disabled",
    removeCard: "Remove card",
    removeCardConfirm: "Remove card and disable auto-renewal?",
    removeCardDone: "Card removed. Auto-renewal disabled.",
    statusLabels: {
      active: "Active",
      cancelled: "Cancelled",
      past_due: "Past due",
      expired: "Expired",
    },
    paymentStatus: {
      succeeded: { label: "Paid", color: "text-green-400" },
      pending: { label: "Pending", color: "text-yellow-400" },
      cancelled: { label: "Cancelled", color: "text-red-400" },
      refunded: { label: "Refunded", color: "text-cream-muted" },
    },
  },
};

function formatDate(iso: string | null, region: Region): string {
  if (!iso) return "—";
  const locale = region === "ru" ? "ru-RU" : "en-US";
  return new Date(iso).toLocaleDateString(locale, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function formatAmount(minorUnits: number, currency: string): string {
  const amount = minorUnits / 100;
  if (currency === "RUB") {
    return amount.toLocaleString("ru-RU") + " \u20BD";
  }
  return "\u20AC" + amount.toLocaleString("en-US");
}

export function SubscriptionSettings() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const regionConfig = useRegion();
  const t = TEXT[regionConfig.region];

  const [sub, setSub] = useState<SubscriptionInfo | null>(null);
  const [payments, setPayments] = useState<PaymentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [removingCard, setRemovingCard] = useState(false);
  const [confirmRemoveCard, setConfirmRemoveCard] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getSubscription(), getPayments()])
      .then(([subRes, payRes]) => {
        setSub(subRes.subscription);
        setPayments(payRes.payments);
        // Auto-show cancel dialog when arriving from notification link
        if (searchParams.get("action") === "cancel-subscription" && subRes.subscription?.status === "active") {
          setConfirmCancel(true);
          setSearchParams({}, { replace: true });
        }
      })
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const isStripe = sub?.payment_provider === "stripe";
  const isAdmin = sub?.payment_provider === "admin";
  const isIndefinite = sub?.current_period_end && new Date(sub.current_period_end).getFullYear() >= 2099;

  const handlePortal = useCallback(async () => {
    try {
      const { url } = await getPortalUrl();
      window.open(url, "_blank");
    } catch {
      setMessage(t.cancelError);
    }
  }, [t.cancelError]);

  const handleCancel = useCallback(async () => {
    setCancelling(true);
    try {
      const res = await cancelSubscription();
      setMessage(res.message);
      setConfirmCancel(false);
      // Refresh subscription data
      const subRes = await getSubscription();
      setSub(subRes.subscription);
    } catch {
      setMessage(t.cancelError);
    } finally {
      setCancelling(false);
    }
  }, [t.cancelError]);

  const handleRemoveCard = useCallback(async () => {
    setRemovingCard(true);
    try {
      await removePaymentMethod();
      setMessage(t.removeCardDone);
      setConfirmRemoveCard(false);
      const subRes = await getSubscription();
      setSub(subRes.subscription);
    } catch {
      setMessage(t.cancelError);
    } finally {
      setRemovingCard(false);
    }
  }, [t.removeCardDone, t.cancelError]);

  if (loading) {
    return (
      <div className="bg-surface border border-border-subtle rounded-2xl p-6">
        <div className="text-cream-muted text-sm">{t.loading}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Subscription card */}
      <div className="bg-surface border border-border-subtle rounded-2xl p-6">
        <h3 className="text-base font-semibold text-cream mb-4">{t.title}</h3>

        {sub ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-cream font-medium">
                  {TIER_NAMES[sub.tier] || sub.tier}
                </span>
                {!isAdmin && (
                  <span className="ml-2 text-xs text-cream-muted">
                    {sub.billing_interval === "yearly" ? t.yearly : t.monthly}
                  </span>
                )}
              </div>
              <span
                className={`text-xs px-2.5 py-1 rounded-full ${
                  sub.status === "active"
                    ? "bg-green-500/10 text-green-400 border border-green-500/20"
                    : sub.status === "cancelled"
                      ? "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20"
                      : "bg-red-500/10 text-red-400 border border-red-500/20"
                }`}
              >
                {t.statusLabels[sub.status] || sub.status}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-cream-muted">{t.amount}</span>
                <p className="text-cream">
                  {isAdmin
                    ? (regionConfig.region === "ru" ? "Назначено администратором" : "Granted by admin")
                    : formatAmount(sub.amount_kopecks, sub.currency)}
                </p>
              </div>
              <div>
                <span className="text-cream-muted">{t.activeUntil}</span>
                <p className="text-cream">
                  {isIndefinite
                    ? (regionConfig.region === "ru" ? "Бессрочно" : "Indefinite")
                    : formatDate(sub.current_period_end, regionConfig.region)}
                </p>
              </div>
            </div>

            {/* Auto-renewal & payment method (376-ФЗ) */}
            {sub.status === "active" && !isStripe && !isAdmin && (
              <div className="flex items-center justify-between py-2 px-3 rounded-xl bg-surface-light/50 border border-border-subtle text-sm">
                <div>
                  <span className="text-cream-muted">{t.autoRenewal}: </span>
                  <span className={sub.auto_renewal_enabled ? "text-green-400" : "text-cream-muted"}>
                    {sub.auto_renewal_enabled ? t.autoRenewalOn : t.autoRenewalOff}
                  </span>
                </div>
                {sub.has_payment_method && (
                  !confirmRemoveCard ? (
                    <button
                      onClick={() => setConfirmRemoveCard(true)}
                      className="text-xs text-red-400/70 hover:text-red-400 transition-colors"
                    >
                      {t.removeCard}
                    </button>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-cream-muted">{t.removeCardConfirm}</span>
                      <button
                        onClick={handleRemoveCard}
                        disabled={removingCard}
                        className="text-xs px-2.5 py-1 bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 rounded-full transition-colors disabled:opacity-50"
                      >
                        {removingCard ? "..." : t.confirmCancel}
                      </button>
                      <button
                        onClick={() => setConfirmRemoveCard(false)}
                        className="text-xs text-cream-muted hover:text-cream transition-colors"
                      >
                        {t.cancelNo}
                      </button>
                    </div>
                  )
                )}
              </div>
            )}

            {sub.status === "active" && !isAdmin && (
              <div className="pt-2 flex flex-wrap gap-2 sm:gap-3">
                {isStripe ? (
                  <button
                    onClick={handlePortal}
                    className="px-4 py-2 text-sm border border-border-subtle hover:border-cream-muted rounded-full text-cream-muted hover:text-cream transition-colors"
                  >
                    {t.manageSub}
                  </button>
                ) : (
                  <button
                    onClick={() => navigate("/pricing")}
                    className="px-4 py-2 text-sm border border-border-subtle hover:border-cream-muted rounded-full text-cream-muted hover:text-cream transition-colors"
                  >
                    {t.changePlan}
                  </button>
                )}
                {!confirmCancel ? (
                  <button
                    onClick={() => setConfirmCancel(true)}
                    className="px-4 py-2 text-sm text-red-400 hover:text-red-300 transition-colors"
                  >
                    {t.cancelSub}
                  </button>
                ) : (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleCancel}
                      disabled={cancelling}
                      className="px-4 py-2 text-sm bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 rounded-full transition-colors disabled:opacity-50"
                    >
                      {cancelling ? t.cancelling : t.confirmCancel}
                    </button>
                    <button
                      onClick={() => setConfirmCancel(false)}
                      className="px-4 py-2 text-sm text-cream-muted hover:text-cream transition-colors"
                    >
                      {t.cancelNo}
                    </button>
                  </div>
                )}
              </div>
            )}

            {sub.status === "cancelled" && sub.current_period_end && (
              <div className="space-y-2">
                <p className="text-sm text-yellow-400/80">
                  {t.accessUntil} {formatDate(sub.current_period_end, regionConfig.region)}
                </p>
                {isStripe && (
                  <button
                    onClick={handlePortal}
                    className="px-4 py-2 text-sm border border-border-subtle hover:border-cream-muted rounded-full text-cream-muted hover:text-cream transition-colors"
                  >
                    {t.manageSub}
                  </button>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-cream-dim text-sm">
              {t.noSub}
            </p>
            <button
              onClick={() => navigate("/pricing")}
              className="px-5 py-2.5 bg-cream text-[#0C0C0C] hover:bg-cream-dim font-medium rounded-full text-sm transition-colors"
            >
              {t.choosePlan}
            </button>
          </div>
        )}

        {message && (
          <div className="mt-4 p-3 rounded-xl bg-surface-light text-sm text-cream-dim">
            {message}
          </div>
        )}
      </div>

      {/* Payment history */}
      {payments.length > 0 && (
        <div className="bg-surface border border-border-subtle rounded-2xl p-6">
          <h3 className="text-base font-semibold text-cream mb-4">
            {t.paymentHistory}
          </h3>
          <div className="space-y-3">
            {payments.slice(0, 10).map((p) => {
              const st = t.paymentStatus[p.status] || {
                label: p.status,
                color: "text-cream-muted",
              };
              return (
                <div
                  key={p.id}
                  className="flex items-center justify-between py-2 border-b border-border-subtle last:border-0"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-cream truncate">
                      {p.description || t.defaultPaymentDesc}
                    </p>
                    <p className="text-xs text-cream-muted">
                      {formatDate(p.paid_at || p.created_at, regionConfig.region)}
                    </p>
                  </div>
                  <div className="text-right shrink-0 ml-4">
                    <p className="text-sm text-cream">
                      {p.payment_provider === "admin"
                        ? (regionConfig.region === "ru" ? "0 ₽" : "€0")
                        : formatAmount(p.amount_kopecks, p.currency)}
                    </p>
                    <p className={`text-xs ${st.color}`}>{st.label}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
