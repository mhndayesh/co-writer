"use client";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import * as api from "@/lib/api";
import { Card, PageHdr, Tag } from "@/components/ui/Primitives";

export default function TimelinePage() {
  const { storyId } = useParams<{ storyId: string }>();
  const { data: chapters } = useQuery({ queryKey: ["chapters", storyId], queryFn: () => api.listChapters(storyId) });
  const { data: characters } = useQuery({ queryKey: ["characters", storyId], queryFn: () => api.listCharacters(storyId) });

  const byId = Object.fromEntries((characters || []).map((c: any) => [c.id, c]));

  return (
    <div className="max-w-4xl">
      <PageHdr title="Memory Timeline" subtitle="Chronological pulse of your story — chapters, POVs, and the cast walking on stage." />
      <ol className="relative border-l border-ink-border ml-3 pl-6 space-y-4">
        {(chapters || []).map((c: any) => (
          <li key={c.id} className="relative">
            <span className="absolute -left-[33px] top-2 w-3 h-3 rounded-full bg-ink-gold border border-ink-deep"/>
            <Card>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs text-ink-text3">Ch {c.number}</span>
                <h3 className="font-display text-lg">{c.title || "Untitled"}</h3>
              </div>
              {c.summary && <p className="text-sm text-ink-text2 mb-2">{c.summary}</p>}
              <div className="flex flex-wrap gap-1">
                {c.pov_character_id && byId[c.pov_character_id] && <Tag color="gold">POV: {byId[c.pov_character_id].name}</Tag>}
                {(c.character_ids || []).map((cid: string) => byId[cid] && <Tag key={cid} color="muted">{byId[cid].name}</Tag>)}
              </div>
            </Card>
          </li>
        ))}
        {(!chapters || chapters.length === 0) && <li><Card><p className="text-ink-text2">No chapters yet.</p></Card></li>}
      </ol>
    </div>
  );
}
