"use client";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles, Check, MessageSquarePlus, X, BookOpen } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr, Ta, Tag } from "@/components/ui/Primitives";
import { useDebouncedSave } from "@/lib/debounce";

type Phase = "writing" | "polishing" | "reviewing" | "extracting" | "done";

export default function FlowPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();

  const [raw, setRaw] = useState("");
  const [polished, setPolished] = useState("");
  const [notes, setNotes] = useState("");
  const [extracted, setExtracted] = useState<any>(null);
  const [phase, setPhase] = useState<Phase>("writing");
  const [chapterTitle, setChapterTitle] = useState("");
  const [chapterSummary, setChapterSummary] = useState("");

  const { data: draft } = useQuery({ queryKey: ["flow-draft", storyId], queryFn: () => api.flowGetDraft(storyId) });
  const { data: existingChapters } = useQuery({ queryKey: ["chapters", storyId], queryFn: () => api.listChapters(storyId) });
  const { data: existingCharacters } = useQuery({ queryKey: ["characters", storyId], queryFn: () => api.listCharacters(storyId) });

  // Use max(chapter.number) + 1 so the hint matches what the backend will
  // actually assign on approve — even after deletes leave gaps.
  const lastChapter = useMemo(() => {
    if (!existingChapters || existingChapters.length === 0) return null;
    return [...existingChapters].sort((a, b) => b.number - a.number)[0];
  }, [existingChapters]);
  const nextChapterNumber = lastChapter ? lastChapter.number + 1 : 1;

  // Detect gaps in chapter numbering (e.g. Ch1, Ch3 exist → gap at Ch2).
  const numberGaps = useMemo<number[]>(() => {
    if (!existingChapters || existingChapters.length === 0) return [];
    const present = new Set(existingChapters.map((c: any) => c.number));
    const gaps: number[] = [];
    for (let i = 1; i <= (lastChapter?.number || 0); i++) {
      if (!present.has(i)) gaps.push(i);
    }
    return gaps;
  }, [existingChapters, lastChapter]);

  // Where to save on Approve: "new" = append, or a chapter id = overwrite, or "gap:N" = fill gap N
  // Default: if there are gaps (the writer deleted a middle chapter), aim at the
  // lowest gap first — so writing fills the hole instead of jumping to the end.
  const [target, setTarget] = useState<string>("new");
  const [targetTouched, setTargetTouched] = useState(false);
  useEffect(() => {
    if (targetTouched) return;
    setTarget(numberGaps.length > 0 ? `gap:${numberGaps[0]}` : "new");
  }, [storyId, numberGaps, targetTouched]);

  // The "active number" we're writing into right now (drives the header + story-so-far card).
  const activeChapterNumber = target.startsWith("gap:")
    ? Number(target.slice(4))
    : target !== "new"
      ? (existingChapters?.find((c: any) => c.id === target)?.number || nextChapterNumber)
      : nextChapterNumber;

  // For "story so far" we want the chapter that comes BEFORE the active one in order.
  const previousChapter = useMemo(() => {
    if (!existingChapters) return null;
    const before = existingChapters.filter((c: any) => c.number < activeChapterNumber);
    if (before.length === 0) return null;
    return [...before].sort((a:any,b:any) => b.number - a.number)[0];
  }, [existingChapters, activeChapterNumber]);

  useEffect(() => {
    if (!draft) return;
    if (raw === "" && polished === "") {
      setRaw(draft.raw || "");
      setPolished(draft.polished || "");
      setNotes(draft.notes || "");
      if (draft.extracted && Object.keys(draft.extracted).length > 0) setExtracted(draft.extracted);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  // Autosave the in-progress draft every ~900ms
  useDebouncedSave({ raw, polished, notes, extracted }, 900, (v) => {
    if (!v.raw && !v.polished) return;
    api.flowSaveDraft(storyId, v).catch(() => {});
  });

  const polish = useMutation({
    mutationKey: ["llm", "flow.polish"],
    mutationFn: () => api.flowPolish(storyId, raw, notes),
    onMutate: () => setPhase("polishing"),
    onSuccess: (r) => {
      if (!r.polished || !r.polished.trim()) {
        alert("The model returned an empty response. This usually happens with reasoning models (Qwen3, DeepSeek-R1) that spend their token budget on internal <think> reasoning. Try a shorter raw draft, or switch to a non-thinking model in Settings.");
        setPhase("writing");
        return;
      }
      setPolished(r.polished); setPhase("reviewing");
    },
    onError: () => setPhase("writing"),
  });

  const extract = useMutation({
    mutationKey: ["llm", "flow.extract"],
    mutationFn: () => api.flowExtract(storyId, polished),
    onMutate: () => setPhase("extracting"),
    onSuccess: (r) => {
      setExtracted(r);
      setChapterTitle(r.title_suggestion || "");
      setChapterSummary(r.summary || "");
      setPhase("done");
    },
    onError: () => setPhase("reviewing"),
  });

  // Skip AI polish entirely: use the raw text as-is and jump straight to extract.
  // The chapter content saved on approve will be the writer's own words verbatim.
  const skipPolish = useMutation({
    mutationKey: ["llm", "flow.skip-polish"],
    mutationFn: () => api.flowExtract(storyId, raw),
    onMutate: () => { setPolished(raw); setPhase("extracting"); },
    onSuccess: (r) => {
      setExtracted(r);
      setChapterTitle(r.title_suggestion || "");
      setChapterSummary(r.summary || "");
      setPhase("done");
    },
    onError: () => setPhase("writing"),
  });

  const approve = useMutation({
    mutationKey: ["llm", "flow.approve"],
    mutationFn: () => {
      const body: any = {
        raw, polished, extracted,
        include_character_names: [],  // empty = auto-add everything new
        chapter_title: chapterTitle, chapter_summary: chapterSummary,
      };
      if (target.startsWith("gap:")) body.target_chapter_number = Number(target.slice(4));
      else if (target !== "new") body.target_chapter_id = target;
      return api.flowApprove(storyId, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chapters", storyId] });
      qc.invalidateQueries({ queryKey: ["characters", storyId] });
      qc.invalidateQueries({ queryKey: ["locations", storyId] });
      qc.invalidateQueries({ queryKey: ["world", storyId] });
      qc.invalidateQueries({ queryKey: ["factions", storyId] });
      qc.invalidateQueries({ queryKey: ["threads", storyId] });
      qc.invalidateQueries({ queryKey: ["graph", storyId] });
      // Reset for the next scene; let the gap-detector pick the new default target
      setRaw(""); setPolished(""); setNotes(""); setExtracted(null);
      setChapterTitle(""); setChapterSummary("");
      setTargetTouched(false);
      setPhase("writing");
    },
  });

  function reset() {
    setRaw(""); setPolished(""); setExtracted(null); setNotes(""); setPhase("writing");
    setChapterTitle(""); setChapterSummary("");
    polish.reset(); extract.reset(); skipPolish.reset();
    // Also clear the server-side draft so the next Flow Writing visit starts blank.
    api.flowClearDraft(storyId).catch(() => {});
    qc.invalidateQueries({ queryKey: ["flow-draft", storyId] });
  }

  const isFillingGap = target.startsWith("gap:");
  const isRedoing = target !== "new" && !isFillingGap;
  const redoingChapter = isRedoing ? existingChapters?.find((c: any) => c.id === target) : null;

  return (
    <div className="max-w-4xl mx-auto">
      <PageHdr
        title={
          activeChapterNumber === 1 && target === "new"
            ? "❦ Flow Writing"
            : isFillingGap
              ? `❦ Flow Writing — Chapter ${activeChapterNumber} (fill gap)`
              : isRedoing
                ? `❦ Flow Writing — Redo Chapter ${activeChapterNumber}`
                : `❦ Flow Writing — Chapter ${activeChapterNumber}`
        }
        subtitle={
          isFillingGap
            ? `Chapter ${activeChapterNumber} is missing — write the scene that goes here.`
            : isRedoing
              ? `Overwriting "${redoingChapter?.title || ""}". Any new characters/places will still be added; existing chapter ID stays the same.`
              : activeChapterNumber === 1
                ? "Pour out the raw idea. The AI shapes it into a scene and quietly files the rest."
                : `Continuing the story. The AI already knows your cast (${existingCharacters?.length || 0}) and what happened so far.`
        }
        right={
          (existingChapters && existingChapters.length > 0) ? (
            <select
              className="input max-w-xs"
              value={target}
              onChange={(e) => { setTarget(e.target.value); setTargetTouched(true); }}
            >
              <option value="new">+ New Chapter {nextChapterNumber}</option>
              {numberGaps.length > 0 && (
                <optgroup label="Fill a gap">
                  {numberGaps.map(n => <option key={`gap:${n}`} value={`gap:${n}`}>↳ Chapter {n} (missing)</option>)}
                </optgroup>
              )}
              <optgroup label="Redo existing (overwrite)">
                {[...existingChapters].sort((a:any,b:any)=>a.number-b.number).map((c: any) => (
                  <option key={c.id} value={c.id}>↻ Ch{c.number}: {c.title || "Untitled"}</option>
                ))}
              </optgroup>
            </select>
          ) : undefined
        }
      />

      {(phase === "writing" || phase === "polishing") && (
        <>
          {numberGaps.length > 0 && !targetTouched && (
            <Card className="mb-4 border-ink-gold/40 bg-ink-gold/5">
              <p className="text-sm">
                <strong className="text-ink-goldLight">Gap detected:</strong> Chapter{numberGaps.length > 1 ? "s" : ""} {numberGaps.join(", ")} {numberGaps.length > 1 ? "are" : "is"} missing.
                Writing now will fill Chapter <strong>{numberGaps[0]}</strong>. (Change the target on the right if you'd rather skip the gap.)
              </p>
            </Card>
          )}
          {previousChapter && (
            <Card className="mb-4 border-ink-gold/30">
              <div className="flex items-center gap-2 text-xs text-ink-text2 uppercase tracking-wider mb-2"><BookOpen size={12}/> Comes after</div>
              <p className="text-sm"><strong>Ch{previousChapter.number}. {previousChapter.title}</strong>{previousChapter.summary && <span className="text-ink-text2"> — {previousChapter.summary}</span>}</p>
              <p className="text-xs text-ink-text3 mt-2">Just write what happens next. New characters/places/threads will be added; existing ones will be recognized.</p>
            </Card>
          )}
          <Card>
            <FG label={isFillingGap
              ? `Free write — what happens in Chapter ${activeChapterNumber} (filling the gap)`
              : isRedoing
                ? `Free write — re-doing Chapter ${activeChapterNumber}`
                : activeChapterNumber === 1
                  ? "Free write"
                  : `Free write — what happens in Chapter ${activeChapterNumber}`}>
              <Ta rows={12} value={raw} onChange={e => setRaw(e.target.value)}
                  placeholder={activeChapterNumber === 1 && target === "new"
                    ? "Write freely — fragments, typos, shorthand are all fine."
                    : "Pick up where you left off…"}
                  className="text-base leading-relaxed" />
            </FG>
            <div className="flex justify-between items-center gap-2 mt-2">
              <Btn
                variant="ghost"
                disabled={!raw.trim() || polish.isPending || skipPolish.isPending}
                onClick={() => skipPolish.mutate()}
                title="Skip the AI rewrite. Your words are kept as-is; the AI just files characters/places/themes."
              >
                {skipPolish.isPending ? "Filing…" : "Use my writing as-is →"}
              </Btn>
              <Btn
                variant="primary"
                disabled={!raw.trim() || polish.isPending || skipPolish.isPending}
                onClick={() => polish.mutate()}
              >
                <Sparkles size={14}/> {polish.isPending ? "Shaping…" : "Shape this into a scene →"}
              </Btn>
            </div>
          </Card>
        </>
      )}

      {(phase === "reviewing" || phase === "extracting") && (
        <>
          <Card className="mb-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-display text-lg">Polished prose</h2>
              <Btn variant="ghost" onClick={reset}><X size={14}/> Discard</Btn>
            </div>
            <Ta rows={14} value={polished} onChange={e => setPolished(e.target.value)} className="leading-relaxed" />
            <FG label="Revision notes (optional)">
              <Inp value={notes} onChange={e => setNotes(e.target.value)} placeholder="e.g. make her angrier; the brother is older" />
            </FG>
            <div className="flex gap-2 justify-end mt-2">
              <Btn onClick={() => polish.mutate()} disabled={polish.isPending}>
                <MessageSquarePlus size={14}/> {polish.isPending ? "Revising…" : "Add notes & revise"}
              </Btn>
              <Btn variant="primary" disabled={!polished.trim() || extract.isPending} onClick={() => extract.mutate()}>
                <Sparkles size={14}/> {extract.isPending ? "Reading the scene…" : "Approve — what's in it?"}
              </Btn>
            </div>
          </Card>
        </>
      )}

      {phase === "done" && extracted && (
        <>
          <Card className="mb-4">
            <div className="flex items-center justify-between gap-2 mb-3">
              <p className="text-xs uppercase tracking-wider text-ink-text2">
                {polished === raw ? "Your scene (kept as-is)" : "Polished scene"}
              </p>
              <Btn variant="ghost" onClick={() => setPhase(polished === raw ? "writing" : "reviewing")}>
                <X size={12}/> Edit
              </Btn>
            </div>
            <pre className="whitespace-pre-wrap leading-relaxed text-sm text-ink-text max-h-60 overflow-y-auto scrollbar-thin border-l-2 border-ink-border pl-3">{polished}</pre>
          </Card>
          <Card className="mb-4">
            <h2 className="font-display text-lg mb-2">
              What the AI found
              {nextChapterNumber > 1 && <span className="text-sm text-ink-text2 font-normal ml-2">· will be added to your existing cast, world, and threads</span>}
            </h2>
            {extracted.fallback && (
              <div className="mb-3 p-2 border border-ink-red/40 bg-ink-red/10 rounded text-xs text-ink-red">
                ⚠ Fallback mode: the LLM call failed (often a thinking-model issue or LM Studio rejecting <code>response_format</code>). Nothing was auto-extracted. Approving will still save the polished prose as a new chapter — just without any character/theme additions.
              </div>
            )}
            <p className="text-sm text-ink-text2 mb-4">Tick the new characters to add to your cast. Themes and locations are added automatically.</p>

            <div className="grid gap-4 md:grid-cols-2">
              <FG label="Chapter title"><Inp value={chapterTitle} onChange={e => setChapterTitle(e.target.value)} /></FG>
              <FG label="Summary"><Inp value={chapterSummary} onChange={e => setChapterSummary(e.target.value)} /></FG>
            </div>
            <FG label="Save as" hint={
              target === "new"
                ? `Will be added as Chapter ${nextChapterNumber}.`
                : target.startsWith("gap:")
                  ? `Will fill the gap at Chapter ${target.slice(4)}.`
                  : "Will overwrite the chosen chapter (additive: any new characters/places/etc still get added)."
            }>
              <select className="input" value={target} onChange={e => { setTarget(e.target.value); setTargetTouched(true); }}>
                <option value="new">+ New Chapter {nextChapterNumber}</option>
                {numberGaps.length > 0 && (
                  <optgroup label="Fill gap">
                    {numberGaps.map(n => <option key={`gap:${n}`} value={`gap:${n}`}>Chapter {n} (missing)</option>)}
                  </optgroup>
                )}
                {(existingChapters || []).length > 0 && (
                  <optgroup label="Redo an existing chapter (overwrite)">
                    {[...(existingChapters || [])].sort((a:any,b:any)=>a.number-b.number).map((c: any) => (
                      <option key={c.id} value={c.id}>↻ Ch{c.number}: {c.title || "Untitled"}</option>
                    ))}
                  </optgroup>
                )}
              </select>
            </FG>

            {(extracted.characters || []).length > 0 && (
              <div className="mb-4">
                <h3 className="label">Characters in this scene <span className="text-ink-text3 normal-case tracking-normal">— new ones are added to your Cast automatically.</span></h3>
                <div className="flex flex-wrap gap-2">
                  {extracted.characters.map((c: any) => (
                    <div key={c.name} className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded border ${c.is_new ? "border-ink-gold/40 bg-ink-gold/10" : "border-ink-border bg-ink-surface2"}`}>
                      <span>{c.name}</span>
                      {c.role && <span className="text-xs text-ink-text2">· {c.role}</span>}
                      <Tag color={c.is_new ? "gold" : "muted"}>{c.is_new ? "new" : "existing"}</Tag>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(extracted.relationships || []).length > 0 && (
              <div className="mb-3">
                <h3 className="label">Relationships</h3>
                <ul className="space-y-1 text-sm">
                  {extracted.relationships.map((r: any, i: number) => (
                    <li key={i}>• <strong>{r.source}</strong> <Tag color="gold">{r.type}</Tag> <strong>{r.target}</strong>{r.description && <span className="text-ink-text2"> — {r.description}</span>}</li>
                  ))}
                </ul>
              </div>
            )}
            {(extracted.themes || []).length > 0 && (
              <div className="mb-3">
                <h3 className="label">Themes</h3>
                <div className="flex flex-wrap gap-2">{extracted.themes.map((t: string) => <Tag key={t} color="green">{t}</Tag>)}</div>
              </div>
            )}
            {(extracted.locations || []).length > 0 && (
              <div className="mb-3">
                <h3 className="label">Locations</h3>
                <div className="flex flex-wrap gap-2">{extracted.locations.map((l: any) => <Tag key={l.name} color="rose">{l.name}</Tag>)}</div>
              </div>
            )}
            {(extracted.factions || []).length > 0 && (
              <div className="mb-3">
                <h3 className="label">Factions</h3>
                <div className="flex flex-wrap gap-2">{extracted.factions.map((f: any) => <Tag key={f.name} color="muted">{f.name}</Tag>)}</div>
              </div>
            )}
            {(extracted.threads || []).length > 0 && (
              <div className="mb-3">
                <h3 className="label">Plot threads</h3>
                <ul className="space-y-1 text-sm">
                  {extracted.threads.map((t: any, i: number) => (<li key={i}>• <strong>{t.name}</strong> <Tag color={t.status === "paid_off" ? "green" : t.status === "abandoned" ? "muted" : "gold"}>{t.status}</Tag>{t.description && <span className="text-ink-text2"> — {t.description}</span>}</li>))}
                </ul>
              </div>
            )}
            {(extracted.events || []).length > 0 && (
              <div className="mb-3">
                <h3 className="label">Key events</h3>
                <ul className="space-y-1 text-sm">
                  {extracted.events.map((e: any, i: number) => (<li key={i}>• <span className="text-ink-text3 uppercase tracking-wider text-[10px] mr-1">{e.kind}</span> {e.description}</li>))}
                </ul>
              </div>
            )}

            <div className="flex gap-2 justify-end mt-4">
              <Btn variant="ghost" onClick={reset}>Discard</Btn>
              <Btn variant="primary" disabled={approve.isPending} onClick={() => approve.mutate()}>
                <Check size={14}/> {approve.isPending
                  ? "Filing…"
                  : target === "new"
                    ? `Approve & save as Chapter ${nextChapterNumber}`
                    : target.startsWith("gap:")
                      ? `Approve & fill Chapter ${target.slice(4)}`
                      : `Approve & overwrite chosen chapter`}
              </Btn>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
