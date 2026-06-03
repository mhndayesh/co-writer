"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftCircle, Cpu, KeyRound, Sparkles, Gift, Lock, CheckCircle2 } from "lucide-react";
import * as api from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { useUI } from "@/lib/store";
import { useEntitlement } from "@/lib/useEntitlement";
import { Btn, Card, Inp, PageHdr, Tag } from "@/components/ui/Primitives";
import { ProviderForm, ProviderValue, emptyProvider, type Provider } from "@/components/settings/ProviderForm";
import { OwnerPanel } from "@/components/settings/OwnerPanel";

function toValue(p?: api.LaneConfig | null, fallback: Provider = "lmstudio"): ProviderValue {
  if (!p || !p.provider) return emptyProvider(fallback);
  return {
    provider: p.provider as Provider,
    base_url: p.base_url || "",
    model: p.model || "",
    embed_model: p.embed_model || "",
    api_key: "",
    has_api_key: !!p.has_api_key,
  };
}

function toPayload(v: ProviderValue) {
  return { provider: v.provider, base_url: v.base_url, model: v.model, embed_model: v.embed_model, api_key: v.api_key };
}

const TIER_NAME: Record<string, string> = { free: "Free trial", dev_ai: "Plus", byok: "Bring Your Own Key", owner: "Owner" };

function RedeemCodeCard() {
  const qc = useQueryClient();
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const redeem = useMutation({
    mutationFn: () => api.redeemCode(code.trim()),
    onSuccess: (res) => {
      const when = res.lifetime ? "for life" : res.expires_at ? `through ${new Date(res.expires_at).toLocaleDateString()}` : "";
      const verb = res.extended ? "Extended" : "Code redeemed";
      setMsg({ ok: true, text: `${verb} — you’re on ${TIER_NAME[res.tier] ?? res.tier} ${when}.` });
      setCode("");
      qc.invalidateQueries({ queryKey: ["billing-me"] });
      qc.invalidateQueries({ queryKey: ["me", "profile"] });
    },
    onError: (e: unknown) => setMsg({ ok: false, text: e instanceof Error ? e.message : "Couldn’t redeem that code." }),
  });

  return (
    <Card className="mb-6">
      <div className="flex items-center gap-2 mb-1">
        <Gift size={16} className="text-ink-gold" />
        <h3 className="font-display text-lg">Redeem a code</h3>
      </div>
      <p className="text-sm text-ink-text2 mb-3">Got a promo or gift code? Enter it to unlock a free subscription.</p>
      <div className="flex gap-2">
        <Inp value={code} onChange={e => setCode(e.target.value.toUpperCase())} placeholder="e.g. GINK-AB12-CD34"
          onKeyDown={e => { if (e.key === "Enter" && code.trim()) redeem.mutate(); }} />
        <Btn variant="primary" disabled={!code.trim() || redeem.isPending} onClick={() => redeem.mutate()}>
          {redeem.isPending ? "Redeeming…" : "Redeem"}
        </Btn>
      </div>
      {msg && <p className={`text-sm mt-2 ${msg.ok ? "text-ink-green" : "text-ink-red"}`}>{msg.text}</p>}
    </Card>
  );
}

