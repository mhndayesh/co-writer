"use client";
// apps/web/components/reader/StoryLandingPage.tsx

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { request, mediaUrl } from "@/lib/api";
import RatingModal from "./RatingModal";
import ReviewPanel from "./ReviewPanel";

interface PublishedChapter {
  chapter_number: number;
  title: string;
  word_count: number;
  pushed_at: string;
}

interface StoryLanding {
  publication: {
    id: string;
    slug: string;
    status: string;
    release_type: "complete" | "serial";
    cover_image_url: string | null;
    tagline: string | null;
    genre: string | null;
    tags: string[];
    content_warnings: string[];
    view_count: number;
    total_planned_chapters: number | null;
    published_at: string | null;
  };
  story_title: string;
  story_logline: string | null;
  author_name: string;
  chapters: PublishedChapter[];
  avg_rating: number | null;
  rating_count: number;
}

interface Progress {
  last_chapter_number: number;
  completion_percentage: number;
  is_following: boolean;
}

function totalWords(chapters: PublishedChapter[]): string {
  const total = chapters.reduce((s, c) => s + (c.word_count || 0), 0);
  if (total < 1000) return `${total} words`;
  return `${(total / 1000).toFixed(0)}k words`;
}

function readTime(wordCount: number): string {
  const mins = Math.ceil(wordCount / 250);
  if (mins < 60) return `${mins} min read`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m read`;
}

export default function StoryLandingPage({
  slug,
  isAuthenticated,
}: {
  slug: string;
  isAuthenticated: boolean;
}) {
  const [showRatingModal, setShowRatingModal] = useState(false);
  const [followStatus, setFollowStatus]       = useState<"idle" | "loading" | "done">("idle");
  const [isFollowing, setIsFollowing]         = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["landing", slug],
    queryFn: () => request<StoryLanding>(`/v1/read/${slug}`),
  });

  const { data: progress } = useQuery({
    queryKey: ["progress", slug],
    queryFn: () => request<Progress | null>(`/v1/read/${slug}/progress`),
    enabled: isAuthenticated,
  });

  if (isLoading || !data) {
    return (
      <div className="min-h-screen bg-ink-bg flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-ink-gold/40 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const { publication: pub, story_title, story_logline, author_name, chapters, avg_rating, rating_count } = data;
  const totalChapters = chapters.length;
  const allWords      = chapters.reduce((s, c) => s + (c.word_count || 0), 0);
  const resumeChapter = progress?.last_chapter_number ?? 0;

  const handleFollow = async () => {
    if (!isAuthenticated) return;
    setFollowStatus("loading");
    try {
      if (isFollowing) {
        await request(`/v1/read/${slug}/follow`, { method: "DELETE" });
        setIsFollowing(false);
      } else {
        await request(`/v1/read/${slug}/follow`, { method: "POST" });
        setIsFollowing(true);
      }
      setFollowStatus("done");
      setTimeout(() => setFollowStatus("idle"), 1000);
    } catch {
      setFollowStatus("idle");
    }
  };

  return (
    <div className="min-h-screen bg-ink-bg text-ink-text">

      {/* Hero */}
      <div className="border-b border-ink-border">
        <div className="max-w-5xl mx-auto px-6 py-14 flex gap-10 items-start">

          {/* Cover */}
          <div className="shrink-0 w-36 h-52 rounded-xl overflow-hidden shadow-lg border border-ink-border">
            {pub.cover_image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={mediaUrl(pub.cover_image_url)} alt={story_title} className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full bg-ink-surface2 flex items-center justify-center">
                <span className="text-4xl font-bold font-serif text-ink-text3 opacity-60">
                  {story_title.slice(0, 2).toUpperCase()}
                </span>
              </div>
            )}
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0 space-y-4">
            <div>
              <h1 className="text-3xl font-display leading-tight text-ink-text">{story_title}</h1>
              <p className="text-ink-text2 text-sm mt-1">by {author_name}</p>
            </div>

            {pub.tagline && (
              <p className="text-sm text-ink-text2 leading-relaxed italic">{pub.tagline}</p>
            )}

            {/* Tags */}
            <div className="flex flex-wrap gap-2">
              {pub.genre && (
                <span className="text-xs px-2.5 py-1 rounded-full border border-ink-gold/40 bg-ink-gold/10 text-ink-goldLight font-medium capitalize">
                  {pub.genre}
                </span>
              )}
              <span className="text-xs px-2.5 py-1 rounded-full border border-ink-border bg-ink-surface2 text-ink-text2">
                {pub.release_type === "serial" ? "📅 Serial" : "📖 Complete"}
              </span>
              {pub.content_warnings.length > 0 && (
                <span className="text-xs px-2.5 py-1 rounded-full border border-ink-red/30 bg-ink-red/10 text-ink-red">
                  ⚠ Content warnings
                </span>
              )}
              {pub.tags.slice(0, 3).map(tag => (
                <span key={tag} className="text-xs px-2.5 py-1 rounded-full border border-ink-border text-ink-text3">
                  {tag}
                </span>
              ))}
            </div>

            {/* Stats */}
            <div className="flex flex-wrap items-center gap-4 text-sm text-ink-text2">
              <span>{totalChapters} chapter{totalChapters !== 1 ? "s" : ""}</span>
              <span className="text-ink-text3">·</span>
              <span>{totalWords(chapters)}</span>
              <span className="text-ink-text3">·</span>
              <span>{(pub.view_count ?? 0).toLocaleString()} reads</span>
              {avg_rating && (
                <>
                  <span className="text-ink-text3">·</span>
                  <span className="inline-flex items-center gap-1">
                    <span className="text-ink-gold">★</span>
                    {avg_rating.toFixed(1)}
                    <span className="text-ink-text3">({rating_count})</span>
                  </span>
                </>
              )}
            </div>

            {/* CTAs */}
            <div className="flex flex-wrap gap-3 pt-1">
              {resumeChapter > 0 && resumeChapter < totalChapters ? (
                <Link href={`/read/${slug}/${resumeChapter + 1}`} className="btn btn-primary">
                  Resume — Ch. {resumeChapter + 1}
                </Link>
              ) : (
                <Link href={`/read/${slug}/1`} className="btn btn-primary">
                  Start reading
                </Link>
              )}

              {isAuthenticated && pub.release_type === "serial" && (
                <button
                  onClick={handleFollow}
                  disabled={followStatus === "loading"}
                  className={`btn ${isFollowing ? "" : "btn-ghost"}`}
                >
                  {followStatus === "loading" ? "…" : isFollowing ? "✓ Following" : "+ Follow"}
                </button>
              )}

              {isAuthenticated && (
                <button onClick={() => setShowRatingModal(true)} className="btn btn-ghost">
                  ★ Rate
                </button>
              )}
            </div>

            {pub.content_warnings.length > 0 && (
              <details className="text-xs text-ink-text3 cursor-pointer">
                <summary className="hover:text-ink-text2 transition">
                  ▸ Content warnings ({pub.content_warnings.length})
                </summary>
                <p className="mt-1 text-ink-red/80 leading-relaxed">{pub.content_warnings.join(", ")}</p>
              </details>
            )}
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="max-w-5xl mx-auto px-6 py-10 grid grid-cols-1 lg:grid-cols-3 gap-10">

        {/* Left: chapters + reviews */}
        <div className="lg:col-span-2 space-y-6">
          <h2 className="font-display text-lg text-ink-text">
            Chapters
            {pub.release_type === "serial" && pub.total_planned_chapters && (
              <span className="ml-2 text-xs font-normal text-ink-text3">
                ({totalChapters} of {pub.total_planned_chapters} planned)
              </span>
            )}
          </h2>

          <div className="space-y-0.5">
            {chapters.map(ch => {
              const isRead = resumeChapter >= ch.chapter_number;
              return (
                <Link
                  key={ch.chapter_number}
                  href={`/read/${slug}/${ch.chapter_number}`}
                  className="group flex items-center justify-between py-3 px-4 rounded-lg hover:bg-ink-surface2 transition"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className={`text-xs font-mono shrink-0 w-6 text-center ${isRead ? "text-ink-gold" : "text-ink-text3"}`}>
                      {isRead ? "✓" : ch.chapter_number}
                    </span>
                    <span className={`text-sm truncate transition ${isRead ? "text-ink-text2" : "text-ink-text"} group-hover:text-ink-text`}>
                      {ch.title || `Chapter ${ch.chapter_number}`}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 shrink-0 ml-4 text-xs text-ink-text3">
                    <span>{ch.word_count.toLocaleString()} w</span>
                    <span className="hidden sm:block">
                      {new Date(ch.pushed_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                    </span>
                    <span className="text-ink-text3 group-hover:text-ink-text2 transition">→</span>
                  </div>
                </Link>
              );
            })}
          </div>

          {/* Reviews */}
          <div className="pt-6 border-t border-ink-border">
            <ReviewPanel pubId={pub.id} slug={slug} isAuthenticated={isAuthenticated} />
          </div>
        </div>

        {/* Right: sidebar */}
        <div className="space-y-4">
          {/* Reading stats */}
          <div className="card-ink p-4 space-y-3">
            <h3 className="text-xs text-ink-text3 uppercase tracking-wide">Reading stats</h3>
            <div className="space-y-2">
              {[
                { label: "Total length", value: totalWords(chapters) },
                { label: "Est. time",    value: readTime(allWords) },
                { label: "Chapters",     value: `${totalChapters}` },
                { label: "Reads",        value: pub.view_count.toLocaleString() },
                ...(avg_rating ? [{ label: "Rating", value: `★ ${avg_rating.toFixed(1)} (${rating_count})` }] : []),
              ].map(({ label, value }) => (
                <div key={label} className="flex justify-between items-center text-sm">
                  <span className="text-ink-text2">{label}</span>
                  <span className="text-ink-text font-medium">{value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Reader progress */}
          {progress && progress.completion_percentage > 0 && (
            <div className="card-ink p-4 space-y-2">
              <h3 className="text-xs text-ink-text3 uppercase tracking-wide">Your progress</h3>
              <div className="h-1.5 bg-ink-surface3 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-ink-gold transition-all"
                  style={{ width: `${progress.completion_percentage}%` }}
                />
              </div>
              <p className="text-xs text-ink-text3">
                {Math.round(progress.completion_percentage)}% complete
                {progress.last_chapter_number > 0 && ` · up to Ch. ${progress.last_chapter_number}`}
              </p>
            </div>
          )}

          {/* About */}
          {story_logline && (
            <div className="card-ink p-4 space-y-2">
              <h3 className="text-xs text-ink-text3 uppercase tracking-wide">About</h3>
              <p className="text-sm text-ink-text2 leading-relaxed">{story_logline}</p>
            </div>
          )}
        </div>
      </div>

      {showRatingModal && (
        <RatingModal pubId={pub.id} storyTitle={story_title} onClose={() => setShowRatingModal(false)} />
      )}
    </div>
  );
}
