import { useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { createTelegramCode, checkTelegramCode } from "../api/client";
import { useTranslation } from "../i18n";

interface TelegramAuthQRProps {
  onAuth: (token: string) => void;
}

const POLL_INTERVAL = 2000;
const STORAGE_KEY = "tg_auth_pending";

export function TelegramAuthQR({ onAuth }: TelegramAuthQRProps) {
  const { t } = useTranslation();
  const [deepLink, setDeepLink] = useState("");
  const [code, setCode] = useState("");
  const [expired, setExpired] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onAuthRef = useRef(onAuth);
  onAuthRef.current = onAuth;

  const generateCode = useCallback(async () => {
    setLoading(true);
    setError(null);
    setExpired(false);
    try {
      const result = await createTelegramCode();
      setDeepLink(result.deep_link);
      setCode(result.code);
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          code: result.code,
          deep_link: result.deep_link,
          expires_at: result.expires_at,
        }),
      );
    } catch {
      setError(t.auth_error_generic);
    } finally {
      setLoading(false);
    }
  }, [t.auth_error_generic]);

  // On mount: restore pending code from sessionStorage or generate new
  useEffect(() => {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.expires_at && new Date(parsed.expires_at) > new Date()) {
          setDeepLink(parsed.deep_link);
          setCode(parsed.code);
          setLoading(false);
          return;
        }
      } catch {
        // corrupted — fall through
      }
      sessionStorage.removeItem(STORAGE_KEY);
    }
    generateCode();
  }, [generateCode]);

  // Poll for confirmation
  useEffect(() => {
    if (!code) return;

    pollRef.current = setInterval(async () => {
      try {
        const result = await checkTelegramCode(code);
        if (result.expired) {
          setExpired(true);
          sessionStorage.removeItem(STORAGE_KEY);
          if (pollRef.current) clearInterval(pollRef.current);
          return;
        }
        if (result.confirmed && result.token) {
          sessionStorage.removeItem(STORAGE_KEY);
          if (pollRef.current) clearInterval(pollRef.current);
          onAuthRef.current(result.token);
        }
      } catch {
        // Silently retry on next interval
      }
    }, POLL_INTERVAL);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [code]);

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <div className="w-6 h-6 border-2 border-cream border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (expired) {
    return (
      <div className="space-y-3 text-center py-4">
        <p className="text-amber-400 text-sm">{t.modal_telegram_code_expired}</p>
        <button
          onClick={generateCode}
          className="text-sm text-cream underline underline-offset-4 hover:text-cream-dim transition-colors"
        >
          {t.modal_telegram_retry}
        </button>
      </div>
    );
  }

  if (error) {
    return <p className="text-red-400 text-sm text-center py-4">{error}</p>;
  }

  return (
    <div className="space-y-4 text-center">
      {/* QR Code */}
      <div className="flex justify-center">
        <div className="bg-white p-3 rounded-xl inline-block">
          <QRCodeSVG value={deepLink} size={180} />
        </div>
      </div>

      <p className="text-cream-muted text-xs">{t.modal_telegram_scan_qr}</p>

      {/* Direct link button (for mobile) */}
      <a
        href={deepLink}
        target="_blank"
        rel="noopener noreferrer"
        className="block w-full py-2.5 bg-[#2AABEE] hover:bg-[#229ED9] text-white font-medium rounded-full text-sm text-center transition-colors"
      >
        {t.modal_telegram_open_bot}
      </a>
    </div>
  );
}