function SettingsInner() {
  const qc = useQueryClient();
  const search = useSearchParams();
  const openUpgrade = useUI((s) => s.openUpgrade);
  useRequireAuth();

  const { entitlement, isByok, isOwner, isRealOwner, planTier, planStatus } = useEntitlement();

  // Returning from a successful checkout → refresh entitlement + status.
  useEffect(() => {
    if (search.get("billing") === "success") {
      qc.invalidateQueries({ queryKey: ["billing-me"] });
      qc.invalidateQueries({ queryKey: ["llm-status"] });
    }
  }, [search, qc]);

  const { data: config } = useQuery({ queryKey: ["llm-config"], queryFn: api.llmGetConfig });
  const { data: status } = useQuery({ queryKey: ["llm-status"], queryFn: api.llmStatus });

  const [unified, setUnified] = useState(true);
  const [creative, setCreative] = useState<ProviderValue>(emptyProvider());
  const [technical, setTechnical] = useState<ProviderValue>(emptyProvider());
  const [embedding, setEmbedding] = useState<ProviderValue>(emptyProvider());

  useEffect(() => {
    if (!config) return;
    const c = toValue(config.creative);
    const t = toValue(config.technical);
    const e = toValue(config.embedding);
    setCreative(c); setTechnical(t); setEmbedding(e);
    const same = c.provider === t.provider && c.model === t.model && c.base_url === t.base_url
      && c.provider === e.provider && c.model === e.model;
    setUnified(same);
  }, [config]);

  const statusByLane = useMemo(() => {
    const map: Record<string, api.LLMStatusItem> = {};
    for (const s of status?.statuses || []) map[s.lane] = s;
    return map;
  }, [status]);

  const save = useMutation({
    mutationFn: () => {
      if (unified) {
        const p = toPayload(creative);
        return api.llmPutConfig({ creative: p, technical: p, embedding: p });
      }
      return api.llmPutConfig({ creative: toPayload(creative), technical: toPayload(technical), embedding: toPayload(embedding) });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["llm-config"] });
      qc.invalidateQueries({ queryKey: ["llm-status"] });
    },
  });

  const portal = useMutation({
    mutationFn: api.billingPortal,
    onSuccess: (r) => { if (r.url) window.location.href = r.url; else alert(r.message || "Contact support to manage your plan."); },
  });

  const metered = entitlement?.metered;
  const usedActions = entitlement?.usage.actions_used ?? 0;
  const maxActions = entitlement?.limits.max_actions ?? null;

  return (
    <main className="max-w-3xl mx-auto p-4 sm:p-6">
      <Link href="/studio" className="text-xs text-ink-text2 hover:text-ink-goldLight inline-flex items-center gap-1.5 mb-4"><ArrowLeftCircle size={14}/> Back to studio</Link>
      <PageHdr title="Settings" subtitle="Choose how the AI is powered: G-Ink's built-in models, or your own provider keys." />

      {search.get("billing") === "success" && (
        <Card className="mb-4 border-ink-green/40 bg-ink-green/10">
          <p className="text-sm text-ink-green inline-flex items-center gap-2"><CheckCircle2 size={15}/> Your plan is active. Happy writing.</p>
        </Card>
      )}

      {/* ── Current plan ──────────────────────────────────────────────── */}
      <Card className="mb-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-display text-lg">Your plan</h3>
              <Tag color={planTier === "byok" ? "gold" : planTier === "dev_ai" ? "green" : "muted"}>{TIER_NAME[planTier] ?? planTier}</Tag>
              {planStatus === "past_due" && <Tag color="red">past due</Tag>}
            </div>
            <p className="text-sm text-ink-text2 mt-1">
              {isOwner && "Unlimited AI on the house models — owner account, no subscription needed."}
              {planTier === "byok" && "AI runs on your own provider keys — unlimited on our side."}
              {planTier === "dev_ai" && metered && maxActions != null && `${usedActions} of ${maxActions} AI actions used this month.`}
              {planTier === "free" && metered && maxActions != null && `Free trial — ${usedActions} of ${maxActions} AI actions used.`}
            </p>
          </div>
          {!isOwner && (
            <div className="flex flex-col gap-2 shrink-0">
              <Btn variant="primary" onClick={() => openUpgrade("manual")}>{planTier === "free" ? "Subscribe" : "Change plan"}</Btn>
              {planTier !== "free" && <Btn variant="ghost" onClick={() => portal.mutate()} disabled={portal.isPending}>Manage billing</Btn>}
            </div>
          )}
        </div>
      </Card>

      {/* ── Redeem a code ─────────────────────────────────────────────── */}
      <RedeemCodeCard />

      {/* ── Owner-only control panel: shape-shift + house default + caps ── */}
      {isRealOwner && <OwnerPanel />}

      {/* ── Section 1: G-Ink's models (dev AI) ────────────────────────── */}
      <Card className={`mb-4 ${!isByok ? "border-ink-gold/40" : ""}`}>
        <div className="flex items-center gap-2 mb-1">
          <Sparkles size={16} className="text-ink-gold" />
          <h3 className="font-display text-lg">Use G-Ink&apos;s models</h3>
          {!isByok && <Tag color="green">active</Tag>}
        </div>
        <p className="text-sm text-ink-text2">
          The simplest option: we run everything on G-Ink&apos;s built-in models — no keys to manage. Available on the
          {" "}<strong>Free</strong> trial and the <strong>Plus</strong> plan.
        </p>
        {!isByok ? (
          <div className="mt-3 rounded border border-ink-border bg-ink-surface2/50 p-3 text-sm">
            {metered && maxActions != null ? (
              <>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-ink-text2 inline-flex items-center gap-1.5">
                    {planTier === "free" ? <Gift size={13} className="text-ink-gold"/> : <Cpu size={13} className="text-ink-gold"/>}
                    {planTier === "free" ? "Trial allowance" : "This month"}
                  </span>
                  <span className="text-ink-text3">{usedActions}/{maxActions} actions</span>
                </div>
                <div className="h-1.5 rounded-full bg-ink-surface3 overflow-hidden">
                  <div className={`h-full rounded-full ${entitlement?.ai_available ? "bg-ink-gold" : "bg-ink-red"}`}
                       style={{ width: `${Math.min(100, Math.round((usedActions / Math.max(1, maxActions)) * 100))}%` }} />
                </div>
              </>
            ) : (
              <span className="text-ink-text2">{isOwner ? "Unlimited — owner account." : "Active."}</span>
            )}
          </div>
        ) : (
          <div className="mt-3 text-sm text-ink-text3 inline-flex items-center gap-1.5">
            <Lock size={13}/> You&apos;re on BYOK — switch plans to use G-Ink&apos;s models instead.
          </div>
        )}
      </Card>

      {/* ── Section 2: Bring your own key (BYOK) ──────────────────────── */}
      <Card className={`mb-4 ${isByok ? "border-ink-gold/40" : ""}`}>
        <div className="flex items-center gap-2 mb-1">
          <KeyRound size={16} className="text-ink-gold" />
          <h3 className="font-display text-lg">Bring your own key</h3>
          {isByok ? <Tag color="green">active</Tag> : <Tag color="muted">BYOK plan</Tag>}
        </div>
        <p className="text-sm text-ink-text2 mb-3">
          Use your own provider keys (OpenAI, Anthropic, Gemini, OpenRouter, or a local LM Studio). Unlimited on our side —
          you pay your provider directly.
        </p>

        {isRealOwner && (
          <p className="text-xs text-ink-text3 mb-3 -mt-1">
            As the owner you can run on any provider — local, DeepSeek, OpenAI, whatever. This is <strong>your</strong> AI;
            your paid &amp; free users get the house default you set in <em>Owner controls</em> above.
          </p>
        )}
        {(isByok || isRealOwner) ? (
          <>
            <label className="flex items-center gap-2 cursor-pointer mb-3">
              <input type="checkbox" checked={unified} onChange={(e) => setUnified(e.target.checked)} />
              <span className="text-sm"><Cpu size={14} className="inline mr-1"/> Use the same model for everything</span>
            </label>

            {unified ? (
              <ProviderForm value={creative} onChange={setCreative} lane="creative" status={statusByLane["creative"]} />
            ) : (
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-ink-text3 mb-2">Creative — Flow Polish · Writing Companion · Story Check</p>
                  <ProviderForm value={creative} onChange={setCreative} lane="creative" showEmbed={false} status={statusByLane["creative"]} />
                </div>
                <div>
                  <p className="text-xs text-ink-text3 mb-2">Technical — structured extraction · filing</p>
                  <ProviderForm value={technical} onChange={setTechnical} lane="technical" showEmbed={false} status={statusByLane["technical"]} />
                </div>
                <div>
                  <p className="text-xs text-ink-text3 mb-2">Embeddings — Graph-RAG vectors (Anthropic / OpenRouter can&apos;t embed → local LM Studio)</p>
                  <ProviderForm value={embedding} onChange={setEmbedding} lane="embedding" showEmbed status={statusByLane["embedding"]} />
                </div>
              </div>
            )}

            <div className="flex justify-end mt-4">
              <Btn variant="primary" onClick={() => save.mutate()} disabled={save.isPending}>
                {save.isPending ? "Saving…" : "Save keys"}
              </Btn>
            </div>
          </>
        ) : (
          <div className="rounded border border-ink-border bg-ink-surface2/50 p-4 text-center">
            <Lock size={18} className="text-ink-gold mx-auto mb-2" />
            <p className="text-sm text-ink-text2 mb-3">Configuring your own keys is part of the BYOK plan.</p>
            <Btn variant="primary" onClick={() => openUpgrade("byok_key_missing")}>Get the BYOK plan</Btn>
          </div>
        )}
      </Card>

      <Card>
        <h2 className="font-display text-lg mb-2">How AI routing works</h2>
        <p className="text-sm text-ink-text2">Every AI action is tagged. With G-Ink&apos;s models, creative tasks (Flow Polish, the Writing Companion, Story Check) and structured filing all run on our house models, metered against your plan. With Bring Your Own Key, those same tasks run on your configured providers and are never metered by us. If a provider is unreachable, the studio degrades to a deterministic fallback so the UI never breaks.</p>
      </Card>
    </main>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<main className="max-w-3xl mx-auto p-6 text-ink-text2">Loading…</main>}>
      <SettingsInner />
    </Suspense>
  );
}
