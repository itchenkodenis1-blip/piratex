import { useEffect, useRef, useState } from "react";
import { getJob } from "../api/client";
import type { JobResult } from "../types";

export function useJobPolling(jobId: string | null, enabled: boolean = true) {
  const [result, setResult] = useState<JobResult | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setResult(null);
    if (!jobId || !enabled) return;

    const poll = async () => {
      try {
        const data = await getJob(jobId);
        setResult(data);
        if (data.status === "completed" || data.status === "failed") {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch {
        // Ignore polling errors
      }
    };

    poll();
    intervalRef.current = setInterval(poll, 3000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [jobId, enabled]);

  return result;
}
