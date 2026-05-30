"use client";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Link as LinkIcon, X, RefreshCcw } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr, Sel, Ta, Tag } from "@/components/ui/Primitives";
import { useDebouncedSave } from "@/lib/debounce";

const ROLES = ["protagonist", "antagonist", "ally", "mentor", "rival", "love interest", "supporting"];
const STATUSES = ["alive", "dead", "unknown", "missing", "transformed"];
const REL_TYPES = ["ally", "enemy", "lover", "rival", "family", "mentor", "student", "colleague"];

export default function CharactersPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();

  const { data: characters } = useQuery({ queryKey: ["characters", storyId], queryFn: () => api.listCharacters(storyId) });
  const { data: voiceProfiles } = useQuery({ queryKey: ["voice", storyId], queryFn: () => api.listVoiceProfiles(storyId) });
  const [activeId, setActiveId] = useState<string | null>(null);
  useEffect(() => { if (!activeId && characters && characters.length > 0) setActiveId(characters[0].id); }, [characters, activeId]);

  const active = useMemo(() => characters?.find((c: any) => c.id === activeId) || null, [characters, activeId]);
  const activeVoice = useMemo(() => voiceProfiles?.find((p: any) => p.character_id === activeId) || null, [voiceProfiles, activeId]);
  const [draft, setDraft] = useState<any>(null);
  useEffect(() => { setDraft(active ? { ...active } : null); }, [active]);

  const create = useMutation({
    mutationFn: () => api.createCharacter(storyId, { name: "New character" }),
    onSuccess: (c) => { qc.invalidateQueries({ queryKey: ["characters", storyId] }); setActiveId(c.id); },
  });
  const patch = useMutation({
    mutationFn: (p: any) => api.patchCharacter(storyId, activeId!, p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["characters", storyId] }),
  });
  const del = useMutation({
    mutationFn: () => api.deleteCharacter(storyId, activeId!),
    onSuccess: () => { setActiveId(null); qc.invalidateQueries({ queryKey: ["characters", storyId] }); },
  });
  const rebuildVoice = useMutation({
    mutationFn: () => api.rebuildVoiceProfiles(storyId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["voice", storyId] }),
  });

  useDebouncedSave(draft, 900, (d) => {
    if (!d || !activeId) return;
    const { id, story_id, ...patchable } = d;
    patch.mutate(patchable);
  });

  // Relationships
  const { data: rels } = useQuery({
    queryKey: ["relationships", storyId, activeId],
    queryFn: () => api.listRelationships(storyId, activeId!),
    enabled: !!activeId,
  });
  const [relTarget, setRelTarget] = useState("");
  const [relType, setRelType] = useState(REL_TYPES[0]);
  const [relDesc, setRelDesc] = useState("");
  const addRel = useMutation({
    mutationFn: () => api.addRelationship(storyId, activeId!, { target_id: relTarget, type: relType, description: relDesc }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["relationships", storyId, activeId] }); setRelTarget(""); setRelDesc(""); },
  });
  const delRel = useMutation({
    mutationFn: (relId: string) => api.deleteRelationship(storyId, relId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["relationships", storyId, activeId] }),
  });

  return (
    <div className="grid grid-cols-[260px_1fr] gap-6 max-w-7xl">
      <aside>
        <PageHdr title="◈ Characters" />
        <Btn variant="primary" className="w-full mb-3" onClick={() => create.mutate()}><Plus size={14}/> New character</Btn>
        <ul className="space-y-1">
          {(characters || []).map((c: any) => (
            <li key={c.id}>
              <button onClick={() => setActiveId(c.id)} className={`w-full text-left px-3 py-2 rounded text-sm ${activeId === c.id ? "bg-ink-gold/10 text-ink-goldLight border border-ink-gold/30" : "text-ink-text2 hover:text-ink-text hover:bg-ink-surface2"}`}>
                {c.name} <span className="text-ink-text3 text-xs">{c.role}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section>
        {!active && <p className="text-ink-text2">Select a character on the left.</p>}
        {active && draft && (
          <>
            <PageHdr
              title={draft.name}
              subtitle="Autosaves as you type."
              right={<Btn variant="ghost" onClick={() => { if (confirm("Delete this character?")) del.mutate(); }}><Trash2 size={14}/> Delete</Btn>}
            />

            <Card className="mb-4">
              <div className="grid gap-3 md:grid-cols-3">
                <FG label="Name"><Inp value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></FG>
                <FG label="Role">
                  <Sel value={draft.role || ""} onChange={e => setDraft({ ...draft, role: e.target.value })}>
                    <option value="">— role —</option>
                    {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                  </Sel>
                </FG>
                <FG label="Status">
                  <Sel value={draft.status || "alive"} onChange={e => setDraft({ ...draft, status: e.target.value })}>
                    {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                  </Sel>
                </FG>
                <FG label="Age"><Inp value={draft.age || ""} onChange={e => setDraft({ ...draft, age: e.target.value })} /></FG>
                <FG label="Icon"><Inp value={draft.icon || ""} onChange={e => setDraft({ ...draft, icon: e.target.value })} placeholder="emoji or short text" /></FG>
              </div>
              <FG label="Appearance"><Ta value={draft.appearance || ""} onChange={e => setDraft({ ...draft, appearance: e.target.value })} /></FG>
              <FG label="Personality"><Ta value={draft.personality || ""} onChange={e => setDraft({ ...draft, personality: e.target.value })} /></FG>
              <FG label="Backstory"><Ta value={draft.backstory || ""} onChange={e => setDraft({ ...draft, backstory: e.target.value })} /></FG>
              <div className="grid gap-3 md:grid-cols-2">
                <FG label="Motivation"><Ta rows={3} value={draft.motivation || ""} onChange={e => setDraft({ ...draft, motivation: e.target.value })} /></FG>
                <FG label="Fatal flaw"><Ta rows={3} value={draft.flaw || ""} onChange={e => setDraft({ ...draft, flaw: e.target.value })} /></FG>
              </div>
              <FG label="Character arc"><Ta value={draft.arc || ""} onChange={e => setDraft({ ...draft, arc: e.target.value })} /></FG>
            </Card>

            <Card className="mb-4">
              <div className="flex items-center justify-between gap-2 mb-3">
                <h3 className="font-display text-lg">Voice Fingerprint</h3>
                <Btn variant="ghost" disabled={rebuildVoice.isPending} onClick={() => rebuildVoice.mutate()}><RefreshCcw size={14}/> Rebuild</Btn>
              </div>
              {activeVoice && activeVoice.sample_count > 0 ? (
                <>
                  <div className="grid gap-2 md:grid-cols-4">
                    <Tag color="gold">Samples {activeVoice.sample_count}</Tag>
                    <Tag color="muted">Avg {activeVoice.avg_sentence_words} words</Tag>
                    <Tag color="muted">Questions {Math.round(activeVoice.question_rate * 100)}%</Tag>
                    <Tag color="muted">Exclaims {Math.round(activeVoice.exclamation_rate * 100)}%</Tag>
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-2 text-sm text-ink-text2">
                    <p>Vocabulary variety: <strong className="text-ink-text">{Math.round(activeVoice.vocabulary_variety * 100)}%</strong></p>
                    <p>Dialogue share: <strong className="text-ink-text">{Math.round(activeVoice.dialogue_share * 100)}%</strong></p>
                  </div>
                  {(activeVoice.repeated_phrases || []).length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1">
                      {activeVoice.repeated_phrases.map((p: string) => <Tag key={p} color="rose">{p}</Tag>)}
                    </div>
                  )}
                </>
              ) : (
                <p className="text-sm text-ink-text3">No attributed dialogue samples yet.</p>
              )}
            </Card>

            <Card>
              <h3 className="font-display text-lg mb-2 flex items-center gap-2"><LinkIcon size={16}/> Relationships</h3>
              <div className="grid gap-2 md:grid-cols-[1fr_180px_1fr_auto] items-end mb-3">
                <FG label="Target">
                  <Sel value={relTarget} onChange={e => setRelTarget(e.target.value)}>
                    <option value="">— pick character —</option>
                    {(characters || []).filter((c: any) => c.id !== activeId).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </Sel>
                </FG>
                <FG label="Type">
                  <Sel value={relType} onChange={e => setRelType(e.target.value)}>
                    {REL_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </Sel>
                </FG>
                <FG label="Description"><Inp value={relDesc} onChange={e => setRelDesc(e.target.value)} /></FG>
                <Btn variant="primary" disabled={!relTarget} className="mb-3" onClick={() => addRel.mutate()}><Plus size={14}/> Add</Btn>
              </div>
              <ul className="space-y-1">
                {(rels || []).map((r: any) => {
                  const target = characters?.find((c: any) => c.id === r.target_id);
                  return (
                    <li key={r.id} className="flex items-center justify-between gap-2 text-sm py-1.5 px-2 rounded hover:bg-ink-surface2">
                      <span><strong>{target?.name || "?"}</strong> — <Tag>{r.type}</Tag>{r.description && <span className="text-ink-text2 ml-2">{r.description}</span>}</span>
                      <button onClick={() => delRel.mutate(r.id)} className="text-ink-text3 hover:text-ink-red"><X size={14}/></button>
                    </li>
                  );
                })}
                {(!rels || rels.length === 0) && <li className="text-sm text-ink-text3">No relationships yet.</li>}
              </ul>
            </Card>
          </>
        )}
      </section>
    </div>
  );
}
