"use client";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, XCircle, KeyRound } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, FG, Inp, Sel } from "@/components/ui/Primitives";

export type Provider = "lmstudio" | "openai" | "anthropic" | "openrouter" | "gemini";

// Providers that cannot produce embeddings — mirrors the backend EMBED_CAPABLE.
export const EMBED_INCAPABLE: Provider[] = ["anthropic", "openrouter"];

export type ProviderValue = {
  provider: Provider;
  base_url: string;
  model: string;
  embed_model: string;
  api_key: string;     // only sent when non-empty
  has_api_key: boolean; // whether a key is already stored server-side
};

export const PROVIDER_DEFAULTS: Record<Provider, { base_url: string; model: string; embed_model: string }> = {
  lmstudio:   { base_url: "http://localhost:1234/v1", model: "local-model", embed_model: "nomic-embed-text-v1.5" },
  openai:     { base_url: "https://api.openai.com/v1", model: "gpt-4o-mini", embed_model: "text-embedding-3-small" },
  anthropic:  { base_url: "", model: "claude-sonnet-4-5", embed_model: "" },
  openrouter: { base_url: "https://openrouter.ai/api/v1", model: "openai/gpt-4o-mini", embed_model: "" },
  gemini:     { base_url: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-2.0-flash", embed_model: "text-embedding-004" },
};

const PROVIDER_LABELS: Record<Provider, string> = {
  lmstudio: "LM Studio (local)",
  openai: "OpenAI",
  anthropic: "Anthropic",
  openrouter: "OpenRouter",
  gemini: "Google Gemini",
};

export function emptyProvider(p: Provider = "lmstudio"): ProviderValue {
  return { provider: p, ...PROVIDER_DEFAULTS[p], api_key: "", has_api_key: false };
}

export function ProviderForm({
  value,
  onChange,
  testRole,
  showEmbed = true,
  status,
}: {
  value: ProviderValue;
  onChange: (v: ProviderValue) => void;
  testRole: string;       // "default" | "creative" | "technical" | "embedding" | "task:<page>"
  showEmbed?: boolean;
  status?: { reachable: boolean; detail: string; provider: string; model: string };
}) {
  const test = useMutation({
    mutationKey: ["llm", "llm.test"],
    mutationFn: () => api.llmTest({ role: testRole }),
  });

  function applyProvider(p: Provider) {
    onChange({ ...value, provider: p, ...PROVIDER_DEFAULTS[p] });
  }

  const isAnthropic = value.provider === "anthropic";
  const isEmbeddingSlot = testRole === "embedding";
  const cantEmbed = EMBED_INCAPABLE.includes(value.provider);
  // Embedding slots only allow embed-capable providers.
  const providerOptions = (Object.keys(PROVIDER_LABELS) as Provider[]).filter(
    (p) => !isEmbeddingSlot || !EMBED_INCAPABLE.includes(p),
  );

  return (
    <div className="space-y-3">
      {status && (
        <div className={`inline-flex items-center gap-1 text-xs ${status.reachable ? "text-ink-green" : "text-ink-red"}`}>
          {status.reachable ? <CheckCircle2 size={13}/> : <XCircle size={13}/>}
          {status.provider}/{status.model} — {status.reachable ? "reachable" : `unreachable (${status.detail})`}
        </div>
      )}

      <FG label="Provider">
        <Sel value={value.provider} onChange={(e) => applyProvider(e.target.value as Provider)}>
          {providerOptions.map((p) => <option key={p} value={p}>{PROVIDER_LABELS[p]}</option>)}
        </Sel>
      </FG>

      <FG label="Base URL" hint={isAnthropic ? "Not used — Anthropic Messages API." : ""}>
        <Inp value={value.base_url} onChange={(e) => onChange({ ...value, base_url: e.target.value })}
             placeholder={PROVIDER_DEFAULTS[value.provider].base_url} disabled={isAnthropic} />
      </FG>

      <div className={`grid gap-3 ${showEmbed && !isEmbeddingSlot ? "md:grid-cols-2" : ""}`}>
        {!isEmbeddingSlot && (
          <FG label="Chat model">
            <Inp value={value.model} onChange={(e) => onChange({ ...value, model: e.target.value })}
                 placeholder={PROVIDER_DEFAULTS[value.provider].model} />
          </FG>
        )}
        {(showEmbed || isEmbeddingSlot) && (
          <FG label="Embedding model" hint={cantEmbed ? `${PROVIDER_LABELS[value.provider]} can't embed — will use LM Studio.` : ""}>
            <Inp value={value.embed_model} onChange={(e) => onChange({ ...value, embed_model: e.target.value })}
                 placeholder={PROVIDER_DEFAULTS[value.provider].embed_model} disabled={cantEmbed} />
          </FG>
        )}
      </div>

      {value.provider !== "lmstudio" && (
        <FG label="API key" hint="Encrypted at rest. Leave blank to keep the current one.">
          <div className="relative">
            <KeyRound size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-ink-text3"/>
            <Inp type="password" className="pl-7" value={value.api_key}
                 onChange={(e) => onChange({ ...value, api_key: e.target.value })}
                 placeholder={value.has_api_key ? "•••••• (set)" : "paste key here"} />
          </div>
        </FG>
      )}

      <div className="flex items-center gap-2">
        <Btn onClick={() => test.mutate()} disabled={test.isPending}>
          {test.isPending ? "Testing…" : "Test"}
        </Btn>
        {test.data && (
          <span className={`text-xs ${test.data.fallback ? "text-ink-red" : "text-ink-text2"}`}>
            {test.data.fallback ? "fallback — not reachable" : `✓ ${test.data.model}: ${test.data.text.slice(0, 60)}`}
          </span>
        )}
      </div>
    </div>
  );
}
