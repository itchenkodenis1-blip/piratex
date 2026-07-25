import { useEffect, useState, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { AuthUser } from "../types";
import { useTranslation } from "../i18n";
import { useRegion } from "../region";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { CookieConsentBanner } from "./CookieConsentBanner";

const AVATAR_GRADIENTS = [
  "linear-gradient(135deg, #6366f1, #8b5cf6)",
  "linear-gradient(135deg, #ec4899, #f43f5e)",
  "linear-gradient(135deg, #14b8a6, #06b6d4)",
  "linear-gradient(135deg, #f59e0b, #ef4444)",
  "linear-gradient(135deg, #8b5cf6, #ec4899)",
  "linear-gradient(135deg, #06b6d4, #3b82f6)",
];

function getUserInitial(user: AuthUser): string {
  if (user.name) return user.name[0].toUpperCase();
  if (user.email) return user.email[0].toUpperCase();
  return "U";
}

function getUserGradient(user: AuthUser): string {
  const key = user.email || user.id || "";
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = key.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_GRADIENTS[Math.abs(hash) % AVATAR_GRADIENTS.length];
}

function maskEmail(email: string): string {
  const [local, domain] = email.split("@");
  if (!domain) return email;
  const visible = local.slice(0, 3);
  return `${visible}***@${domain}`;
}

interface Props {
  user: AuthUser | null;
  logout: () => void;
  onLoginClick?: () => void;
  children: React.ReactNode;
  showOnboardingBanner?: boolean;
  onOnboardingBannerClick?: () => void;
  onOnboardingBannerDismiss?: () => void;
}

export function AppLayout({ user, logout, onLoginClick, children, showOnboardingBanner, onOnboardingBannerClick, onOnboardingBannerDismiss }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const regionConfig = useRegion();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const isTrends = location.pathname.startsWith("/trends");
  const isMyVideos = location.pathname.startsWith("/my-videos");
  const isPricing = location.pathname === "/pricing";
  const isSettings = location.pathname === "/settings";
  const isAdmin = location.pathname.startsWith("/admin");

  const isAnonymous = !user || user.is_anonymous;

  const avatarInitial = useMemo(() => user && !user.is_anonymous ? getUserInitial(user) : "", [user]);
  const avatarGradient = useMemo(() => user && !user.is_anonymous ? getUserGradient(user) : "", [user]);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-[#0C0C0C] text-cream" style={{ paddingTop: 'env(safe-area-inset-top)' }}>
      {/* Header */}
      <header className="border-b border-border-subtle px-4 sm:px-6 md:px-8 py-3 sm:py-5">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          {/* Logo — always visible */}
          <div
            className="flex items-center gap-3 cursor-pointer group"
            onClick={() => navigate("/")}
          >
            <img src="/logo.png" alt={regionConfig.brand} className="h-8 w-8" />
            <h1 className="text-lg font-serif font-medium text-cream group-hover:text-cream-dim transition-colors">
              {regionConfig.brand}
            </h1>
          </div>

          {/* Desktop navigation */}
          <div className="hidden md:flex items-center gap-10">
            <nav className="flex items-center gap-6">
              <button
                onClick={() => navigate("/")}
                className={`text-sm transition-colors ${
                  !isTrends && !isMyVideos && !isPricing && !isSettings
                    ? "text-cream"
                    : "text-cream-muted hover:text-cream"
                }`}
              >
                {t.nav_analysis}
              </button>
              {!isAnonymous && (
                <button
                  onClick={() => navigate("/my-videos")}
                  className={`text-sm transition-colors ${
                    isMyVideos
                      ? "text-cream"
                      : "text-cream-muted hover:text-cream"
                  }`}
                >
                  {t.nav_my_videos}
                </button>
              )}
              <button
                onClick={() => navigate("/trends")}
                className={`text-sm transition-colors ${
                  isTrends
                    ? "text-cream"
                    : "text-cream-muted hover:text-cream"
                }`}
              >
                {t.nav_trends}
              </button>
            </nav>
          </div>

          {/* Desktop right side */}
          <div className="hidden md:flex items-center gap-5">
            <LanguageSwitcher />
            <button
              onClick={() => navigate("/pricing")}
              className={`text-sm transition-colors ${
                isPricing
                  ? "text-cream"
                  : "text-cream-muted hover:text-cream"
              }`}
            >
              {t.nav_pricing}
            </button>
            {isAnonymous ? (
              <button
                onClick={onLoginClick}
                className="text-sm px-4 py-1.5 border border-border-subtle rounded-full text-cream-dim hover:text-cream hover:border-cream-muted transition-colors"
              >
                {t.nav_login}
              </button>
            ) : (
              <>
                {user?.is_admin && (
                  <button
                    onClick={() => navigate("/shooting-queue")}
                    className={`transition-colors ${location.pathname === "/shooting-queue" ? "text-amber-300" : "text-cream-muted hover:text-cream"}`}
                    title="Очередь съёмки"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><polyline points="17 2 12 7 7 2"/></svg>
                  </button>
                )}
                {user?.is_admin && (
                  <button
                    onClick={() => navigate("/admin")}
                    className={`transition-colors ${isAdmin ? "text-cream" : "text-cream-muted hover:text-cream"}`}
                    title="Admin"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                  </button>
                )}
                <button
                  onClick={() => navigate("/settings")}
                  className={`w-[30px] h-[30px] rounded-full flex items-center justify-center text-[13px] font-semibold text-white transition-all hover:opacity-80 ${isSettings ? "ring-2 ring-cream/60" : ""}`}
                  style={{ background: avatarGradient }}
                  title={user?.email ? `${maskEmail(user.email)} · ${t.nav_settings}` : t.nav_settings}
                >
                  {avatarInitial}
                </button>
              </>
            )}
          </div>

          {/* Mobile inline nav + hamburger */}
          <div className="md:hidden flex items-center gap-1">
            {!isAnonymous && (
              <button
                onClick={() => navigate("/my-videos")}
                className={`text-xs px-2.5 py-1.5 rounded-full transition-colors ${
                  isMyVideos
                    ? "text-cream bg-surface-light"
                    : "text-cream-muted hover:text-cream"
                }`}
              >
                {t.nav_my_videos}
              </button>
            )}
            <button
              onClick={() => navigate("/trends")}
              className={`text-xs px-2.5 py-1.5 rounded-full transition-colors ${
                isTrends
                  ? "text-cream bg-surface-light"
                  : "text-cream-muted hover:text-cream"
              }`}
            >
              {t.nav_trends}
            </button>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 -mr-2 text-cream-muted hover:text-cream transition-colors"
              aria-label="Menu"
            >
              {mobileMenuOpen ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 12h18M3 6h18M3 18h18" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Mobile menu panel — animated */}
        <div
          className={`md:hidden overflow-hidden transition-all duration-300 ease-out max-w-6xl mx-auto ${
            mobileMenuOpen ? "max-h-[400px] opacity-100 mt-3 pt-3 pb-1 border-t border-border-subtle" : "max-h-0 opacity-0"
          }`}
        >
          <nav className="flex flex-col gap-1">
            <button
              onClick={() => navigate("/pricing")}
              className={`text-left text-sm py-2.5 px-3 rounded-lg transition-colors ${
                isPricing
                  ? "text-cream bg-surface-light"
                  : "text-cream-muted hover:text-cream hover:bg-surface-light/50"
              }`}
            >
              {t.nav_pricing}
            </button>
          </nav>
          <div className="mt-3 pt-3 border-t border-border-subtle">
            {isAnonymous ? (
              <div className="flex items-center justify-between">
                <LanguageSwitcher />
                <button
                  onClick={onLoginClick}
                  className="text-sm px-4 py-2 border border-border-subtle rounded-full text-cream-dim hover:text-cream hover:border-cream-muted transition-colors"
                >
                  {t.nav_login}
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <div
                  className="flex items-center gap-3 cursor-pointer"
                  onClick={() => navigate("/settings")}
                >
                  <div
                    className="w-9 h-9 rounded-full flex items-center justify-center text-[15px] font-semibold text-white shrink-0"
                    style={{ background: avatarGradient }}
                  >
                    {avatarInitial}
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm text-cream truncate">
                      {user?.email ? maskEmail(user.email) : t.nav_settings}
                    </div>
                    <div className="text-xs text-cream-muted mt-0.5">
                      {user?.tier || "FREE"}
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <LanguageSwitcher />
                  <div className="flex items-center gap-3">
                    {user?.is_admin && (
                      <button
                        onClick={() => { navigate("/shooting-queue"); setMobileMenuOpen(false); }}
                        className={`transition-colors ${location.pathname === "/shooting-queue" ? "text-amber-300" : "text-cream-muted hover:text-cream"}`}
                        title="Очередь съёмки"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><polyline points="17 2 12 7 7 2"/></svg>
                      </button>
                    )}
                    {user?.is_admin && (
                      <button
                        onClick={() => navigate("/admin")}
                        className={`transition-colors ${isAdmin ? "text-cream" : "text-cream-muted hover:text-cream"}`}
                        title="Admin"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                      </button>
                    )}
                    <button
                      onClick={() => navigate("/settings")}
                      className="text-sm text-cream-muted hover:text-cream transition-colors"
                    >
                      {t.nav_settings}
                    </button>
                    <button
                      onClick={logout}
                      className="text-sm text-cream-muted hover:text-red-400 transition-colors"
                    >
                      {t.nav_logout}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Telegram banner for REGISTERED users — smart: bot first, then subscription */}
      {user && !user.is_anonymous && user.tier === "REGISTERED" && (
        !user.telegram_user_id ? (
          <div
            className="bg-[#2AABEE]/10 border-b border-[#2AABEE]/20 px-4 sm:px-8 py-2.5 text-center cursor-pointer hover:bg-[#2AABEE]/15 transition-colors"
            onClick={() => navigate("/settings")}
          >
            <span className="text-sm text-[#2AABEE]">
              {t.tg_promo_banner_no_bot} →
            </span>
          </div>
        ) : !user.telegram_subscribed ? (
          <div
            className="bg-violet-900/20 border-b border-violet-800/30 px-4 sm:px-8 py-2.5 text-center cursor-pointer hover:bg-violet-900/30 transition-colors"
            onClick={() => navigate("/settings")}
          >
            <span className="text-sm text-violet-300">
              {t.usage_telegram_required}
            </span>
          </div>
        ) : null
      )}

      {/* Payment failed banner — past_due subscription */}
      {user && user.subscription_status === "past_due" && (
        <div className="bg-amber-900/20 border-b border-amber-800/30 px-4 sm:px-8 py-2.5">
          <div className="max-w-6xl mx-auto flex items-center justify-center gap-2 sm:gap-3">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-amber-400 shrink-0"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <span className="text-sm text-amber-300">
              {t.payment_failed_banner}
            </span>
            <button
              onClick={() => navigate("/settings")}
              className="text-xs px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 transition-colors shrink-0"
            >
              {t.payment_failed_banner_btn}
            </button>
          </div>
        </div>
      )}

      {/* Onboarding profile nudge banner */}
      {showOnboardingBanner && (
        <div className="bg-amber-900/20 border-b border-amber-800/30 px-4 sm:px-8 py-2.5">
          <div className="max-w-6xl mx-auto flex items-center justify-center gap-3">
            <span
              className="text-sm text-amber-300 cursor-pointer hover:text-amber-200 transition-colors"
              onClick={onOnboardingBannerClick}
            >
              {t.onboarding_banner}
            </span>
            <button
              onClick={onOnboardingBannerDismiss}
              className="text-amber-500/60 hover:text-amber-300 transition-colors text-lg leading-none"
              aria-label={t.modal_close}
            >
              &times;
            </button>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="px-4 sm:px-6 md:px-8 py-5 sm:py-12 md:py-16 max-w-6xl mx-auto">{children}</main>

      {/* Footer with legal entity */}
      <footer className="border-t border-border-subtle px-4 sm:px-8 py-6" style={{ paddingBottom: 'max(env(safe-area-inset-bottom), 1.5rem)' }}>
        <div className="max-w-6xl mx-auto flex flex-col items-center gap-2 text-xs text-cream-muted">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-2 w-full">
            <span>&copy; {new Date().getFullYear()} {regionConfig.legalEntity}</span>
            <div className="flex items-center gap-1 flex-wrap justify-center">
              <button onClick={() => navigate("/pricing")} className="py-2 px-2 hover:text-cream transition-colors">{t.nav_pricing}</button>
              <a href={regionConfig.termsUrl} className="py-2 px-2 hover:text-cream transition-colors">{t.footer_terms}</a>
              <a href={regionConfig.privacyUrl} className="py-2 px-2 hover:text-cream transition-colors">{t.footer_privacy}</a>
              <a href={regionConfig.refundUrl} className="py-2 px-2 hover:text-cream transition-colors">{t.footer_refund}</a>
              <a href={regionConfig.cookiePolicyUrl} className="py-2 px-2 hover:text-cream transition-colors">{t.footer_cookies}</a>
              <a href={`mailto:${regionConfig.supportEmail}`} className="py-2 px-2 hover:text-cream transition-colors">{regionConfig.supportEmail}</a>
            </div>
          </div>
          {t.footer_meta_disclaimer && (
            <p className="text-[10px] text-cream-muted/60 text-center max-w-xl leading-relaxed">{t.footer_meta_disclaimer}</p>
          )}
        </div>
      </footer>

      {/* Cookie consent banner */}
      <CookieConsentBanner />
    </div>
  );
}
