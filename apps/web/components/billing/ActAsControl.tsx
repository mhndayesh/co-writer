"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Drama } from "lucide-react";
import * as api from "@/lib/api";
import { useEntitlement } from "@/lib/useEntitlement";
import { Btn } from "@/components/ui/Primitives";

// The tiers an owner can "become" to test the real per-tier experience.
const OPTIONS: { value: api.Tier; label: string }[] = [
  { value: "owner", label: "Owner (you)" },
  { value: "free", label: "Free" },
  { value: "dev_ai", label: "Paid" },
  { value: "byok", label: "BYOK" },
];

/** Owner-only: flip your effective tier to test how each user type experiences the
 *  app. Persistent — it sticks until you switch back. Renders nothing for non-owners. */
export function ActAsControl() {
  const qc = useQueryClient();
  const { isRealOwner, actingAs } = useEntitlement();

  const set = useMutation({
    mutationFn: (tier: api.Tier) => api.adminSetActAs(tier),
    onSuccess: () => {
      // The whole app reads the entitlement + resolved provider — re-fetch all of it.
      qc.invalidateQueries({ queryKey: ["billing-me"] });
      qc.invalidateQueries({ queryKey: ["llm-config"] });
      qc.invalidateQueries({ queryKey: ["llm-status"] });
    },
  });

  if (!isRealOwner) return null;
  const current = actingAs ?? "owner";

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm text-ink-text2">
        <Drama size={15} className="text-ink-gold" />
        <span>View the app as:</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {OPTIONS.map((o) => (
          <Btn
            key={o.value}
            variant={current === o.value ? "primary" : "ghost"}
            onClick={() => set.mutate(o.value)}
            disabled={set.isPending}
          >
            {o.label}
          </Btn>
        ))}
      </div>
      <p className="text-xs text-ink-text3">
        Test mode is real: it changes your AI routing, limits and screens until you switch back to Owner.
        While viewing as Paid, your AI runs count toward that plan&apos;s limit (so you can watch it kick in).
      </p>
    </div>
  );
}
