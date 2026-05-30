"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr, Sel, Ta } from "@/components/ui/Primitives";

export default function ScenesPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["scenes", storyId], queryFn: () => api.listScenes(storyId) });
  const { data: chapters } = useQuery({ queryKey: ["chapters", storyId], queryFn: () => api.listChapters(storyId) });
  const [beat, setBeat] = useState("");
  const [content, setContent] = useState("");
  const [chapterId, setChapterId] = useState("");

  const create = useMutation({
    mutationFn: () => api.createScene(storyId, { beat, content, chapter_id: chapterId || null, ordinal: 0 }),
    onSuccess: () => { setBeat(""); setContent(""); qc.invalidateQueries({ queryKey: ["scenes", storyId] }); },
  });
  const del = useMutation({
    mutationFn: (id: string) => api.deleteScene(storyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scenes", storyId] }),
  });

  return (
    <div className="max-w-3xl">
      <PageHdr title="Scene Cards" subtitle="Beat-level outline. Useful for plotting before drafting." />
      <Card className="mb-4">
        <div className="grid gap-3 md:grid-cols-2">
          <FG label="Beat"><Inp value={beat} onChange={e => setBeat(e.target.value)} placeholder="e.g. Inciting incident" /></FG>
          <FG label="Chapter">
            <Sel value={chapterId} onChange={e => setChapterId(e.target.value)}>
              <option value="">— unassigned —</option>
              {(chapters || []).map((c: any) => <option key={c.id} value={c.id}>Ch{c.number}. {c.title}</option>)}
            </Sel>
          </FG>
        </div>
        <FG label="Content"><Ta value={content} onChange={e => setContent(e.target.value)} /></FG>
        <div className="flex justify-end"><Btn variant="primary" disabled={!content.trim() || create.isPending} onClick={() => create.mutate()}><Plus size={14}/> Add scene card</Btn></div>
      </Card>
      <ul className="space-y-2">
        {(data || []).map((s: any) => (
          <li key={s.id}>
            <Card className="flex items-start justify-between gap-2">
              <div className="flex-1">
                {s.beat && <p className="text-xs uppercase tracking-wider text-ink-text2 mb-1">{s.beat}</p>}
                <p className="text-sm">{s.content}</p>
              </div>
              <button onClick={() => del.mutate(s.id)} className="text-ink-text3 hover:text-ink-red"><X size={16}/></button>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
