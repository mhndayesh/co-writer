"use client";
import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MessagesSquare, Sparkles } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Sel, Ta, Tag } from "@/components/ui/Primitives";

const TIERS = [
  { key: "quick", label: "Quick — 10 (side cast)" },
  { key: "medium", label: "Medium — 20 (recurring cast)" },
  { key: "deep", label: "Deep — 35 (leads & antagonists)" },
];

const LAYER_LABELS: Record<string, string> = {
  core: "Core personality",
  behavioral: "Behavioral patterns",
  voice: "Voice fingerprint",
  relationship: "Relationship masks",
  current: "Current state",
};
const LAYER_ORDER = ["core", "behavioral", "voice", "relationship", "current"];

// Method 2 — Guided interview. Walks a researched question bank with branching:
// each question may declare branches keyed by the chosen answer, revealing follow-ups.
export function Interview({ storyId, characterId }: { storyId: string; characterId: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [tier, setTier] = useState("quick");
  const [answers, setAnswers] = useState<Record<string, any>>({});

  const { data: bank } = useQuery({
    queryKey: ["interview", storyId, tier],
    queryFn: () => api.getInterview(storyId, tier),
    enabled: open,
  });

  // Resolve which questions are visible: a base question is always shown; a branch
  // question is shown only when its trigger answer is selected (client-side walk).
  const visible = useMemo(() => {
    const questions: any[] = bank?.questions || [];
    const byId = new Map(questions.map(q => [q.id, q]));
    const shown: any[] = [];
    const pushChain = (q: any) => {
      shown.push(q);
      const ans = answers[q.id];
      const branchIds: string[] = (q.branches && ans && q.branches[ans]) || [];
      for (const bid of branchIds) { const bq = byId.get(bid); if (bq) pushChain(bq); }
    };
    for (const q of questions) { if (!q.is_branch) pushChain(q); }
    return shown;
  }, [bank, answers]);

  const submit = useMutation({
    mutationKey: ["llm", "voice.interview"],
    mutationFn: () => api.submitInterview(storyId, characterId, answers, tier),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["identity", storyId, characterId] });
      setAnswers({}); setOpen(false);
    },
  });

  return (
    <Card>
      <button className="w-full flex items-center justify-between" onClick={() => setOpen(o => !o)}>
        <h3 className="font-display text-lg flex items-center gap-2"><MessagesSquare size={16}/> Guided interview</h3>
        <Tag color="muted">{open ? "hide" : "open"}</Tag>
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          <FG label="Depth"><Sel value={tier} onChange={e => { setTier(e.target.value); setAnswers({}); }}>{TIERS.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}</Sel></FG>
          <div className="space-y-4 max-h-[460px] overflow-y-auto scrollbar-thin pr-1">
            {LAYER_ORDER.map(layer => {
              const group = visible.filter(q => q.layer === layer);
              if (group.length === 0) return null;
              return (
                <div key={layer}>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-ink-text3 mb-1">{LAYER_LABELS[layer] || layer}</p>
                  <div className="space-y-2">
                    {group.map(q => (
                      <FG key={q.id} label={q.text} hint={q.hint}>
                        {Array.isArray(q.options) && q.options.length > 0 ? (
                          <Sel value={answers[q.id] || ""} onChange={e => setAnswers(a => ({ ...a, [q.id]: e.target.value }))}>
                            <option value="">— choose —</option>
                            {q.options.map((o: string) => <option key={o} value={o}>{o}</option>)}
                          </Sel>
                        ) : (
                          <Ta rows={2} value={answers[q.id] || ""} onChange={e => setAnswers(a => ({ ...a, [q.id]: e.target.value }))} />
                        )}
                      </FG>
                    ))}
                  </div>
                </div>
              );
            })}
            {visible.length === 0 && <p className="text-sm text-ink-text3">Loading questions…</p>}
          </div>
          <Btn variant="primary" disabled={submit.isPending || Object.keys(answers).length === 0} onClick={() => submit.mutate()}>
            <Sparkles size={14}/> {submit.isPending ? "Building…" : "Generate profile"}
          </Btn>
        </div>
      )}
    </Card>
  );
}
