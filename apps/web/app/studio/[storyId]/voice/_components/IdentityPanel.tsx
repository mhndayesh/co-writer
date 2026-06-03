"use client";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X, Layers as LayersIcon, Link as LinkIcon } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, Sel, Ta, Tag } from "@/components/ui/Primitives";
import { useDebouncedSave } from "@/lib/debounce";
import { LAYER_META, VOICE_SHIFTS, type LayerField } from "./layers";
import { AnalyzeWriting } from "./AnalyzeWriting";
import { Interview } from "./Interview";

const STATE_KINDS = ["temporary", "recurring", "arc"];
const REL_TYPES = ["ally", "enemy", "lover", "rival", "family", "mentor", "student", "colleague"];

// Read a possibly-list value back into the textarea/input string form.
function toInput(field: LayerField, v: any): string {
  if (field.kind === "list") return Array.isArray(v) ? v.join(", ") : (v || "");
  return v ?? "";
}
function fromInput(field: LayerField, s: string): any {
  if (field.kind === "list") return s.split(",").map(x => x.trim()).filter(Boolean);
  return s;
}

export function IdentityPanel({ storyId, characters, activeId }: { storyId: string; characters: any[]; activeId: string | null }) {
  const qc = useQueryClient();
  const { data: voiceProfiles } = useQuery({ queryKey: ["voice", storyId], queryFn: () => api.listVoiceProfiles(storyId) });
  const { data: identityData } = useQuery({
    queryKey: ["identity", storyId, activeId],
    queryFn: () => api.getIdentity(storyId, activeId!),
    enabled: !!activeId,
  });

  const activeVoice = useMemo(() => voiceProfiles?.find((p: any) => p.character_id === activeId) || null, [voiceProfiles, activeId]);
  const character = useMemo(() => characters.find(c => c.id === activeId) || null, [characters, activeId]);

  // Per-layer drafts (autosaved). Keyed by layer name. Re-sync from the server
  // whenever the identity row CHANGES (character switch OR a write like
  // analyze-approve / interview), detected via updated_at — not just on character
  // switch. Depending on character_id alone left approved traits saved-but-invisible
  // until you navigated away and back; depending on the whole object would clobber
  // your typing on every autosave refetch. updated_at changes only on a real write.
  const [draft, setDraft] = useState<Record<string, any>>({});
  const syncKey = `${identityData?.identity?.character_id || ""}:${identityData?.identity?.updated_at || ""}`;
  useEffect(() => {
    if (identityData?.identity) {
      setDraft({
        core: identityData.identity.core_personality || {},
        behavioral: identityData.identity.behavioral_patterns || {},
        voice: identityData.identity.voice_fingerprint || {},
      });
    }
  }, [syncKey]);  // eslint-disable-line react-hooks/exhaustive-deps

  const saveLayer = useMutation({
    mutationFn: ({ layer, payload }: { layer: string; payload: any }) => api.patchIdentityLayer(storyId, activeId!, layer, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["identity", storyId, activeId] }),
  });

  // Debounce-save each layer independently when its draft changes.
  useDebouncedSave(draft.core, 900, (v) => { if (activeId && v) saveLayer.mutate({ layer: "core", payload: v }); });
  useDebouncedSave(draft.behavioral, 900, (v) => { if (activeId && v) saveLayer.mutate({ layer: "behavioral", payload: v }); });
  useDebouncedSave(draft.voice, 900, (v) => { if (activeId && v) saveLayer.mutate({ layer: "voice", payload: v }); });

  if (!activeId) return <p className="text-ink-text2">Select a character on the left to build their identity.</p>;
  if (!character) return null;

  const completeness = identityData?.identity?.completeness || {};

  return (
    <div className="space-y-4 max-w-4xl">
      {/* Build methods */}
      <div className="grid gap-4 md:grid-cols-2">
        <AnalyzeWriting storyId={storyId} characterId={activeId} />
        <Interview storyId={storyId} characterId={activeId} />
      </div>

      {/* Layers 1-3 */}
      {(["core", "behavioral", "voice"] as const).map(layer => (
        <Card key={layer}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display text-lg flex items-center gap-2"><LayersIcon size={16}/> {LAYER_META[layer].title}</h3>
            <Tag color={(completeness[layer] || 0) >= 60 ? "green" : "muted"}>{completeness[layer] || 0}% filled</Tag>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {LAYER_META[layer].fields.map(f => {
              const val = toInput(f, draft[layer]?.[f.key]);
              const set = (s: string) => setDraft(d => ({ ...d, [layer]: { ...d[layer], [f.key]: fromInput(f, s) } }));
              return (
                <FG key={f.key} label={f.label} hint={f.hint}>
                  {f.kind === "area"
                    ? <Ta rows={2} value={val} onChange={e => set(e.target.value)} />
                    : <Inp value={val} onChange={e => set(e.target.value)} />}
                </FG>
              );
            })}
            {/* Safety net: render any stored key the field set doesn't know about
                (e.g. legacy data or a future question) so it's never invisible. */}
            {Object.entries(draft[layer] || {})
              .filter(([k, v]) =>
                k !== "shifts" &&
                !LAYER_META[layer].fields.some(f => f.key === k) &&
                v != null && v !== "")
              .map(([k, v]) => {
                const display = Array.isArray(v) ? v.join(", ") : String(v);
                const set = (s: string) => setDraft(d => ({ ...d, [layer]: { ...d[layer], [k]: s } }));
                return (
                  <FG key={k} label={k.replace(/_/g, " ")} hint="additional saved field">
                    <Ta rows={2} value={display} onChange={e => set(e.target.value)} />
                  </FG>
                );
              })}
          </div>

          {/* Voice fingerprint: deterministic stats + how-voice-shifts */}
          {layer === "voice" && (
            <>
              <div className="mt-4 pt-3 border-t border-ink-border">
                <p className="label mb-2">Measured (from your prose)</p>
                {activeVoice && activeVoice.sample_count > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    <Tag color="gold">Samples {activeVoice.sample_count}</Tag>
                    <Tag color="muted">Avg {activeVoice.avg_sentence_words} words</Tag>
                    <Tag color="muted">Questions {Math.round(activeVoice.question_rate * 100)}%</Tag>
                    <Tag color="muted">Exclaims {Math.round(activeVoice.exclamation_rate * 100)}%</Tag>
                    <Tag color="muted">Vocab variety {Math.round(activeVoice.vocabulary_variety * 100)}%</Tag>
                    {(activeVoice.repeated_phrases || []).map((p: string) => <Tag key={p} color="rose">{p}</Tag>)}
                  </div>
                ) : <p className="text-sm text-ink-text3">No attributed dialogue samples yet — write some chapters, then rebuild.</p>}
              </div>
              <div className="mt-4 pt-3 border-t border-ink-border">
                <p className="label mb-2">How the voice shifts</p>
                <div className="grid gap-3 md:grid-cols-2">
                  {VOICE_SHIFTS.map(f => {
                    const shifts = draft.voice?.shifts || {};
                    const set = (s: string) => setDraft(d => ({ ...d, voice: { ...d.voice, shifts: { ...(d.voice?.shifts || {}), [f.key]: s } } }));
                    return <FG key={f.key} label={f.label}><Ta rows={2} value={shifts[f.key] || ""} onChange={e => set(e.target.value)} /></FG>;
                  })}
                </div>
              </div>
            </>
          )}
        </Card>
      ))}

      <RelationshipsCard storyId={storyId} characterId={activeId} characters={characters} />
      <MasksCard storyId={storyId} characterId={activeId} characters={characters} />
      <StatesCard storyId={storyId} characterId={activeId} />
    </div>
  );
}

