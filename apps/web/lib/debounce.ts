import { useEffect, useRef } from "react";

// Debounced autosave hook. Fires `fn(value)` ~ `delay` ms after the last
// change. Skips the initial render so we don't immediately re-save what we
// just loaded.
export function useDebouncedSave<T>(value: T, delay: number, fn: (v: T) => void) {
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    const t = setTimeout(() => fn(value), delay);
    return () => clearTimeout(t);
  }, [value, delay, fn]);
}
