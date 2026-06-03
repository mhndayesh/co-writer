"use client";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Drama, ArrowRight } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr, QueryError, Sel, Tag } from "@/components/ui/Primitives";
import { useDebouncedSave } from "@/lib/debounce";

// The Characters tab is now a lightweight ROSTER: name, role, status, age, icon.
// All depth — personality, behavior, voice fingerprint, relationship masks,
// current state — lives in the Character Voice Studio (one source of truth).
const ROLES = ["protagonist", "antagonist", "ally", "mentor", "rival", "love interest", "supporting"];
const STATUSES = ["alive", "dead", "unknown", "missing", "transformed"];

export default function CharactersPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();

  const { data: characters, isError, error, refetch } = useQuery({ queryKey: ["characters", storyId], queryFn: () => api.listCharacters(storyId) });
  const [activeId, setActiveId] = useState<string | null>(null);
  useEffect(() => { if (!activeId && characters && characters.length > 0) setActiveId(characters[0].id); }, [characters, activeId]);

  const active = useMemo(() => characters?.find((c: any) => c.id === activeId) || null, [characters, activeId]);
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

  // Autosave only the roster basics (name/role/status/age/icon).
  useDebouncedSave(draft, 900, (d) => {
    if (!d || !activeId) return;
    patch.mutate({ name: d.name, role: d.role, status: d.status, age: d.age, icon: d.icon });
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4 lg:gap-6 max-w-7xl">
      <aside>
        <PageHdr title="◈ Characters" />
        <Btn variant="primary" className="w-full mb-3" onClick={() => create.mutate()}><Plus size={14}/> New character</Btn>
        {isError && <div className="mb-3"><QueryError error={error} retry={refetch} what="your characters" /></div>}
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
              subtitle="Basic roster info. Autosaves as you type."
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
            </Card>

            <Card>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="font-display text-lg flex items-center gap-2"><Drama size={16}/> Full identity & voice</h3>
                  <p className="text-sm text-ink-text2 mt-1">
                    Personality, behavior, voice fingerprint, relationship masks and current state now live in the Voice Studio.
                  </p>
                </div>
                <Link href={`/studio/${storyId}/voice?character=${active.id}`}
                  className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-semibold bg-ink-gold text-ink-deep hover:brightness-110 transition">
                  Edit in Voice Studio <ArrowRight size={14}/>
                </Link>
              </div>
              {(active.personality || active.backstory || active.motivation) && (
                <div className="mt-3 pt-3 border-t border-ink-border text-sm text-ink-text2 space-y-1">
                  <p className="label">Compiled summary (read-only)</p>
                  {active.personality && <p><Tag color="muted">personality</Tag> {active.personality}</p>}
                  {active.motivation && <p><Tag color="muted">motivation</Tag> {active.motivation}</p>}
                  {active.flaw && <p><Tag color="muted">flaw</Tag> {active.flaw}</p>}
                </div>
              )}
            </Card>
          </>
        )}
      </section>
    </div>
  );
}
