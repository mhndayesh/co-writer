"use client";
import { useQuery } from "@tanstack/react-query";
import { ArrowUp, ArrowDown, Hash, Activity } from "lucide-react";
import * as api from "@/lib/api";
import { useEntitlement } from "@/lib/useEntitlement";

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}k`;
  return `${n}`;
}

/**
 * Compact "tokens used" readout for the logged-in account only. Counts every AI
 * call's sent (tokens_in) + received (tokens_out) tokens, all-time, plus the
 * average per run — handy for estimating typical usage while testing. Refreshes
 * itself every few seconds so it tracks as you run AI actions.
 */
export function TokenCounter() {
  // Owner-only readout — same backend owner flag the API enforces (not a
  // hardcoded email), and it persists while shape-shifted for testing.
  const { isRealOwner } = useEntitlement();

  const { data } = useQuery({
    queryKey: ["token-stats"],
    queryFn: api.tokenStats,
    enabled: isRealOwner,
    refetchInterval: 8000,
  });

  if (!isRealOwner || !data) return null;

  return (
    <div className="px-2 py-1.5 text-[10px] text-ink-text3">
      <div className="flex items-center justify-between text-ink-text2 mb-0.5">
        <span className="inline-flex items-center gap-1 uppercase tracking-wider"><Activity size={10} /> Token usage</span>
        <span>{data.runs} runs</span>
      </div>
      <div className="flex items-center gap-2.5">
        <span className="inline-flex items-center gap-0.5" title="Sent to the model (prompt tokens)">
          <ArrowUp size={9} /> {fmt(data.tokens_in)}
        </span>
        <span className="inline-flex items-center gap-0.5" title="Returned by the model (completion tokens)">
          <ArrowDown size={9} /> {fmt(data.tokens_out)}
        </span>
        <span className="inline-flex items-center gap-0.5 text-ink-goldLight" title="Total tokens (in + out)">
          <Hash size={9} /> {fmt(data.total)}
        </span>
      </div>
      <div className="mt-0.5">
        avg {fmt(Math.round(data.avg_total))}/run
        <span className="text-ink-text3/80"> · {fmt(Math.round(data.avg_in))}↑ {fmt(Math.round(data.avg_out))}↓</span>
      </div>
    </div>
  );
}
