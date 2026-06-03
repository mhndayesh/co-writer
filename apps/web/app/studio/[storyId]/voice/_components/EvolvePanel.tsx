"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles, Check } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, Sel, Ta, Tag } from "@/components/ui/Primitives";

const SAVE_AS = ["temporary", "recurring", "permanent", "not_saved"];

// Post-scene evolve — after a scene is written, surface what it reveals/changes
// about the cast and let the author choose how each becomes canon. The four
// save-as classes are what prevent one-off moments from polluting the profile.
export function EvolvePanel({ storyId }: { storyId: string }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [choices, setChoices] = useState<Record<number, string>>({});

  const scan = useMutation({
    mutationKey: ["llm", "voice.evolve"],
    mutationFn: () => api.evolveSuggestions(storyId, text),
    onSuccess: (r) => {
      setSuggestions(r.suggestions || []);
      // Default each choice to the model's suggestion.
      const def: Record<number, string> = {};
      (r.suggestions || []).forEach((s: any, i: number) => { def[i] = s.suggested_save_as || "temporary"; });
      setChoices(def);
    },
  });

  const apply = useMutation({
    mutationFn: () => {
      const decisions = suggestions.map((s, i) => ({
        type: s.type, character_id: s.character_id, summary: s.summary, save_as: choices[i] || "not_saved",
      })).filter(d => d.save_as !== "not_saved" && d.character_id);
      return api.applyEvolution(storyId, decisions);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["identity", storyId] });
      setSuggestions([]); setText("");
    },
  });

  return (
    <div className="max-w-3xl space-y-4">
      <Card>
        <h3 className="font-display text-lg mb-1 flex items-center gap-2"><Sparkles size={16}/> What changed this scene?</h3>
        <p className="text-sm text-ink-text3 mb-3">Paste a just-written scene; choose what becomes canon so one-offs don't pollute the profile.</p>
        <Ta rows={8} value={text} onChange={e => setText(e.target.value)} placeholder="Paste the approved scene…" />
        <Btn variant="primary" className="mt-3" disabled={!text.trim() || scan.isPending} onClick={() => scan.mutate()}>
          <Sparkles size={14}/> {scan.isPending ? "Reading…" : "Find updates"}
        </Btn>
      </Card>

      {suggestions.length > 0 && (
        <Card>
          <h3 className="font-display text-lg mb-3">Suggested updates</h3>
          <div className="space-y-2">
            {suggestions.map((s, i) => (
              <div key={i} className="p-2 rounded border border-ink-border text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <Tag color="muted">{s.type}</Tag>
                  {s.character && <Tag color="gold">{s.character}</Tag>}
                </div>
                <p>{s.summary}</p>
                {s.excerpt && <p className="text-xs text-ink-text3 italic mt-1">“{s.excerpt}”</p>}
                <div className="mt-2 w-48">
                  <Sel value={choices[i] || "not_saved"} onChange={e => setChoices(c => ({ ...c, [i]: e.target.value }))}>
                    {SAVE_AS.map(o => <option key={o} value={o}>{o.replace("_", " ")}</option>)}
                  </Sel>
                </div>
              </div>
            ))}
          </div>
          <Btn variant="primary" className="mt-3" disabled={apply.isPending} onClick={() => apply.mutate()}>
            <Check size={14}/> {apply.isPending ? "Saving…" : "Apply selected"}
          </Btn>
        </Card>
      )}
    </div>
  );
}
