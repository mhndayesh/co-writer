"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr, QueryError, Ta } from "@/components/ui/Primitives";

export default function FactionsPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();
  const { data, isError, error, refetch } = useQuery({ queryKey: ["factions", storyId], queryFn: () => api.listFactions(storyId) });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visual, setVisual] = useState("");

  const create = useMutation({
    mutationFn: () => api.createFaction(storyId, { name, description, visual_signature: visual }),
    onSuccess: () => { setName(""); setDescription(""); setVisual(""); qc.invalidateQueries({ queryKey: ["factions", storyId] }); },
  });
  const del = useMutation({
    mutationFn: (id: string) => api.deleteFaction(storyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["factions", storyId] }),
  });

  return (
    <div className="max-w-3xl">
      <PageHdr title="Factions" subtitle="The houses, guilds, cults, and crews that shape your world." />
      <Card className="mb-4">
        <FG label="Name"><Inp value={name} onChange={e => setName(e.target.value)} /></FG>
        <FG label="Description"><Ta value={description} onChange={e => setDescription(e.target.value)} /></FG>
        <FG label="Visual signature" hint="Colors, sigils, dress code."><Inp value={visual} onChange={e => setVisual(e.target.value)} /></FG>
        <div className="flex justify-end"><Btn variant="primary" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}><Plus size={14}/> Add faction</Btn></div>
      </Card>
      {isError && <QueryError error={error} retry={refetch} what="factions" />}
      <ul className="space-y-2">
        {(data || []).map((f: any) => (
          <li key={f.id}>
            <Card className="flex items-start justify-between gap-2">
              <div>
                <h3 className="font-display text-lg">{f.name}</h3>
                <p className="text-sm text-ink-text2">{f.description}</p>
                {f.visual_signature && <p className="text-xs text-ink-text3 mt-1">Visual: {f.visual_signature}</p>}
              </div>
              <button onClick={() => { if (confirm(`Delete faction "${f.name}"? This can't be undone.`)) del.mutate(f.id); }} className="text-ink-text3 hover:text-ink-red"><X size={16}/></button>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
