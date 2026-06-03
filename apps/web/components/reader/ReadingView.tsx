"use client";
// apps/web/components/reader/ReadingView.tsx
//
// The core reading experience. Features:
//  - Clean serif typography for comfortable reading
//  - Text selection → "Add Note" floating button (key differentiator)
//  - Progress bar + chapter navigation
//  - Reading settings (font size, theme)
//  - Inline rating/review trigger after completion

import { useState, useEffect, useRef, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { request } from "@/lib/api";

interface ChapterData {
  chapter: {
    id: string;
    chapter_number: number;
    title: string;
    content: string;
    word_count: number;
    pushed_at: string;
  };
  total_chapters: number;
  pub_slug: string;
  pub_id: string;
  story_title?: string;
  author_name?: string;
}

interface ReadingViewProps {
  slug: string;
  chapterNumber: number;
  storyTitle: string;
  authorName: string;
  isAuthenticated: boolean;
}

type Theme = "site" | "cream" | "sepia" | "dark";

// "site" follows the app's ink-* CSS variables (light or dark based on the user's
// active theme). The others are fixed reading-specific palettes.
const THEMES: Record<Theme, { bg: string; text: string; muted: string; border: string }> = {
  site: {
    bg:     "rgb(var(--ink-bg))",
    text:   "rgb(var(--ink-text))",
    muted:  "rgb(var(--ink-text2))",
    border: "rgb(var(--ink-border))",
  },
  cream: {
    bg:     "#FAFAF7",
    text:   "#1A1915",
    muted:  "#6B6960",
    border: "#E2E0D8",
  },
  sepia: {
    bg:     "#F5EEDF",
    text:   "#2C2416",
    muted:  "#8A7B65",
    border: "#D5C8B0",
  },
  dark: {
    bg:     "#121210",
    text:   "#E8E4D8",
    muted:  "#8A8880",
    border: "#2A2A26",
  },
};

const FONT_SIZES = [16, 18, 20, 22, 24];

// Approximate reading time
function readingMinutes(wordCount: number): string {
  const mins = Math.ceil(wordCount / 250);
  return mins <= 1 ? "~1 min" : `~${mins} min`;
}

function wpmProgress(content: string, scrollPct: number): number {
  return Math.min(100, Math.round(scrollPct));
}

export default function ReadingView({
  slug, chapterNumber, storyTitle, authorName, isAuthenticated,
}: ReadingViewProps) {
  const qc = useQueryClient();
  const contentRef = useRef<HTMLDivElement>(null);

  const [theme, setTheme]         = useState<Theme>("site");
  const [fontSize, setFontSize]   = useState(18);
  const [showSettings, setShowSettings] = useState(false);
  const [scrollPct, setScrollPct] = useState(0);

  // Text-selection note state
  const [selection, setSelection]         = useState<{ text: string; top: number; left: number } | null>(null);
  const [noteModal, setNoteModal]         = useState<{ passage: string } | null>(null);
  const [noteBody, setNoteBody]           = useState("");
  const [noteSent, setNoteSent]           = useState(false);

  // Post-completion state
  const [showRating, setShowRating]       = useState(false);
  const [ratingSubmitted, setRatingSubmitted] = useState(false);
  const [hoveredStar, setHoveredStar]     = useState(0);
  const [selectedStar, setSelectedStar]   = useState(0);

  const colors = THEMES[theme];

  // ── Data ─────────────────────────────────────────────────────────────────

  const { data, isLoading, error } = useQuery({
    queryKey: ["chapter", slug, chapterNumber],
    queryFn: () => request<ChapterData>(`/v1/read/${slug}/chapters/${chapterNumber}`),
  });

  const chapter = data?.chapter;
  const totalChapters = data?.total_chapters ?? 0;
  // The page passes empty strings (it doesn't know them); the chapter fetch now
  // carries them, so prefer those and fall back to any explicit prop.
  const displayTitle = data?.story_title || storyTitle;
  const displayAuthor = data?.author_name || authorName;

  // ── Scroll tracking + progress sync ──────────────────────────────────────

  const updateProgress = useMutation({
    mutationFn: (pct: number) =>
      request(`/v1/read/${slug}/progress`, {
        method: "PUT",
        body: JSON.stringify({ chapter_number: chapterNumber, completion_percentage: pct }),
      }),
  });

  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;

    let lastSyncPct = 0;
    const onScroll = () => {
      const scrolled = window.scrollY + window.innerHeight - el.offsetTop;
      const pct = Math.min(100, Math.round((scrolled / el.offsetHeight) * 100));
      setScrollPct(pct);

      // Global completion: chapter progress within full story
      const chapterWeight = 100 / Math.max(totalChapters, 1);
      const globalPct = ((chapterNumber - 1) * chapterWeight) + (pct / 100 * chapterWeight);

      // Sync to server every 10% increment, throttled
      if (Math.abs(pct - lastSyncPct) >= 10 && isAuthenticated) {
        lastSyncPct = pct;
        updateProgress.mutate(Math.round(globalPct));
      }

      // Show rating prompt when near bottom of last chapter
      if (chapterNumber === totalChapters && pct >= 90 && !ratingSubmitted) {
        setShowRating(true);
      }
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [chapterNumber, totalChapters, isAuthenticated, ratingSubmitted]);

  // ── Text selection → note popup ───────────────────────────────────────────

  const handleMouseUp = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.toString().trim().length < 5) {
      setSelection(null);
      return;
    }
    const text = sel.toString().trim().slice(0, 400);
    const range = sel.getRangeAt(0);
    const rect  = range.getBoundingClientRect();
    setSelection({
      text,
      top:  rect.top  + window.scrollY - 50,
      left: rect.left + (rect.width / 2),
    });
  }, []);

  const sendNote = useMutation({
    mutationFn: (body: { body: string; passage_reference: string; chapter_number: number }) =>
      request(`/v1/social/${data?.pub_id}/note`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setNoteModal(null);
      setNoteBody("");
      setNoteSent(true);
      setTimeout(() => setNoteSent(false), 3000);
    },
  });

  const submitRating = useMutation({
    mutationFn: (overall: number) =>
      request(`/v1/social/${data?.pub_id}/rate`, {
        method: "POST",
        body: JSON.stringify({ overall }),
      }),
    onSuccess: () => {
      setRatingSubmitted(true);
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen" style={{ background: colors.bg }}>
        <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin opacity-30"
             style={{ borderColor: colors.text }} />
      </div>
    );
  }

  if (!chapter || error) {
    return (
      <div className="flex items-center justify-center min-h-screen" style={{ background: colors.bg }}>
        <p style={{ color: colors.muted }}>Chapter not found.</p>
      </div>
    );
  }

  const paragraphs = chapter.content.split(/\n\n+/).filter(Boolean);

  return (
    <div
      style={{ background: colors.bg, color: colors.text, minHeight: "100vh" }}
      className="transition-colors duration-300"
    >
      {/* Progress bar */}
      <div className="fixed top-0 left-0 right-0 z-50 h-0.5" style={{ background: colors.border }}>
        <div
          className="h-full transition-all duration-300"
          style={{ width: `${scrollPct}%`, background: "#C0974F" }}
        />
      </div>

      {/* Top nav */}
      <nav
        className="fixed top-0.5 left-0 right-0 z-40 flex items-center justify-between px-6 py-3 backdrop-blur-sm"
        style={{ background: `${colors.bg}E0`, borderBottom: `1px solid ${colors.border}` }}
      >
        <Link
          href={`/read/${slug}`}
          className="text-sm transition-opacity hover:opacity-70"
          style={{ color: colors.muted }}
        >
          ← {displayTitle || "Back"}
        </Link>

        <div className="flex items-center gap-1">
          {/* Theme toggles */}
          <div
            className="flex rounded-lg overflow-hidden text-xs"
            style={{ border: `1px solid ${colors.border}` }}
          >
            {(Object.keys(THEMES) as Theme[]).map(t => (
              <button
                key={t}
                onClick={() => setTheme(t)}
                className="px-2.5 py-1.5 capitalize transition"
                style={{
                  background: theme === t ? "#C0974F20" : "transparent",
                  color: theme === t ? "#C0974F" : colors.muted,
                }}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Font size */}
          <div className="flex items-center gap-1 ml-2">
            <button
              onClick={() => setFontSize(s => Math.max(16, s - 2))}
              className="w-7 h-7 flex items-center justify-center text-lg transition-opacity hover:opacity-60"
              style={{ color: colors.muted }}
            >
              A
            </button>
            <button
              onClick={() => setFontSize(s => Math.min(24, s + 2))}
              className="w-7 h-7 flex items-center justify-center text-xl font-semibold transition-opacity hover:opacity-60"
              style={{ color: colors.muted }}
            >
              A
            </button>
          </div>
        </div>
      </nav>

      {/* Text-selection note button */}
      {selection && (
        <button
          onClick={() => {
            setNoteModal({ passage: selection.text });
            setSelection(null);
            window.getSelection()?.removeAllRanges();
          }}
          style={{
            position: "absolute",
            top: selection.top,
            left: selection.left,
            transform: "translateX(-50%)",
            background: colors.bg,
            color: "#C0974F",
            border: `1px solid ${colors.border}`,
            boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
            zIndex: 60,
          }}
          className="px-3 py-1.5 text-xs rounded-full shadow-xl whitespace-nowrap font-medium"
        >
          ✎ Add note to writer
        </button>
      )}

      {/* Private note modal */}
      {noteModal && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.6)" }}
          onClick={e => { if (e.target === e.currentTarget) setNoteModal(null); }}
        >
          <div
            className="w-full max-w-md rounded-2xl shadow-2xl p-6 space-y-4"
            style={{ background: colors.bg, border: `1px solid ${colors.border}` }}
          >
            <div>
              <h3 className="text-base font-semibold" style={{ color: colors.text }}>
                Private note to author
              </h3>
              <p className="text-xs mt-1" style={{ color: colors.muted }}>
                Only the author will see this. It won't be published.
              </p>
            </div>
            {noteModal.passage && (
              <blockquote
                className="text-sm italic px-3 py-2 rounded-lg border-l-2"
                style={{
                  borderColor: "#C0974F",
                  background: `${colors.border}50`,
                  color: colors.muted,
                }}
              >
                "{noteModal.passage.slice(0, 200)}{noteModal.passage.length > 200 ? "…" : ""}"
              </blockquote>
            )}
            <textarea
              value={noteBody}
              onChange={e => setNoteBody(e.target.value)}
              placeholder="Your thoughts, feedback, or reaction…"
              rows={4}
              className="w-full rounded-lg px-3 py-2.5 text-sm resize-none focus:outline-none transition"
              style={{
                background: `${colors.border}50`,
                border: `1px solid ${colors.border}`,
                color: colors.text,
              }}
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setNoteModal(null)}
                className="px-4 py-2 text-sm rounded-lg transition"
                style={{ color: colors.muted }}
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  sendNote.mutate({
                    body: noteBody,
                    passage_reference: noteModal.passage,
                    chapter_number: chapterNumber,
                  })
                }
                disabled={noteBody.trim().length < 5 || sendNote.isPending}
                className="px-4 py-2 text-sm rounded-lg font-medium transition disabled:opacity-40"
                style={{ background: "#C0974F", color: "#fff" }}
              >
                {sendNote.isPending ? "Sending…" : "Send note"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main reading area */}
      <main className="pt-20 pb-32">
        <div className="max-w-[68ch] mx-auto px-6">
          {/* Chapter header */}
          <header className="mb-10 mt-4 text-center">
            <p className="text-xs uppercase tracking-widest mb-3" style={{ color: colors.muted }}>
              Chapter {chapterNumber} of {totalChapters}
            </p>
            <h1
              className="font-serif leading-tight mb-3"
              style={{ fontSize: "1.75rem", color: colors.text }}
            >
              {chapter.title}
            </h1>
            <div className="flex items-center justify-center gap-3 text-xs" style={{ color: colors.muted }}>
              <span>{chapter.word_count.toLocaleString()} words</span>
              <span>·</span>
              <span>{readingMinutes(chapter.word_count)}</span>
            </div>
          </header>

          {/* Chapter content */}
          <div
            ref={contentRef}
            onMouseUp={handleMouseUp}
            className="leading-relaxed font-serif select-text"
            style={{ fontSize: `${fontSize}px`, lineHeight: 1.85, color: colors.text }}
          >
            {paragraphs.map((para, i) => (
              <p
                key={i}
                className="mb-0"
                style={{
                  textIndent: i === 0 ? 0 : "1.5em",
                  marginBottom: "1.1em",
                }}
              >
                {para}
              </p>
            ))}
          </div>

          {/* Note sent toast */}
          {noteSent && (
            <div
              className="fixed bottom-24 left-1/2 -translate-x-1/2 px-5 py-2.5 rounded-full text-sm font-medium shadow-xl z-50"
              style={{ background: "#C0974F", color: "#fff" }}
            >
              ✓ Note sent to author
            </div>
          )}

          {/* Chapter navigation */}
          <div
            className="flex items-center justify-between mt-16 pt-8"
            style={{ borderTop: `1px solid ${colors.border}` }}
          >
            {chapterNumber > 1 ? (
              <Link
                href={`/read/${slug}/${chapterNumber - 1}`}
                className="flex items-center gap-2 text-sm transition-opacity hover:opacity-60"
                style={{ color: colors.muted }}
              >
                ← Previous chapter
              </Link>
            ) : <div />}

            {chapterNumber < totalChapters ? (
              <Link
                href={`/read/${slug}/${chapterNumber + 1}`}
                className="px-5 py-2.5 rounded-xl text-sm font-medium transition"
                style={{ background: "#C0974F", color: "#fff" }}
              >
                Next chapter →
              </Link>
            ) : (
              <div
                className="px-5 py-2.5 rounded-xl text-sm border"
                style={{ color: colors.muted, borderColor: colors.border }}
              >
                End of story
              </div>
            )}
          </div>

          {/* Rating prompt at end of final chapter */}
          {showRating && chapterNumber === totalChapters && (
            <div
              className="mt-12 p-6 rounded-2xl text-center space-y-4"
              style={{ background: `${colors.border}50`, border: `1px solid ${colors.border}` }}
            >
              {ratingSubmitted ? (
                <div>
                  <div className="text-2xl mb-2">✨</div>
                  <p className="text-sm font-medium" style={{ color: colors.text }}>
                    Thank you for rating!
                  </p>
                  <p className="text-xs mt-1" style={{ color: colors.muted }}>
                    You can also leave a written review on the story page.
                  </p>
                  <Link
                    href={`/read/${slug}`}
                    className="inline-block mt-3 text-xs text-amber-600 hover:underline"
                  >
                    Back to story page →
                  </Link>
                </div>
              ) : (
                <>
                  <p className="text-base font-semibold font-serif" style={{ color: colors.text }}>
                    {displayTitle ? `You finished "${displayTitle}"` : "You finished this story"}
                    {displayAuthor && <span className="block text-sm font-normal opacity-70 mt-0.5">by {displayAuthor}</span>}
                  </p>
                  <p className="text-sm" style={{ color: colors.muted }}>
                    How would you rate it?
                  </p>
                  <div className="flex justify-center gap-2">
                    {[1,2,3,4,5].map(star => (
                      <button
                        key={star}
                        onMouseEnter={() => setHoveredStar(star)}
                        onMouseLeave={() => setHoveredStar(0)}
                        onClick={() => {
                          setSelectedStar(star);
                          if (isAuthenticated) submitRating.mutate(star);
                          else setRatingSubmitted(true);
                        }}
                        className="text-3xl transition-transform hover:scale-110"
                        style={{
                          color: star <= (hoveredStar || selectedStar)
                            ? "#F59E0B"
                            : colors.border,
                        }}
                      >
                        ★
                      </button>
                    ))}
                  </div>
                  {!isAuthenticated && (
                    <p className="text-xs" style={{ color: colors.muted }}>
                      Sign in to save your rating
                    </p>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
