"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Radar, Search } from "lucide-react";
import * as api from "@/lib/api";
import { Btn, Card, FG, Inp, PageHdr } from "@/components/ui/Primitives";

export default function RadarPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const [q, setQ] = useState("");
  const preview = useMutation({
    mutationKey: ["llm", "rag.preview"],
    mutationFn: (query: string) => api.ragPreview(storyId, query),
  });
  const reindex = useMutation({
    mutationKey: ["llm", "rag.reindex"],
    mutationFn: () => api.ragReindex(storyId),
  });

  return (
    <div className="max-w-3xl">
      <PageHdr
        title="Continuity Radar"
        subtitle="What does the AI see for a given question? Inspect the Graph-RAG slice that gets fed into Story Check, Companion, and Flow Writing."
        right={<Btn onClick={() => reindex.mutate()} disabled={reindex.isPending}>{reindex.isPending ? "Reindexing…" : "Reindex story vectors"}</Btn>}
      />
      <Card className="mb-4">
        <FG label="Query"><Inp value={q} onChange={e => setQ(e.target.value)} placeholder="e.g. Aiden and the broken pact" onKeyDown={e => e.key === "Enter" && q.trim() && preview.mutate(q)} /></FG>
        <div className="flex justify-end"><Btn variant="primary" disabled={!q.trim() || preview.isPending} onClick={() => preview.mutate(q)}><Search size={14}/> {preview.isPending ? "Retrieving…" : "Show retrieval"}</Btn></div>
      </Card>
      {preview.data && (
        <Card>
          <h3 className="font-display text-lg mb-2 flex items-center gap-2"><Radar size={16}/> Graph-RAG context</h3>
          {preview.data.block ? (
            <pre className="whitespace-pre-wrap text-sm font-mono leading-relaxed text-ink-text">{preview.data.block}</pre>
          ) : (
            <p className="text-sm text-ink-text2">No retrieval — either Qdrant/Neo4j are unreachable, or the story has no embedded content yet. Click <em>Reindex story vectors</em> above.</p>
          )}
        </Card>
      )}
      {reindex.data && (
        <Card className="mt-4">
          {reindex.data.reason === "qdrant_unavailable" ? (
            <p className="text-sm text-ink-red">
              Qdrant is not running. Start it with <code className="font-mono bg-ink-surface2 px-1 rounded">./run.sh</code> — it
              launches Qdrant automatically via Docker. Vector search will be unavailable until then.
            </p>
          ) : reindex.data.reason ? (
            <p className="text-sm text-ink-red">Indexing failed: {reindex.data.reason}</p>
          ) : (
            <p className="text-sm text-ink-green">Indexed {reindex.data.indexed} vector{reindex.data.indexed !== 1 ? "s" : ""} successfully.</p>
          )}
        </Card>
      )}
    </div>
  );
}
