import { useState } from "react";
import { useTranslation } from "../i18n";
import { useRegion } from "../region";

const COOKIE_CONSENT_KEY = "cookie_consent";

function hasStoredConsent(): boolean {
  const stored = localStorage.getItem(COOKIE_CONSENT_KEY);
  return stored === "accepted" || stored === "rejected";
}

export function CookieConsentBanner() {
  const { t } = useTranslation();
  const regionConfig = useRegion();
  const [visible, setVisible] = useState(() => !hasStoredConsent());

  const handleAccept = () => {
    localStorage.setItem(COOKIE_CONSENT_KEY, "accepted");
    setVisible(false);
  };

  const handleReject = () => {
    localStorage.setItem(COOKIE_CONSENT_KEY, "rejected");
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 p-4 sm:p-6" style={{ paddingBottom: 'max(env(safe-area-inset-bottom), 1rem)' }}>
      <div className="max-w-2xl mx-auto bg-surface border border-border-subtle rounded-2xl p-4 sm:p-5 shadow-2xl shadow-black/40">
        <div className="text-sm text-cream-dim leading-relaxed mb-4">
          <p>{t.cookie_message}</p>
          <a
            href={regionConfig.privacyUrl}
            className="inline-block mt-1 py-1 text-cream underline underline-offset-2 hover:text-cream-dim transition-colors"
          >
            {t.cookie_learn_more}
          </a>
        </div>
        <div className="flex items-center gap-3">
          {/* GDPR/CNIL: Accept and Reject must be equally prominent */}
          <button
            onClick={handleReject}
            className="flex-1 py-2.5 px-4 border border-border-subtle rounded-full text-sm text-cream-dim hover:text-cream hover:border-cream-muted transition-colors"
          >
            {t.cookie_reject}
          </button>
          <button
            onClick={handleAccept}
            className="flex-1 py-2.5 px-4 bg-cream text-[#0C0C0C] rounded-full text-sm font-medium hover:bg-cream-dim transition-colors"
          >
            {t.cookie_accept}
          </button>
        </div>
      </div>
    </div>
  );
}
