import { useState, useCallback, useEffect, useRef } from "react";
import { useAuth } from "./useAuth";

const STORAGE_KEY_COUNT = "tg_promo_count";
const STORAGE_KEY_LAST = "tg_promo_last";
const STORAGE_KEY_STOP = "tg_promo_stop";
const SESSION_KEY = "tg_promo_session";

const MAX_SHOWS = 3;
// Progressive cooldown: after 1st show wait 1 day, after 2nd wait 3 days
const COOLDOWN_DAYS = [0, 1, 3];

function getCount(): number {
  return parseInt(localStorage.getItem(STORAGE_KEY_COUNT) || "0", 10);
}

function getLastShown(): Date | null {
  const raw = localStorage.getItem(STORAGE_KEY_LAST);
  return raw ? new Date(raw) : null;
}

function isStopped(): boolean {
  return localStorage.getItem(STORAGE_KEY_STOP) === "true";
}

function isShownThisSession(): boolean {
  return sessionStorage.getItem(SESSION_KEY) === "true";
}

function daysSince(date: Date): number {
  return (Date.now() - date.getTime()) / (1000 * 60 * 60 * 24);
}

/** Compute whether promo is eligible (pure, reads localStorage only) */
function computeEligible(hasTelegram: boolean, isLoggedIn: boolean): boolean {
  if (hasTelegram || !isLoggedIn) return false;

  const count = getCount();
  if (count >= MAX_SHOWS || isStopped()) return false;
  if (isShownThisSession()) return false;

  const lastShown = getLastShown();
  if (lastShown) {
    const requiredDays = COOLDOWN_DAYS[Math.min(count, COOLDOWN_DAYS.length - 1)];
    if (daysSince(lastShown) < requiredDays) return false;
  }

  return true;
}

/**
 * Hook to manage Telegram promo display logic.
 *
 * Returns:
 * - canShow: whether the promo should be displayed right now
 * - markShown: call when the promo is displayed to the user
 * - dismiss: call when user clicks "Not now"
 * - dismissForever: call when user clicks "Don't show again"
 * - showCount: how many times the promo has been shown
 * - hasTelegram: whether user has Telegram connected
 */
export function useTelegramPromo() {
  const { user } = useAuth();
  const hasTelegram = user?.telegram_user_id != null;
  const isLoggedIn = user != null && !user.is_anonymous;

  const [dismissed, setDismissed] = useState(false);
  const [showCount, setShowCount] = useState(() => getCount());
  const cleanedRef = useRef(false);

  // Clean up localStorage when Telegram gets connected externally (subscription to auth state)
  useEffect(() => {
    if (hasTelegram && !cleanedRef.current) {
      cleanedRef.current = true;
      localStorage.removeItem(STORAGE_KEY_COUNT);
      localStorage.removeItem(STORAGE_KEY_LAST);
      localStorage.removeItem(STORAGE_KEY_STOP);
      sessionStorage.removeItem(SESSION_KEY);
      setShowCount(0);
    }
    if (!hasTelegram) {
      cleanedRef.current = false;
    }
  }, [hasTelegram]);

  const canShow = !dismissed && computeEligible(hasTelegram, isLoggedIn);

  const markShown = useCallback(() => {
    // Synchronously mark session to prevent concurrent instances from also showing
    sessionStorage.setItem(SESSION_KEY, "true");
    const newCount = getCount() + 1;
    localStorage.setItem(STORAGE_KEY_COUNT, String(newCount));
    localStorage.setItem(STORAGE_KEY_LAST, new Date().toISOString());
    setShowCount(newCount);
  }, []);

  const dismiss = useCallback(() => {
    sessionStorage.setItem(SESSION_KEY, "true");
    setDismissed(true);
  }, []);

  const dismissForever = useCallback(() => {
    localStorage.setItem(STORAGE_KEY_STOP, "true");
    sessionStorage.setItem(SESSION_KEY, "true");
    setDismissed(true);
  }, []);

  return { canShow, markShown, dismiss, dismissForever, showCount, hasTelegram };
}
