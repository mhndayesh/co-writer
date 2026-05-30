"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftCircle, Cpu } from "lucide-react";
import * as api from "@/lib/api";
import { isAuthed } from "@/lib/auth";
import { Btn, Card, PageHdr } from "@/components/ui/Primitives";
import { ProviderForm, ProviderValue, emptyProvider, type Provider } from "@/components/settings/ProviderForm";

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

export default function SettingsPage() {
  const router = useRouter();
  const qc = useQueryClient();
  useEffect(() => { if (!isAuthed()) router.replace("/login"); }, [router]);

  const { data: config } = useQuery({ queryKey: ["llm-config"], queryFn: api.llmGetConfig });
  const { data: status } = useQuery({ queryKey: ["llm-status"], queryFn: api.llmStatus });

  // "Same model for everything" is on when all three lanes match; otherwise split.
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
        // Write the creative form to all three lanes.
        const p = toPayload(creative);
        return api.llmPutConfig({ creative: p, technical: p, embedding: p });
      }
      return api.llmPutConfig({
        creative: toPayload(creative),
        technical: toPayload(technical),
        embedding: toPayload(embedding),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["llm-config"] });
      qc.invalidateQueries({ queryKey: ["llm-status"] });
    },
  });

  return (
    <main className="max-w-3xl mx-auto p-6">
      <Link href="/studio" className="text-xs text-ink-text2 hover:text-ink-goldLight inline-flex items-center gap-1.5 mb-4"><ArrowLeftCircle size={14}/> Back to studio</Link>
      <PageHdr title="Settings" subtitle="Choose which model handles your writing vs. the behind-the-scenes filing. LM Studio (local) is the default." />

      <Card className="mb-4">
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={unified} onChange={(e) => setUnified(e.target.checked)} />
          <span className="text-sm"><Cpu size={14} className="inline mr-1"/> Use the same model for everything</span>
        </label>
        <p className="text-sm text-ink-text2 mt-2">
          {unified
            ? "One provider/model handles writing, structured filing, and embeddings."
            : "Route creative writing, technical filing, and embeddings to different models. Each lane has its own provider, model, and key."}
        </p>
      </Card>

      {unified ? (
        <Card className="mb-4">
          <h3 className="font-display text-lg mb-3">Model</h3>
          <ProviderForm value={creative} onChange={setCreative} lane="creative" status={statusByLane["creative"]} />
        </Card>
      ) : (
        <>
          <Card className="mb-4">
            <h3 className="font-display text-lg mb-1">Creative</h3>
            <p className="text-xs text-ink-text3 mb-3">Flow Polish · Writing Companion · Story Check</p>
            <ProviderForm value={creative} onChange={setCreative} lane="creative" showEmbed={false} status={statusByLane["creative"]} />
          </Card>
          <Card className="mb-4">
            <h3 className="font-display text-lg mb-1">Technical</h3>
            <p className="text-xs text-ink-text3 mb-3">Structured extraction · filing</p>
            <ProviderForm value={technical} onChange={setTechnical} lane="technical" showEmbed={false} status={statusByLane["technical"]} />
          </Card>
          <Card className="mb-4">
            <h3 className="font-display text-lg mb-1">Embeddings (Graph-RAG vectors)</h3>
            <p className="text-xs text-ink-text3 mb-3">Must be embed-capable. Anthropic / OpenRouter can't embed — defaults to local LM Studio.</p>
            <ProviderForm value={embedding} onChange={setEmbedding} lane="embedding" showEmbed status={statusByLane["embedding"]} />
          </Card>
        </>
      )}

      <div className="flex justify-end mb-6">
        <Btn variant="primary" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save settings"}
        </Btn>
      </div>

      <Card>
        <h2 className="font-display text-lg mb-2">How routing works</h2>
        <p className="text-sm text-ink-text2">Every AI action is tagged. Creative tasks (Flow Polish, the Writing Companion, Story Check) use the <strong>Creative</strong> model; structured extraction uses the <strong>Technical</strong> model; Graph-RAG vectors use the <strong>Embedding</strong> model. With "same model for everything" on, all three are identical. If a provider is unreachable, the studio degrades to a deterministic fallback so the UI never breaks.</p>
      </Card>
    </main>
  );
}
