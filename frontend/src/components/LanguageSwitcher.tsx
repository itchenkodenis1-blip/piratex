import { useState, useRef, useEffect, useMemo } from "react";
import { useTranslation, LANGUAGE_FLAGS, LANGUAGE_LABELS, SUPPORTED_LANGUAGES } from "../i18n";
import type { SupportedLanguage } from "../i18n";
import { updateSettings } from "../api/client";
import { isViralexDomain } from "../region";

export function LanguageSwitcher() {
  const { lang, setLang } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // On viralex.ai domain, hide Russian from the language list
  const availableLanguages = useMemo(() => {
    const base = isViralexDomain()
      ? SUPPORTED_LANGUAGES.filter((code) => code !== "ru")
      : // Только рынки с рабочей оплатой и релевантной аудиторией (de/fr скрыты до спроса)
        (["ru", "en", "pt"] as const);
    return base.filter((code) => code !== lang);
  }, [lang]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function handleSelect(newLang: SupportedLanguage) {
    setLang(newLang);
    setOpen(false);
    updateSettings({ language: newLang }).catch(() => {});
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2 py-2.5 text-sm text-cream-muted hover:text-cream rounded-lg transition-colors"
      >
        <span>{LANGUAGE_FLAGS[lang]}</span>
        <svg width="12" height="12" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M5 8l5 5 5-5" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 bg-surface-light border border-border-subtle rounded-xl shadow-xl overflow-hidden z-50 min-w-[160px]">
          {availableLanguages.map((code) => (
            <button
              key={code}
              onClick={() => handleSelect(code)}
              className={`w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors ${
                code === lang
                  ? "bg-border-subtle text-cream"
                  : "text-cream-dim hover:bg-border-subtle/50 hover:text-cream"
              }`}
            >
              <span>{LANGUAGE_FLAGS[code]}</span>
              <span>{LANGUAGE_LABELS[code]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
