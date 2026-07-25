import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AdaptationSummary,
  FrameAnalysis,
  ProgressUpdate,
  StrategyData,
  TranscriptSegment,
} from "../types";

export interface LiveData {
  metadata: {
    title: string | null;
    duration: number | null;
    platform: string | null;
    author: string | null;
    views: number | null;
    likes: number | null;
    comments: number | null;
    thumbnail: string | null;
  } | null;
  transcript: TranscriptSegment[] | null;
  frameStubs: { frame_index: number; timestamp: number; timecode: string }[] | null;
  analyzedFrames: Map<number, FrameAnalysis>;
  summary: AdaptationSummary | null;
  strategy: StrategyData | null;
}

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_DELAY = 1000;

export function useJobWebSocket(jobId: string | null) {
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);
  const [liveData, setLiveData] = useState<LiveData>({
    metadata: null,
    transcript: null,
    frameStubs: null,
    analyzedFrames: new Map(),
    summary: null,
    strategy: null,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const progressRef = useRef<ProgressUpdate | null>(null);

  const disconnect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    progressRef.current = null;
    setProgress(null);
    setLiveData({
      metadata: null,
      transcript: null,
      frameStubs: null,
      analyzedFrames: new Map(),
      summary: null,
      strategy: null,
    });
  }, []);

  useEffect(() => {
    if (!jobId) return;

    reset();
    reconnectAttempts.current = 0;
    let tokenListener: (() => void) | null = null;

    function connect() {
      const token = localStorage.getItem("token");
      if (!token) {
        // Token not yet available (anonymous user, getMe still in flight).
        // Listen for token-ready event and retry once.
        const onTokenReady = () => {
          tokenListener = null;
          window.removeEventListener("piratex:token-ready", onTokenReady);
          connect();
        };
        tokenListener = onTokenReady;
        window.addEventListener("piratex:token-ready", onTokenReady);
        return;
      }
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(
        `${protocol}//${window.location.host}/ws/jobs/${jobId}?token=${encodeURIComponent(token)}`
      );
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttempts.current = 0;
      };

      ws.onmessage = (event) => {
        let msg;
        try {
          msg = JSON.parse(event.data);
        } catch {
          return; // Malformed JSON — skip
        }

        if (msg.type === "progress" || (!msg.type && msg.status)) {
          const update: ProgressUpdate = {
            status: msg.status,
            progress: msg.progress,
            message: msg.message,
            error: msg.error,
          };
          progressRef.current = update;
          setProgress(update);
        } else if (msg.type === "metadata") {
          setLiveData((prev) => ({
            ...prev,
            metadata: {
              title: msg.title,
              duration: msg.duration,
              platform: msg.platform,
              author: msg.author,
              views: msg.views,
              likes: msg.likes,
              comments: msg.comments,
              thumbnail: msg.thumbnail ?? null,
            },
          }));
        } else if (msg.type === "transcript") {
          setLiveData((prev) => ({
            ...prev,
            transcript: msg.segments,
          }));
        } else if (msg.type === "frame_stub") {
          // Per-frame event: append one stub as it arrives
          setLiveData((prev) => ({
            ...prev,
            frameStubs: [...(prev.frameStubs ?? []), msg.frame],
          }));
        } else if (msg.type === "frames_extracted") {
          // Batch fallback (legacy)
          setLiveData((prev) => ({
            ...prev,
            frameStubs: msg.frames,
          }));
        } else if (msg.type === "frame_analyzed") {
          setLiveData((prev) => {
            const updated = new Map(prev.analyzedFrames);
            updated.set(msg.frame.frame_index, msg.frame);
            return { ...prev, analyzedFrames: updated };
          });
        } else if (msg.type === "content_ready") {
          setLiveData((prev) => ({
            ...prev,
            summary: msg.summary,
          }));
        } else if (msg.type === "strategy_ready") {
          setLiveData((prev) => ({
            ...prev,
            strategy: msg.strategy,
          }));
        }
      };

      ws.onerror = () => {
        // onerror is always followed by onclose — reconnect logic is there
      };

      ws.onclose = (event) => {
        wsRef.current = null;

        // Don't reconnect on auth errors — token won't change between attempts
        if (event.code === 4001 || event.code === 4003) return;

        // Don't reconnect if job is already completed or failed
        const status = progressRef.current;
        if (
          status?.status === "completed" ||
          status?.status === "failed"
        ) {
          return;
        }

        // Exponential backoff reconnect
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttempts.current);
          reconnectAttempts.current += 1;
          reconnectTimer.current = setTimeout(connect, delay);
        }
      };
    }

    connect();

    return () => {
      if (tokenListener) {
        window.removeEventListener("piratex:token-ready", tokenListener);
      }
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [jobId, reset]);

  return { progress, liveData, disconnect, reset };
}
