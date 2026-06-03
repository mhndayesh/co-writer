"use client";
import { useQuery } from "@tanstack/react-query";
import * as api from "@/lib/api";
import { useIsAuthed } from "@/lib/auth";

/**
 * Current subscription entitlement + usage meter. Backed by GET /v1/billing/me.
 * Used to lock AI buttons proactively and render the usage meter. The query key
 * "billing-me" is invalidated after checkout so the UI reflects a new plan.
 */
export function useEntitlement() {
  const authed = useIsAuthed();
  const q = useQuery({
    queryKey: ["billing-me"],
    queryFn: api.billingMe,
    enabled: authed,
    staleTime: 30_000,
  });
  const ent = q.data;
  return {
    entitlement: ent,
    isLoading: q.isLoading,
    // Default to allowing while loading so we never flash a lock on a paying user.
    aiAvailable: ent ? ent.ai_available : true,
    tier: ent?.effective_tier ?? "free",
    planTier: ent?.plan_tier ?? "free",
    planStatus: ent?.plan_status ?? "none",
    isByok: ent?.key_source === "user",
    isOwner: ent?.effective_tier === "owner",
    metered: ent?.metered ?? false,
    // Owner "shape-shift": which tier the owner is viewing as (null = not testing).
    actingAs: ent?.acting_as ?? null,
    // The REAL owner flag — true even while the owner is simulating a lower tier,
    // so owner-only UI (control panel, banner) stays visible during a test.
    isRealOwner: ent?.is_owner ?? false,
  };
}
