import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";
import { useRegion } from "../region";
import { startOAuth, sendMagicLink, verifyMagicLinkPin } from "../api/client";
import type { AuthUser, UsageInfo } from "../types";

interface AuthGateModalProps {
  isOpen: boolean;
  onClose: () => void;
  reason?: string;
  onSuccess: () => void;
  user: AuthUser | null;
  usage: UsageInfo | null;
  refreshUser: () => Promise<void>;
}

type Step = "choose_method" | "consent" | "email_auth" | "done";
type PendingAction = { type: "oauth"; provider: string } | { type: "email" } | null;

export function AuthGateModal({
  isOpen, onClose, onSuccess,
  user, usage, refreshUser,
}: AuthGateModalProps) {
  const { t, lang } = useTranslation();
  const regionConfig = useRegion();

  // Personal data consent (two checkboxes for Russian law compliance)
  const [consentPersonalData, setConsentPersonalData] = useState(false);
  const [consentTerms, setConsentTerms] = useState(false);
  const consentGiven = consentPersonalData && consentTerms;

  // Pending action — remembers what the user clicked before consent
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);

  // Email state
  const [email, setEmail] = useState("");
  const [emailSent, setEmailSent] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [emailSending, setEmailSending] = useState(false);
  const emailPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // PIN code input state
  const [pinDigits, setPinDigits] = useState<string[]>(["", "", "", "", "", ""]);
  const [pinVerifying, setPinVerifying] = useState(false);
  const [pinError, setPinError] = useState<string | null>(null);
  const pinInputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // OAuth loading
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);

  // Stable ref for onSuccess
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;

  // Determine initial step
  const getInitialStep = useCallback((): Step => {
    if (!user || user.is_anonymous) return "choose_method";
    if (user.tier === "REGISTERED") return "choose_method";
    return "done";
  }, [user]);

  const [step, setStep] = useState<Step>(getInitialStep);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setStep(getInitialStep());
      setEmail("");
      setEmailSent(false);
      setEmailError(null);
      setOauthLoading(null);
      setPendingAction(null);
      setPinDigits(["", "", "", "", "", ""]);
      setPinVerifying(false);
      setPinError(null);
    }
  }, [isOpen, getInitialStep]);

  // Cleanup email polling on unmount
  useEffect(() => {
    return () => {
      if (emailPollRef.current) clearInterval(emailPollRef.current);
    };
  }, []);

  // Watch user changes after auth
  useEffect(() => {
    if (!isOpen) return;
    if (step !== "email_auth" && step !== "choose_method") return;
    if (!user || user.is_anonymous) return;

    if (user.tier === "FREE" || user.tier === "START" || user.tier === "PRO" || user.tier === "UNLIMITED" || user.tier === "REGISTERED") {
      onSuccessRef.current();
    }
  }, [user, isOpen, step]);

  // Execute a pending action after consent
  const executePendingAction = useCallback(async (action: PendingAction) => {
    if (!action) return;
    if (action.type === "oauth") {
      setOauthLoading(action.provider);
      try {
        const { authorize_url } = await startOAuth(action.provider, window.location.pathname + window.location.search);
        window.location.href = authorize_url;
      } catch {
        setOauthLoading(null);
      }
    } else if (action.type === "email") {
      setStep("email_auth");
    }
  }, []);

  // Gate action behind consent — if not consented, show consent step first
  const requireConsent = (action: PendingAction) => {
    if (consentGiven) {
      executePendingAction(action);
    } else {
      setPendingAction(action);
      setStep("consent");
    }
  };

  // Handle magic link send
  const handleSendMagicLink = async () => {
    if (!email.trim()) return;
    setEmailSending(true);
    setEmailError(null);
    try {
      const result = await sendMagicLink(email.trim(), lang, regionConfig.brand);
      if (result.sent) {
        setEmailSent(true);
        // Start polling if we have a code (debug mode)
        // In production, user clicks the link in email which redirects to /auth/callback
        // But we also support polling via check endpoint
      }
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      setEmailError(error.response?.data?.detail || t.auth_error_generic);
    } finally {
      setEmailSending(false);
    }
  };

  // Handle PIN digit input
  const handlePinChange = (index: number, value: string) => {
    // Only allow digits
    const digit = value.replace(/\D/g, "").slice(-1);
    const newDigits = [...pinDigits];
    newDigits[index] = digit;
    setPinDigits(newDigits);
    setPinError(null);

    // Auto-advance to next input
    if (digit && index < 5) {
      pinInputRefs.current[index + 1]?.focus();
    }

    // Auto-submit when all 6 digits filled
    const fullPin = newDigits.join("");
    if (fullPin.length === 6 && !pinVerifying) {
      handleVerifyPin(fullPin);
    }
  };

  const handlePinKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === "Backspace" && !pinDigits[index] && index > 0) {
      pinInputRefs.current[index - 1]?.focus();
    }
  };

  const handlePinPaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!pasted) return;
    const newDigits = [...pinDigits];
    for (let i = 0; i < 6; i++) {
      newDigits[i] = pasted[i] || "";
    }
    setPinDigits(newDigits);
    setPinError(null);
    if (pasted.length === 6 && !pinVerifying) {
      handleVerifyPin(pasted);
    } else {
      pinInputRefs.current[pasted.length]?.focus();
    }
  };

  const handleVerifyPin = async (pin: string) => {
    setPinVerifying(true);
    setPinError(null);
    try {
      const result = await verifyMagicLinkPin(email.trim(), pin);
      if (result.verified) {
        // Store JWT so subsequent requests use the new identity (not the old anonymous token)
        if (result.token) {
          localStorage.setItem("token", result.token);
        }
        await refreshUser();
        // Close modal immediately — don't rely on useEffect/tier detection
        onSuccessRef.current();
      }
    } catch (err: unknown) {
      const error = err as { response?: { status?: number; data?: { detail?: string } } };
      if (error.response?.status === 429 || error.response?.status === 410) {
        setPinError(t.modal_email_code_expired);
      } else {
        setPinError(t.modal_email_wrong_code);
      }
      setPinDigits(["", "", "", "", "", ""]);
      pinInputRefs.current[0]?.focus();
    } finally {
      setPinVerifying(false);
    }
  };

  const handleResend = () => {
    setEmailSent(false);
    setPinDigits(["", "", "", "", "", ""]);
    setPinError(null);
  };

  if (!isOpen) return null;

  const freeLimit = usage?.limit ?? 3;

  // Step labels for indicator
  const stepLabels: { key: string; label: string }[] = [
    { key: "auth", label: t.modal_choose_method },
    { key: "done", label: t.modal_step_done },
  ];

  const currentStepIndex =
    step === "choose_method" || step === "consent" || step === "email_auth" ? 0 : 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md mx-4 bg-surface border border-border-subtle rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 sm:px-6 pt-5 pb-0">
          <div className="flex items-center gap-3">
            <img src="/logo.png" alt="ВидеоРентген" className="h-7 w-7" />
            <span className="text-sm font-serif font-medium text-cream">ВидеоРентген</span>
          </div>
          <button
            onClick={onClose}
            className="text-cream-muted hover:text-cream transition-colors p-1"
            aria-label={t.modal_close}
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-1.5 sm:gap-2 px-4 sm:px-6 pt-4 pb-2">
          {stepLabels.map((s, i) => (
            <div key={s.key} className="flex items-center gap-2 flex-1">
              <div className="flex items-center gap-1.5">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium transition-colors ${
                    i < currentStepIndex
                      ? "bg-green-600 text-white"
                      : i === currentStepIndex
                        ? "bg-cream text-[#0C0C0C]"
                        : "bg-surface-light text-cream-muted"
                  }`}
                >
                  {i < currentStepIndex ? (
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M2 6l3 3 5-5" />
                    </svg>
                  ) : (
                    i + 1
                  )}
                </div>
                <span className={`text-[10px] sm:text-xs whitespace-nowrap ${
                  i === currentStepIndex ? "text-cream" : "text-cream-muted"
                }`}>
                  {s.label}
                </span>
              </div>
              {i < stepLabels.length - 1 && (
                <div className={`flex-1 h-px ${
                  i < currentStepIndex ? "bg-green-600" : "bg-border-subtle"
                }`} />
              )}
            </div>
          ))}
        </div>

        {/* Content */}
        <div className="px-4 sm:px-6 pb-6 pt-3">
          {/* Step: Choose Method */}
          {step === "choose_method" && (
            <div className="space-y-4">
              <div className="text-center space-y-1">
                <p className="text-cream text-sm">{t.modal_choose_method || "Выберите способ входа"}</p>
                <p className="text-cream-muted text-xs">{t.modal_auto_register_hint}</p>
              </div>

              <div className="space-y-2.5">
                {/* Yandex ID */}
                {regionConfig.region === "ru" && (
                  <button
                    onClick={() => requireConsent({ type: "oauth", provider: "yandex" })}
                    disabled={!!oauthLoading}
                    className="w-full py-2.5 bg-[#FC3F1D] hover:bg-[#e03616] disabled:opacity-50 text-white font-medium rounded-full text-sm text-center transition-colors flex items-center justify-center gap-2"
                  >
                    {oauthLoading === "yandex" ? (
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M13.32 7.67h-.84c-1.33 0-2.04.71-2.04 1.76 0 1.19.54 1.75 1.65 2.49l.91.61-2.64 4.47H8.5l2.3-3.89C9.6 12.18 8.86 11.2 8.86 9.56c0-2.02 1.4-3.39 3.62-3.39h2.19V17h-1.35V7.67z"/></svg>
                    )}
                    {t.modal_oauth_yandex || "Войти через Яндекс"}
                  </button>
                )}

                {/* Google */}
                {regionConfig.region !== "ru" && (
                  <button
                    onClick={() => requireConsent({ type: "oauth", provider: "google" })}
                    disabled={!!oauthLoading}
                    className="w-full py-2.5 bg-white hover:bg-gray-100 disabled:opacity-50 text-gray-700 font-medium rounded-full text-sm text-center transition-colors flex items-center justify-center gap-2 border border-gray-300"
                  >
                    {oauthLoading === "google" ? (
                      <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                    )}
                    {t.modal_oauth_google || "Sign in with Google"}
                  </button>
                )}

                {/* Divider */}
                <div className="flex items-center gap-3 py-1">
                  <div className="flex-1 h-px bg-border-subtle" />
                  <span className="text-xs text-cream-muted">{t.modal_or || "или"}</span>
                  <div className="flex-1 h-px bg-border-subtle" />
                </div>

                {/* Email magic link */}
                <button
                  onClick={() => requireConsent({ type: "email" })}
                  className="w-full py-2.5 bg-surface-light hover:bg-surface-lighter text-cream font-medium rounded-full text-sm text-center transition-colors flex items-center justify-center gap-2 border border-border-subtle"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
                  {t.modal_email_login || "Войти по Email"}
                </button>
              </div>
            </div>
          )}

          {/* Step: Consent */}
          {step === "consent" && (
            <div className="space-y-4">
              <button
                onClick={() => { setStep("choose_method"); setPendingAction(null); }}
                className="text-cream-muted hover:text-cream text-xs flex items-center gap-1 transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8.5 3L4.5 7l4 4"/></svg>
                {t.modal_back || "Назад"}
              </button>

              <p className="text-cream text-sm text-center">{t.consent_step_title}</p>

              <div className="space-y-3">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consentPersonalData}
                    onChange={(e) => setConsentPersonalData(e.target.checked)}
                    className="mt-0.5 w-4 h-4 rounded border-border-subtle accent-cream shrink-0"
                  />
                  <span className="text-xs text-cream-muted leading-relaxed">
                    {t.consent_personal_data}{" "}
                    <a href={regionConfig.privacyUrl} className="text-cream underline underline-offset-2">{t.footer_privacy}</a>
                  </span>
                </label>

                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consentTerms}
                    onChange={(e) => setConsentTerms(e.target.checked)}
                    className="mt-0.5 w-4 h-4 rounded border-border-subtle accent-cream shrink-0"
                  />
                  <span className="text-xs text-cream-muted leading-relaxed">
                    {t.consent_terms_accept}{" "}
                    <a href={regionConfig.termsUrl} className="text-cream underline underline-offset-2">{t.footer_terms}</a>
                  </span>
                </label>
              </div>

              <button
                onClick={() => {
                  if (consentGiven) executePendingAction(pendingAction);
                }}
                disabled={!consentGiven}
                className="w-full py-2.5 bg-cream text-[#0C0C0C] hover:bg-cream-dim disabled:bg-surface-light disabled:text-cream-muted font-medium rounded-full text-sm transition-colors"
              >
                {t.consent_continue}
              </button>
            </div>
          )}

          {/* Step: Email Auth */}
          {step === "email_auth" && (
            <div className="space-y-4">
              <button
                onClick={() => { setStep("choose_method"); setEmailSent(false); setEmailError(null); }}
                className="text-cream-muted hover:text-cream text-xs flex items-center gap-1 transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8.5 3L4.5 7l4 4"/></svg>
                {t.modal_back || "Назад"}
              </button>

              {!emailSent ? (
                <div className="space-y-4">
                  <p className="text-cream text-sm text-center">{t.modal_email_enter || "Введите email — мы отправим ссылку для входа"}</p>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSendMagicLink()}
                    placeholder="email@example.com"
                    className="w-full px-4 py-2.5 bg-surface-light border border-border-subtle rounded-full text-cream text-sm placeholder-cream-muted focus:outline-none focus:border-cream/50"
                    autoFocus
                  />
                  {emailError && <p className="text-red-400 text-xs text-center">{emailError}</p>}
                  <button
                    onClick={handleSendMagicLink}
                    disabled={emailSending || !email.trim()}
                    className="w-full py-2.5 bg-cream text-[#0C0C0C] hover:bg-cream-dim disabled:bg-surface-light disabled:text-cream-muted font-medium rounded-full text-sm transition-colors"
                  >
                    {emailSending ? (
                      <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin mx-auto" />
                    ) : (
                      t.modal_email_send || "Отправить ссылку"
                    )}
                  </button>
                </div>
              ) : (
                <div className="space-y-5">
                  {/* Header */}
                  <div className="text-center space-y-1.5">
                    <div className="w-12 h-12 mx-auto rounded-full bg-cream/10 flex items-center justify-center mb-3">
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-cream"><path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
                    </div>
                    <p className="text-cream text-sm font-medium">{t.modal_email_sent}</p>
                    <p className="text-cream-muted text-xs">{t.modal_email_check_inbox}</p>
                    <p className="text-cream-muted/60 text-xs">{email}</p>
                  </div>

                  {/* 6-digit PIN input */}
                  <div className="flex justify-center gap-2" onPaste={handlePinPaste}>
                    {pinDigits.map((digit, i) => (
                      <input
                        key={i}
                        ref={(el) => { pinInputRefs.current[i] = el; }}
                        type="text"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={1}
                        value={digit}
                        onChange={(e) => handlePinChange(i, e.target.value)}
                        onKeyDown={(e) => handlePinKeyDown(i, e)}
                        autoFocus={i === 0}
                        disabled={pinVerifying}
                        className={`w-10 h-12 text-center text-lg font-mono font-bold rounded-lg border
                          bg-surface-light text-cream
                          focus:outline-none focus:ring-2 focus:ring-cream/40 focus:border-cream/50
                          disabled:opacity-50 transition-all
                          ${pinError ? "border-red-500/60 shake" : "border-border-subtle"}
                        `}
                      />
                    ))}
                  </div>

                  {/* Verifying spinner */}
                  {pinVerifying && (
                    <div className="flex justify-center">
                      <div className="w-5 h-5 border-2 border-cream border-t-transparent rounded-full animate-spin" />
                    </div>
                  )}

                  {/* Error message */}
                  {pinError && (
                    <p className="text-red-400 text-xs text-center">{pinError}</p>
                  )}

                  {/* Or use link hint */}
                  <p className="text-cream-muted/50 text-[11px] text-center">{t.modal_email_or_link}</p>

                  {/* Resend button */}
                  <button
                    onClick={handleResend}
                    className="w-full text-cream-muted hover:text-cream text-xs text-center transition-colors py-1"
                  >
                    {t.modal_email_resend}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Step: Done */}
          {step === "done" && (
            <div className="text-center space-y-5 py-4">
              <div className="w-16 h-16 mx-auto rounded-full bg-green-600/20 flex items-center justify-center">
                <svg width="32" height="32" viewBox="0 0 32 32" fill="none" stroke="#22c55e" strokeWidth="2.5">
                  <path d="M8 16l6 6 10-10" />
                </svg>
              </div>
              <h3 className="text-xl font-serif font-medium text-cream">{t.modal_step_done}</h3>
              <p className="text-cream-muted text-sm">
                {t.modal_done_message.replace("{limit}", String(freeLimit))}
              </p>
              <button
                onClick={() => onSuccessRef.current()}
                className="w-full py-2.5 bg-cream text-[#0C0C0C] hover:bg-cream-dim font-medium rounded-full text-sm transition-colors"
              >
                {t.modal_done_start}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
