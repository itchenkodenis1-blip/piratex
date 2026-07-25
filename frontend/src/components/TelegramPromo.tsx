import { useState, useEffect, useRef } from "react";
import { useTranslation } from "../i18n";
import { useAuth } from "../hooks/useAuth";
import { useTelegramPromo } from "../hooks/useTelegramPromo";
import { createTelegramConnectCode, checkTelegramCode } from "../api/client";
import { QRCodeSVG } from "qrcode.react";

type PromoVariant = "processing" | "trends" | "results";

interface TelegramPromoProps {
  variant: PromoVariant;
}

function getIsMobile(): boolean {
  return typeof navigator !== "undefined" &&
    (navigator.maxTouchPoints > 0 || /Mobi|Android/i.test(navigator.userAgent));
}

export function TelegramPromo({ variant }: TelegramPromoProps) {
  const { t } = useTranslation();
  const { refreshUser } = useAuth();
  const { canShow, markShown, dismiss, dismissForever, showCount, hasTelegram } = useTelegramPromo();

  const [visible, setVisible] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [deepLink, setDeepLink] = useState("");
  const [qrExpired, setQrExpired] = useState(false);
  const [qrError, setQrError] = useState(false);
  const [connected, setConnected] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const markedRef = useRef(false);
  const isMobile = getIsMobile();

  // Show with a slight delay for smooth entrance
  useEffect(() => {
    if (!canShow) return;
    const timer = setTimeout(() => {
      setVisible(true);
      if (!markedRef.current) {
        markShown();
        markedRef.current = true;
      }
    }, 1500);
    return () => clearTimeout(timer);
  }, [canShow, markShown]);

  // If Telegram gets connected externally (e.g. another tab, useAuth polling),
  // force-hide the promo and stop polling
  useEffect(() => {
    if (hasTelegram) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      if (successTimerRef.current) { clearTimeout(successTimerRef.current); successTimerRef.current = null; }
      setVisible(false);
    }
  }, [hasTelegram]);

  // Cleanup polling + success timer on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
    };
  }, []);

  if (!canShow && !visible) return null;
  if (connected) {
    return (
      <div className="bg-green-900/15 border border-green-700/25 rounded-2xl px-5 py-4 text-center animate-fade-in">
        <div className="flex items-center justify-center gap-2 text-green-400 text-sm font-medium">
          <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
          </svg>
          {t.tg_promo_connected}
        </div>
      </div>
    );
  }

  const titles: Record<PromoVariant, string> = {
    processing: t.tg_promo_processing_title,
    trends: t.tg_promo_trends_title,
    results: t.tg_promo_results_title,
  };
  const descs: Record<PromoVariant, string> = {
    processing: t.tg_promo_processing_desc,
    trends: t.tg_promo_trends_desc,
    results: t.tg_promo_results_desc,
  };

  const handleConnect = async () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setConnecting(true);
    setQrExpired(false);
    setQrError(false);
    try {
      const result = await createTelegramConnectCode();
      setDeepLink(result.deep_link);

      if (isMobile) {
        window.open(result.deep_link, "_blank");
      }

      pollRef.current = setInterval(async () => {
        try {
          const check = await checkTelegramCode(result.code);
          if (check.expired) {
            setQrExpired(true);
            if (pollRef.current) clearInterval(pollRef.current);
            return;
          }
          if (check.confirmed && check.token) {
            if (pollRef.current) clearInterval(pollRef.current);
            localStorage.setItem("token", check.token);
            await refreshUser();
            setConnected(true);
            successTimerRef.current = setTimeout(() => setVisible(false), 3000);
          }
        } catch { /* poll retry */ }
      }, 2000);
    } catch {
      setQrError(true);
    }
    setConnecting(false);
  };

  const handleDismiss = () => {
    setVisible(false);
    dismiss();
  };

  const handleStop = () => {
    setVisible(false);
    dismissForever();
  };

  if (!visible) return null;

  return (
    <div className="bg-[#2AABEE]/8 border border-[#2AABEE]/20 rounded-2xl px-5 py-4 space-y-3 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="#2AABEE" className="flex-shrink-0 mt-0.5">
            <path d="M11.94 24c6.6 0 11.94-5.37 11.94-12S18.54 0 11.94 0 0 5.37 0 12s5.34 12 11.94 12zm-3.15-8.4l-.3-3.15 7.74-7.05c.33-.3-.08-.45-.54-.18L6.84 11.4l-3.06-.96c-.66-.18-.66-.66.15-.99l11.94-4.62c.54-.24 1.05.12.84.99l-2.04 9.6c-.15.66-.54.81-1.11.51l-3.06-2.25-1.47 1.41c-.18.18-.3.3-.54.3z"/>
          </svg>
          <div>
            <p className="text-sm font-medium text-cream">{titles[variant]}</p>
            <p className="text-xs text-cream-muted mt-0.5">{descs[variant]}</p>
          </div>
        </div>
        <button
          onClick={handleDismiss}
          className="text-cream-muted/50 hover:text-cream-muted transition-colors text-lg leading-none flex-shrink-0"
          aria-label="Close"
        >
          &times;
        </button>
      </div>

      {/* Connect flow (expanded) */}
      {connecting || deepLink ? (
        <div className="space-y-3 text-center">
          {qrError ? (
            <div className="space-y-2 py-2">
              <p className="text-red-400 text-xs">{t.auth_error_generic}</p>
              <button onClick={handleConnect} className="text-xs text-cream underline underline-offset-4 hover:text-cream-dim transition-colors">
                {t.modal_telegram_retry}
              </button>
            </div>
          ) : qrExpired ? (
            <div className="space-y-2 py-2">
              <p className="text-amber-400 text-xs">{t.modal_telegram_code_expired}</p>
              <button onClick={handleConnect} className="text-xs text-cream underline underline-offset-4 hover:text-cream-dim transition-colors">
                {t.modal_telegram_retry}
              </button>
            </div>
          ) : deepLink ? (
            <>
              {!isMobile && (
                <div className="flex justify-center">
                  <div className="bg-white p-2.5 rounded-xl inline-block">
                    <QRCodeSVG value={deepLink} size={128} />
                  </div>
                </div>
              )}
              <a
                href={deepLink}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block px-4 py-2 bg-[#2AABEE] hover:bg-[#229ED9] text-white font-medium rounded-full text-xs transition-colors"
              >
                {t.modal_telegram_open_bot}
              </a>
            </>
          ) : (
            <div className="flex justify-center py-3">
              <div className="w-5 h-5 border-2 border-[#2AABEE] border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </div>
      ) : (
        /* Actions */
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={handleConnect}
            className="px-4 py-2 bg-[#2AABEE] hover:bg-[#229ED9] text-white font-medium rounded-full text-xs transition-colors inline-flex items-center gap-1.5"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M11.94 24c6.6 0 11.94-5.37 11.94-12S18.54 0 11.94 0 0 5.37 0 12s5.34 12 11.94 12zm-3.15-8.4l-.3-3.15 7.74-7.05c.33-.3-.08-.45-.54-.18L6.84 11.4l-3.06-.96c-.66-.18-.66-.66.15-.99l11.94-4.62c.54-.24 1.05.12.84.99l-2.04 9.6c-.15.66-.54.81-1.11.51l-3.06-2.25-1.47 1.41c-.18.18-.3.3-.54.3z"/>
            </svg>
            {t.tg_promo_connect}
          </button>
          <button
            onClick={handleDismiss}
            className="px-4 py-2 text-xs text-cream-muted hover:text-cream border border-border-subtle hover:border-cream-muted/30 rounded-full transition-colors"
          >
            {t.tg_promo_not_now}
          </button>
          {showCount >= 1 && (
            <button
              onClick={handleStop}
              className="text-xs text-cream-muted/40 hover:text-cream-muted transition-colors ml-auto"
            >
              {t.tg_promo_stop}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
