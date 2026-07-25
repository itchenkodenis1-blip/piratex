import { createContext, useContext, useState, useCallback, useEffect } from "react";
import type { ReactNode } from "react";
import { createElement } from "react";
import type { Translations, SupportedLanguage } from "./types";
import { SUPPORTED_LANGUAGES } from "./types";

// Only Russian is bundled (primary audience); others are lazy-loaded
import { ru } from "./translations/ru";

const translationLoaders: Record<SupportedLanguage, () => Promise<Translations>> = {
  ru: () => Promise.resolve(ru),
  en: () => import("./translations/en").then(m => m.en),
  fr: () => import("./translations/fr").then(m => m.fr),
  pt: () => import("./translations/pt").then(m => m.pt),
  de: () => import("./translations/de").then(m => m.de),
};

// Cache loaded translations in memory
const loadedTranslations: Partial<Record<SupportedLanguage, Translations>> = { ru };

const STORAGE_KEY = "app_lang";
const OLD_STORAGE_KEY = "piratex_lang";

// Migrate old key → new key (one-time, for existing users)
(() => {
  const old = localStorage.getItem(OLD_STORAGE_KEY);
  if (old && !localStorage.getItem(STORAGE_KEY)) {
    localStorage.setItem(STORAGE_KEY, old);
    localStorage.removeItem(OLD_STORAGE_KEY);
  }
})();

function detectBrowserLanguage(): SupportedLanguage {
  const browserLang = navigator.language.split("-")[0];
  if ((SUPPORTED_LANGUAGES as readonly string[]).includes(browserLang)) {
    return browserLang as SupportedLanguage;
  }
  return "en";
}

function getInitialLanguage(): SupportedLanguage {
  // 1. User already chose a language — respect it
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && (SUPPORTED_LANGUAGES as readonly string[]).includes(stored)) {
    return stored as SupportedLanguage;
  }

  // 2. Viralex domain — always default to English (international marketing)
  const host = window.location.hostname;
  if (host.includes("viralex")) {
    return "en";
  }

  // 3. Browser language detection
  return detectBrowserLanguage();
}

interface LanguageContextValue {
  lang: SupportedLanguage;
  setLang: (lang: SupportedLanguage) => void;
  t: Translations;
}

const LanguageContext = createContext<LanguageContextValue>({
  lang: "ru",
  setLang: () => {},
  t: ru,
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const initialLang = getInitialLanguage();
  const [lang, setLangState] = useState<SupportedLanguage>(initialLang);
  const [translations, setTranslations] = useState<Translations>(loadedTranslations[initialLang] || ru);

  // Load translations for the initial language (if not ru)
  useEffect(() => {
    if (!loadedTranslations[initialLang]) {
      translationLoaders[initialLang]().then(t => {
        loadedTranslations[initialLang] = t;
        setTranslations(t);
      });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const setLang = useCallback((newLang: SupportedLanguage) => {
    setLangState(newLang);
    localStorage.setItem(STORAGE_KEY, newLang);

    if (loadedTranslations[newLang]) {
      setTranslations(loadedTranslations[newLang]!);
    } else {
      translationLoaders[newLang]().then(t => {
        loadedTranslations[newLang] = t;
        setTranslations(t);
      });
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    const brand = window.location.hostname.includes("viralex") ? "Viralex.ai" : "Piratex.ai";
    document.title = `${brand} — ${translations.app_tagline}`;
  }, [lang, translations]);

  return createElement(
    LanguageContext.Provider,
    { value: { lang, setLang, t: translations } },
    children,
  );
}

export function useTranslation() {
  return useContext(LanguageContext);
}

export function pluralRu(n: number, one: string, few: string, many: string): string {
  const abs = Math.abs(n) % 100;
  const lastDigit = abs % 10;
  if (abs > 10 && abs < 20) return many;
  if (lastDigit > 1 && lastDigit < 5) return few;
  if (lastDigit === 1) return one;
  return many;
}

export { SUPPORTED_LANGUAGES, type SupportedLanguage, type Translations } from "./types";
export { LANGUAGE_LABELS, LANGUAGE_FLAGS } from "./types";
