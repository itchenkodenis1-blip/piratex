import { useRef, useState } from "react";
import { Turnstile, type TurnstileInstance } from "@marsidev/react-turnstile";
import { useTranslation } from "../i18n";

const TURNSTILE_SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY || "";

interface Props {
  onSubmit: (url: string, turnstileToken?: string) => void;
  loading: boolean;
  initialValue?: string;
  requireCaptcha?: boolean;
}

export function UrlInput({ onSubmit, loading, initialValue = "", requireCaptcha = false }: Props) {
  const { t } = useTranslation();
  const [url, setUrl] = useState(initialValue);
  const [resolving, setResolving] = useState(false);
  const turnstileRef = useRef<TurnstileInstance | null>(null);
  const pendingUrlRef = useRef<string | null>(null);

  const showTurnstile = requireCaptcha && !!TURNSTILE_SITE_KEY;

  const handleTurnstileSuccess = (token: string) => {
    const pendingUrl = pendingUrlRef.current;
    pendingUrlRef.current = null;
    setResolving(false);
    if (pendingUrl) {
      onSubmit(pendingUrl, token);
    }
    turnstileRef.current?.reset();
  };

  const handleTurnstileError = () => {
    pendingUrlRef.current = null;
    setResolving(false);
    // Fallback: submit without token, backend will reject if needed
    onSubmit(url.trim(), undefined);
    turnstileRef.current?.reset();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;

    if (showTurnstile) {
      pendingUrlRef.current = trimmed;
      setResolving(true);
      turnstileRef.current?.execute();
    } else {
      onSubmit(trimmed, undefined);
    }
  };

  const isDisabled = loading || resolving || !url.trim();

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl mx-auto">
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder={t.input_placeholder}
          disabled={loading || resolving}
          className="flex-1 px-4 sm:px-5 py-3.5 bg-surface border border-border-subtle rounded-full text-cream placeholder-cream-muted focus:outline-none focus:border-cream-muted transition-colors disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={isDisabled}
          className="w-full sm:w-auto px-7 py-3.5 bg-cream text-[#0C0C0C] hover:bg-cream-dim disabled:bg-surface-light disabled:text-cream-muted disabled:cursor-not-allowed font-medium rounded-full transition-colors"
        >
          {loading || resolving ? t.input_processing : t.input_submit}
        </button>
      </div>
      {showTurnstile && (
        <div className="mt-3 flex justify-center">
          <Turnstile
            ref={turnstileRef}
            siteKey={TURNSTILE_SITE_KEY}
            onSuccess={handleTurnstileSuccess}
            onError={handleTurnstileError}
            onExpire={handleTurnstileError}
            options={{ size: "invisible", execution: "execute" }}
          />
        </div>
      )}
    </form>
  );
}
