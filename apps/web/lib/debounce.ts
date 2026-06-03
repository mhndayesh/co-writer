import { useEffect, useRef } from "react";

// Debounced autosave hook. Fires `fn(value)` ~ `delay` ms after the last change.
// Skips the initial render so we don't immediately re-save what we just loaded.
//
// Crucially it also FLUSHES a still-pending save on unmount, route change, and
// `beforeunload` — otherwise the cleanup just clears the timer and the last
// <delay> ms of edits are silently dropped whenever you navigate away (switching
// chapters/characters/scenes/etc. mid-type). The latest value + fn are held in
// refs so the flush always saves what's actually on screen, not a stale closure.
export function useDebouncedSave<T>(value: T, delay: number, fn: (v: T) => void) {
  const first = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pending = useRef(false);
  const latest = useRef(value);
  const fnRef = useRef(fn);
  latest.current = value;
  fnRef.current = fn;

  // Schedule a save whenever the value changes.
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    pending.current = true;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      pending.current = false;
      timer.current = null;
      fnRef.current(latest.current);
    }, delay);
    // Note: no flush here — a value change shouldn't force an immediate save.
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [value, delay]);

  // Flush a pending save on unmount/navigation and on tab close. Defined inside
  // the effect so it closes over the stable refs (pending/timer/fnRef/latest) and
  // the same function instance is used for both the listener and the cleanup.
  useEffect(() => {
    const flush = () => {
      if (!pending.current) return;
      pending.current = false;
      if (timer.current) { clearTimeout(timer.current); timer.current = null; }
      fnRef.current(latest.current);
    };
    window.addEventListener("beforeunload", flush);
    return () => {
      window.removeEventListener("beforeunload", flush);
      flush();
    };
  }, []);
}
