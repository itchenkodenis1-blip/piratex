import { useCallback, useEffect, useState } from "react";
import {
  createCheckout,
  getPaymentProviders,
  getPricing,
  validatePromoCode,
} from "../api/client";
import type { AuthUser, FeatureItem, PaymentProviderInfo, PricingTier } from "../types";
import { useRegion } from "../region";
import type { Region, RegionConfig } from "../region";

interface PricingPageProps {
  user: AuthUser | null;
  onLoginClick: () => void;
}

/* ------------------------------------------------------------------ */
/* Region-aware text                                                   */
/* ------------------------------------------------------------------ */

const TEXT: Record<Region, {
  title: string;
  subtitle: string;
  monthly: string;
  yearly: string;
  perMonth: string;
  perYear: string;
  select: string;
  currentPlan: string;
  redirecting: string;
  popularBadge: string;
  autoRenewalConsent: string;
  autoRenewalNote: string;
  roiManualCost: string;
  roiManualDesc: string;
  roiPiratexCost: string;
  roiPiratexDesc: string;
  unlimitedFootnote: string;
  faqTitle: string;
  earlyBirdTitle: string;
  earlyBirdSubtitle: string;
  promoPlaceholder: string;
  promoApply: string;
  promoRemove: string;
  promoApplied: string;
  promoRemaining: string;
  promoInvalid: string;
  promoCheckError: string;
  providerTitle: string;
  providerCancel: string;
  loadError: string;
  checkoutError: string;
  tierBadges: Record<string, string>;
  promoErrors: Record<string, string>;
  faq: { q: string; a: string }[];
}> = {
  ru: {
    title: "Тарифы",
    subtitle: "Готовые сценарии для рилсов — быстрее и дешевле, чем писать вручную",
    monthly: "Ежемесячно",
    yearly: "Ежегодно",
    perMonth: "/мес",
    perYear: "/год",
    select: "Выбрать",
    currentPlan: "Текущий тариф",
    redirecting: "Переход к оплате...",
    popularBadge: "Популярный",
    autoRenewalConsent: "Я соглашаюсь на автоматическое продление подписки и списание средств. Отменить можно в любой момент в настройках.",
    autoRenewalNote: "Подписка продлевается автоматически. Отменить — в настройках аккаунта.",
    roiManualCost: "Написать сценарий вручную ≈ 2 000₽",
    roiManualDesc: "Посмотреть рилс → разобрать структуру → адаптировать под себя → 2 часа работы",
    roiPiratexCost: "С ВидеоРентгеном — от 33₽ за сценарий",
    roiPiratexDesc: "В 60 раз дешевле. Попробуйте бесплатно — 3 сценария без оплаты.",
    unlimitedFootnote: "* 300 сценариев на полной скорости, далее без ограничения по месяцу",
    faqTitle: "Частые вопросы",
    earlyBirdTitle: "Ранний доступ — скидка 30% на первые 3 месяца",
    earlyBirdSubtitle: "Введите промокод EARLYBIRD30 при оплате. Первые 200 подписчиков.",
    promoPlaceholder: "Промокод",
    promoApply: "Применить",
    promoRemove: "Убрать",
    promoApplied: "применён",
    promoRemaining: "осталось {n} активаций",
    promoInvalid: "Промокод недействителен",
    promoCheckError: "Ошибка проверки промокода",
    providerTitle: "Какой картой оплачиваете?",
    providerCancel: "Отмена",
    loadError: "Не удалось загрузить тарифы",
    checkoutError: "Ошибка создания платежа",
    tierBadges: { START: "Старт", PRO: "Популярный", UNLIMITED: "Максимум" },
    promoErrors: {
      invalid_code: "Промокод не найден",
      not_started: "Промокод ещё не активен",
      expired: "Промокод истёк",
      exhausted: "Промокод больше не действует",
      invalid_tier: "Промокод не действует для этого тарифа",
      invalid_interval: "Промокод не действует для этого периода",
      already_used: "Вы уже использовали этот промокод",
    },
    faq: [
      { q: "Могу ли я сменить тариф?", a: "Да, вы можете повысить тариф в любой момент. Новый тариф активируется сразу после оплаты." },
      { q: "Как отменить подписку?", a: "В настройках аккаунта → Подписка → Отменить. Доступ сохранится до конца оплаченного периода." },
      { q: "Какие способы оплаты поддерживаются?", a: "Банковские карты (Visa, Mastercard, МИР), СБП, ЮMoney." },
      { q: "Что значит «безлимит» на тарифе «Максимум»?", a: "Первые 300 сценариев в месяц выполняются на полной скорости (до 10 одновременно). Далее — до 15 сценариев в день без ограничения по месяцу." },
      { q: "Есть ли скидки?", a: "Да! При оплате за год вы получаете скидку 25%. Также следите за промоакциями — мы регулярно выпускаем промокоды для новых пользователей." },
      { q: "Как работает автопродление?", a: "Подписка продлевается автоматически в конце каждого оплаченного периода. За 3 дня до списания мы отправляем уведомление. Вы можете отменить подписку или удалить карту в настройках в любой момент — доступ сохранится до конца оплаченного периода." },
    ],
  },
  int: {
    title: "Pricing",
    subtitle: "Ready-made scripts for reels — faster and cheaper than writing them yourself",
    monthly: "Monthly",
    yearly: "Yearly",
    perMonth: "/mo",
    perYear: "/yr",
    select: "Select",
    currentPlan: "Current plan",
    redirecting: "Redirecting to payment...",
    popularBadge: "Popular",
    autoRenewalConsent: "I agree to automatic subscription renewal and recurring charges. You can cancel anytime in settings.",
    autoRenewalNote: "Subscription auto-renews. Cancel anytime in account settings.",
    roiManualCost: "Writing a script manually ≈ €20",
    roiManualDesc: "Watch the reel → break down the structure → adapt for yourself → 2 hours of work",
    roiPiratexCost: "With VideoRentgen — from €0.33 per script",
    roiPiratexDesc: "60x cheaper. Try free — 3 scripts at no cost.",
    unlimitedFootnote: "* 300 scripts at full speed, then unlimited with no monthly cap",
    faqTitle: "FAQ",
    earlyBirdTitle: "Early Bird — 30% off for the first 3 months",
    earlyBirdSubtitle: "Enter promo code EARLYBIRD30 at checkout. First 200 subscribers.",
    promoPlaceholder: "Promo code",
    promoApply: "Apply",
    promoRemove: "Remove",
    promoApplied: "applied",
    promoRemaining: "{n} uses remaining",
    promoInvalid: "Invalid promo code",
    promoCheckError: "Error validating promo code",
    providerTitle: "Payment method",
    providerCancel: "Cancel",
    loadError: "Failed to load pricing",
    checkoutError: "Payment error",
    tierBadges: { START: "Start", PRO: "Popular", UNLIMITED: "Unlimited" },
    promoErrors: {
      invalid_code: "Promo code not found",
      not_started: "Promo code not yet active",
      expired: "Promo code expired",
      exhausted: "Promo code no longer valid",
      invalid_tier: "Promo code not valid for this plan",
      invalid_interval: "Promo code not valid for this period",
      already_used: "You have already used this promo code",
    },
    faq: [
      { q: "Can I change my plan?", a: "Yes, you can upgrade at any time. Your new plan activates immediately after payment." },
      { q: "How do I cancel?", a: "Go to Settings → Subscription → Cancel. Access continues until the end of your paid period." },
      { q: "What payment methods are supported?", a: "Visa, Mastercard, and other international cards via Stripe." },
      { q: "What does 'Unlimited' mean?", a: "First 300 scripts per month run at full speed (up to 10 simultaneously). After that — up to 15 scripts per day with no monthly cap." },
      { q: "Are there discounts?", a: "Yes! Pay annually and save 25%. We also regularly release promo codes for new users." },
      { q: "How does auto-renewal work?", a: "Your subscription renews automatically at the end of each paid period. We send a reminder 3 days before the charge. You can cancel or remove your card in settings at any time — access continues until the end of your paid period." },
    ],
  },
};

