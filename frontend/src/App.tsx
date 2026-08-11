import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { HomePage } from "./components/HomePage";
import { AuthGateModal } from "./components/AuthGateModal";
import { YandexMetrika } from "./components/YandexMetrika";
import { useAuth } from "./hooks/useAuth";
import { useTranslation } from "./i18n";
import { getSettings } from "./api/client";
import type { SupportedLanguage } from "./i18n";
import { SUPPORTED_LANGUAGES } from "./i18n";

// Lazy-loaded route components
const CheckoutSuccess = lazy(() => import("./components/CheckoutSuccess").then(m => ({ default: m.CheckoutSuccess })));
const MyVideosPage = lazy(() => import("./components/MyVideosPage").then(m => ({ default: m.MyVideosPage })));
const PricingPage = lazy(() => import("./components/PricingPage").then(m => ({ default: m.PricingPage })));
const SettingsPage = lazy(() => import("./components/SettingsPage").then(m => ({ default: m.SettingsPage })));
const SharedScriptPage = lazy(() => import("./components/SharedScriptPage").then(m => ({ default: m.SharedScriptPage })));
const TrendsPage = lazy(() => import("./components/TrendsPage").then(m => ({ default: m.TrendsPage })));
const PipelinePage = lazy(() => import("./components/pipeline/PipelinePage").then(m => ({ default: m.PipelinePage })));
const LibraryReelDetailPage = lazy(() => import("./components/LibraryReelDetail").then(m => ({ default: m.LibraryReelDetailPage })));
const UpgradeModal = lazy(() => import("./components/UpgradeModal").then(m => ({ default: m.UpgradeModal })));
const AdminPage = lazy(() => import("./components/admin/AdminPage").then(m => ({ default: m.AdminPage })));
const AdminGuard = lazy(() => import("./components/admin/AdminGuard").then(m => ({ default: m.AdminGuard })));
const ShootingQueuePage = lazy(() => import("./components/ShootingQueuePage").then(m => ({ default: m.ShootingQueuePage })));
const ShowcaseDashboard = lazy(() => import("./components/admin/ShowcaseDashboard").then(m => ({ default: m.ShowcaseDashboard })));
const OnboardingModal = lazy(() => import("./components/OnboardingModal").then(m => ({ default: m.OnboardingModal })));
const AuthCallbackPage = lazy(() => import("./components/AuthCallbackPage").then(m => ({ default: m.AuthCallbackPage })));
const ChatWidget = lazy(() => import("./components/support/ChatWidget").then(m => ({ default: m.ChatWidget })));
const CancelConfirmPage = lazy(() => import("./components/CancelConfirmPage").then(m => ({ default: m.CancelConfirmPage })));
const RefundPolicyPage = lazy(() => import("./components/RefundPolicyPage").then(m => ({ default: m.RefundPolicyPage })));
const CookiePolicyPage = lazy(() => import("./components/CookiePolicyPage").then(m => ({ default: m.CookiePolicyPage })));
const TermsPage = lazy(() => import("./components/TermsPage").then(m => ({ default: m.TermsPage })));
const PrivacyPolicyPage = lazy(() => import("./components/PrivacyPolicyPage").then(m => ({ default: m.PrivacyPolicyPage })));

function LoadingFallback() {
  return (
    <div className="min-h-[50vh] flex items-center justify-center">
      <div className="text-zinc-500">Загрузка...</div>
    </div>
  );
}

