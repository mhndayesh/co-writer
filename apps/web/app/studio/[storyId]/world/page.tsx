"use client";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr, Ta, Tag } from "@/components/ui/Primitives";
import { CoverUploader } from "@/components/ui/CoverUploader";
import { useDebouncedSave } from "@/lib/debounce";

export default function WorldPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();
  const { data: world } = useQuery({ queryKey: ["world", storyId], queryFn: () => api.getWorld(storyId) });
  const { data: story } = useQuery({ queryKey: ["story", storyId], queryFn: () => api.getStory(storyId) });

  const setCover = useMutation({
    mutationFn: (url: string | null) => api.updateStory(storyId, { cover_image_url: url }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["story", storyId] });
      qc.invalidateQueries({ queryKey: ["stories"] });
    },
  });

  const [draft, setDraft] = useState<any>(null);
  useEffect(() => { if (world && !draft) setDraft({ ...world }); }, [world, draft]);

  const patch = useMutation({
    mutationFn: (p: any) => api.patchWorld(storyId, p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["world", storyId] }),
  });

  useDebouncedSave(draft, 900, (d) => {
    if (!d) return;
    const { story_id, ...rest } = d;
    patch.mutate(rest);
  });

  const [newRule, setNewRule] = useState("");
  const [newTheme, setNewTheme] = useState("");

  function addRule() { if (!newRule.trim() || !draft) return; setDraft({ ...draft, rules: [...(draft.rules || []), newRule.trim()] }); setNewRule(""); }
  function removeRule(i: number) { if (!draft) return; setDraft({ ...draft, rules: draft.rules.filter((_: any, idx: number) => idx !== i) }); }
  function addTheme() { if (!newTheme.trim() || !draft) return; setDraft({ ...draft, themes: [...(draft.themes || []), newTheme.trim()] }); setNewTheme(""); }
  function removeTheme(i: number) { if (!draft) return; setDraft({ ...draft, themes: draft.themes.filter((_: any, idx: number) => idx !== i) }); }

  if (!draft) return <p className="text-ink-text2">Loading…</p>;

  return (
    <div className="max-w-4xl">
      <PageHdr title="✦ Your World" subtitle="The story bible. The AI respects everything here on every generation." />

      <Card className="mb-4">
        <h3 className="font-display text-lg mb-1">Project cover</h3>
        <p className="text-sm text-ink-text2 mb-3">Shown on your stories hub and used as the default when you publish.</p>
        <CoverUploader value={story?.cover_image_url} onChange={(url) => setCover.mutate(url)} label="" />
      </Card>

      <Card className="mb-4">
        <div className="grid gap-3 md:grid-cols-2">
          <FG label="Title"><Inp value={draft.title || ""} onChange={e => setDraft({ ...draft, title: e.target.value })} /></FG>
          <FG label="Genre"><Inp value={draft.genre || ""} onChange={e => setDraft({ ...draft, genre: e.target.value })} /></FG>
        </div>
        <FG label="Logline" hint="One-sentence story pitch."><Inp value={draft.logline || ""} onChange={e => setDraft({ ...draft, logline: e.target.value })} /></FG>
        <FG label="Time period"><Inp value={draft.time_period || ""} onChange={e => setDraft({ ...draft, time_period: e.target.value })} /></FG>
        <FG label="Setting"><Ta value={draft.setting || ""} onChange={e => setDraft({ ...draft, setting: e.target.value })} /></FG>
      </Card>

      <Card className="mb-4">
        <h3 className="font-display text-lg mb-2">World rules</h3>
        <p className="text-sm text-ink-text2 mb-3">Hard constraints the AI must never violate.</p>
        <div className="flex gap-2 mb-3">
          <Inp value={newRule} onChange={e => setNewRule(e.target.value)} placeholder="e.g. Magic requires a year of life per casting" onKeyDown={e => e.key === "Enter" && addRule()} />
          <Btn variant="primary" onClick={addRule}><Plus size={14}/> Add</Btn>
        </div>
        <ul className="space-y-1">
          {(draft.rules || []).map((r: string, i: number) => (
            <li key={i} className="flex items-center justify-between text-sm py-1.5 px-2 rounded hover:bg-ink-surface2">
              <span>• {r}</span>
              <button onClick={() => removeRule(i)} className="text-ink-text3 hover:text-ink-red"><X size={14}/></button>
            </li>
          ))}
          {(draft.rules || []).length === 0 && <li className="text-sm text-ink-text3">No rules yet.</li>}
        </ul>
      </Card>

      <Card className="mb-4">
        <h3 className="font-display text-lg mb-2">Themes</h3>
        <div className="flex gap-2 mb-3">
          <Inp value={newTheme} onChange={e => setNewTheme(e.target.value)} placeholder="e.g. legacy, sacrifice, identity" onKeyDown={e => e.key === "Enter" && addTheme()} />
          <Btn variant="primary" onClick={addTheme}><Plus size={14}/> Add</Btn>
        </div>
        <div className="flex flex-wrap gap-2">
          {(draft.themes || []).map((t: string, i: number) => (
            <span key={t + i} className="inline-flex items-center gap-2"><Tag color="green">{t}</Tag><button onClick={() => removeTheme(i)} className="text-ink-text3 hover:text-ink-red"><X size={12}/></button></span>
          ))}
        </div>
      </Card>

      <Card>
        <FG label="Lore" hint="Backstory the reader may never see but the world depends on."><Ta rows={6} value={draft.lore || ""} onChange={e => setDraft({ ...draft, lore: e.target.value })} /></FG>
        <FG label="Seeds → payoff" hint="Foreshadowing tracker. Plant something here, mark it paid off later."><Ta rows={4} value={draft.seeds || ""} onChange={e => setDraft({ ...draft, seeds: e.target.value })} /></FG>
      </Card>
    </div>
  );
}
