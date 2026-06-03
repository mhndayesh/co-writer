"use client";
import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MapPin, Sparkles, Wand2 } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, Ta, Tag } from "@/components/ui/Primitives";
import { useDebouncedSave } from "@/lib/debounce";

const SENSES = ["sound", "smell", "lighting", "temperature", "textures"];
const VARIATIONS = ["time", "weather", "phase"];

export function PlacePanel({ storyId }: { storyId: string }) {
  const { data: locations } = useQuery({ queryKey: ["locations", storyId], queryFn: () => api.listLocations(storyId) });
  const [activeId, setActiveId] = useState<string | null>(null);
  useEffect(() => { if (!activeId && locations && locations.length > 0) setActiveId(locations[0].id); }, [locations, activeId]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-4 lg:gap-6 max-w-5xl">
      <aside>
        <p className="label mb-2">Locations</p>
        <ul className="space-y-1">
          {(locations || []).map((l: any) => (
            <li key={l.id}>
              <button onClick={() => setActiveId(l.id)} className={`w-full text-left px-3 py-2 rounded text-sm ${activeId === l.id ? "bg-ink-gold/10 text-ink-goldLight border border-ink-gold/30" : "text-ink-text2 hover:text-ink-text hover:bg-ink-surface2"}`}>
                {l.name}
              </button>
            </li>
          ))}
          {(!locations || locations.length === 0) && <li className="text-sm text-ink-text3">No locations yet. Add them in the Locations tab.</li>}
        </ul>
      </aside>
      <section>{activeId ? <PlaceEditor storyId={storyId} locationId={activeId} /> : <p className="text-ink-text2">Pick a location.</p>}</section>
    </div>
  );
}

function PlaceEditor({ storyId, locationId }: { storyId: string; locationId: string }) {
  const qc = useQueryClient();
  const { data: place } = useQuery({ queryKey: ["place", storyId, locationId], queryFn: () => api.getPlaceIdentity(storyId, locationId) });
  const [draft, setDraft] = useState<any>(null);
  useEffect(() => { setDraft(place ? { ...place } : null); }, [place?.id]);

  const save = useMutation({
    mutationFn: (patch: any) => api.patchPlaceIdentity(storyId, locationId, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["place", storyId, locationId] }),
  });
  useDebouncedSave(draft, 900, (d) => {
    if (!d) return;
    const { id, location_id, story_id, ...patch } = d;
    save.mutate(patch);
  });

  if (!draft) return <p className="text-ink-text2">Loading…</p>;
  return (
    <div className="space-y-4">
      <PlaceBuild storyId={storyId} locationId={locationId} />
      <PlaceFields draft={draft} setDraft={setDraft} />
    </div>
  );
}

function PlaceBuild({ storyId, locationId }: { storyId: string; locationId: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const { data: bank } = useQuery({ queryKey: ["place-questions", storyId], queryFn: () => api.getPlaceQuestions(storyId), enabled: open });
  const build = useMutation({
    mutationKey: ["llm", "voice.place"],
    mutationFn: () => api.buildPlace(storyId, locationId, answers),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["place", storyId, locationId] }); setAnswers({}); setOpen(false); },
  });
  return (
    <Card>
      <button className="w-full flex items-center justify-between" onClick={() => setOpen(o => !o)}>
        <h3 className="font-display text-lg flex items-center gap-2"><Wand2 size={16}/> Build from a few questions</h3>
        <Tag color="muted">{open ? "hide" : "open"}</Tag>
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          {(bank?.questions || []).map((q: any) => (
            <FG key={q.id} label={q.text}><Inp value={answers[q.id] || ""} onChange={e => setAnswers(a => ({ ...a, [q.id]: e.target.value }))} /></FG>
          ))}
          <Btn variant="primary" disabled={build.isPending || Object.keys(answers).length === 0} onClick={() => build.mutate()}>
            <Sparkles size={14}/> {build.isPending ? "Building…" : "Generate place profile"}
          </Btn>
        </div>
      )}
    </Card>
  );
}

function PlaceFields({ draft, setDraft }: { draft: any; setDraft: (fn: any) => void }) {
  const setF = (k: string, v: any) => setDraft((d: any) => ({ ...d, [k]: v }));
  const sensory = draft.sensory_palette || {};
  const variations = draft.variations || {};

  return (
    <Card>
      <h3 className="font-display text-lg mb-3 flex items-center gap-2"><MapPin size={16}/> Place identity</h3>
      <div className="grid gap-3 md:grid-cols-2">
        <FG label="Purpose"><Ta rows={2} value={draft.purpose || ""} onChange={e => setF("purpose", e.target.value)} /></FG>
        <FG label="Emotional atmosphere"><Ta rows={2} value={draft.atmosphere || ""} onChange={e => setF("atmosphere", e.target.value)} /></FG>
      </div>
      <div className="mt-3">
        <p className="label mb-2">Sensory palette</p>
        <div className="grid gap-3 md:grid-cols-5">
          {SENSES.map(s => <FG key={s} label={s}><Inp value={sensory[s] || ""} onChange={e => setF("sensory_palette", { ...sensory, [s]: e.target.value })} /></FG>)}
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2 mt-3">
        <FG label="Spatial layout (affects action)"><Ta rows={2} value={draft.spatial_layout || ""} onChange={e => setF("spatial_layout", e.target.value)} /></FG>
        <FG label="Who controls the space"><Inp value={draft.controls_space || ""} onChange={e => setF("controls_space", e.target.value)} /></FG>
        <FG label="Social rules"><Ta rows={2} value={draft.social_rules || ""} onChange={e => setF("social_rules", e.target.value)} /></FG>
        <FG label="How people normally behave"><Ta rows={2} value={draft.normal_behavior || ""} onChange={e => setF("normal_behavior", e.target.value)} /></FG>
      </div>
      <div className="mt-3">
        <p className="label mb-2">Variations</p>
        <div className="grid gap-3 md:grid-cols-3">
          {VARIATIONS.map(v => <FG key={v} label={`By ${v}`}><Inp value={variations[v] || ""} onChange={e => setF("variations", { ...variations, [v]: e.target.value })} /></FG>)}
        </div>
      </div>
      <FG label="Symbolic motif"><Inp value={draft.symbolic_motif || ""} onChange={e => setF("symbolic_motif", e.target.value)} /></FG>
      <p className="text-xs text-ink-text3 mt-2">Autosaves as you type.</p>
    </Card>
  );
}
