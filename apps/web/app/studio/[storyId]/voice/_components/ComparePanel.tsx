"use client";
import { useState, type CSSProperties } from "react";
import { useMutation } from "@tanstack/react-query";
import { Users, GitCompare } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Ta } from "@/components/ui/Primitives";

// Voice comparison — same situation, side-by-side responses. Reveals whether the
// characters genuinely feel distinct or whether the profiles still produce generic
// dialogue.
export function ComparePanel({ storyId, characters }: { storyId: string; characters: any[] }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [situation, setSituation] = useState("");
  const [entries, setEntries] = useState<any[]>([]);

  const compare = useMutation({
    mutationKey: ["llm", "voice.compare"],
    mutationFn: () => api.compareVoices(storyId, picked, situation),
    onSuccess: (r) => setEntries(r.entries || []),
  });

  const toggle = (id: string) => setPicked(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id]);

  return (
    <div className="max-w-5xl space-y-4">
      <Card>
        <h3 className="font-display text-lg mb-3 flex items-center gap-2"><Users size={16}/> Pick 2+ characters</h3>
        <div className="flex flex-wrap gap-2">
          {characters.map(c => (
            <button key={c.id} onClick={() => toggle(c.id)} className={`px-3 py-1.5 rounded text-sm border ${picked.includes(c.id) ? "border-ink-gold/40 bg-ink-gold/10 text-ink-goldLight" : "border-ink-border text-ink-text2 hover:text-ink-text"}`}>
              {c.name}
            </button>
          ))}
        </div>
        <FG label="Situation" hint="e.g. A stranger enters carrying a blood-covered bag. What does each say or do?">
          <Ta rows={3} value={situation} onChange={e => setSituation(e.target.value)} />
        </FG>
        <Btn variant="primary" disabled={picked.length < 2 || !situation.trim() || compare.isPending} onClick={() => compare.mutate()}>
          <GitCompare size={14}/> {compare.isPending ? "Comparing…" : "Compare voices"}
        </Btn>
      </Card>

      {entries.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:[grid-template-columns:var(--cmp-cols)]" style={{ "--cmp-cols": `repeat(${Math.min(entries.length, 3)}, minmax(0, 1fr))` } as CSSProperties}>
          {entries.map((e, i) => (
            <Card key={i}>
              <h4 className="font-display mb-2">{e.character || characters.find(c => c.id === e.character_id)?.name || "?"}</h4>
              <p className="text-sm whitespace-pre-wrap text-ink-text2">{e.response}</p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
