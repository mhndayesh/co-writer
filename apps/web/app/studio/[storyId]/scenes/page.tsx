"use client";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, X } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr, QueryError, Sel, Ta, Tag } from "@/components/ui/Primitives";
import { useDebouncedSave } from "@/lib/debounce";

const SENSES = ["sight", "sound", "smell", "taste", "touch"];

function toggleId(list: string[] = [], id: string) {
  return list.includes(id) ? list.filter(x => x !== id) : [...list, id];
}

export default function ScenesPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();
  const { data: scenes, isError: scenesError, error: scenesErr, refetch: refetchScenes } = useQuery({ queryKey: ["scenes", storyId], queryFn: () => api.listScenes(storyId) });
  const { data: chapters } = useQuery({ queryKey: ["chapters", storyId], queryFn: () => api.listChapters(storyId) });
  const { data: characters } = useQuery({ queryKey: ["characters", storyId], queryFn: () => api.listCharacters(storyId) });
  const { data: locations } = useQuery({ queryKey: ["locations", storyId], queryFn: () => api.listLocations(storyId) });
  const { data: threads } = useQuery({ queryKey: ["threads", storyId], queryFn: () => api.listThreads(storyId) });
  const { data: revelations } = useQuery({ queryKey: ["revelations", storyId], queryFn: () => api.listRevelations(storyId) });

  const [activeId, setActiveId] = useState<string | null>(null);
  useEffect(() => { if (!activeId && scenes && scenes.length > 0) setActiveId(scenes[0].id); }, [activeId, scenes]);
  const active = useMemo(() => scenes?.find((s: any) => s.id === activeId) || null, [scenes, activeId]);
  const [draft, setDraft] = useState<any>(null);
  useEffect(() => { setDraft(active ? { ...active, sensory_palette: active.sensory_palette || {} } : null); }, [active]);

  const create = useMutation({
    mutationFn: () => api.createScene(storyId, { title: "New scene", beat: "", content: "", ordinal: (scenes?.length || 0) + 1 }),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["scenes", storyId] });
      qc.invalidateQueries({ queryKey: ["timeline", storyId] });
      qc.invalidateQueries({ queryKey: ["weave", storyId] });
      setActiveId(s.id);
    },
  });
  const patch = useMutation({
    mutationFn: (p: any) => api.patchScene(storyId, activeId!, p),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scenes", storyId] });
      qc.invalidateQueries({ queryKey: ["timeline", storyId] });
      qc.invalidateQueries({ queryKey: ["weave", storyId] });
    },
  });
  const del = useMutation({
    mutationFn: () => api.deleteScene(storyId, activeId!),
    onSuccess: () => {
      setActiveId(null);
      qc.invalidateQueries({ queryKey: ["scenes", storyId] });
      qc.invalidateQueries({ queryKey: ["timeline", storyId] });
      qc.invalidateQueries({ queryKey: ["weave", storyId] });
    },
  });

  useDebouncedSave(draft, 800, (d) => {
    if (!d || !activeId) return;
    const { id, story_id, ...patchable } = d;
    patch.mutate(patchable);
  });

  const [revText, setRevText] = useState("");
  const addRev = useMutation({
    mutationFn: () => api.createRevelation(storyId, { scene_id: activeId, description: revText, kind: "revelation", reader_knows: true }),
    onSuccess: () => {
      setRevText("");
      qc.invalidateQueries({ queryKey: ["revelations", storyId] });
    },
  });
  const delRev = useMutation({
    mutationFn: (id: string) => api.deleteRevelation(storyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["revelations", storyId] }),
  });

  const sceneRevelations = (revelations || []).filter((r: any) => r.scene_id === activeId);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4 lg:gap-6 max-w-7xl">
      <aside>
        <PageHdr title="Scene Cards" />
        <Btn variant="primary" className="w-full mb-3" onClick={() => create.mutate()}><Plus size={14}/> New scene</Btn>
        {scenesError && <div className="mb-3"><QueryError error={scenesErr} retry={refetchScenes} what="scene cards" /></div>}
        <ul className="space-y-1">
          {(scenes || []).map((s: any) => (
            <li key={s.id}>
              <button
                onClick={() => setActiveId(s.id)}
                className={`w-full text-left px-3 py-2 rounded text-sm ${activeId === s.id ? "bg-ink-gold/10 text-ink-goldLight border border-ink-gold/30" : "text-ink-text2 hover:text-ink-text hover:bg-ink-surface2"}`}
              >
                <span className="text-ink-text3 mr-1">{s.ordinal || 0}.</span>
                {s.title || s.beat || s.summary || "Untitled scene"}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section>
        {!draft && <p className="text-ink-text2">Select or create a scene card.</p>}
        {draft && (
          <>
            <PageHdr
              title={draft.title || draft.beat || "Scene"}
              subtitle="Autosaves as you type."
              right={<Btn variant="ghost" onClick={() => { if (confirm("Delete this scene?")) del.mutate(); }}><Trash2 size={14}/> Delete</Btn>}
            />

            <Card className="mb-4">
              <div className="grid gap-3 md:grid-cols-3">
                <FG label="Title"><Inp value={draft.title || ""} onChange={e => setDraft({ ...draft, title: e.target.value })} /></FG>
                <FG label="Beat"><Inp value={draft.beat || ""} onChange={e => setDraft({ ...draft, beat: e.target.value })} /></FG>
                <FG label="Order"><Inp type="number" value={draft.ordinal || 0} onChange={e => setDraft({ ...draft, ordinal: Number(e.target.value) })} /></FG>
                <FG label="Chapter">
                  <Sel value={draft.chapter_id || ""} onChange={e => setDraft({ ...draft, chapter_id: e.target.value || null })}>
                    <option value="">unassigned</option>
                    {(chapters || []).map((c: any) => <option key={c.id} value={c.id}>Ch{c.number}. {c.title}</option>)}
                  </Sel>
                </FG>
                <FG label="POV">
                  <Sel value={draft.pov_character_id || ""} onChange={e => setDraft({ ...draft, pov_character_id: e.target.value || null })}>
                    <option value="">none</option>
                    {(characters || []).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </Sel>
                </FG>
                <FG label="Location">
                  <Sel value={draft.location_id || ""} onChange={e => setDraft({ ...draft, location_id: e.target.value || null })}>
                    <option value="">none</option>
                    {(locations || []).map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}
                  </Sel>
                </FG>
              </div>
              <FG label="Summary"><Ta rows={3} value={draft.summary || ""} onChange={e => setDraft({ ...draft, summary: e.target.value })} /></FG>
              <div className="grid gap-3 md:grid-cols-3">
                <FG label="Goal"><Ta rows={3} value={draft.goal || ""} onChange={e => setDraft({ ...draft, goal: e.target.value })} /></FG>
                <FG label="Conflict"><Ta rows={3} value={draft.conflict || ""} onChange={e => setDraft({ ...draft, conflict: e.target.value })} /></FG>
                <FG label="Outcome"><Ta rows={3} value={draft.outcome || ""} onChange={e => setDraft({ ...draft, outcome: e.target.value })} /></FG>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <FG label="Story time"><Inp value={draft.time_anchor || ""} onChange={e => setDraft({ ...draft, time_anchor: e.target.value })} /></FG>
                <FG label="Sort key"><Inp type="number" value={draft.time_sort_key ?? ""} onChange={e => setDraft({ ...draft, time_sort_key: e.target.value === "" ? null : Number(e.target.value) })} /></FG>
                <FG label="Duration"><Inp value={draft.duration_hint || ""} onChange={e => setDraft({ ...draft, duration_hint: e.target.value })} /></FG>
              </div>
            </Card>

            <Card className="mb-4">
              <h3 className="font-display text-lg mb-3">Cast and Threads</h3>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <p className="label">Characters</p>
                  <div className="flex flex-wrap gap-2">
                    {(characters || []).map((c: any) => (
                      <button key={c.id} onClick={() => setDraft({ ...draft, character_ids: toggleId(draft.character_ids || [], c.id) })}>
                        <Tag color={(draft.character_ids || []).includes(c.id) ? "gold" : "muted"}>{c.name}</Tag>
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="label">Plot threads</p>
                  <div className="flex flex-wrap gap-2">
                    {(threads || []).map((t: any) => (
                      <button key={t.id} onClick={() => setDraft({ ...draft, plot_thread_ids: toggleId(draft.plot_thread_ids || [], t.id) })}>
                        <Tag color={(draft.plot_thread_ids || []).includes(t.id) ? "green" : "muted"}>{t.name}</Tag>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </Card>

            <Card className="mb-4">
              <h3 className="font-display text-lg mb-3">Sensory Palette</h3>
              <div className="grid gap-3 md:grid-cols-5">
                {SENSES.map(sense => (
                  <FG key={sense} label={sense}>
                    <Inp
                      type="number"
                      min={0}
                      max={100}
                      value={draft.sensory_palette?.[sense] ?? 0}
                      onChange={e => setDraft({ ...draft, sensory_palette: { ...(draft.sensory_palette || {}), [sense]: Number(e.target.value) } })}
                    />
                  </FG>
                ))}
              </div>
            </Card>

            <Card>
              <h3 className="font-display text-lg mb-3">Revelations</h3>
              <div className="grid gap-2 md:grid-cols-[1fr_auto] items-end mb-3">
                <FG label="New revelation"><Inp value={revText} onChange={e => setRevText(e.target.value)} /></FG>
                <Btn variant="primary" className="mb-3" disabled={!revText.trim() || addRev.isPending} onClick={() => addRev.mutate()}><Plus size={14}/> Add</Btn>
              </div>
              <ul className="space-y-1">
                {sceneRevelations.map((r: any) => (
                  <li key={r.id} className="flex items-center justify-between gap-2 text-sm py-1.5 px-2 rounded hover:bg-ink-surface2">
                    <span>{r.description} <Tag color={r.reader_knows ? "gold" : "muted"}>{r.reader_knows ? "reader knows" : "hidden"}</Tag></span>
                    <button onClick={() => delRev.mutate(r.id)} className="text-ink-text3 hover:text-ink-red"><X size={14}/></button>
                  </li>
                ))}
                {sceneRevelations.length === 0 && <li className="text-sm text-ink-text3">No revelations on this scene.</li>}
              </ul>
            </Card>
          </>
        )}
      </section>
    </div>
  );
}
