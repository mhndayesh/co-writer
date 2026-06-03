"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr, QueryError, Ta } from "@/components/ui/Primitives";

export default function LocationsPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();
  const { data, isError, error, refetch } = useQuery({ queryKey: ["locations", storyId], queryFn: () => api.listLocations(storyId) });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const create = useMutation({
    mutationFn: () => api.createLocation(storyId, { name, description }),
    onSuccess: () => { setName(""); setDescription(""); qc.invalidateQueries({ queryKey: ["locations", storyId] }); },
  });
  const del = useMutation({
    mutationFn: (id: string) => api.deleteLocation(storyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["locations", storyId] }),
  });

  return (
    <div className="max-w-3xl">
      <PageHdr title="Locations" subtitle="Places that anchor your scenes." />
      <Card className="mb-4">
        <FG label="Name"><Inp value={name} onChange={e => setName(e.target.value)} /></FG>
        <FG label="Description"><Ta value={description} onChange={e => setDescription(e.target.value)} /></FG>
        <div className="flex justify-end"><Btn variant="primary" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}><Plus size={14}/> Add location</Btn></div>
      </Card>
      {isError && <QueryError error={error} retry={refetch} what="locations" />}
      <ul className="space-y-2">
        {(data || []).map((l: any) => (
          <li key={l.id}>
            <Card className="flex items-start justify-between gap-2">
              <div>
                <h3 className="font-display text-lg">{l.name}</h3>
                <p className="text-sm text-ink-text2">{l.description}</p>
              </div>
              <button onClick={() => { if (confirm(`Delete location "${l.name}"? This can't be undone.`)) del.mutate(l.id); }} className="text-ink-text3 hover:text-ink-red"><X size={16}/></button>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