const PROVIDER_ICONS: Record<string, string> = {
  cloudpayments: "🇷🇺",
  yookassa: "🇷🇺",
  stripe: "🌍",
};

const PROVIDER_LABELS: Record<string, Record<string, string>> = {
  cloudpayments: { ru: "Картой РФ", int: "Russian card" },
  yookassa: { ru: "Картой РФ (ЮКасса)", int: "Russian card (YooKassa)" },
  stripe: { ru: "Зарубежной картой", int: "International card" },
};

const PROVIDER_DESCRIPTIONS: Record<string, Record<string, string>> = {
  cloudpayments: { ru: "Visa, Mastercard, МИР, СБП, Tinkoff Pay", int: "Visa, Mastercard, MIR, SBP, Tinkoff Pay" },
  yookassa: { ru: "Visa, Mastercard, МИР, СБП, ЮMoney", int: "Visa, Mastercard, MIR, SBP, YooMoney" },
  stripe: { ru: "Visa, Mastercard (не РФ)", int: "Visa, Mastercard" },
};

function formatPrice(price: number, region: Region): string {
  return region === "ru"
    ? price.toLocaleString("ru-RU")
    : price.toLocaleString("en-US");
}

/* ------------------------------------------------------------------ */
/* Provider selection modal                                           */
/* ------------------------------------------------------------------ */

