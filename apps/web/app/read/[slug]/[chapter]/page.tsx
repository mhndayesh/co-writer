"use client";

import { useParams } from "next/navigation";
import ReadingView from "@/components/reader/ReadingView";
import { useIsAuthed } from "@/lib/auth";

export default function ChapterPage() {
  const params = useParams<{ slug: string; chapter: string }>();
  const authed = useIsAuthed();
  const chapterNum = parseInt(params.chapter, 10);

  if (isNaN(chapterNum) || chapterNum < 1) {
    return <p className="p-8 text-ink-text2">Invalid chapter.</p>;
  }

  return (
    <ReadingView
      slug={params.slug}
      chapterNumber={chapterNum}
      storyTitle=""
      authorName=""
      isAuthenticated={authed}
    />
  );
}
