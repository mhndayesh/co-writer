"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr, QueryError, Sel, Ta, Tag } from "@/components/ui/Primitives";

const STATUSES = ["open", "paid_off", "abandoned"];

export default function ThreadsPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();
  const { data, isError, error, refetch } = useQuery({ queryKey: ["threads", storyId], queryFn: () => api.listThreads(storyId) });
  const { data: weave } = useQuery({ queryKey: ["weave", storyId], queryFn: () => api.listWeave(storyId) });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("open");

  const create = useMutation({
    mutationFn: () => api.createThread(storyId, { name, description, status, chapter_ids: [] }),
    onSuccess: () => {
      setName("");
      setDescription("");
      qc.invalidateQueries({ queryKey: ["threads", storyId] });
      qc.invalidateQueries({ queryKey: ["weave", storyId] });
    },
  });
  const del = useMutation({
    mutationFn: (id: string) => api.deleteThread(storyId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["threads", storyId] });
      qc.invalidateQueries({ queryKey: ["weave", storyId] });
    },
  });

  return (
    <div className="max-w-6xl">
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
      {(weave?.threads || []).length > 0 && (
        <Card className="mb-4 overflow-x-auto">
          <h3 className="font-display text-lg mb-3">Subplot Weave</h3>
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="text-left text-ink-text3">
                <th className="py-2 pr-3 font-normal">Thread</th>
                {(weave?.scenes || []).map((s: any) => (
                  <th key={s.id} className="py-2 px-2 font-normal align-bottom">
                    <span className="block text-[10px] uppercase">Ch{s.chapter_number ?? "?"}</span>
                    <span className="line-clamp-2">{s.title || s.beat || `Scene ${s.ordinal}`}</span>
                  </th>
                ))}
                <th className="py-2 pl-3 font-normal">Dormant</th>
              </tr>
            </thead>
            <tbody>
              {(weave?.threads || []).map((t: any) => {
                const byScene = Object.fromEntries((t.cells || []).map((c: any) => [c.scene_id, c]));
                return (
                  <tr key={t.thread_id} className="border-t border-ink-border">
                    <td className="py-2 pr-3">
                      <div className="flex items-center gap-2">
                        <strong>{t.name}</strong>
                        <Tag color={t.status === "paid_off" ? "green" : t.status === "abandoned" ? "muted" : "gold"}>{t.status.replace("_"," ")}</Tag>
                      </div>
                    </td>
                    {(weave?.scenes || []).map((s: any) => {
                      const cell = byScene[s.id];
                      return (
                        <td key={s.id} className="py-2 px-2 text-center">
                          {cell ? <span className="inline-block h-3 w-3 rounded-full bg-ink-gold" title={cell.evidence || cell.status} /> : <span className="text-ink-text3">·</span>}
                        </td>
                      );
                    })}
                    <td className="py-2 pl-3 text-ink-text2">{t.dormant_after ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
      {isError && <QueryError error={error} retry={refetch} what="plot threads" />}
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