function ProviderModal({
  providers,
  onSelect,
  onClose,
  loading,
  region,
  text,
  orderSummary,
  userEmail,
}: {
  providers: PaymentProviderInfo[];
  onSelect: (provider: string, email?: string) => void;
  onClose: () => void;
  loading: boolean;
  region: Region;
  text: typeof TEXT["ru"];
  orderSummary?: { tierName: string; price: string; interval: string } | null;
  userEmail?: string | null;
}) {
  const [consent, setConsent] = useState(false);
  const [email, setEmail] = useState("");
  const needsEmail = !userEmail?.trim();
  const emailValid = !needsEmail || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-sm rounded-2xl bg-surface border border-border-subtle p-6 shadow-2xl">
        <h3 className="text-lg font-semibold text-cream mb-5 text-center">
          {text.providerTitle}
        </h3>

        {/* Order summary */}
        {orderSummary && (
          <div className="mb-4 p-3 rounded-xl bg-surface-light/50 border border-border-subtle text-sm">
            <div className="flex justify-between text-cream-dim">
              <span>{orderSummary.tierName}</span>
              <span className="font-medium text-cream">{orderSummary.price}{orderSummary.interval}</span>
            </div>
          </div>
        )}

        {/* Auto-renewal consent checkbox (376-ФЗ, 69-ФЗ) */}
        <label className="flex items-start gap-3 mb-5 p-3 rounded-xl border border-border-subtle bg-surface-light/50 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            className="mt-0.5 shrink-0 w-4 h-4 accent-cream rounded"
          />
          <span className="text-xs text-cream-dim leading-relaxed">
            {text.autoRenewalConsent}{" "}
            <a href="/terms" className="underline text-cream-muted hover:text-cream" onClick={(e) => e.stopPropagation()}>
              {region === "ru" ? "Условия" : "Terms"}
            </a>
          </span>
        </label>

        {/* Email input — shown when user has no email */}
        {needsEmail && (
          <div className="mb-4">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={region === "ru" ? "Email для уведомлений о списаниях" : "Email for billing notifications"}
              className="w-full px-4 py-2.5 bg-surface border border-border-subtle rounded-xl
                text-sm text-cream placeholder:text-cream-muted/50
                focus:outline-none focus:border-cream/30 transition-colors"
            />
          </div>
        )}

        <div className="space-y-3">
          {providers.map((p) => (
            <button
              key={p.name}
              onClick={() => onSelect(p.name, needsEmail ? email : undefined)}
              disabled={loading || !consent || !emailValid}
              className="w-full flex items-center gap-4 p-4 rounded-xl border border-border-subtle
                hover:border-cream/30 hover:bg-surface-light transition-colors
                disabled:opacity-50 disabled:cursor-not-allowed text-left"
            >
              <div className="w-10 h-10 rounded-full bg-surface-light border border-border-subtle flex items-center justify-center shrink-0">
                <span className="text-sm font-bold text-cream">
                  {PROVIDER_ICONS[p.name] || p.display_name[0]}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-cream">
                  {PROVIDER_LABELS[p.name]?.[region] || p.display_name}
                </p>
                <p className="text-xs text-cream-muted truncate">
                  {PROVIDER_DESCRIPTIONS[p.name]?.[region] || ""}
                </p>
              </div>
            </button>
          ))}
        </div>
        <button
          onClick={onClose}
          className="mt-4 w-full py-2.5 text-sm text-cream-muted hover:text-cream transition-colors"
        >
          {text.providerCancel}
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Tier card                                                          */
/* ------------------------------------------------------------------ */

function TierCard({
  tier,
  isYearly,
  currentTier,
  onSelect,
  loading,
  discountPercent,
  regionConfig,
  text,
}: {
  tier: PricingTier;
  isYearly: boolean;
  currentTier: string | null;
  onSelect: (tier: string) => void;
  loading: string | null;
  discountPercent: number | null;
  regionConfig: RegionConfig;
  text: typeof TEXT["ru"];
}) {
  const basePrice = isYearly
    ? Math.round(tier.price_yearly / 12)
    : tier.price_monthly;
  const price = discountPercent
    ? Math.round(basePrice * (1 - discountPercent / 100))
    : basePrice;
  const isCurrent = currentTier === tier.tier;
  const isPopular = tier.popular;
  const region = regionConfig.region;

  return (
    <div
      className={`relative flex flex-col rounded-2xl border p-6 sm:p-8 transition-all ${
        isPopular
          ? "border-cream/30 bg-surface-light shadow-[0_0_40px_rgba(235,235,235,0.04)]"
          : "border-border-subtle bg-surface"
      }`}
    >
      {isPopular && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-cream text-[#0C0C0C] text-xs font-semibold rounded-full">
          {text.popularBadge}
        </div>
      )}

      <div className="mb-6">
        <h3 className="text-lg font-semibold text-cream">
          {text.tierBadges[tier.tier] || tier.name}
        </h3>
      </div>

      <div className="mb-6">
        <div className="flex items-baseline gap-1">
          <span className="text-4xl font-serif font-bold text-cream">
            {regionConfig.currencySymbol}{formatPrice(price, region)}
          </span>
          <span className="text-cream-muted text-sm">{text.perMonth}</span>
        </div>
        {discountPercent ? (
          <p className="text-xs mt-1">
            <span className="text-cream-muted line-through mr-2">
              {regionConfig.currencySymbol}{formatPrice(basePrice, region)}
            </span>
            <span className="text-green-400 font-medium">
              -{discountPercent}%
            </span>
          </p>
        ) : isYearly ? (
          <p className="text-cream-muted text-xs mt-1">
            {regionConfig.currencySymbol}{formatPrice(tier.price_yearly, region)}{text.perYear}
          </p>
        ) : null}
      </div>

      <ul className="space-y-3 mb-8 flex-1">
        {tier.features.map((feature: FeatureItem, i: number) => (
          <li
            key={i}
            className={`flex items-start gap-2 text-sm ${
              feature.style === "highlight"
                ? "text-cream font-medium"
                : feature.style === "disabled"
                  ? "text-cream-muted/40 line-through"
                  : "text-cream-dim"
            }`}
          >
            <span
              className={`mt-0.5 shrink-0 ${
                feature.style === "disabled" ? "text-cream-muted/40" : "text-cream"
              }`}
            >
              {feature.style === "disabled" ? "—" : "\u2713"}
            </span>
            {feature.text}
          </li>
        ))}
      </ul>

      <button
        onClick={() => onSelect(tier.tier)}
        disabled={isCurrent || loading !== null}
        className={`w-full py-3 rounded-full font-medium text-sm transition-colors ${
          isCurrent
            ? "bg-surface-light text-cream-muted border border-border-subtle cursor-default"
            : isPopular
              ? "bg-cream text-[#0C0C0C] hover:bg-cream-dim"
              : "border border-cream/20 text-cream hover:bg-surface-light"
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        {loading === tier.tier
          ? text.redirecting
          : isCurrent
            ? text.currentPlan
            : text.select}
      </button>

      {!isCurrent && (
        <p className="mt-3 text-[11px] text-cream-muted/50 text-center leading-relaxed">
          {text.autoRenewalNote}
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main page                                                          */
/* ------------------------------------------------------------------ */

export function PricingPage({ user, onLoginClick }: PricingPageProps) {
  const regionConfig = useRegion();
  const text = TEXT[regionConfig.region];

  const [tiers, setTiers] = useState<PricingTier[]>([]);
  const [providers, setProviders] = useState<PaymentProviderInfo[]>([]);
  const [isYearly, setIsYearly] = useState(false);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Provider modal
  const [pendingTier, setPendingTier] = useState<string | null>(null);

  // Promo code state
  const [promoInput, setPromoInput] = useState("");
  const [promoApplied, setPromoApplied] = useState<{
    code: string;
    discount_percent: number;
    remaining_uses: number | null;
  } | null>(null);
  const [promoError, setPromoError] = useState<string | null>(null);
  const [promoLoading, setPromoLoading] = useState(false);

  useEffect(() => {
    getPricing(regionConfig.currency)
      .then((res) => setTiers(res.tiers))
      .catch(() => setError(text.loadError));

    getPaymentProviders()
      .then(setProviders)
      .catch(() => {});
  }, [regionConfig.currency, text.loadError]);

  const handleApplyPromo = useCallback(async () => {
    const code = promoInput.trim();
    if (!code) return;
    if (!user || user.is_anonymous) {
      onLoginClick();
      return;
    }

    setPromoLoading(true);
    setPromoError(null);

    try {
      const res = await validatePromoCode(code);
      if (res.valid && res.discount_percent) {
        setPromoApplied({
          code: code.toUpperCase(),
          discount_percent: res.discount_percent,
          remaining_uses: res.remaining_uses ?? null,
        });
        setPromoError(null);
      } else {
        setPromoError(
          text.promoErrors[res.error || ""] || text.promoInvalid
        );
        setPromoApplied(null);
      }
    } catch {
      setPromoError(text.promoCheckError);
      setPromoApplied(null);
    } finally {
      setPromoLoading(false);
    }
  }, [promoInput, user, onLoginClick, text]);

  // Actual checkout call — auto-select provider based on region
  const doCheckout = useCallback(
    async (tier: string, provider: string, email?: string) => {
      setPendingTier(null);
      setLoading(tier);
      setError(null);

      try {
        const interval = isYearly ? "yearly" : "monthly";
        const res = await createCheckout(
          tier,
          interval,
          promoApplied?.code,
          provider,
          email,
        );

        // CloudPayments: open JS widget instead of redirect
        if (res.provider === "cloudpayments") {
          try {
            const widgetParams = JSON.parse(res.payment_url);
            const widget = new cp.CloudPayments();
            widget.pay("charge", {
              publicId: widgetParams.publicId,
              description: widgetParams.description,
              amount: widgetParams.amount,
              currency: widgetParams.currency,
              accountId: widgetParams.accountId,
              invoiceId: widgetParams.invoiceId,
              email: widgetParams.email,
              skin: "mini",
              data: widgetParams.data,
            }, {
              onSuccess: () => {
                window.location.href = "/checkout/success";
              },
              onFail: (reason) => {
                setError(reason || text.checkoutError);
                setLoading(null);
              },
              onComplete: () => {
                setLoading(null);
              },
            });
          } catch {
            setError(text.checkoutError);
            setLoading(null);
          }
          return;
        }

        // Other providers: redirect to hosted checkout page
        window.location.href = res.payment_url;
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : text.checkoutError;
        setError(msg);
        setLoading(null);
      }
    },
    [isYearly, promoApplied, text.checkoutError]
  );

  // Called when user clicks "Select" on a tier card
  const handleSelect = useCallback(
    (tier: string) => {
      if (!user || user.is_anonymous) {
        onLoginClick();
        return;
      }

      // Always show provider modal with consent checkbox (376-ФЗ compliance)
      setPendingTier(tier);
    },
    [user, onLoginClick]
  );

  const currentTier = user?.tier || null;

  return (
    <div className="max-w-4xl mx-auto">
      <div className="text-center mb-10">
        <h1 className="text-3xl sm:text-4xl font-serif font-bold text-cream mb-3">
          {text.title}
        </h1>
        <p className="text-cream-dim text-base max-w-lg mx-auto">
          {text.subtitle}
        </p>
      </div>

      {/* Interval toggle */}
      <div className="flex items-center justify-center gap-3 mb-8">
        <button
          onClick={() => setIsYearly(false)}
          className={`px-4 py-2.5 sm:py-2 rounded-full text-sm font-medium transition-colors ${
            !isYearly
              ? "bg-cream text-[#0C0C0C]"
              : "text-cream-muted hover:text-cream"
          }`}
        >
          {text.monthly}
        </button>
        <button
          onClick={() => setIsYearly(true)}
          className={`px-4 py-2.5 sm:py-2 rounded-full text-sm font-medium transition-colors flex items-center gap-2 ${
            isYearly
              ? "bg-cream text-[#0C0C0C]"
              : "text-cream-muted hover:text-cream"
          }`}
        >
          {text.yearly}
          <span
            className={`text-xs px-2 py-0.5 rounded-full ${
              isYearly
                ? "bg-[#0C0C0C]/10 text-[#0C0C0C]"
                : "bg-cream/10 text-cream"
            }`}
          >
            -25%
          </span>
        </button>
      </div>

      {/* Promo code input */}
      <div className="max-w-sm mx-auto mb-10">
        <div className="flex gap-2">
          <input
            type="text"
            value={promoInput}
            onChange={(e) => setPromoInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && handleApplyPromo()}
            placeholder={text.promoPlaceholder}
            disabled={promoLoading || !!promoApplied}
            className="flex-1 px-4 py-2.5 bg-surface border border-border-subtle rounded-xl
              text-sm text-cream placeholder:text-cream-muted/50
              focus:outline-none focus:border-cream/30 transition-colors
              disabled:opacity-50 font-mono tracking-wider"
          />
          {promoApplied ? (
            <button
              onClick={() => {
                setPromoApplied(null);
                setPromoInput("");
              }}
              className="px-4 py-2.5 text-sm text-cream-muted hover:text-cream
                border border-border-subtle rounded-xl transition-colors"
            >
              {text.promoRemove}
            </button>
          ) : (
            <button
              onClick={handleApplyPromo}
              disabled={promoLoading || !promoInput.trim()}
              className="px-5 py-2.5 text-sm font-medium bg-surface-light border border-border-subtle
                rounded-xl text-cream hover:bg-surface transition-colors
                disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {promoLoading ? "..." : text.promoApply}
            </button>
          )}
        </div>
        {promoError && (
          <p className="mt-2 text-xs text-red-400 text-center">{promoError}</p>
        )}
        {promoApplied && (
          <p className="mt-2 text-xs text-green-400 text-center">
            {promoApplied.code} {text.promoApplied}: -{promoApplied.discount_percent}%
            {promoApplied.remaining_uses !== null && (
              <span className="text-cream-muted ml-1">
                ({text.promoRemaining.replace("{n}", String(promoApplied.remaining_uses))})
              </span>
            )}
          </p>
        )}
      </div>

      {error && (
        <div className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm text-center">
          {error}
        </div>
      )}

      {/* Tier cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mt-4 md:mt-0">
        {tiers.map((tier) => (
          <TierCard
            key={tier.tier}
            tier={tier}
            isYearly={isYearly}
            currentTier={currentTier}
            onSelect={handleSelect}
            loading={loading}
            discountPercent={promoApplied?.discount_percent ?? null}
            regionConfig={regionConfig}
            text={text}
          />
        ))}
      </div>

      {/* Unlimited footnote */}
      {tiers.some((t) => t.tier === "UNLIMITED") && (
        <p className="mt-6 text-center text-cream-muted/60 text-xs">
          {text.unlimitedFootnote}
        </p>
      )}

      {/* ROI comparison block */}
      <div className="mt-10 max-w-xl mx-auto rounded-2xl border border-border-subtle bg-surface p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-8">
          <div className="flex-1">
            <p className="text-cream font-medium text-sm">{text.roiManualCost}</p>
            <p className="text-cream-muted text-xs mt-1">{text.roiManualDesc}</p>
          </div>
          <div className="hidden sm:block w-px h-12 bg-border-subtle" />
          <div className="flex-1">
            <p className="text-green-400 font-medium text-sm">{text.roiPiratexCost}</p>
            <p className="text-cream-muted text-xs mt-1">{text.roiPiratexDesc}</p>
          </div>
        </div>
      </div>

      {/* FAQ */}
      <div className="mt-16 max-w-2xl mx-auto">
        <h2 className="text-xl font-serif font-bold text-cream mb-6 text-center">
          {text.faqTitle}
        </h2>
        <div className="space-y-4">
          {text.faq.map((item, i) => (
            <FaqItem key={i} q={item.q} a={item.a} />
          ))}
        </div>
      </div>

      {/* Provider selection modal — RU users choose card type */}
      {pendingTier && (
        <ProviderModal
          providers={
            regionConfig.region === "ru"
              ? [
                  // Show CloudPayments if configured, otherwise fall back to YooKassa
                  ...(providers.some((p) => p.name === "cloudpayments")
                    ? [{ name: "cloudpayments", display_name: "CloudPayments", icon: "" }]
                    : providers.some((p) => p.name === "yookassa")
                      ? [{ name: "yookassa", display_name: "ЮKassa", icon: "" }]
                      : []),
                  ...(providers.some((p) => p.name === "stripe")
                    ? [{ name: "stripe", display_name: "Stripe", icon: "" }]
                    : []),
                ]
              : providers
          }
          onSelect={(provider, email) => doCheckout(pendingTier, provider, email)}
          onClose={() => setPendingTier(null)}
          loading={loading !== null}
          region={regionConfig.region}
          text={text}
          userEmail={user?.email}
          orderSummary={(() => {
            const tier = tiers.find((t) => t.tier === pendingTier);
            if (!tier) return null;
            const basePrice = isYearly ? Math.round(tier.price_yearly / 12) : tier.price_monthly;
            const price = promoApplied ? Math.round(basePrice * (1 - promoApplied.discount_percent / 100)) : basePrice;
            return {
              tierName: text.tierBadges[tier.tier] || tier.name,
              price: `${regionConfig.currencySymbol}${formatPrice(price, regionConfig.region)}`,
              interval: isYearly ? text.perMonth + ` (${regionConfig.currencySymbol}${formatPrice(isYearly ? (promoApplied ? Math.round(tier.price_yearly * (1 - promoApplied.discount_percent / 100)) : tier.price_yearly) : price, regionConfig.region)}${text.perYear})` : text.perMonth,
            };
          })()}
        />
      )}
    </div>
  );
}

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-border-subtle rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-surface-light transition-colors"
      >
        <span className="text-sm font-medium text-cream">{q}</span>
        <span className="text-cream-muted ml-4 shrink-0">
          {open ? "−" : "+"}
        </span>
      </button>
      {open && (
        <div className="px-4 pb-4 text-sm text-cream-dim">{a}</div>
      )}
    </div>
  );
}
