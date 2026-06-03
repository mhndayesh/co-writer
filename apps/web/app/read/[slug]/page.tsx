"use client";

import { useParams } from "next/navigation";
import StoryLandingPage from "@/components/reader/StoryLandingPage";
import { useIsAuthed } from "@/lib/auth";

export default function StoryPage() {
  const params = useParams<{ slug: string }>();
  const authed = useIsAuthed();
  return (
    <StoryLandingPage
      slug={params.slug}
      isAuthenticated={authed}
    />
  );
}
