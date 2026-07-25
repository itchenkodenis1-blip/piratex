import { useCallback, useEffect, useState } from "react";
import { getMe, logout as apiLogout } from "../api/client";
import type { AuthUser, UsageInfo } from "../types";

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const res = await getMe();
      setUser(res.user);
      setUsage(res.usage);
      // Store JWT for anonymous users (enables WebSocket connection)
      // Always update: old token may be expired
      if (res.token) {
        localStorage.setItem("token", res.token);
        window.dispatchEvent(new Event("piratex:token-ready"));
      }
    } catch {
      setUser(null);
      setUsage(null);
    }
  }, []);

  useEffect(() => {
    refreshUser().finally(() => setLoading(false));
  }, [refreshUser]);

  // Background polling: refresh user & usage every 5 min to catch tier changes
  const isLoggedIn = user != null;
  useEffect(() => {
    if (!isLoggedIn) return;
    const interval = setInterval(async () => {
      try {
        const res = await getMe();
        setUser(res.user);
        setUsage(res.usage);
      } catch { /* ignore — next poll will retry */ }
    }, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [isLoggedIn]);

  const logout = useCallback(async () => {
    localStorage.removeItem("token");
    setUser(null);
    setUsage(null);
    try { await apiLogout(); } catch { /* ignore */ }
    refreshUser();
  }, [refreshUser]);

  return { user, usage, loading, logout, refreshUser };
}
