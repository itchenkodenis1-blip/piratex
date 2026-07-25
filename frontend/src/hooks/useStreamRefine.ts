import { useCallback, useEffect, useRef, useState } from "react";

export type RefineField = "script" | "description" | "editor_instructions" | "hook_variant";
export type RefineState = "idle" | "streaming" | "review";
export type RefineAction =
  | { actionKey: string; instruction?: never }
  | { instruction: string; actionKey?: never };

interface RefineQuota {
  used: number;
  limit: number;
}

interface UseStreamRefineOptions {
  jobId: string;
  field: RefineField;
  onAccept: (newText: string) => void;
  // When refining a translated (second-language) version, keep the refinement
  // in that language instead of the user's primary settings language.
  language?: string;
}

export function useStreamRefine({
  jobId,
  field,
  onAccept,
  language,
}: UseStreamRefineOptions) {
  const [state, setState] = useState<RefineState>("idle");
  const [streamedText, setStreamedText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<RefineQuota | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastActionRef = useRef<{ action: RefineAction; currentText: string } | null>(null);

  // Abort on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const startRefine = useCallback(
    async (action: RefineAction, currentText: string) => {
      abortRef.current?.abort();

      const controller = new AbortController();
      abortRef.current = controller;
      lastActionRef.current = { action, currentText };

      setState("streaming");
      setStreamedText("");
      setError(null);

      try {
        const token = localStorage.getItem("token");
        const res = await fetch(`/api/jobs/${jobId}/refine`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            field,
            ...(action.actionKey
              ? { action_key: action.actionKey }
              : { instruction: action.instruction }),
            current_text: currentText,
            ...(language ? { language } : {}),
          }),
          signal: controller.signal,
        });

        // Extract quota headers from response
        const usedHeader = res.headers.get("X-Refine-Used");
        const limitHeader = res.headers.get("X-Refine-Limit");
        if (usedHeader && limitHeader) {
          const u = parseInt(usedHeader, 10);
          const l = parseInt(limitHeader, 10);
          if (!isNaN(u) && !isNaN(l)) {
            setQuota({ used: u, limit: l });
          }
        }

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          const detail = errData.detail || `Error ${res.status}`;
          // On client/quota/rate limit errors go straight to idle (no stream to review)
          if (res.status === 400 || res.status === 429 || res.status === 403) {
            setError(detail);
            setState("idle");
            return;
          }
          throw new Error(detail);
        }

        const reader = res.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let accumulated = "";
        let buffer = "";

        reading: while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const data = JSON.parse(line.slice(6));
              if (data.done) break reading;
              if (data.error) {
                setError(data.error);
                break reading;
              }
              if (data.t) {
                accumulated += data.t;
                setStreamedText(accumulated);
              }
            } catch {
              // skip malformed JSON
            }
          }
        }

        await reader.cancel();
        setState("review");
      } catch (err: unknown) {
        if ((err as Error).name === "AbortError") return;
        setError((err as Error).message || "Refinement failed");
        setState("review");
      }
    },
    [jobId, field, language],
  );

  const accept = useCallback(() => {
    onAccept(streamedText);
    setState("idle");
    setStreamedText("");
    setError(null);
  }, [streamedText, onAccept]);

  const reject = useCallback(() => {
    setState("idle");
    setStreamedText("");
    setError(null);
  }, []);

  const retry = useCallback(() => {
    const last = lastActionRef.current;
    if (last) {
      startRefine(last.action, last.currentText);
    } else {
      reject();
    }
  }, [startRefine, reject]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setState("idle");
    setStreamedText("");
    setError(null);
  }, []);

  return {
    state,
    streamedText,
    error,
    quota,
    startRefine,
    accept,
    reject,
    retry,
    cancel,
  };
}
