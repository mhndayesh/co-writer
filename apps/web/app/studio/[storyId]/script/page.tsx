"use client";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import * as api from "@/lib/api";
import { Card, PageHdr } from "@/components/ui/Primitives";

export default function ScriptPage() {
  const { storyId } = useParams<{ storyId: string }>();
  const { data: chapters } = useQuery({ queryKey: ["chapters", storyId], queryFn: () => api.listChapters(storyId) });

  return (
    <div className="max-w-4xl">
      <PageHdr title="Chapter Script" subtitle="Manuscript view of every chapter, in order. Use Chapters tab to edit." />
      {(chapters || []).map((c: any) => (
        <Card key={c.id} className="mb-4">
          <p className="text-xs text-ink-text2">Chapter {c.number}</p>
          <h2 className="font-display text-2xl mt-1 mb-3">{c.title || "Untitled"}</h2>
          {c.summary && <p className="italic text-ink-text2 mb-3">{c.summary}</p>}
          <pre className="whitespace-pre-wrap leading-relaxed text-base font-body text-ink-text">{c.content || "(empty)"}</pre>
        </Card>
      ))}
      {(!chapters || chapters.length === 0) && <Card><p className="text-ink-text2">No chapters yet. Write your first scene in Flow Writing.</p></Card>}
    </div>
  );
}
