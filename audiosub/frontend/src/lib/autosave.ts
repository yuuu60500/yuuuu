"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, Segment } from "./api";

type Patch = Partial<Pick<Segment, "start_time" | "end_time" | "original_text" | "translated_text" | "speaker">>;
export type SaveState = "idle" | "pending" | "saving" | "saved" | "error";

const DELAY_MS = 700;
const RETRY_MS = 3000;

/**
 * Debounced per-segment autosave. Edits are merged per segment and sent as a
 * single PATCH; failed saves are kept and retried so nothing is lost.
 */
export function useAutosave(onSaved: (segment: Segment) => void) {
  const pending = useRef(new Map<string, Patch>());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inflight = useRef<Promise<void> | null>(null);
  const [state, setState] = useState<SaveState>("idle");
  const [lastError, setLastError] = useState<string | null>(null);
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;

  const run = useCallback(async (): Promise<void> => {
    if (inflight.current) await inflight.current;
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    if (pending.current.size === 0) return;
    const batch = new Map(pending.current);
    pending.current.clear();
    setState("saving");
    const work = (async () => {
      let failed = false;
      for (const [id, patch] of batch) {
        try {
          onSavedRef.current(await api.updateSegment(id, patch));
        } catch (e) {
          const status = (e as { status?: number }).status;
          if (status === 404) continue; // segment was deleted meanwhile
          failed = true;
          setLastError(e instanceof Error ? e.message : String(e));
          // Keep the failed edit (newer edits for the same segment win).
          if (status !== 422) pending.current.set(id, { ...patch, ...pending.current.get(id) });
        }
      }
      if (failed) {
        setState("error");
        if (pending.current.size) timer.current = setTimeout(() => void run(), RETRY_MS);
      } else {
        setLastError(null);
        setState(pending.current.size ? "pending" : "saved");
      }
    })();
    inflight.current = work;
    await work;
    inflight.current = null;
  }, []);

  const queue = useCallback(
    (id: string, patch: Patch) => {
      pending.current.set(id, { ...pending.current.get(id), ...patch });
      setState("pending");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void run(), DELAY_MS);
    },
    [run],
  );

  const drop = useCallback((id: string) => {
    pending.current.delete(id);
  }, []);

  // Warn before leaving with unsaved edits.
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (pending.current.size || inflight.current) {
        void run();
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [run]);

  return { queue, flush: run, drop, state, lastError };
}
