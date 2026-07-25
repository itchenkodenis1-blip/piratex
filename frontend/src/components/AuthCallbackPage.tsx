import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "../i18n";

type ErrorKind = "expired" | "already_used" | "not_found" | "generic";

export function AuthCallbackPage({ refreshUser }: { refreshUser: () => Promise<void> }) {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [errorKind, setErrorKind] = useState<ErrorKind | null>(null);

  useEffect(() => {
    // Read token from URL fragment (#token=...) first, then fall back to query (?token=...)
    const hash = window.location.hash.slice(1); // remove leading #
    const hashParams = new URLSearchParams(hash);
    const token = hashParams.get("token") || searchParams.get("token");
    const errorParam = searchParams.get("error");

    if (errorParam) {
      if (errorParam === "expired" || errorParam === "already_used" || errorParam === "not_found") {
        setErrorKind(errorParam);
      } else {
        setErrorKind("generic");
      }
      return;
    }

    if (token) {
      // Clear fragment from URL to avoid token leaking via history
      if (window.location.hash) {
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
      localStorage.setItem("token", token);
      const redirectTo = searchParams.get("redirect") || "/";
      refreshUser().then(() => {
        navigate(redirectTo, { replace: true });
      });
    } else {
      setErrorKind("generic");
    }
  }, [searchParams, navigate, refreshUser]);

  if (errorKind) {
    const messages: Record<ErrorKind, string> = {
      expired: t.auth_callback_link_expired,
      already_used: t.auth_callback_link_used,
      not_found: t.auth_callback_link_not_found,
      generic: t.auth_callback_error,
    };

    const isWarning = errorKind === "already_used";

    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center space-y-5 px-6 text-center">
        <div className={`w-16 h-16 rounded-full flex items-center justify-center ${
          isWarning ? "bg-yellow-500/20" : "bg-red-600/20"
        }`}>
          {isWarning ? (
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="#eab308" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M16 12v6M16 22h.01" />
              <path d="M5.3 26h21.4a2 2 0 001.7-3L17.7 5a2 2 0 00-3.4 0L3.6 23a2 2 0 001.7 3z" />
            </svg>
          ) : (
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="#ef4444" strokeWidth="2.5">
              <path d="M10 10l12 12M22 10L10 22" />
            </svg>
          )}
        </div>
        <p className="text-cream text-lg font-medium max-w-sm">{messages[errorKind]}</p>
        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => navigate("/", { replace: true })}
            className="px-6 py-2.5 bg-cream text-[#0C0C0C] hover:bg-cream-dim font-medium rounded-full text-sm transition-colors"
          >
            {t.auth_callback_home}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-cream border-t-transparent rounded-full animate-spin" />
    </div>
  );
}
