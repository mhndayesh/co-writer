"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Drama, X } from "lucide-react";
import * as api from "@/lib/api";
import { useEntitlement } from "@/lib/useEntitlement";

const LABEL: Record<string, string> = { free: "Free", dev_ai: "Paid", byok: "BYOK", owner: "Owner" };

/** Persistent banner shown only while the owner is shape-shifted into another tier.
 *  Mounted app-wide (in Providers) so it follows the owner across every page. */
export function TestModeBanner() {
  const qc = useQueryClient();
  const { isRealOwner, actingAs } = useEntitlement();

  const exit = useMutation({
    mutationFn: () => api.adminClearActAs(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing-me"] });
      qc.invalidateQueries({ queryKey: ["llm-config"] });
      qc.invalidateQueries({ queryKey: ["llm-status"] });
    },
  });

  if (!isRealOwner || !actingAs) return null;

  return (
    // In normal flow (not fixed) so it pushes the sticky GlobalNav down instead of
    // overlapping it. It's mounted above GlobalNav in the tree, so it sits at the
    // very top of the page; when you scroll, it scrolls away and the nav sticks.
    <div className="w-full flex items-center justify-center gap-3 bg-ink-gold/15 border-b border-ink-gold/40 px-4 py-1.5 text-xs text-ink-text">
      <Drama size={13} className="text-ink-gold" />
      <span>
        Test mode — viewing the app as <strong>{LABEL[actingAs] ?? actingAs}</strong>.
      </span>
      <button
        onClick={() => exit.mutate()}
        disabled={exit.isPending}
        className="inline-flex items-center gap-1 rounded border border-ink-gold/50 px-2 py-0.5 font-medium text-ink-gold hover:bg-ink-gold/10"
      >
        <X size={11} /> {exit.isPending ? "Exiting…" : "Exit test mode"}
      </button>
    </div>
  );
}
