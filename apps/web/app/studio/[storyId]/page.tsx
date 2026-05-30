"use client";
import { useEffect } from "react";
import { useRouter, useParams } from "next/navigation";

export default function StoryHome() {
  const router = useRouter();
  const { storyId } = useParams<{ storyId: string }>();
  useEffect(() => { router.replace(`/studio/${storyId}/flow`); }, [router, storyId]);
  return null;
}
