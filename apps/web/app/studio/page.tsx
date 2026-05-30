"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Plus, Settings, Trash2, LogOut } from "lucide-react";
import * as api from "@/lib/api";
import { clearTokens, isAuthed } from "@/lib/auth";
import { Btn, Card, FG, Inp, Sel, PageHdr, Tag } from "@/components/ui/Primitives";
import { ThemeToggle } from "@/components/shell/ThemeToggle";

const GENRES = ["Fantasy", "Sci-Fi", "Mystery", "Thriller", "Romance", "Historical", "Horror", "Literary", "Other"];

export default function StudioHub() {
  const router = useRouter();
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState(GENRES[0]);

  useEffect(() => { if (!isAuthed()) router.replace("/login"); }, [router]);

  const { data: stories, isLoading } = useQuery({ queryKey: ["stories"], queryFn: api.listStories, enabled: typeof window !== "undefined" });

  const create = useMutation({
    mutationFn: (p: any) => api.createStory(p),
    onSuccess: (s) => { qc.invalidateQueries({ queryKey: ["stories"] }); router.push(`/studio/${s.id}/flow`); },
  });

  const del = useMutation({
    mutationFn: (id: string) => api.deleteStory(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["stories"] }),
  });

  function logout() { clearTokens(); router.push("/login"); }

  return (
    <main className="max-w-6xl mx-auto p-6">
      <PageHdr
        title="Your stories"
        subtitle="Each story is a separate project. Open one to start writing."
        right={
          <div className="flex gap-2 items-center">
            <ThemeToggle />
            <Link href="/settings" className="btn"><Settings size={14}/> Settings</Link>
            <Btn variant="ghost" onClick={logout}><LogOut size={14}/> Sign out</Btn>
          </div>
        }
      />

      <Card className="mb-6">
        <h2 className="font-display text-lg mb-3">New story</h2>
        <div className="grid gap-3 md:grid-cols-[1fr_220px_auto] items-end">
          <FG label="Title">
            <Inp value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Bonebreaker Bay" />
          </FG>
          <FG label="Genre">
            <Sel value={genre} onChange={e => setGenre(e.target.value)}>
              {GENRES.map(g => <option key={g} value={g}>{g}</option>)}
            </Sel>
          </FG>
          <Btn
            variant="primary"
            disabled={!title.trim() || create.isPending}
            onClick={() => create.mutate({ title: title.trim(), genre })}
            className="mb-3"
          >
            <Plus size={14}/> {create.isPending ? "Creating…" : "Create"}
          </Btn>
        </div>
      </Card>

      {isLoading && <p className="text-ink-text2">Loading…</p>}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {(stories || []).map((s: any) => (
          <Card key={s.id} className="flex flex-col">
            <div className="flex items-start justify-between gap-2">
              <Link href={`/studio/${s.id}/flow`} className="flex-1">
                <h3 className="font-display text-lg text-ink-text mb-1">{s.title || "Untitled"}</h3>
                <p className="text-xs text-ink-text2 uppercase tracking-wider">{s.genre || "Story"}</p>
              </Link>
              <button
                onClick={() => { if (confirm(`Delete "${s.title}"?`)) del.mutate(s.id); }}
                className="text-ink-text3 hover:text-ink-red"
                aria-label="Delete story"
              ><Trash2 size={14}/></button>
            </div>
            <div className="flex gap-2 mt-3 text-xs text-ink-text2">
              <Tag color="muted"><BookOpen size={10}/> {s.stats?.chapters ?? 0} chapters</Tag>
              <Tag color="muted">{s.stats?.characters ?? 0} characters</Tag>
              <Tag color="muted">{s.stats?.words ?? 0} words</Tag>
            </div>
            <Link href={`/studio/${s.id}/flow`} className="btn btn-primary w-full mt-4">Open →</Link>
          </Card>
        ))}
        {!isLoading && (stories || []).length === 0 && (
          <Card className="md:col-span-2 lg:col-span-3 text-center text-ink-text2">
            No stories yet. Create your first above.
          </Card>
        )}
      </div>
    </main>
  );
}
