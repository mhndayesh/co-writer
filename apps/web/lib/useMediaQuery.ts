"use client";
import { useEffect, useState } from "react";

/** SSR-safe media-query hook. Returns false on the server and on first client
 *  render (so markup matches and there's no hydration mismatch), then updates to
 *  the real match after mount and on viewport changes. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

/** True on phones + tablets in portrait (below Tailwind's `lg` = 1024px), where
 *  the studio switches its sidebar to a slide-in drawer. */
export function useIsMobile(): boolean {
  return useMediaQuery("(max-width: 1023px)");
}
