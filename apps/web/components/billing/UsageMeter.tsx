"use client";
import { KeyRound, Sparkles, Gift, Crown } from "lucide-react";
import { useEntitlement } from "@/lib/useEntitlement";
import { useUI } from "@/lib/store";

const TIER_LABEL: Record<string, string> = {
  free: "Free trial",
  dev_ai: "Plus",
  byok: "Your own keys",
  owner: "Owner",
};

/** Compact subscription + usage readout for the studio sidebar. */
export function UsageMeter() {
  const { entitlement: e } = useEntitlement();
  const openUpgrade = useUI((s) => s.openUpgrade);
  if (!e) return null;

  const tier = e.effective_tier;
  const label = TIER_LABEL[tier] ?? tier;
  const Icon = tier === "owner" ? Crown : tier === "byok" ? KeyRound : tier === "free" ? Gift : Sparkles;

  const cap = e.limits.max_actions;
  const used = e.usage.actions_used;
  const showBar = e.metered && cap != null;
  const pct = showBar ? Math.min(100, Math.round((used / Math.max(1, cap as number)) * 100)) : 0;
  const exhausted = !e.ai_available;

  return (
    <div className="px-2 py-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-ink-text2">
          <Icon size={12} className="text-ink-gold" /> {label}
        </span>
        {tier !== "byok" && tier !== "owner" && (
          <button
            onClick={() => openUpgrade("manual")}
            className="text-[10px] uppercase tracking-wider text-ink-goldLight hover:underline"
          >
            {tier === "free" ? "Upgrade" : "Manage"}
          </button>
        )}
      </div>

      {showBar && (
        <div className="mt-1">
          <div className="h-1 rounded-full bg-ink-surface3 overflow-hidden">
            <div
              className={`h-full rounded-full ${exhausted ? "bg-ink-red" : "bg-ink-gold"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="text-[10px] text-ink-text3 mt-0.5">
            {used}/{cap} AI actions {e.period === "lifetime" ? "(trial)" : "this month"}
          </div>
        </div>
      )}

      {tier === "byok" && <div className="text-[10px] text-ink-text3 mt-0.5">Unlimited · billed by your provider</div>}
      {tier === "owner" && <div className="text-[10px] text-ink-text3 mt-0.5">Unlimited · owner account</div>}
    </div>
  );
}
