"use client";
// apps/web/components/inbox/WriterInbox.tsx
//
// Writer's feedback dashboard. Shows ratings aggregate, pending reviews,
// and unread private notes across all publications.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "@/lib/api";

interface InboxStats {
  total_views: number;
  total_ratings: number;
  avg_rating: number | null;
  total_reviews: number;
  pending_reviews: number;
  total_notes: number;
  unread_notes: number;
  followers: number;
}

interface ReviewItem {
  id: string;
  reader_id: string;
  body: string;
  status: string;
  created_at: string;
  reader_display_name: string | null;
  publication_slug?: string;
  publication_title?: string;
}

interface NoteItem {
  id: string;
  reader_id: string;
  publication_id: string;
  chapter_number: number | null;
  passage_reference: string | null;
  body: string;
  writer_reply: string | null;
  replied_at: string | null;
  is_read_by_writer: boolean;
  created_at: string;
  reader_display_name: string | null;
}

interface InboxData {
  stats: InboxStats;
  pending_reviews: ReviewItem[];
  unread_notes: NoteItem[];
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-ink-bg2 rounded-xl p-4 border border-ink-text2/10">
      <div className="text-xs text-ink-text2 uppercase tracking-wide mb-1">{label}</div>
      <div className="text-2xl font-bold text-ink-text">{value}</div>
      {sub && <div className="text-xs text-ink-text2 mt-0.5">{sub}</div>}
    </div>
  );
}

