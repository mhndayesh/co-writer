"use client";
import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ScanText, Check, X, Pencil, AlertTriangle } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, Ta, Tag } from "@/components/ui/Primitives";

const SAMPLE_BUDGET = 128_000;  // must match ANALYZE_SAMPLE_BUDGET on the backend
// Past this, warn that the sample is large enough to eat a real slice of a metered
// plan's token budget (it's one big AI call).
const HEAVY_SAMPLE = 60_000;

// Method 1 — Analyze existing writing. Pick any number of chapters and/or paste
// prose; the model proposes traits, each with a confidence score and source
// excerpts. Nothing is committed until the author Approves/Edits per trait.
export function AnalyzeWriting({ storyId, characterId }: { storyId: string; characterId: string }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [proposals, setProposals] = useState<any[]>([]);
  const [edits, setEdits] = useState<Record<number, any>>({});   // index → edited value
  const [decided, setDecided] = useState<Record<number, "approve" | "reject">>({});
  const [lastRun, setLastRun] = useState<{ used: any[]; truncated: boolean } | null>(null);

  const { data: chapters } = useQuery({
    queryKey: ["chapters", storyId],
    queryFn: () => api.listChapters(storyId),
    enabled: open,
  });

  // Rough budget readout: selected chapters' lengths + pasted text vs the 32k cap.
  const used = useMemo(() => {
    const chLen = (chapters || [])
      .filter((c: any) => picked.includes(c.id))
      .reduce((n: number, c: any) => n + (c.content?.length || 0) + 40, 0);
    return chLen + text.length;
  }, [chapters, picked, text]);
  const overBudget = used > SAMPLE_BUDGET;
  const heavy = used > HEAVY_SAMPLE;
  const hasInput = picked.length > 0 || text.trim().length > 0;

  const [note, setNote] = useState<string | null>(null);

  const analyze = useMutation({
    mutationKey: ["llm", "voice.analyze"],
    mutationFn: () => api.analyzeWriting(storyId, characterId, { text, chapter_ids: picked }),
    onSuccess: (r) => {
      setProposals(r.traits || []); setEdits({}); setDecided({});
      setLastRun({ used: r.used_chapters || [], truncated: !!r.truncated });
      if ((r.traits || []).length === 0) {
        setNote(
          r.fallback
            ? "The AI model wasn't reachable, so no traits were proposed. Check that LM Studio (or your provider) is running, then try again."
            : "No traits found in this sample. Try selecting more chapters, or prose with more of this character's dialogue and action."
        );
      } else {
        setNote(null);
      }
    },
    onError: (e: any) => setNote(`Analyze failed: ${e?.message || "unknown error"}. Check your AI provider and try again.`),
  });

  const approve = useMutation({
    mutationFn: () => {
      const decisions = proposals
        .map((p, i) => ({ ...p, value: edits[i] ?? p.value, decision: decided[i] || "reject" }))
        .filter(d => d.decision === "approve")
        .map(d => ({ layer: d.layer, field: d.field, value: d.value, decision: "approve" }));
      return api.approveTraits(storyId, characterId, decisions);
    },
    onSuccess: (_r, _v) => {
      const n = Object.values(decided).filter(d => d === "approve").length;
      qc.invalidateQueries({ queryKey: ["identity", storyId, characterId] });
      setProposals([]); setText(""); setPicked([]); setLastRun(null);
      setNote(`Saved ${n} trait${n === 1 ? "" : "s"} to the layers below.`);
    },
  });

  const toggle = (id: string) => setPicked(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id]);

  return (
    <Card>
      <button className="w-full flex items-center justify-between" onClick={() => setOpen(o => !o)}>
        <h3 className="font-display text-lg flex items-center gap-2"><ScanText size={16}/> Analyze existing writing</h3>
        <Tag color="muted">{open ? "hide" : "open"}</Tag>
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          <p className="text-sm text-ink-text3">Pick any chapters and/or paste prose. The model proposes traits — you approve each.</p>

          {/* Chapter picker */}
          {(chapters || []).length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <p className="label">Chapters</p>
                <div className="flex items-center gap-2">
                  <button className="text-xs text-ink-text3 hover:text-ink-text" onClick={() => setPicked((chapters || []).map((c: any) => c.id))}>all</button>
                  <button className="text-xs text-ink-text3 hover:text-ink-text" onClick={() => setPicked([])}>none</button>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto scrollbar-thin">
                {(chapters || []).map((c: any) => {
                  const on = picked.includes(c.id);
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => toggle(c.id)}
                      title={c.title || `Chapter ${c.number}`}
                      className={`px-2.5 py-1 rounded text-xs border ${on ? "border-ink-gold/40 bg-ink-gold/10 text-ink-goldLight" : "border-ink-border text-ink-text2 hover:text-ink-text"}`}
                    >
                      Ch{c.number}{c.title ? ` · ${c.title.slice(0, 18)}` : ""}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <Ta rows={4} value={text} onChange={e => setText(e.target.value)} placeholder="…or paste prose featuring this character (optional)" />

          {/* Budget readout */}
          <div className="flex items-center justify-between text-xs">
            <span className={overBudget ? "text-ink-red" : "text-ink-text3"}>
              ~{(used / 1000).toFixed(1)}k / {SAMPLE_BUDGET / 1000}k chars
              {overBudget && " — over budget; extra will be truncated"}
            </span>
            {picked.length > 0 && <span className="text-ink-text3">{picked.length} chapter{picked.length > 1 ? "s" : ""} selected</span>}
          </div>
          <div className="h-1 rounded bg-ink-surface3 overflow-hidden">
            <div className={`h-full ${overBudget ? "bg-ink-red" : heavy ? "bg-ink-rose" : "bg-ink-gold"}`} style={{ width: `${Math.min(100, (used / SAMPLE_BUDGET) * 100)}%` }} />
          </div>

          {heavy && (
            <p className="text-xs text-ink-rose flex items-start gap-1.5">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" />
              <span>Large sample — this is one big AI call and can use a meaningful chunk of your plan's token budget. Analyze fewer chapters if you want to keep usage low.</span>
            </p>
          )}

          <Btn variant="primary" disabled={!hasInput || analyze.isPending} onClick={() => { setNote(null); analyze.mutate(); }}>
            <ScanText size={14}/> {analyze.isPending ? "Analyzing…" : "Analyze"}
          </Btn>

          {note && <p className="text-xs text-ink-text2">{note}</p>}

          {lastRun && (lastRun.used.length > 0 || lastRun.truncated) && (
            <p className="text-xs text-ink-text3">
              Analyzed {lastRun.used.length > 0 ? lastRun.used.map((c: any) => `Ch${c.number}`).join(", ") : "pasted text"}
              {lastRun.truncated && " (sample truncated to fit the 128k budget)"}
            </p>
          )}

          {proposals.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs text-ink-text3">
                Mark each trait <strong className="text-ink-text2">Approve</strong> or Reject, then click <strong className="text-ink-text2">Save</strong> below to write the approved ones into the character.
              </p>
              {proposals.map((p, i) => (
                <div key={i} className={`p-2 rounded border text-sm ${decided[i] === "approve" ? "border-ink-green/40 bg-ink-green/5" : decided[i] === "reject" ? "border-ink-border opacity-40" : "border-ink-border"}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <Tag color="muted">{p.layer}</Tag>
                    <Tag color={p.confidence >= 0.7 ? "green" : p.confidence >= 0.4 ? "gold" : "rose"}>conf {Math.round((p.confidence || 0) * 100)}%</Tag>
                  </div>
                  {p.question && <p className="text-xs text-ink-text2 mb-1">{p.question}</p>}
                  <Ta rows={2} value={edits[i] ?? p.value ?? ""} onChange={e => setEdits(s => ({ ...s, [i]: e.target.value }))} />
                  {(p.excerpts || []).length > 0 && (
                    <p className="text-xs text-ink-text3 mt-1 italic">“{(p.excerpts || []).join("” / “")}”</p>
                  )}
                  <div className="flex gap-1 mt-2">
                    <Btn variant={decided[i] === "approve" ? "primary" : "ghost"} onClick={() => setDecided(s => ({ ...s, [i]: "approve" }))}><Check size={13}/> Approve</Btn>
                    <Btn variant="ghost" onClick={() => setEdits(s => ({ ...s, [i]: p.value }))}><Pencil size={13}/> Edit</Btn>
                    <Btn variant={decided[i] === "reject" ? "primary" : "ghost"} onClick={() => setDecided(s => ({ ...s, [i]: "reject" }))}><X size={13}/> Reject</Btn>
                  </div>
                </div>
              ))}
              {(() => {
                const n = Object.values(decided).filter(d => d === "approve").length;
                return (
                  <Btn variant="primary" disabled={approve.isPending || n === 0} onClick={() => approve.mutate()}>
                    <Check size={14}/> {approve.isPending ? "Saving…" : `Save ${n} approved trait${n === 1 ? "" : "s"}`}
                  </Btn>
                );
              })()}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
