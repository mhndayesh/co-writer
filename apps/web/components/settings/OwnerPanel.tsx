"use client";
import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Crown, Cpu, Gauge } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, Tag } from "@/components/ui/Primitives";
import { ProviderForm, ProviderValue, emptyProvider, type Provider } from "@/components/settings/ProviderForm";
import { ActAsControl } from "@/components/billing/ActAsControl";

type Caps = api.SiteConfigCaps;
const EMPTY_CAPS: Caps = {
  dev_ai_max_actions: null, dev_ai_max_tokens: null,
  free_trial_max_actions: null, free_trial_max_tokens: null,
};

function houseToValue(sc?: api.SiteConfig): ProviderValue {
  const fallback = (sc?.defaults.env_house_provider as Provider) || "lmstudio";
  const h = sc?.house;
  if (!h || !h.provider) return emptyProvider(fallback);
  return {
    provider: h.provider as Provider,
    base_url: h.base_url || "",
    model: h.model || "",
    embed_model: h.embed_model || "",
    api_key: "",
    has_api_key: !!h.has_api_key,
  };
}

// "" → null; numeric string → number. Used for the cap inputs.
function numOrNull(s: string): number | null {
  const t = s.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : null;
}

/** Owner-only control surface: shape-shift + the default AI every paid/free user
 *  runs on + the tunable usage caps. Renders nothing for non-owners. */
export function OwnerPanel() {
  const qc = useQueryClient();
  const { data: sc } = useQuery({ queryKey: ["site-config"], queryFn: api.adminGetSiteConfig });

  const [house, setHouse] = useState<ProviderValue>(emptyProvider());
  const [caps, setCaps] = useState<Caps>(EMPTY_CAPS);

  useEffect(() => {
    if (!sc) return;
    setHouse(houseToValue(sc));
    setCaps(sc.caps);
  }, [sc]);

  const save = useMutation({
    mutationFn: () =>
      api.adminPutSiteConfig({
        house: {
          provider: house.provider,
          base_url: house.base_url,
          model: house.model,
          embed_model: house.embed_model,
          api_key: house.api_key, // blank keeps the stored key
        },
        caps,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["site-config"] });
      qc.invalidateQueries({ queryKey: ["llm-status"] }); // your house provider may have changed
    },
  });

  const def = sc?.defaults;
  const capRow = (label: string, key: keyof Caps, placeholder?: number | null) => (
    <FG label={label}>
      <Inp
        type="number"
        min={0}
        value={caps[key] ?? ""}
        placeholder={placeholder != null ? `default ${placeholder.toLocaleString()}` : "default"}
        onChange={(e) => setCaps({ ...caps, [key]: numOrNull(e.target.value) })}
      />
    </FG>
  );

  return (
    <Card className="mb-4 border-ink-gold/40">
      <div className="flex items-center gap-2 mb-1">
        <Crown size={16} className="text-ink-gold" />
        <h3 className="font-display text-lg">Owner controls</h3>
        <Tag color="gold">owner only</Tag>
      </div>
      <p className="text-sm text-ink-text2 mb-4">
        Set the default AI your paid &amp; free users run on, tune their limits, and view the app as any user type.
      </p>

      {/* Shape-shift */}
      <div className="mb-5">
        <ActAsControl />
      </div>

      {/* House default AI */}
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-2">
          <Cpu size={14} className="text-ink-gold" />
          <h4 className="font-medium">Default AI (what paid &amp; free users get)</h4>
        </div>
        <ProviderForm value={house} onChange={setHouse} lane="creative" showEmbed />
      </div>

      {/* Tunable caps */}
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-2">
          <Gauge size={14} className="text-ink-gold" />
          <h4 className="font-medium">Usage limits (paid &amp; free)</h4>
        </div>
        <p className="text-xs text-ink-text3 mb-2">Leave blank to use the built-in default. BYOK and owner are never capped.</p>
        <div className="grid gap-3 md:grid-cols-2">
          {capRow("Paid — actions / month", "dev_ai_max_actions", def?.dev_ai_max_actions)}
          {capRow("Paid — tokens / month", "dev_ai_max_tokens", def?.dev_ai_max_tokens)}
          {capRow("Free trial — actions", "free_trial_max_actions", def?.free_trial_max_actions)}
          {capRow("Free trial — tokens", "free_trial_max_tokens", def?.free_trial_max_tokens)}
        </div>
      </div>

      <div className="flex items-center justify-end gap-2">
        {save.isSuccess && <span className="text-xs text-ink-green">Saved.</span>}
        <Btn variant="primary" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save owner settings"}
        </Btn>
      </div>
    </Card>
  );
}