function StarBar({ avg }: { avg: number | null }) {
  if (!avg) return <span className="text-ink-text2 text-sm">No ratings yet</span>;
  const full = Math.round(avg);
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex gap-0.5">
        {[1,2,3,4,5].map(s => (
          <span key={s} className={`text-base ${s <= full ? "text-amber-400" : "text-ink-text2/30"}`}>★</span>
        ))}
      </div>
      <span className="text-ink-text font-semibold">{avg.toFixed(1)}</span>
    </div>
  );
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 2)   return "just now";
  if (minutes < 60)  return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24)    return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30)     return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export default function WriterInbox() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"overview" | "reviews" | "notes">("overview");
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [replyText, setReplyText]   = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["inbox"],
    queryFn: () => request<InboxData>("/v1/inbox/"),
  });

  const approveReview = useMutation({
    mutationFn: (id: string) =>
      request(`/v1/social/reviews/${id}/approve`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inbox"] }),
  });

  const declineReview = useMutation({
    mutationFn: (id: string) =>
      request(`/v1/social/reviews/${id}/decline`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inbox"] }),
  });

  const replyNote = useMutation({
    mutationFn: ({ id, reply }: { id: string; reply: string }) =>
      request(`/v1/social/notes/${id}/reply`, {
        method: "POST",
        body: JSON.stringify({ reply }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["inbox"] });
      setReplyingTo(null);
      setReplyText("");
    },
  });

  const markRead = useMutation({
    mutationFn: (id: string) =>
      request(`/v1/social/notes/${id}/read`, { method: "PUT" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inbox"] }),
  });

  if (isLoading || !data) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="w-5 h-5 border-2 border-ink-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const { stats, pending_reviews, unread_notes } = data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-ink-text">Reader Feedback</h2>
        <p className="text-sm text-ink-text2 mt-1">
          Ratings, reviews, and private notes from your readers.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-ink-text2/15">
        {(["overview", "reviews", "notes"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-5 py-2.5 text-sm font-medium capitalize transition border-b-2 -mb-px flex items-center gap-2 ${
              tab === t
                ? "border-ink-gold text-ink-gold"
                : "border-transparent text-ink-text2 hover:text-ink-text"
            }`}
          >
            {t}
            {t === "reviews" && stats.pending_reviews > 0 && (
              <span className="text-xs bg-amber-400/20 text-amber-300 px-1.5 py-0.5 rounded-full">
                {stats.pending_reviews}
              </span>
            )}
            {t === "notes" && stats.unread_notes > 0 && (
              <span className="text-xs bg-ink-gold/20 text-ink-gold px-1.5 py-0.5 rounded-full">
                {stats.unread_notes}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Overview ── */}
      {tab === "overview" && (
        <div className="space-y-6">
          {/* Stats grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Total views" value={stats.total_views.toLocaleString()} />
            <StatCard label="Ratings" value={stats.total_ratings} />
            <StatCard label="Followers" value={stats.followers} />
            <StatCard label="Reviews" value={stats.total_reviews}
                      sub={stats.pending_reviews > 0 ? `${stats.pending_reviews} pending` : undefined} />
          </div>

          {/* Rating display */}
          <div className="bg-ink-bg2 rounded-xl p-5 border border-ink-text2/10">
            <div className="text-xs text-ink-text2 uppercase tracking-wide mb-3">Average rating</div>
            <StarBar avg={stats.avg_rating} />
            {stats.total_ratings > 0 && (
              <p className="text-xs text-ink-text2 mt-2">
                Based on {stats.total_ratings} rating{stats.total_ratings !== 1 ? "s" : ""}
              </p>
            )}
          </div>

          {/* Quick actions */}
          {(stats.pending_reviews > 0 || stats.unread_notes > 0) && (
            <div className="space-y-2">
              {stats.pending_reviews > 0 && (
                <button
                  onClick={() => setTab("reviews")}
                  className="w-full text-left flex justify-between items-center p-4 bg-amber-400/5 border border-amber-400/20 rounded-xl hover:border-amber-400/40 transition"
                >
                  <span className="text-sm text-amber-300">
                    {stats.pending_reviews} review{stats.pending_reviews !== 1 ? "s" : ""} waiting for approval
                  </span>
                  <span className="text-amber-300 text-sm">→</span>
                </button>
              )}
              {stats.unread_notes > 0 && (
                <button
                  onClick={() => setTab("notes")}
                  className="w-full text-left flex justify-between items-center p-4 bg-ink-gold/5 border border-ink-gold/20 rounded-xl hover:border-ink-gold/40 transition"
                >
                  <span className="text-sm text-ink-gold">
                    {stats.unread_notes} unread private note{stats.unread_notes !== 1 ? "s" : ""}
                  </span>
                  <span className="text-ink-gold text-sm">→</span>
                </button>
              )}
            </div>
          )}

          {stats.total_views === 0 && (
            <div className="text-center py-12 text-ink-text2">
              <div className="text-4xl mb-3">📖</div>
              <p className="text-sm">No reader activity yet.</p>
              <p className="text-xs mt-1 text-ink-text2/60">
                Publish your story to start receiving feedback.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── Reviews ── */}
      {tab === "reviews" && (
        <div className="space-y-3">
          {pending_reviews.length === 0 ? (
            <div className="text-center py-12 text-ink-text2">
              <div className="text-3xl mb-3">✓</div>
              <p className="text-sm">No pending reviews.</p>
            </div>
          ) : (
            <>
              <p className="text-xs text-ink-text2">
                Approve reviews to make them public. Declined reviews are invisible
                to readers (but counted in your transparency stats).
              </p>
              {pending_reviews.map(review => (
                <div
                  key={review.id}
                  className="bg-ink-bg2 rounded-xl p-4 border border-ink-text2/10 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-ink-text">
                      {review.reader_display_name || "Anonymous reader"}
                    </span>
                    <span className="text-xs text-ink-text2">{timeAgo(review.created_at)}</span>
                  </div>
                  <p className="text-sm text-ink-text leading-relaxed">{review.body}</p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => approveReview.mutate(review.id)}
                      disabled={approveReview.isPending}
                      className="px-4 py-1.5 text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20 rounded-lg hover:bg-green-500/20 transition disabled:opacity-50"
                    >
                      ✓ Approve
                    </button>
                    <button
                      onClick={() => declineReview.mutate(review.id)}
                      disabled={declineReview.isPending}
                      className="px-4 py-1.5 text-xs font-medium bg-transparent text-ink-text2 border border-ink-text2/20 rounded-lg hover:border-red-400/40 hover:text-red-400 transition disabled:opacity-50"
                    >
                      Decline
                    </button>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* ── Notes ── */}
      {tab === "notes" && (
        <div className="space-y-3">
          {unread_notes.length === 0 ? (
            <div className="text-center py-12 text-ink-text2">
              <div className="text-3xl mb-3">✉️</div>
              <p className="text-sm">No new private notes.</p>
            </div>
          ) : (
            unread_notes.map(note => (
              <div
                key={note.id}
                className={`bg-ink-bg2 rounded-xl p-4 border space-y-3 ${
                  note.is_read_by_writer
                    ? "border-ink-text2/10"
                    : "border-ink-gold/25"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-ink-text">
                        {note.reader_display_name || "A reader"}
                      </span>
                      {note.chapter_number && (
                        <span className="text-xs text-ink-text2 border border-ink-text2/20 rounded px-1.5 py-0.5">
                          Ch. {note.chapter_number}
                        </span>
                      )}
                      {!note.is_read_by_writer && (
                        <span className="text-xs bg-ink-gold/15 text-ink-gold rounded px-1.5 py-0.5">
                          new
                        </span>
                      )}
                    </div>
                    {note.passage_reference && (
                      <blockquote className="text-xs italic text-ink-text2 border-l-2 border-ink-gold/40 pl-2 mb-2 line-clamp-2">
                        "{note.passage_reference}"
                      </blockquote>
                    )}
                    <p className="text-sm text-ink-text leading-relaxed">{note.body}</p>
                  </div>
                  <span className="text-xs text-ink-text2 shrink-0">
                    {timeAgo(note.created_at)}
                  </span>
                </div>

                {/* Writer's existing reply */}
                {note.writer_reply && (
                  <div className="ml-4 pl-3 border-l border-ink-gold/30">
                    <p className="text-xs text-ink-text2 mb-1">Your reply:</p>
                    <p className="text-sm text-ink-text">{note.writer_reply}</p>
                  </div>
                )}

                {/* Reply input */}
                {replyingTo === note.id ? (
                  <div className="space-y-2">
                    <textarea
                      value={replyText}
                      onChange={e => setReplyText(e.target.value)}
                      placeholder="Your private reply…"
                      rows={3}
                      className="w-full bg-ink-bg border border-ink-text2/20 rounded-lg px-3 py-2 text-sm text-ink-text resize-none focus:outline-none focus:border-ink-gold/50 placeholder-ink-text2/50"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => replyNote.mutate({ id: note.id, reply: replyText })}
                        disabled={replyText.trim().length < 1 || replyNote.isPending}
                        className="px-4 py-1.5 text-xs bg-ink-gold text-ink-bg rounded-lg font-medium disabled:opacity-40 hover:opacity-90 transition"
                      >
                        {replyNote.isPending ? "Sending…" : "Send reply"}
                      </button>
                      <button
                        onClick={() => { setReplyingTo(null); setReplyText(""); }}
                        className="px-4 py-1.5 text-xs text-ink-text2 hover:text-ink-text transition"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    {!note.writer_reply && (
                      <button
                        onClick={() => {
                          setReplyingTo(note.id);
                          if (!note.is_read_by_writer) markRead.mutate(note.id);
                        }}
                        className="text-xs text-ink-gold hover:underline transition"
                      >
                        Reply privately
                      </button>
                    )}
                    {!note.is_read_by_writer && (
                      <button
                        onClick={() => markRead.mutate(note.id)}
                        className="text-xs text-ink-text2 hover:text-ink-text transition"
                      >
                        Mark as read
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