function App() {
  const { user, usage, loading: authLoading, logout, refreshUser } = useAuth();
  const { t, setLang } = useTranslation();
  const location = useLocation();
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [authModalReason, setAuthModalReason] = useState<string | undefined>();
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [upgradeReason, setUpgradeReason] = useState<string | undefined>();
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [onboardingInitialStep, setOnboardingInitialStep] = useState<"choice" | "instagram" | "from_scratch">("choice");
  const [onboardingNeeded, setOnboardingNeeded] = useState(false);
  const [showOnboardingBanner, setShowOnboardingBanner] = useState(false);
  const onboardingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync language + track onboarding status (but don't show modal on load)
  useEffect(() => {
    if (user && !user.is_anonymous) {
      getSettings()
        .then((settings) => {
          if (
            settings.language &&
            (SUPPORTED_LANGUAGES as readonly string[]).includes(settings.language)
          ) {
            setLang(settings.language as SupportedLanguage);
          }
          if (!settings.onboarding_completed) {
            setOnboardingNeeded(true);
          } else {
            setOnboardingNeeded(false);
            setShowOnboardingBanner(false);
          }
        })
        .catch(() => {});
    }
  }, [user, setLang]);

  // Listen for job-completed events → show onboarding modal or banner
  useEffect(() => {
    const handler = () => {
      if (!onboardingNeeded) return;
      if (!user || user.is_anonymous) return;
      if (showOnboarding || showOnboardingBanner) return;

      const dismissCount = parseInt(localStorage.getItem("onboarding_dismiss_count") || "0", 10);
      if (dismissCount >= 3) return; // stop nagging after 3 dismissals

      if (dismissCount === 0) {
        // First time: show modal after delay so user sees results first
        onboardingTimerRef.current = setTimeout(() => setShowOnboarding(true), 3500);
      } else {
        // Previously skipped: show soft banner instead
        setShowOnboardingBanner(true);
      }
    };
    window.addEventListener("piratex:job-completed", handler);
    return () => {
      window.removeEventListener("piratex:job-completed", handler);
      if (onboardingTimerRef.current) clearTimeout(onboardingTimerRef.current);
    };
  }, [onboardingNeeded, user, showOnboarding, showOnboardingBanner]);

  // Listen for limit-reached events → open modal
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      const reason = typeof detail === "string" ? detail : detail?.detail;
      // For authenticated tiers at limit → show upgrade modal instead of auth gate
      if (user && !user.is_anonymous && ["REGISTERED", "FREE", "START", "PRO"].includes(user.tier)) {
        setUpgradeReason(reason);
        setShowUpgradeModal(true);
        return;
      }
      setAuthModalReason(reason || "anonymous_limit");
      setShowAuthModal(true);
    };
    window.addEventListener("piratex:limit-reached", handler);
    return () => window.removeEventListener("piratex:limit-reached", handler);
  }, [user]);

  // Open modal
  const openModal = useCallback((reason: string) => {
    setAuthModalReason(reason);
    setShowAuthModal(true);
  }, []);

  const handleLoginClick = useCallback(() => { openModal("login_click"); }, [openModal]);

  const handleModalSuccess = useCallback(() => {
    setShowAuthModal(false);
    refreshUser();
  }, [refreshUser]);

  const handleModalClose = useCallback(() => {
    setShowAuthModal(false);
  }, []);

  // Public routes — no auth required
  if (location.pathname.startsWith("/share/")) {
    return (
      <>
        <YandexMetrika />
        <Suspense fallback={<LoadingFallback />}>
          <Routes>
            <Route path="/share/:token" element={<SharedScriptPage />} />
          </Routes>
        </Suspense>
      </>
    );
  }

  // Showcase dashboard — full-screen cinematic view, admin-only
  if (location.pathname === "/showcase") {
    return (
      <Suspense fallback={<LoadingFallback />}>
        <Routes>
          <Route
            path="/showcase"
            element={
              <AdminGuard>
                <ShowcaseDashboard />
              </AdminGuard>
            }
          />
        </Routes>
      </Suspense>
    );
  }

  // Admin panel — own layout, own guard
  if (location.pathname.startsWith("/admin")) {
    return (
      <Suspense fallback={<LoadingFallback />}>
        <Routes>
          <Route
            path="/admin/*"
            element={
              <AdminGuard>
                <AdminPage />
              </AdminGuard>
            }
          />
        </Routes>
      </Suspense>
    );
  }

  if (authLoading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="text-zinc-500">{t.app_loading}</div>
      </div>
    );
  }

  return (
    <>
      <YandexMetrika />
      <AppLayout
        user={user}
        logout={logout}
        onLoginClick={handleLoginClick}
        showOnboardingBanner={showOnboardingBanner && !showOnboarding}
        onOnboardingBannerClick={() => {
          setShowOnboardingBanner(false);
          setShowOnboarding(true);
        }}
        onOnboardingBannerDismiss={() => {
          setShowOnboardingBanner(false);
          const count = parseInt(localStorage.getItem("onboarding_dismiss_count") || "0", 10);
          localStorage.setItem("onboarding_dismiss_count", String(count + 1));
        }}
      >
        <Suspense fallback={<LoadingFallback />}>
        <Routes>
          <Route
            path="/"
            element={
              <HomePage
                user={user}
                usage={usage}
                refreshUser={refreshUser}
              />
            }
          />
          <Route
            path="/my-videos"
            element={<MyVideosPage />}
          />
          <Route
            path="/pipeline"
            element={user?.is_admin ? <PipelinePage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/shooting-queue"
            element={user?.is_admin ? <ShootingQueuePage /> : <Navigate to="/" replace />}
          />
          <Route path="/trends" element={<TrendsPage user={user} onLoginClick={handleLoginClick} onOpenOnboarding={(step) => { setOnboardingInitialStep(step || "choice"); setShowOnboarding(true); }} />} />
          <Route
            path="/pricing"
            element={<PricingPage user={user} onLoginClick={handleLoginClick} />}
          />
          <Route
            path="/checkout/success"
            element={<CheckoutSuccess refreshUser={refreshUser} />}
          />
          <Route
            path="/library/:id"
            element={<LibraryReelDetailPage backPath="/my-videos" />}
          />
          <Route
            path="/settings"
            element={<SettingsPage />}
          />
          <Route path="/terms" element={<TermsPage />} />
          <Route path="/terms-ru" element={<TermsPage />} />
          <Route path="/privacy" element={<PrivacyPolicyPage />} />
          <Route path="/privacy-ru" element={<PrivacyPolicyPage />} />
          <Route path="/cancel-subscription" element={<CancelConfirmPage />} />
          <Route path="/refund" element={<RefundPolicyPage />} />
          <Route path="/refund-ru" element={<RefundPolicyPage />} />
          <Route path="/cookie-policy" element={<CookiePolicyPage />} />
          <Route path="/cookie-policy-ru" element={<CookiePolicyPage />} />
          <Route
            path="/auth/callback"
            element={<AuthCallbackPage refreshUser={refreshUser} />}
          />
          <Route
            path="/auth/error"
            element={<AuthCallbackPage refreshUser={refreshUser} />}
          />
        </Routes>
        </Suspense>
      </AppLayout>

      <Suspense fallback={null}>
      <UpgradeModal
        isOpen={showUpgradeModal}
        onClose={() => setShowUpgradeModal(false)}
        usage={usage}
        currentTier={user?.tier || "FREE"}
        reason={upgradeReason}
      />

      <AuthGateModal
        isOpen={showAuthModal}
        onClose={handleModalClose}
        reason={authModalReason}
        onSuccess={handleModalSuccess}
        user={user}
        usage={usage}
        refreshUser={refreshUser}
      />

      {/* Support chat widget — only for verified users (email or Telegram) */}
      {user && !user.is_anonymous && (user.email || user.telegram_user_id) && <ChatWidget />}

      <OnboardingModal
        isOpen={showOnboarding && !showAuthModal}
        initialStep={onboardingInitialStep}
        onComplete={() => {
          setShowOnboarding(false);
          setOnboardingNeeded(false);
          setShowOnboardingBanner(false);
          setOnboardingInitialStep("choice");
        }}
        onSkip={() => {
          setShowOnboarding(false);
          setOnboardingInitialStep("choice");
          const count = parseInt(localStorage.getItem("onboarding_dismiss_count") || "0", 10);
          localStorage.setItem("onboarding_dismiss_count", String(count + 1));
        }}
        refreshUser={refreshUser}
      />
      </Suspense>
    </>
  );
}

export default App;
