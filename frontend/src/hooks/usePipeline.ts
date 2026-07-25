import { useCallback, useEffect, useRef, useState } from "react";
import type { PipelineItem, ProductionStatus } from "../types";
import { changePipelineStatus, getPipelineItems } from "../api/client";

const MAX_RECONNECT = 5;
const RECONNECT_BASE = 1500;

export function usePipeline(userId: string | null) {
  const [items, setItems] = useState<PipelineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Fetch ──────────────────────────────────────────────────
  const fetchItems = useCallback(async () => {
    try {
      const data = await getPipelineItems();
      setItems(data);
      setError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load pipeline";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  // ── WebSocket ──────────────────────────────────────────────
  useEffect(() => {
    if (!userId) return;

    function connect() {
      const token = localStorage.getItem("token");
      if (!token) return;
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(
        `${protocol}//${window.location.host}/ws/pipeline/${userId}?token=${encodeURIComponent(token)}`
      );
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttempts.current = 0;
      };

      ws.onmessage = (event) => {
        let msg: { type?: string; script_id?: string; production_status?: string };
        try {
          msg = JSON.parse(event.data);
        } catch {
          return;
        }

        if (msg.type === "status_changed") {
          // Re-fetch the full list to stay in sync
          fetchItems();
        }
      };

      ws.onclose = (event) => {
        wsRef.current = null;
        // Don't reconnect on auth errors — token won't change between attempts
        if (event.code === 4001 || event.code === 4003) return;
        if (reconnectAttempts.current < MAX_RECONNECT) {
          const delay = RECONNECT_BASE * Math.pow(2, reconnectAttempts.current);
          reconnectAttempts.current += 1;
          reconnectTimer.current = setTimeout(connect, delay);
        }
      };
    }

    connect();

    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [userId, fetchItems]);

  // ── Initial fetch ──────────────────────────────────────────
  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // ── Mutations ──────────────────────────────────────────────
  const changeStatus = useCallback(
    async (scriptId: string, newStatus: ProductionStatus, comment?: string) => {
      // Optimistic update
      setItems((prev) =>
        prev.map((item) =>
          item.script_id === scriptId
            ? { ...item, production_status: newStatus }
            : item
        )
      );

      try {
        await changePipelineStatus(scriptId, newStatus, comment);
      } catch {
        // Revert on failure — re-fetch
        await fetchItems();
        throw new Error("Status change failed");
      }
    },
    [fetchItems]
  );

  return { items, loading, error, refetch: fetchItems, changeStatus };
}
