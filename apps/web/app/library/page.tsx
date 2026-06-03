"use client";

import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, BookmarkX, BookOpen } from "lucide-react";
import * as api from "@/lib/api";
import { useIsAuthed } from "@/lib/auth";

function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  const mins = Math.max(0, Math.round((Date.now() - d) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function BookCard({ item, action }: { item: any; action?: React.ReactNode }) {
  const cover = api.mediaUrl(item.cover_image_url);
  const resume = item.last_chapter > 0 ? `/read/${item.slug}/${item.last_chapter}` : `/read/${item.slug}`;
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: "var(--r-lg)", overflow: "hidden", boxShadow: "var(--shadow)",
    }}>
      <Link href={resume} style={{ textDecoration: "none", display: "block" }}>
        <div style={{ aspectRatio: "3 / 4", background: "var(--surface-2)", display: "grid", placeItems: "center" }}>
          {cover
            // eslint-disable-next-line @next/next/no-img-element
            ? <img src={cover} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            : <BookOpen size={28} style={{ color: "var(--muted)", opacity: 0.5 }} />}
        </div>
        <div style={{ padding: "10px 12px" }}>
          <h3 style={{ fontFamily: "var(--font-serif)", fontSize: 15, color: "var(--text)", lineHeight: 1.3 }}>{item.title}</h3>
          {item.completion > 0 && (
            <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
              {Math.round(item.completion)}% · up to Ch. {item.last_chapter}
            </p>
          )}
        </div>
      </Link>
      {action && <div style={{ padding: "0 12px 12px" }}>{action}</div>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginTop: 36 }}>
      <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 20, color: "var(--text)", marginBottom: 14 }}>{title}</h2>
      {children}
    </section>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 16 }}>{children}</div>;
}

export default function LibraryPage() {
  const authed = useIsAuthed();
  const qc = useQueryClient();

  const { data: lib } = useQuery({ queryKey: ["library"], queryFn: api.getMyLibrary, enabled: authed });
  const { data: notif } = useQuery({ queryKey: ["notifications"], queryFn: () => api.listNotifications({ limit: 30 }), enabled: authed });

  const markAll = useMutation({
    mutationFn: () => api.markNotificationsRead({ all: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
      qc.invalidateQueries({ queryKey: ["nav-unread"] });
    },
  });
  const unfollow = useMutation({
    mutationFn: (slug: string) => api.unfollowStory(slug),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["library"] }),
  });

  if (!authed) {
    return (
      <div style={{ textAlign: "center", padding: "80px 16px", color: "var(--muted)" }}>
        <p style={{ fontFamily: "var(--font-serif)", fontSize: 22, marginBottom: 10, color: "var(--text)" }}>Your library</p>
        <p style={{ marginBottom: 16 }}>Sign in to save stories and get notified about new chapters.</p>
        <Link href="/login" style={{ color: "var(--accent)", fontWeight: 600 }}>Sign in →</Link>
      </div>
    );
  }

  const following = lib?.following || [];
  const inProgress = lib?.in_progress || [];
  const completed = lib?.completed || [];
  const notifs = notif?.items || [];
  const unread = notif?.unread_count || 0;

  return (
    <main style={{ maxWidth: 980, margin: "0 auto", padding: "40px clamp(16px,4vw,44px) 80px" }}>
      <h1 style={{ fontFamily: "var(--font-serif)", fontSize: 30, color: "var(--text)", letterSpacing: "-0.01em" }}>Your library</h1>

      {/* Notifications */}
      <section style={{ marginTop: 24 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 20, color: "var(--text)", display: "flex", alignItems: "center", gap: 8 }}>
            <Bell size={18} /> Notifications {unread > 0 && <span style={{ fontSize: 12, color: "var(--accent)" }}>({unread} new)</span>}
          </h2>
          {unread > 0 && (
            <button onClick={() => markAll.mutate()} disabled={markAll.isPending}
              style={{ fontSize: 13, color: "var(--muted)", background: "none", border: "none", cursor: "pointer" }}>
              Mark all read
            </button>
          )}
        </div>
        {notifs.length === 0 ? (
          <p style={{ color: "var(--muted)", fontSize: 14 }}>No notifications yet. Follow a story to hear when it posts a new chapter.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {notifs.map((n: any) => (
              <Link key={n.id} href={n.link || "#"} style={{
                textDecoration: "none", display: "block",
                background: n.read ? "transparent" : "var(--accent-soft)",
                border: "1px solid var(--border)", borderRadius: "var(--r-md, 10px)",
                padding: "10px 14px",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                  <span style={{ fontSize: 14, color: "var(--text)", fontWeight: n.read ? 400 : 600 }}>{n.title}</span>
                  <span style={{ fontSize: 12, color: "var(--muted)", flexShrink: 0 }}>{timeAgo(n.created_at)}</span>
                </div>
                {n.body && <p style={{ fontSize: 13, color: "var(--muted)", marginTop: 2 }}>{n.body}</p>}
              </Link>
            ))}
          </div>
        )}
      </section>

      {following.length > 0 && (
        <Section title="Saved stories">
          <Grid>
            {following.map((it: any) => (
              <BookCard key={it.slug} item={it} action={
                <button onClick={() => unfollow.mutate(it.slug)}
                  style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--muted)", background: "none", border: "1px solid var(--border)", borderRadius: 8, padding: "5px 10px", cursor: "pointer", width: "100%", justifyContent: "center" }}>
                  <BookmarkX size={13} /> Unsave
                </button>
              } />
            ))}
          </Grid>
        </Section>
      )}

      {inProgress.length > 0 && (
        <Section title="Continue reading"><Grid>{inProgress.map((it: any) => <BookCard key={it.slug} item={it} />)}</Grid></Section>
      )}

      {completed.length > 0 && (
        <Section title="Finished"><Grid>{completed.map((it: any) => <BookCard key={it.slug} item={it} />)}</Grid></Section>
      )}

      {following.length === 0 && inProgress.length === 0 && completed.length === 0 && (
        <p style={{ color: "var(--muted)", marginTop: 32 }}>
          You haven&apos;t saved or started any stories yet. <Link href="/" style={{ color: "var(--accent)", fontWeight: 600 }}>Browse stories →</Link>
        </p>
      )}
    </main>
  );
}
