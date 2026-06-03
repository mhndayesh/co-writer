"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X, KeyRound, Sparkles, Check } from "lucide-react";
import Link from "next/link";
import * as api from "@/lib/api";
import { useUI } from "@/lib/store";
import { Btn } from "@/components/ui/Primitives";

const REASON_COPY: Record<string, { title: string; body: string }> = {
  subscription_required: {
    title: "Subscribe to keep writing with AI",
    body: "Your free AI trial is used up. Pick a plan to keep the AI tools flowing.",
  },
  quota_exceeded: {
    title: "You've hit this month's AI limit",
    body: "Upgrade your plan, or wait for your allowance to reset at the start of next month.",
  },
  byok_key_missing: {
    title: "Add your own API key",
    body: "Your plan runs on your own provider keys. Add one in Settings — or switch to the Plus plan.",
  },
  manual: {
    title: "Choose your plan",
    body: "Unlock the AI writing tools with the plan that fits how you work.",
  },
};

export function UpgradeModal() {
  const { upgradeOpen, upgradeReason, closeUpgrade } = useUI();
  const qc = useQueryClient();
  const { data: plans } = useQuery({ queryKey: ["billing-plans"], queryFn: api.billingPlans, enabled: upgradeOpen });

  const checkout = useMutation({
    mutationFn: (tier: api.Tier) => api.billingCheckout(tier),
    onSuccess: (res) => {
      if (res.url && !res.activated) { window.location.href = res.url; return; }
      qc.invalidateQueries({ queryKey: ["billing-me"] });
      qc.invalidateQueries({ queryKey: ["llm-status"] });
      qc.invalidateQueries({ queryKey: ["llm-config"] });
      qc.invalidateQueries({ queryKey: ["me"] });
      closeUpgrade();
    },
  });

  if (!upgradeOpen) return null;
  const copy = REASON_COPY[upgradeReason] || REASON_COPY.manual;
  const paid = (plans || []).filter((p) => p.requires_subscription);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={closeUpgrade}>
      <div className="w-full max-w-2xl card-ink p-6 relative" onClick={(e) => e.stopPropagation()}>
        <button className="absolute right-4 top-4 text-ink-text3 hover:text-ink-text" onClick={closeUpgrade} aria-label="Close">
          <X size={18} />
        </button>
        <h2 className="text-2xl font-display text-ink-text pr-8">{copy.title}</h2>
        <p className="text-sm text-ink-text2 mt-1 mb-5">{copy.body}</p>

        <div className="grid gap-4 md:grid-cols-2">
          {paid.map((p) => (
            <div key={p.tier} className="rounded-lg border border-ink-border bg-ink-surface2/50 p-4 flex flex-col">
              <div className="flex items-center gap-2 mb-1">
                {p.tier === "byok" ? <KeyRound size={16} className="text-ink-gold" /> : <Sparkles size={16} className="text-ink-gold" />}
                <h3 className="font-display text-lg">{p.name}</h3>
              </div>
              <p className="text-sm text-ink-text2 flex-1">{p.blurb}</p>
              <ul className="text-xs text-ink-text3 my-3 space-y-1">
                {p.tier === "dev_ai" && <li className="flex items-center gap-1"><Check size={12} /> {p.max_actions ?? "—"} AI actions / month</li>}
                {p.tier === "dev_ai" && <li className="flex items-center gap-1"><Check size={12} /> No API keys to manage</li>}
                {p.tier === "byok" && <li className="flex items-center gap-1"><Check size={12} /> Use your own provider keys</li>}
                {p.tier === "byok" && <li className="flex items-center gap-1"><Check size={12} /> Unlimited on our side</li>}
              </ul>
              <div className="text-sm text-ink-text mb-3">{p.price_label || "Price coming soon"}</div>
              <Btn variant="primary" disabled={checkout.isPending} onClick={() => checkout.mutate(p.tier)}>
                {checkout.isPending ? "Working…" : `Choose ${p.name}`}
              </Btn>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between mt-4">
          <Link href="/pricing" className="text-xs text-ink-text3 hover:text-ink-goldLight underline" onClick={closeUpgrade}>
            Compare plans
          </Link>
          <p className="text-xs text-ink-text3">Pricing is being finalized.</p>
        </div>
      </div>
    </div>
  );
}
