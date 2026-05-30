"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { isAuthed } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    if (isAuthed()) router.replace("/studio");
  }, [router]);
  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-xl text-center">
        <p className="text-xs uppercase tracking-[0.3em] text-ink-text2 mb-4">G-Ink Novel Studio</p>
        <h1 className="text-5xl font-display mb-4">Write freely.<br/>The craft happens behind the scenes.</h1>
        <p className="text-ink-text2 mb-8">An AI-powered writing studio. Pour out the raw idea — the AI polishes the prose, files the characters, places, themes, and watches for continuity slips.</p>
        <div className="flex gap-3 justify-center">
          <Link href="/signup" className="btn btn-primary px-6 py-3">Get started</Link>
          <Link href="/login" className="btn px-6 py-3">Sign in</Link>
        </div>
      </div>
    </main>
  );
}
