"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftCircle, Cpu } from "lucide-react";
import * as api from "@/lib/api";
import { isAuthed } from "@/lib/auth";
import { Btn, Card, PageHdr } from "@/components/ui/Primitives";
import { cn } from "@/lib/cn";
import { ProviderForm, ProviderValue, emptyProvider, type Provider } from "@/components/settings/ProviderForm";

type Mode = "single" | "split" | "custom";

const CUSTOM_TASKS: { page: string; label: string }[] = [
  { page: "flow.polish", label: "Flow Polish (prose rewrite)" },
  { page: "flow.companion", label: "Writing Companion (scene draft)" },
  { page: "story_check", label: "Story Check (continuity)" },
  { page: "flow.extract", label: "Flow Extract (structured filing)" },
];

function toValue(p?: api.LLMProfile | null, fallback: Provider = "lmstudio"): ProviderValue {
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

  const [mode, setMode] = useState<Mode>("single");
  const [def, setDef] = useState<ProviderValue>(emptyProvider());
  const [creative, setCreative] = useState<ProviderValue>(emptyProvider("anthropic"));
  const [technical, setTechnical] = useState<ProviderValue>(emptyProvider("lmstudio"));
  const [embedding, setEmbedding] = useState<ProviderValue>(emptyProvider("lmstudio"));
  const [tasks, setTasks] = useState<Record<string, ProviderValue>>({});

  useEffect(() => {
    if (!config) return;
    setMode(config.mode);
    setDef(toValue(config.default));
    setCreative(toValue(config.creative, "anthropic"));
    setTechnical(toValue(config.technical, "lmstudio"));
    setEmbedding(toValue(config.embedding, "lmstudio"));
    const t: Record<string, ProviderValue> = {};
    for (const { page } of CUSTOM_TASKS) t[page] = toValue(config.tasks?.[page], "lmstudio");
    setTasks(t);
  }, [config]);

  const statusByRole = useMemo(() => {
    const map: Record<string, api.LLMStatusItem> = {};
    for (const s of status?.statuses || []) map[s.role] = s;
    return map;
  }, [status]);

  const save = useMutation({
    mutationFn: () => {
      const payload: any = { mode, default: toPayload(def) };
      if (mode === "split" || mode === "custom") {
        payload.creative = toPayload(creative);
        payload.technical = toPayload(technical);
        payload.embedding = toPayload(embedding);
      }
      if (mode === "custom") {
        payload.tasks = Object.fromEntries(
          CUSTOM_TASKS
            .filter(({ page }) => tasks[page] && tasks[page].provider)
            .map(({ page }) => [page, toPayload(tasks[page])]),
        );
      }
      return api.llmPutConfig(payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["llm-config"] });
      qc.invalidateQueries({ queryKey: ["llm-status"] });
    },
  });

  return (
    <main className="max-w-3xl mx-auto p-6">
      <Link href="/studio" className="text-xs text-ink-text2 hover:text-ink-goldLight inline-flex items-center gap-1.5 mb-4"><ArrowLeftCircle size={14}/> Back to studio</Link>
      <PageHdr title="Settings" subtitle="Route writing and technical work to different models. LM Studio (local) is the default." />

      {/* Mode selector */}
      <Card className="mb-4">
        <div className="flex items-center gap-2 mb-3"><Cpu size={16}/><h2 className="font-display text-lg">Routing mode</h2></div>
        <div className="grid grid-cols-3 gap-1 bg-ink-surface2 border border-ink-border rounded-md p-1 mb-3">
          {(["single", "split", "custom"] as Mode[]).map((m) => (
            <button key={m} onClick={() => setMode(m)}
              className={cn("text-xs py-2 px-2 rounded uppercase tracking-wider transition-colors",
                mode === m ? "bg-ink-gold text-ink-deep" : "text-ink-text2 hover:text-ink-text")}>
              {m === "single" ? "Single model" : m === "split" ? "Split creative/technical" : "Custom per-task"}
            </button>
          ))}
        </div>
        <p className="text-sm text-ink-text2">
          {mode === "single" && "One provider/model handles everything — writing, structured extraction, and embeddings."}
          {mode === "split" && "Creative work (polishing, scene drafting, story-check) uses one model; technical work (structured extraction) uses another. Embeddings have their own slot."}
          {mode === "custom" && "Pick a provider/model for each individual task. Unset tasks fall back to their category (creative/technical), then to the default."}
        </p>
      </Card>

      {mode === "single" && (
        <Card className="mb-4">
          <h3 className="font-display text-lg mb-3">Provider</h3>
          <ProviderForm value={def} onChange={setDef} testRole="default" status={statusByRole["default"]} />
        </Card>
      )}

      {(mode === "split" || mode === "custom") && (
        <>
          {mode === "split" && (
            <div className="grid gap-4 md:grid-cols-2 mb-4">
              <Card>
                <h3 className="font-display text-lg mb-1">Creative</h3>
                <p className="text-xs text-ink-text3 mb-3">Polishing · Writing Companion · Story Check</p>
                <ProviderForm value={creative} onChange={setCreative} testRole="creative" showEmbed={false} status={statusByRole["creative"]} />
              </Card>
              <Card>
                <h3 className="font-display text-lg mb-1">Technical</h3>
                <p className="text-xs text-ink-text3 mb-3">Structured extraction · filing</p>
                <ProviderForm value={technical} onChange={setTechnical} testRole="technical" showEmbed={false} status={statusByRole["technical"]} />
              </Card>
            </div>
          )}

          {mode === "custom" && (
            <div className="space-y-4 mb-4">
              {CUSTOM_TASKS.map(({ page, label }) => (
                <Card key={page}>
                  <h3 className="font-display text-base mb-3">{label}</h3>
                  <ProviderForm
                    value={tasks[page] || emptyProvider()}
                    onChange={(v) => setTasks((prev) => ({ ...prev, [page]: v }))}
                    testRole={`task:${page}`}
                    showEmbed={false}
                  />
                </Card>
              ))}
              <Card>
                <h3 className="font-display text-base mb-1">Default fallback</h3>
                <p className="text-xs text-ink-text3 mb-3">Used by any task left unset above.</p>
                <ProviderForm value={def} onChange={setDef} testRole="default" showEmbed={false} status={statusByRole["default"]} />
              </Card>
            </div>
          )}

          {/* Embedding slot — shared by split + custom */}
          <Card className="mb-4">
            <h3 className="font-display text-lg mb-1">Embeddings (Graph-RAG vectors)</h3>
            <p className="text-xs text-ink-text3 mb-3">Must be embed-capable. Anthropic can't embed — defaults to local LM Studio.</p>
            <ProviderForm value={embedding} onChange={setEmbedding} testRole="embedding" showEmbed status={statusByRole["embedding"]} />
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
        <p className="text-sm text-ink-text2">Every AI action carries a task label. In <strong>Split</strong> mode, creative tasks (prose polishing, the Writing Companion, Story Check) go to the Creative model, and structured extraction goes to the Technical model. In <strong>Custom</strong> mode you override per task. Embeddings always use the Embedding slot. If a provider is unreachable, the studio degrades to a deterministic fallback so the UI never breaks.</p>
      </Card>
    </main>
  );
}
