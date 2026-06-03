"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Plus, Settings, Trash2, LogOut, Send } from "lucide-react";
import * as api from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { Btn, Card, FG, Inp, Sel, PageHdr, Tag } from "@/components/ui/Primitives";
import { ThemeToggle } from "@/components/shell/ThemeToggle";

const GENRES = ["Fantasy", "Sci-Fi", "Mystery", "Thriller", "Romance", "Historical", "Horror", "Literary", "Other"];

export default function StudioHub() {
  const router = useRouter();
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState(GENRES[0]);
  const authed = useRequireAuth();

  const { data: stories, isLoading } = useQuery({
    queryKey: ["stories"],
    queryFn: api.listStories,
    enabled: authed,
  });

  const create = useMutation({
    mutationFn: (p: any) => api.createStory(p),
    onSuccess: (s) => { qc.invalidateQueries({ queryKey: ["stories"] }); router.push(`/studio/${s.id}/flow`); },
  });

  const del = useMutation({
    mutationFn: (id: string) => api.deleteStory(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["stories"] }),
  });

  async function logout() {
    await api.logout();  // server-side revoke + clears local tokens
    qc.clear();          // drop cached stories/entitlement so they don't flash for the next user
    router.push("/login");
  }

  return (
    <main className="max-w-6xl mx-auto p-4 sm:p-6">
      <div className="mb-1">
        <span className="text-[10px] uppercase tracking-[0.25em] text-ink-gold">Co-Writer</span>
        <span className="text-[10px] text-ink-text3 mx-1">·</span>
        <span className="text-[10px] uppercase tracking-[0.2em] text-ink-text3">G-Ink Studio</span>
      </div>
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

      {authed && isLoading && <p className="text-ink-text2">Loading…</p>}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {(stories || []).map((s: any) => {
          const cover = api.mediaUrl(s.cover_image_url);
          return (
          <Card key={s.id} className="flex flex-col !p-0 overflow-hidden">
            {/* Cover banner (or a genre-tinted placeholder) */}
            <Link href={`/studio/${s.id}/flow`} className="block relative h-32 bg-ink-surface2 border-b border-ink-border">
              {cover ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={cover} alt="" className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full grid place-items-center">
                  <BookOpen size={26} className="text-ink-text3" />
                </div>
              )}
            </Link>
            <div className="p-4 flex flex-col flex-1">
              <div className="flex items-start justify-between gap-2">
                <Link href={`/studio/${s.id}/flow`} className="flex-1 min-w-0">
                  <h3 className="font-display text-lg text-ink-text mb-1 truncate">{s.title || "Untitled"}</h3>
                  <p className="text-xs text-ink-text2 uppercase tracking-wider">{s.genre || "Story"}</p>
                </Link>
                <button
                  onClick={() => { if (confirm(`Delete "${s.title}"?`)) del.mutate(s.id); }}
                  className="text-ink-text3 hover:text-ink-red"
                  aria-label="Delete story"
                ><Trash2 size={14}/></button>
              </div>
              <div className="flex flex-wrap gap-2 mt-3 text-xs text-ink-text2">
                <Tag color="muted"><BookOpen size={10}/> {s.stats?.chapters ?? 0} chapters</Tag>
                <Tag color="muted">{s.stats?.characters ?? 0} characters</Tag>
                <Tag color="muted">{s.stats?.words ?? 0} words</Tag>
              </div>
              <div className="flex gap-2 mt-4">
                <Link href={`/studio/${s.id}/flow`} className="btn btn-primary flex-1 justify-center">Open →</Link>
                <Link href={`/publish/${s.id}`} className="btn justify-center" title="Publish this story">
                  <Send size={14}/> Publish
                </Link>
              </div>
            </div>
          </Card>
          );
        })}
        {authed && !isLoading && (stories || []).length === 0 && (
          <Card className="md:col-span-2 lg:col-span-3 text-center text-ink-text2">
            No stories yet. Create your first above.
          </Card>
        )}
      </div>
    </main>
  );
}
