"use client";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Network } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, PageHdr, Tag } from "@/components/ui/Primitives";
import { StoryMap } from "@/components/graph/StoryMap";

export default function MapPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["graph", storyId], queryFn: () => api.graphView(storyId) });
  const reproject = useMutation({
    mutationKey: ["llm", "graph.reproject"],
    mutationFn: () => api.graphReproject(storyId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["graph", storyId] }),
  });

  return (
    <div className="max-w-6xl">
      <PageHdr
        title="◎ Story Map"
        subtitle="Gold = characters · rose = chapters · green = themes · cyan = locations · purple = factions. Drag, scroll to zoom."
        right={
          <div className="flex items-center gap-2">
            {data && <Tag color="muted"><Network size={10}/> {data.source}</Tag>}
            <Btn onClick={() => reproject.mutate()} disabled={reproject.isPending}>
              <RefreshCw size={14}/> {reproject.isPending ? "Re-projecting…" : "Re-project graph"}
            </Btn>
          </div>
        }
      />
      {isLoading && <p className="text-ink-text2">Loading graph…</p>}
      {data && data.nodes.length === 0 && (
        <Card><p className="text-ink-text2">No entities yet. Add characters or chapters to see your map come alive.</p></Card>
      )}
      {data && data.nodes.length > 0 && <StoryMap data={data as any} />}
    </div>
  );
}
