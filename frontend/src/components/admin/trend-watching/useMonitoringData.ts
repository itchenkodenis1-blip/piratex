import { useCallback, useEffect, useRef, useState } from "react";
import {
  adminGetTrendWatchingStats,
  adminGetTrendWatchingPipeline,
  adminGetTrendWatchingActivity,
  adminGetTrendWatchingSparklines,
} from "../../../api/client";
import type {
  TrendWatchingStats,
  TrendWatchingPipeline,
  TrendWatchingSparklines,
  TrendWatchingActivityEvent,
} from "../../../types";

export type WsStatus = "connecting" | "connected" | "disconnected";

export function useMonitoringData() {
  const [stats, setStats] = useState<TrendWatchingStats | null>(null);
  const [pipeline, setPipeline] = useState<TrendWatchingPipeline | null>(null);
  const [activity, setActivity] = useState<TrendWatchingActivityEvent[]>([]);
  const [sparklines, setSparklines] = useState<TrendWatchingSparklines | null>(null);
  const [wsStatus, setWsStatus] = useState<WsStatus>("disconnected");
  const [loading, setLoading] = useState(true);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Initial fetch
  const fetchAll = useCallback(async () => {
    try {
      const [s, p, a, sp] = await Promise.all([
        adminGetTrendWatchingStats(),
        adminGetTrendWatchingPipeline(),
        adminGetTrendWatchingActivity(),
        adminGetTrendWatchingSparklines(),
      ]);
      setStats(s);
      setPipeline(p);
      setActivity(a.events);
      setSparklines(sp);
    } catch (e) {
      console.error("[monitoring] fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  // WebSocket connection
  const connectWs = useCallback(() => {
    const token = localStorage.getItem("token") || document.cookie.replace(/(?:(?:^|.*;\s*)token\s*=\s*([^;]*).*$)|^.*$/, "$1");
    if (!token) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws/admin/trend-watching?token=${encodeURIComponent(token)}`;

    setWsStatus("connecting");
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus("connected");
      reconnectAttempts.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Update pipeline state based on event type
        if (data.type === "profile_status") {
          setPipeline((prev) => {
            if (!prev) return prev;
            const profile = {
              profile_id: data.profile_id,
              username: data.username || "",
              platform: data.platform || "instagram",
              display_name: null,
              followers_count: null,
              niche: null,
              check_priority: "normal",
              last_checked_at: null,
              trending_count: data.details?.trending_count || 0,
              error: data.error,
              details: data.details,
            };

            // Remove from all columns first
            const removeFrom = (arr: typeof prev.queued) =>
              arr.filter((p) => p.profile_id !== data.profile_id);

            const next = {
              queued: removeFrom(prev.queued),
              scraping: removeFrom(prev.scraping),
              analyzing: removeFrom(prev.analyzing),
              completed: removeFrom(prev.completed),
              failed: removeFrom(prev.failed),
            };

            // Add to the correct column
            if (data.status === "scraping") next.scraping = [profile, ...next.scraping];
            else if (data.status === "analyzing") next.analyzing = [profile, ...next.analyzing];
            else if (data.status === "completed") next.completed = [profile, ...next.completed.slice(0, 19)];
            else if (data.status === "failed") next.failed = [profile, ...next.failed.slice(0, 9)];

            return next;
          });
        }

        // Prepend to activity feed
        if (data.type && data.timestamp) {
          setActivity((prev) => [data as TrendWatchingActivityEvent, ...prev.slice(0, 99)]);
        }

        // Update stats on stats_update (only known fields)
        if (data.type === "stats_update") {
          setStats((prev) => {
            if (!prev) return prev;
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            const { type, timestamp, ...updates } = data;
            return { ...prev, ...updates };
          });
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onclose = (event) => {
      setWsStatus("disconnected");
      wsRef.current = null;
      // Don't reconnect on auth errors
      if (event.code === 4001 || event.code === 4003) return;
      // Exponential backoff reconnect
      const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000);
      reconnectAttempts.current++;
      reconnectTimer.current = setTimeout(connectWs, delay);
    };

    ws.onerror = () => {
      // onerror is always followed by onclose
    };
  }, []);

  // Polling fallback for stats (every 30s)
  useEffect(() => {
    fetchAll();
    const interval = setInterval(async () => {
      try {
        const [s, sp] = await Promise.all([
          adminGetTrendWatchingStats(),
          adminGetTrendWatchingSparklines(),
        ]);
        setStats(s);
        setSparklines(sp);
      } catch {
        // silent
      }
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  // WebSocket lifecycle
  useEffect(() => {
    connectWs();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connectWs]);

  return { stats, pipeline, activity, sparklines, wsStatus, loading, refetch: fetchAll };
}
