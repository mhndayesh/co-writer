"use client";
// apps/web/components/reader/ReviewPanel.tsx
//
// Shows approved public reviews and a submission form for authenticated readers.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "@/lib/api";

interface Review {
  id: string;
  reader_id: string;
  body: string;
  status: string;
  approved_at: string | null;
  created_at: string;
  reader_display_name: string | null;
}

interface ReviewPanelProps {
  pubId: string;
  slug: string;
  isAuthenticated: boolean;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30)  return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}

function ReviewCard({ review }: { review: Review }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = review.body.length > 280;
  const displayText = isLong && !expanded
    ? review.body.slice(0, 280) + "…"
    : review.body;

  return (
    <div className="py-5 border-b border-white/[0.05] last:border-0">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-200">
          {review.reader_display_name || "A reader"}
        </span>
        <span className="text-xs text-gray-600">
          {timeAgo(review.approved_at || review.created_at)}
        </span>
      </div>
      <p className="text-sm text-gray-400 leading-relaxed">{displayText}</p>
      {isLong && (
        <button
          onClick={() => setExpanded(e => !e)}
          className="mt-1.5 text-xs text-amber-500/70 hover:text-amber-400 transition"
        >
          {expanded ? "Show less" : "Read more"}
        </button>
      )}
    </div>
  );
}

export default function ReviewPanel({ pubId, slug, isAuthenticated }: ReviewPanelProps) {
  const qc = useQueryClient();
  const [showForm, setShowForm]     = useState(false);
  const [body, setBody]             = useState("");
  const [submitted, setSubmitted]   = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { data: reviews = [], isLoading } = useQuery({
    queryKey: ["reviews", pubId],
    queryFn: () => request<Review[]>(`/v1/social/${pubId}/reviews`),
  });

  const submitReview = useMutation({
    mutationFn: () =>
      request(`/v1/social/${pubId}/review`, {
        method: "POST",
        body: JSON.stringify({ body }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reviews", pubId] });
      setSubmitted(true);
      setShowForm(false);
      setBody("");
      setSubmitError(null);
    },
    onError: (err: any) => {
      setSubmitError(err?.message || "Could not submit review. Please try again.");
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-white">
          Reviews
          {reviews.length > 0 && (
            <span className="ml-2 text-sm font-normal text-gray-500">
              ({reviews.length})
            </span>
          )}
        </h2>
        {isAuthenticated && !submitted && !showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="text-xs text-amber-500/80 hover:text-amber-400 transition"
          >
            + Write review
          </button>
        )}
      </div>

      {/* Submission form */}
      {showForm && (
        <div className="bg-white/[0.03] rounded-xl border border-white/8 p-4 space-y-3">
          <p className="text-xs text-gray-500">
            Your review will be visible to others once the author approves it.
          </p>
          {submitError && (
            <p className="text-xs text-red-400 bg-red-900/15 border border-red-700/20 rounded-lg px-3 py-2">
              {submitError}
            </p>
          )}
          <textarea
            value={body}
            onChange={e => { setBody(e.target.value); setSubmitError(null); }}
            placeholder="Share your thoughts about this story…"
            rows={4}
            maxLength={1000}
            className="w-full bg-[#0D0B08] border border-white/10 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-600 resize-none focus:outline-none focus:border-amber-400/30 transition"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-600">{body.length}/1000</span>
            <div className="flex gap-2">
              <button
                onClick={() => setShowForm(false)}
                className="px-4 py-1.5 text-xs text-gray-500 hover:text-white transition"
              >
                Cancel
              </button>
              <button
                onClick={() => submitReview.mutate()}
                disabled={body.trim().length < 20 || submitReview.isPending}
                className="px-4 py-1.5 text-xs bg-amber-500 hover:bg-amber-400 text-black font-medium rounded-lg transition disabled:opacity-40"
              >
                {submitReview.isPending ? "Submitting…" : "Submit"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Submitted message */}
      {submitted && (
        <div className="bg-green-900/15 border border-green-700/20 rounded-xl p-3 text-sm text-green-400">
          ✓ Review submitted — it will appear once the author approves it.
        </div>
      )}

      {/* Review list */}
      {isLoading ? (
        <div className="space-y-4">
          {[1, 2].map(i => (
            <div key={i} className="h-16 bg-white/[0.03] rounded-lg animate-pulse" />
          ))}
        </div>
      ) : reviews.length === 0 ? (
        <div className="py-8 text-center text-sm text-gray-600">
          No reviews yet.
          {isAuthenticated && !showForm && !submitted && (
            <span>
              {" "}
              <button
                onClick={() => setShowForm(true)}
                className="text-amber-500/70 hover:text-amber-400 transition"
              >
                Be the first.
              </button>
            </span>
          )}
        </div>
      ) : (
        <div>
          {reviews.map(review => (
            <ReviewCard key={review.id} review={review} />
          ))}
        </div>
      )}
    </div>
  );
}
