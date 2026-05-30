"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr, Sel, Ta, Tag } from "@/components/ui/Primitives";

const STATUSES = ["open", "paid_off", "abandoned"];

export default function ThreadsPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["threads", storyId], queryFn: () => api.listThreads(storyId) });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("open");

  const create = useMutation({
    mutationFn: () => api.createThread(storyId, { name, description, status, chapter_ids: [] }),
    onSuccess: () => { setName(""); setDescription(""); qc.invalidateQueries({ queryKey: ["threads", storyId] }); },
  });
  const del = useMutation({
    mutationFn: (id: string) => api.deleteThread(storyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["threads", storyId] }),
  });

  return (
    <div className="max-w-3xl">
      <PageHdr title="Plot Threads" subtitle="Subplots and arcs you want to track end-to-end." />
      <Card className="mb-4">
        <div className="grid gap-3 md:grid-cols-[1fr_180px]">
          <FG label="Name"><Inp value={name} onChange={e => setName(e.target.value)} /></FG>
          <FG label="Status">
            <Sel value={status} onChange={e => setStatus(e.target.value)}>{STATUSES.map(s => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</Sel>
          </FG>
        </div>
        <FG label="Description"><Ta value={description} onChange={e => setDescription(e.target.value)} /></FG>
        <div className="flex justify-end"><Btn variant="primary" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}><Plus size={14}/> Add thread</Btn></div>
      </Card>
      <ul className="space-y-2">
        {(data || []).map((t: any) => (
          <li key={t.id}>
            <Card className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2 mb-1"><h3 className="font-display text-lg">{t.name}</h3><Tag color={t.status === "paid_off" ? "green" : t.status === "abandoned" ? "muted" : "gold"}>{t.status.replace("_"," ")}</Tag></div>
                <p className="text-sm text-ink-text2">{t.description}</p>
              </div>
              <button onClick={() => del.mutate(t.id)} className="text-ink-text3 hover:text-ink-red"><X size={16}/></button>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
