import { useEffect, useRef, useState } from "react";

export interface UsePollOptions<T> {
  fetchFn: () => Promise<T>;
  isDone: (data: T) => boolean;
  enabled?: boolean;
  intervalMs?: number;
  onComplete?: (data: T) => void;
  /**
   * Stop polling after this many **consecutive** fetch errors.
   * Resets to 0 on every successful fetch.
   * Defaults to 5 — prevents hammering a dead / restarted server indefinitely.
   */
  maxConsecutiveErrors?: number;
}

/**
 * Polls `fetchFn` every `intervalMs` until `isDone` returns true.
 * Uses recursive setTimeout (not setInterval) to avoid overlapping requests.
 * Cleans up on unmount and when `enabled` turns false.
 * Stops automatically after `maxConsecutiveErrors` consecutive fetch failures.
 */
export function usePoll<T>({
  fetchFn,
  isDone,
  enabled = true,
  intervalMs = 2000,
  onComplete,
  maxConsecutiveErrors = 5,
}: UsePollOptions<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const cancelledRef = useRef(false);
  const consecutiveErrorsRef = useRef(0);
  // Keep latest callbacks in refs so the effect closure never goes stale
  const cbRef = useRef({ fetchFn, isDone, onComplete });
  cbRef.current = { fetchFn, isDone, onComplete };

  useEffect(() => {
    if (!enabled) return;

    setDone(false);
    setError(null);
    cancelledRef.current = false;
    consecutiveErrorsRef.current = 0;

    let timeoutId: ReturnType<typeof setTimeout>;

    const tick = async () => {
      if (cancelledRef.current) return;
      try {
        const result = await cbRef.current.fetchFn();
        if (cancelledRef.current) return;
        consecutiveErrorsRef.current = 0;
        setData(result);
        setError(null);
        if (cbRef.current.isDone(result)) {
          setDone(true);
          cbRef.current.onComplete?.(result);
          return;
        }
      } catch (err) {
        if (cancelledRef.current) return;
        consecutiveErrorsRef.current += 1;
        setError(err instanceof Error ? err.message : "Poll error");
        // Stop polling after maxConsecutiveErrors failures to avoid
        // hammering a server that has restarted and lost in-memory job state.
        if (consecutiveErrorsRef.current >= maxConsecutiveErrors) {
          return;
        }
      }
      if (!cancelledRef.current) {
        timeoutId = setTimeout(tick, intervalMs);
      }
    };

    tick();

    return () => {
      cancelledRef.current = true;
      clearTimeout(timeoutId);
    };
  }, [enabled, intervalMs, maxConsecutiveErrors]);

  return { data, error, done };
}
