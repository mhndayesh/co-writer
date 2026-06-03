"use client";
import { Lock } from "lucide-react";
import { useEntitlement } from "@/lib/useEntitlement";
import { useUI } from "@/lib/store";
import { Btn } from "@/components/ui/Primitives";

/**
 * Banner shown above AI tools when the current plan can't run them right now
 * (free trial used up, or monthly Dev-AI allowance reached). Manual writing is
 * unaffected — only the AI assists are locked. Renders nothing when AI is free
 * to use, so it can be dropped in at the top of any AI page.
 */
export function AiLockNotice() {
  const { aiAvailable, isLoading, tier } = useEntitlement();
  const openUpgrade = useUI((s) => s.openUpgrade);
  if (isLoading || aiAvailable) return null;

  const trial = tier === "free";
  return (
    <div className="mb-4 flex items-center gap-3 rounded-lg border border-ink-gold/40 bg-ink-gold/10 p-3">
      <Lock size={16} className="text-ink-gold shrink-0" />
      <div className="flex-1 text-sm">
        <p className="text-ink-text">
          {trial ? "Your free AI trial is used up." : "You've reached this month's AI usage limit."}
        </p>
        <p className="text-xs text-ink-text2">
          You can still write and edit manually — subscribe to re-enable the AI tools.
        </p>
      </div>
      <Btn variant="primary" onClick={() => openUpgrade(trial ? "subscription_required" : "quota_exceeded")}>
        See plans
      </Btn>
    </div>
  );
}
