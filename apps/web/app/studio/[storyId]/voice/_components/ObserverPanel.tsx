"use client";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Ear, Wand2, Check, X, Pencil, ShieldOff, CopyCheck, UserCog } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Sel, Ta, Tag } from "@/components/ui/Primitives";

const STRICTNESS = [
  { key: "light", label: "Light touch" },
  { key: "balanced", label: "Balanced" },
  { key: "strict", label: "Strict character fidelity" },
];

const SEV_COLOR: Record<string, any> = { high: "red", medium: "gold", low: "muted" };

// Part 2 — the line-level editor. Two modes: Narrative Observer (critique each line)
// and Dialogue Writer (rewrite in character). Mirrors the Flow page's review/approve UX.
export function ObserverPanel({ storyId }: { storyId: string }) {
  const [draft, setDraft] = useState("");
  const [strictness, setStrictness] = useState("balanced");
  const [notes, setNotes] = useState<any[]>([]);
  const [dismissed, setDismissed] = useState<Record<number, boolean>>({});
  const [rewritten, setRewritten] = useState("");

  const critique = useMutation({
    mutationKey: ["llm", "voice.observe"],
    mutationFn: () => api.observeCritique(storyId, draft, strictness),
    onSuccess: (r) => { setNotes(r.notes || []); setDismissed({}); },
  });
  const rewrite = useMutation({
    mutationKey: ["llm", "voice.rewrite"],
    mutationFn: () => api.rewriteDialogue(storyId, { draft, strictness }),
    onSuccess: (r) => setRewritten(r.rewritten || ""),
  });
  const markIntentional = useMutation({
    mutationFn: (n: any) => api.markIntentional(storyId, { line: n.line, note_kind: n.category, character_id: n.character_id || null }),
  });

  const applySuggestion = (n: any) => {
    if (n.line && n.suggestion && draft.includes(n.line)) setDraft(d => d.replace(n.line, n.suggestion));
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2 max-w-6xl">
      <Card>
        <h3 className="font-display text-lg mb-3 flex items-center gap-2"><Ear size={16}/> Draft</h3>
        <Ta rows={16} value={draft} onChange={e => setDraft(e.target.value)} placeholder="Paste or write the scene to critique or rewrite…" />
        <div className="flex items-end gap-2 mt-3">
          <FG label="Strictness"><Sel value={strictness} onChange={e => setStrictness(e.target.value)}>{STRICTNESS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}</Sel></FG>
          <Btn variant="primary" className="mb-3" disabled={!draft.trim() || critique.isPending} onClick={() => critique.mutate()}><Ear size={14}/> Critique</Btn>
          <Btn variant="ghost" className="mb-3" disabled={!draft.trim() || rewrite.isPending} onClick={() => rewrite.mutate()}><Wand2 size={14}/> Rewrite</Btn>
        </div>
        {rewritten && (
          <div className="mt-3 pt-3 border-t border-ink-border">
            <div className="flex items-center justify-between mb-1"><p className="label">Rewrite</p><Btn variant="ghost" onClick={() => { setDraft(rewritten); setRewritten(""); }}><Check size={13}/> Use this</Btn></div>
            <p className="text-sm whitespace-pre-wrap text-ink-text2">{rewritten}</p>
          </div>
        )}
      </Card>

      <Card>
        <h3 className="font-display text-lg mb-3">Notes</h3>
        {notes.length === 0 && <p className="text-sm text-ink-text3">Run Critique to see line-level notes.</p>}
        <div className="space-y-2">
          {notes.map((n, i) => dismissed[i] ? null : (
            <div key={i} className="p-2 rounded border border-ink-border text-sm">
              <div className="flex items-center gap-2 mb-1">
                <Tag color={SEV_COLOR[n.severity] || "muted"}>{n.severity}</Tag>
                <Tag color="muted">{n.category}</Tag>
                {n.character && <Tag color="gold">{n.character}</Tag>}
              </div>
              {n.line && <p className="italic text-ink-text2">“{n.line}”</p>}
              <p className="mt-1">{n.message}</p>
              {n.suggestion && <p className="mt-1 text-ink-green">→ {n.suggestion}</p>}
              <div className="flex flex-wrap gap-1 mt-2">
                <Btn variant="primary" onClick={() => { applySuggestion(n); setDismissed(s => ({ ...s, [i]: true })); }}><Check size={13}/> Apply</Btn>
                <Btn variant="ghost" onClick={() => { const v = prompt("Edit suggestion", n.suggestion || ""); if (v != null) { setDraft(d => n.line && d.includes(n.line) ? d.replace(n.line, v) : d); setDismissed(s => ({ ...s, [i]: true })); } }}><Pencil size={13}/> Edit</Btn>
                <Btn variant="ghost" onClick={() => setDismissed(s => ({ ...s, [i]: true }))}><X size={13}/> Ignore</Btn>
                <Btn variant="ghost" onClick={() => { markIntentional.mutate(n); setDismissed(s => ({ ...s, [i]: true })); }}><ShieldOff size={13}/> Mark intentional</Btn>
                <Btn variant="ghost" onClick={() => { notes.forEach((m) => { if (m.category === n.category) applySuggestion(m); }); setDismissed(s => { const c = { ...s }; notes.forEach((m, j) => { if (m.category === n.category) c[j] = true; }); return c; }); }}><CopyCheck size={13}/> Apply similar</Btn>
                {n.character_id && <Btn variant="ghost" onClick={() => { if (n.line) api.updateProfileFromNote(storyId, { character_id: n.character_id, layer: "voice", field: "notes", value: n.message }); setDismissed(s => ({ ...s, [i]: true })); }}><UserCog size={13}/> Update profile</Btn>}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
