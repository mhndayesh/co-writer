"use client";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import * as api from "@/lib/api";
import { Card, PageHdr, Tag } from "@/components/ui/Primitives";

export default function BoardPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const { data: chapters } = useQuery({ queryKey: ["chapters", storyId], queryFn: () => api.listChapters(storyId) });
  const { data: threads } = useQuery({ queryKey: ["threads", storyId], queryFn: () => api.listThreads(storyId) });
  const { data: scenes } = useQuery({ queryKey: ["scenes", storyId], queryFn: () => api.listScenes(storyId) });

  return (
    <div className="max-w-6xl">
      <PageHdr title="Plot Board" subtitle="A live read of your story structure: chapters, threads, and scene cards." />

      <h2 className="font-display text-xl mb-3">Chapters</h2>
      <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3 mb-8">
        {(chapters || []).map((c: any) => (
          <Link key={c.id} href={`/studio/${storyId}/chapters`}>
            <Card className="hover:border-ink-gold/50 transition-colors">
              <p className="text-xs text-ink-text2">Ch {c.number}</p>
              <h3 className="font-display text-lg mt-1">{c.title || "Untitled"}</h3>
              {c.summary && <p className="text-sm text-ink-text2 mt-2 line-clamp-3">{c.summary}</p>}
            </Card>
          </Link>
        ))}
        {(!chapters || chapters.length === 0) && <Card><p className="text-ink-text2 text-sm">No chapters yet.</p></Card>}
      </div>

      <h2 className="font-display text-xl mb-3">Threads</h2>
      <div className="grid gap-2 md:grid-cols-2 mb-8">
        {(threads || []).map((t: any) => (
          <Card key={t.id}>
            <div className="flex items-center gap-2 mb-1"><h3 className="font-display">{t.name}</h3><Tag color={t.status === "paid_off" ? "green" : t.status === "abandoned" ? "muted" : "gold"}>{t.status?.replace("_"," ")}</Tag></div>
            <p className="text-sm text-ink-text2">{t.description}</p>
          </Card>
        ))}
        {(!threads || threads.length === 0) && <Card><p className="text-ink-text2 text-sm">No threads yet.</p></Card>}
      </div>

      <h2 className="font-display text-xl mb-3">Scene cards</h2>
      <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
        {(scenes || []).map((s: any) => (
          <Card key={s.id}>
            {s.beat && <p className="text-xs uppercase tracking-wider text-ink-text2">{s.beat}</p>}
            <p className="text-sm mt-1">{s.content}</p>
          </Card>
        ))}
        {(!scenes || scenes.length === 0) && <Card><p className="text-ink-text2 text-sm">No scene cards yet.</p></Card>}
      </div>
    </div>
  );
}
