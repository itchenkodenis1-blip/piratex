import { useEffect } from "react";
import { useLocation } from "react-router-dom";

// Counter id comes from the environment so each deployment uses its own
// Yandex.Metrika account. Leave VITE_YANDEX_METRIKA_ID empty to disable tracking.
const YM_ID = Number(import.meta.env.VITE_YANDEX_METRIKA_ID) || 0;

declare global {
  interface Window {
    ym?: (id: number, action: string, ...args: unknown[]) => void;
  }
}

/**
 * Tracks SPA page navigations in Yandex.Metrika.
 * Excluded from admin routes — mount only in public/user-facing parts.
 */
export function YandexMetrika() {
  const location = useLocation();

  useEffect(() => {
    if (YM_ID && window.ym) {
      window.ym(YM_ID, "hit", location.pathname + location.search);
    }
  }, [location.pathname, location.search]);

  return null;
}