function RelationshipsCard({ storyId, characterId, characters }: { storyId: string; characterId: string; characters: any[] }) {
  const qc = useQueryClient();
  // The actual bonds (ally/enemy/lover…) that feed the Story Map — distinct from
  // Relationship Masks (which capture HOW this character speaks to an audience).
  const { data: rels } = useQuery({
    queryKey: ["relationships", storyId, characterId],
    queryFn: () => api.listRelationships(storyId, characterId),
  });
  const [target, setTarget] = useState("");
  const [type, setType] = useState(REL_TYPES[0]);
  const [desc, setDesc] = useState("");
  const inv = () => qc.invalidateQueries({ queryKey: ["relationships", storyId, characterId] });
  const add = useMutation({
    mutationFn: () => api.addRelationship(storyId, characterId, { target_id: target, type, description: desc }),
    onSuccess: () => { setTarget(""); setDesc(""); inv(); },
  });
  const del = useMutation({ mutationFn: (id: string) => api.deleteRelationship(storyId, id), onSuccess: inv });

  return (
    <Card>
      <h3 className="font-display text-lg mb-1 flex items-center gap-2"><LinkIcon size={16}/> Relationships</h3>
      <p className="text-sm text-ink-text3 mb-3">Who they are bonded to — feeds the Story Map and the AI's relationship context.</p>
      <div className="grid gap-2 md:grid-cols-[1fr_160px_2fr_auto] items-end mb-3">
        <FG label="With">
          <Sel value={target} onChange={e => setTarget(e.target.value)}>
            <option value="">— pick character —</option>
            {characters.filter(c => c.id !== characterId).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Sel>
        </FG>
        <FG label="Type"><Sel value={type} onChange={e => setType(e.target.value)}>{REL_TYPES.map(t => <option key={t} value={t}>{t}</option>)}</Sel></FG>
        <FG label="Description"><Inp value={desc} onChange={e => setDesc(e.target.value)} placeholder="estranged sister, owes him a debt…" /></FG>
        <Btn variant="primary" className="mb-3" disabled={!target} onClick={() => add.mutate()}><Plus size={14}/> Add</Btn>
      </div>
      <ul className="space-y-1">
        {(rels || []).map((r: any) => {
          const t = characters.find(c => c.id === r.target_id);
          return (
            <li key={r.id} className="flex items-center justify-between gap-2 text-sm py-1.5 px-2 rounded hover:bg-ink-surface2">
              <span><strong>{t?.name || "?"}</strong> <Tag color="gold">{r.type}</Tag>{r.description && <span className="text-ink-text2 ml-1">{r.description}</span>}</span>
              <button onClick={() => del.mutate(r.id)} className="text-ink-text3 hover:text-ink-red"><X size={14}/></button>
            </li>
          );
        })}
        {(!rels || rels.length === 0) && <li className="text-sm text-ink-text3">No relationships yet.</li>}
      </ul>
    </Card>
  );
}

function MasksCard({ storyId, characterId, characters }: { storyId: string; characterId: string; characters: any[] }) {
  const qc = useQueryClient();
  const { data: masks } = useQuery({ queryKey: ["masks", storyId, characterId], queryFn: () => api.listMasks(storyId, characterId) });
  const [audience, setAudience] = useState("");
  const [label, setLabel] = useState("");
  const [style, setStyle] = useState("");
  const inv = () => qc.invalidateQueries({ queryKey: ["masks", storyId, characterId] });
  const add = useMutation({
    mutationFn: () => api.addMask(storyId, characterId, { audience_character_id: audience || null, audience_label: label, speech_style: style }),
    onSuccess: () => { setAudience(""); setLabel(""); setStyle(""); inv(); },
  });
  const del = useMutation({ mutationFn: (id: string) => api.deleteMask(storyId, id), onSuccess: inv });

  return (
    <Card>
      <h3 className="font-display text-lg mb-1">Relationship Masks</h3>
      <p className="text-sm text-ink-text3 mb-3">How this character's voice changes per audience — so they aren't one-dimensional.</p>
      <div className="grid gap-2 md:grid-cols-[1fr_1fr_2fr_auto] items-end mb-3">
        <FG label="Audience (cast)">
          <Sel value={audience} onChange={e => setAudience(e.target.value)}>
            <option value="">— or use a label —</option>
            {characters.filter(c => c.id !== characterId).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Sel>
        </FG>
        <FG label="Audience (label)"><Inp value={label} onChange={e => setLabel(e.target.value)} placeholder="police, a client…" /></FG>
        <FG label="Speech style"><Inp value={style} onChange={e => setStyle(e.target.value)} placeholder="guarded, terse, deflects…" /></FG>
        <Btn variant="primary" className="mb-3" disabled={!style || (!audience && !label)} onClick={() => add.mutate()}><Plus size={14}/> Add</Btn>
      </div>
      <ul className="space-y-1">
        {(masks || []).map((m: any) => {
          const aud = m.audience_character_id ? characters.find(c => c.id === m.audience_character_id)?.name : m.audience_label;
          return (
            <li key={m.id} className="flex items-center justify-between gap-2 text-sm py-1.5 px-2 rounded hover:bg-ink-surface2">
              <span>→ <strong>{aud || "?"}</strong>: {m.speech_style}{m.tells && <span className="text-ink-text2"> — tells: {m.tells}</span>}</span>
              <button onClick={() => del.mutate(m.id)} className="text-ink-text3 hover:text-ink-red"><X size={14}/></button>
            </li>
          );
        })}
        {(!masks || masks.length === 0) && <li className="text-sm text-ink-text3">No masks yet.</li>}
      </ul>
    </Card>
  );
}

function StatesCard({ storyId, characterId }: { storyId: string; characterId: string }) {
  const qc = useQueryClient();
  const { data: states } = useQuery({ queryKey: ["states", storyId, characterId], queryFn: () => api.listStates(storyId, characterId) });
  const [label, setLabel] = useState("");
  const [detail, setDetail] = useState("");
  const [kind, setKind] = useState("temporary");
  const inv = () => qc.invalidateQueries({ queryKey: ["states", storyId, characterId] });
  const add = useMutation({
    mutationFn: () => api.setState(storyId, characterId, { label, detail, kind }),
    onSuccess: () => { setLabel(""); setDetail(""); inv(); },
  });
  const clear = useMutation({ mutationFn: (id: string) => api.clearState(storyId, id), onSuccess: inv });

  return (
    <Card>
      <h3 className="font-display text-lg mb-1">Current State</h3>
      <p className="text-sm text-ink-text3 mb-3">Temporary, scene-scoped conditions that color voice without rewriting the core.</p>
      <div className="grid gap-2 md:grid-cols-[1fr_2fr_1fr_auto] items-end mb-3">
        <FG label="State"><Inp value={label} onChange={e => setLabel(e.target.value)} placeholder="injured, grieving…" /></FG>
        <FG label="Detail"><Inp value={detail} onChange={e => setDetail(e.target.value)} /></FG>
        <FG label="Kind"><Sel value={kind} onChange={e => setKind(e.target.value)}>{STATE_KINDS.map(k => <option key={k} value={k}>{k}</option>)}</Sel></FG>
        <Btn variant="primary" className="mb-3" disabled={!label} onClick={() => add.mutate()}><Plus size={14}/> Set</Btn>
      </div>
      <ul className="space-y-1">
        {(states || []).map((s: any) => (
          <li key={s.id} className="flex items-center justify-between gap-2 text-sm py-1.5 px-2 rounded hover:bg-ink-surface2">
            <span className={s.active ? "" : "opacity-50 line-through"}>
              <Tag color={s.kind === "arc" ? "gold" : s.kind === "recurring" ? "rose" : "muted"}>{s.kind}</Tag> <strong>{s.label}</strong>{s.detail && <span className="text-ink-text2"> — {s.detail}</span>}
            </span>
            {s.active && <button onClick={() => clear.mutate(s.id)} className="text-ink-text3 hover:text-ink-red"><X size={14}/></button>}
          </li>
        ))}
        {(!states || states.length === 0) && <li className="text-sm text-ink-text3">No active states.</li>}
      </ul>
    </Card>
  );
}
