"use client";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Sparkles } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr, Ta, Tag } from "@/components/ui/Primitives";
import { useDebouncedSave } from "@/lib/debounce";

export default function ChaptersPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();

  const { data: chapters } = useQuery({ queryKey: ["chapters", storyId], queryFn: () => api.listChapters(storyId) });
  const { data: characters } = useQuery({ queryKey: ["characters", storyId], queryFn: () => api.listCharacters(storyId) });
  const { data: locations } = useQuery({ queryKey: ["locations", storyId], queryFn: () => api.listLocations(storyId) });
  const { data: scenes } = useQuery({ queryKey: ["scenes", storyId], queryFn: () => api.listScenes(storyId) });
  const { data: threads } = useQuery({ queryKey: ["threads", storyId], queryFn: () => api.listThreads(storyId) });

  const [activeId, setActiveId] = useState<string | null>(null);
  useEffect(() => {
    if (!activeId && chapters && chapters.length > 0) setActiveId(chapters[0].id);
  }, [chapters, activeId]);

  const active = useMemo(() => chapters?.find((c: any) => c.id === activeId) || null, [chapters, activeId]);
  const activeScenes = useMemo(
    () => (scenes || []).filter((s: any) => s.chapter_id === activeId).sort((a: any, b: any) => (a.ordinal || 0) - (b.ordinal || 0)),
    [scenes, activeId],
  );
  const threadById = useMemo(() => Object.fromEntries((threads || []).map((t: any) => [t.id, t])), [threads]);
  const charById = useMemo(() => Object.fromEntries((characters || []).map((c: any) => [c.id, c])), [characters]);
  const locById = useMemo(() => Object.fromEntries((locations || []).map((l: any) => [l.id, l])), [locations]);

  const create = useMutation({
    mutationFn: () => api.createChapter(storyId, { title: "New chapter", content: "" }),
    onSuccess: (c) => { qc.invalidateQueries({ queryKey: ["chapters", storyId] }); setActiveId(c.id); },
  });

  const patch = useMutation({
    mutationFn: (p: any) => api.patchChapter(storyId, activeId!, p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chapters", storyId] }),
  });

  const del = useMutation({
    mutationFn: () => api.deleteChapter(storyId, activeId!),
    onSuccess: () => {
      setActiveId(null);
      qc.invalidateQueries({ queryKey: ["chapters", storyId] });
      qc.invalidateQueries({ queryKey: ["graph", storyId] });
      qc.invalidateQueries({ queryKey: ["story", storyId] });
    },
  });

  // Local editable form, debounced into the API
  const [draft, setDraft] = useState<any>(null);
  useEffect(() => { setDraft(active ? { ...active } : null); }, [active]);
  useDebouncedSave(draft, 900, (d) => {
    if (!d || !activeId) return;
    const { id, story_id, created_at, updated_at, ...patchable } = d;
    patch.mutate(patchable);
  });

  // Writing Companion
  const [instruction, setInstruction] = useState("");
  const companion = useMutation({
    mutationKey: ["llm", "flow.companion"],
    mutationFn: (text: string) => api.writingCompanion(storyId, text, activeId || undefined),
  });

  function insertDraftAtEnd(text: string) {
    if (!draft) return;
    setDraft({ ...draft, content: (draft.content ? draft.content + "\n\n" : "") + text });
  }

  return (
    <div className="grid grid-cols-[260px_1fr] gap-6 max-w-7xl">
      <aside>
        <PageHdr title="❧ Chapters" />
        <Btn variant="primary" className="w-full mb-3" onClick={() => create.mutate()}><Plus size={14}/> New chapter</Btn>
        <ul className="space-y-1">
          {(chapters || []).map((c: any) => (
            <li key={c.id}>
              <button
                onClick={() => setActiveId(c.id)}
                className={`w-full text-left px-3 py-2 rounded text-sm ${activeId === c.id ? "bg-ink-gold/10 text-ink-goldLight border border-ink-gold/30" : "text-ink-text2 hover:text-ink-text hover:bg-ink-surface2"}`}
              >
                <span className="text-ink-text3 mr-1">{c.number}.</span> {c.title || "Untitled"}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section>
        {!active && <p className="text-ink-text2">Select a chapter on the left, or create one.</p>}
        {active && draft && (
          <>
            <PageHdr
              title={`Chapter ${draft.number}`}
              subtitle="Autosaves as you type."
              right={
                <Btn variant="ghost" onClick={() => { if (confirm("Delete this chapter?")) del.mutate(); }}>
                  <Trash2 size={14}/> Delete
                </Btn>
              }
            />

            <Card className="mb-4">
              <div className="grid gap-3 md:grid-cols-2">
                <FG label="Title"><Inp value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} /></FG>
                <FG label="POV">
                  <select className="input" value={draft.pov_character_id || ""} onChange={e => setDraft({ ...draft, pov_character_id: e.target.value || null })}>
                    <option value="">— none —</option>
                    {(characters || []).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </FG>
                <FG label="Location">
                  <select className="input" value={draft.location_id || ""} onChange={e => setDraft({ ...draft, location_id: e.target.value || null })}>
                    <option value="">— none —</option>
                    {(locations || []).map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}
                  </select>
                </FG>
                <FG label="Summary"><Inp value={draft.summary || ""} onChange={e => setDraft({ ...draft, summary: e.target.value })} /></FG>
              </div>
            </Card>

            <Card className="mb-4">
              <FG label="Manuscript">
                <Ta rows={20} value={draft.content || ""} onChange={e => setDraft({ ...draft, content: e.target.value })} className="leading-relaxed text-base" />
              </FG>
            </Card>

            {activeScenes.length > 0 && (
              <Card className="mb-4">
                <h3 className="font-display text-lg mb-3">Scene Strip</h3>
                <div className="grid gap-2 md:grid-cols-2">
                  {activeScenes.map((s: any) => (
                    <div key={s.id} className="rounded border border-ink-border bg-ink-surface2/60 p-3">
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <Tag color="muted">{s.ordinal || 0}</Tag>
                        <strong>{s.title || s.beat || "Untitled scene"}</strong>
                      </div>
                      {s.summary && <p className="text-sm text-ink-text2 mb-2">{s.summary}</p>}
                      <div className="flex flex-wrap gap-1">
                        {s.pov_character_id && charById[s.pov_character_id] && <Tag color="gold">POV: {charById[s.pov_character_id].name}</Tag>}
                        {s.location_id && locById[s.location_id] && <Tag color="rose">{locById[s.location_id].name}</Tag>}
                        {(s.plot_thread_ids || []).map((tid: string) => threadById[tid] && <Tag key={tid} color="green">{threadById[tid].name}</Tag>)}
                      </div>
                      {(s.goal || s.conflict || s.outcome) && (
                        <p className="text-xs text-ink-text3 mt-2">
                          {[s.goal && `Goal: ${s.goal}`, s.conflict && `Conflict: ${s.conflict}`, s.outcome && `Outcome: ${s.outcome}`].filter(Boolean).join(" · ")}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            )}

            <Card>
              <h3 className="font-display text-lg mb-2">Writing Companion</h3>
              <p className="text-sm text-ink-text2 mb-3">Describe a scene — the AI drafts it using the full story context (Graph-RAG).</p>
              <Ta rows={3} value={instruction} onChange={e => setInstruction(e.target.value)} placeholder="e.g. The reunion in the throne room, Mira confronts Aiden about the broken pact." />
              <div className="flex justify-end mt-2">
                <Btn variant="primary" disabled={!instruction.trim() || companion.isPending} onClick={() => companion.mutate(instruction)}>
                  <Sparkles size={14}/> {companion.isPending ? "Drafting…" : "Draft scene"}
                </Btn>
              </div>
              {companion.data && (
                <div className="mt-4 border-t border-ink-border pt-4">
                  <p className="text-xs uppercase tracking-wider text-ink-text2 mb-2">Draft</p>
                  <pre className="whitespace-pre-wrap leading-relaxed text-sm text-ink-text">{companion.data.draft}</pre>
                  <div className="flex justify-end mt-2">
                    <Btn variant="primary" onClick={() => { insertDraftAtEnd(companion.data!.draft); companion.reset(); setInstruction(""); }}>
                      Insert into chapter
                    </Btn>
                  </div>
                </div>
              )}
            </Card>
          </>
        )}
      </section>
    </div>
  );
}
