// Auth shim over Clerk. Replaces the old localStorage-JWT scheme: Clerk owns the
// session, mints the bearer token, and exposes a `window.Clerk` singleton once
// <ClerkProvider> mounts. React components should prefer Clerk's hooks directly;
// these helpers exist for (a) plain async code like lib/api.ts that needs the
// token outside React, and (b) drop-in replacements for the old call sites.
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

type ClerkGlobal = {
  user?: unknown;
  loaded?: boolean;
  load?: () => Promise<unknown>;
  session?: { getToken: (opts?: { template?: string }) => Promise<string | null> };
  signOut?: () => Promise<void>;
};

function clerk(): ClerkGlobal | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as unknown as { Clerk?: ClerkGlobal }).Clerk;
}

/** Fetch the current Clerk session token (JWT) for the Authorization header.
 *  Async — Clerk refreshes short-lived tokens on demand. Null when signed out.
 *
 *  On a fresh page load `window.Clerk` is attached before the session finishes
 *  hydrating, so the first queries can land here before the token exists. We
 *  wait for Clerk to finish loading first — otherwise those calls go out with no
 *  Authorization header, 401, and only recover on a later refetch (the burst of
 *  401s in the API log on every hard navigation). */
export async function getToken(): Promise<string | null> {
  try {
    const c = clerk();
    if (!c) return null; // Clerk script not attached yet → caller treats as signed-out
    if (c.loaded === false && typeof c.load === "function") {
      await c.load();
    }
    return (await c.session?.getToken()) ?? null;
  } catch {
    return null;
  }
}

/** Best-effort sign-out via the Clerk singleton, for non-hook call sites. */
export async function signOut(): Promise<void> {
  try {
    await clerk()?.signOut?.();
  } catch {
    /* ignore — caller still clears local UI state */
  }
}

/** Reactive auth state for conditional rendering. */
export function useIsAuthed(): boolean {
  const { isSignedIn } = useAuth();
  return !!isSignedIn;
}

/** Redirect to /login once Clerk has loaded and the visitor is signed out.
 *  Gating on `isLoaded` avoids a flash-redirect before Clerk hydrates. */
export function useRequireAuth(): boolean {
  const { isLoaded, isSignedIn } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/login");
  }, [isLoaded, isSignedIn, router]);
  return !!isSignedIn;
}
