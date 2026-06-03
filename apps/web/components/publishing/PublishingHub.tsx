"use client";
// apps/web/components/publishing/PublishingHub.tsx
//
// Writer's publishing management dashboard for a single story.
// Usage:  <PublishingHub storyId={story.id} storyTitle={story.title} />
//
// Fetches publication data, shows status, allows pushing chapters & going live.

import { useState, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request, mediaUrl } from "@/lib/api";
import { CoverUploader } from "@/components/ui/CoverUploader";

interface Chapter {
  id: string;
  number: number;
  title: string;
  word_count?: number;
}

interface Publication {
  id: string;
  slug: string;
  status: "draft" | "published" | "unlisted" | "archived";
  release_type: "complete" | "serial";
  tagline: string | null;
  genre: string | null;
  tags: string[];
  content_warnings: string[];
  cover_image_url: string | null;
  published_at: string | null;
  last_chapter_pushed_at: string | null;
  total_planned_chapters: number | null;
  view_count: number;
}

interface PushedChapter {
  chapter_number: number;
  title: string;
  word_count: number;
  pushed_at: string;
  version: number;
  is_latest: boolean;
}

interface PublishingHubProps {
  storyId: string;
  storyTitle: string;
  storyChapters: Chapter[];
}

const STATUS_COLORS: Record<string, string> = {
  draft:     "bg-ink-gold/10 text-ink-gold border-ink-gold/30",
  published: "bg-green-500/10 text-green-400 border-green-500/30",
  unlisted:  "bg-blue-500/10 text-blue-400 border-blue-500/30",
  archived:  "bg-ink-text2/10 text-ink-text2 border-ink-text2/20",
};

const WARNING_OPTIONS = [
  "Violence", "Strong language", "Adult themes", "Dark themes",
  "Substance use", "Mental health", "Graphic content",
];

export default function PublishingHub({
  storyId, storyTitle, storyChapters,
}: PublishingHubProps) {
  const qc = useQueryClient();

  const [activeTab, setActiveTab] = useState<"overview" | "settings" | "chapters">("overview");
  const [selectedChapters, setSelectedChapters] = useState<Set<number>>(new Set());
  const [tagline, setTagline]   = useState("");
  const [genre, setGenre]       = useState("");
  const [releaseType, setRelType] = useState<"complete" | "serial">("complete");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [settingsSaved, setSettingsSaved] = useState(false);

  // ── Queries ───────────────────────────────────────────────────────────────

  const { data: pubData, isLoading } = useQuery({
    queryKey: ["publication", storyId],
    queryFn: () => request<Publication | null>(`/v1/publish/${storyId}`),
  });

  const pub: Publication | null = pubData ?? null;

  const { data: pushedChapters = [] } = useQuery({
    queryKey: ["pub-chapters", pub?.id],
    queryFn: () =>
      pub ? request<PushedChapter[]>(`/v1/publish/${pub.id}/chapters`) : [],
    enabled: !!pub,
  });

  // ── Mutations ─────────────────────────────────────────────────────────────

  const createPub = useMutation({
    mutationFn: () =>
      request("/v1/publish/", {
        method: "POST",
        body: JSON.stringify({ story_id: storyId, release_type: releaseType }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["publication", storyId] }),
  });

  const updateSettings = useMutation({
    mutationFn: () =>
      request(`/v1/publish/${pub!.id}`, {
        method: "PUT",
        body: JSON.stringify({ tagline, genre, release_type: releaseType, content_warnings: warnings }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["publication", storyId] });
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2000);
    },
  });

  const pushChapters = useMutation({
    mutationFn: () =>
      request(`/v1/publish/${pub!.id}/push`, {
        method: "POST",
        body: JSON.stringify({ chapter_numbers: Array.from(selectedChapters) }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pub-chapters", pub?.id] });
      qc.invalidateQueries({ queryKey: ["publication", storyId] });
      setSelectedChapters(new Set());
    },
  });

  const goLive = useMutation({
    mutationFn: () =>
      request(`/v1/publish/${pub!.id}/go-live`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["publication", storyId] }),
  });

  const setCover = useMutation({
    mutationFn: (url: string | null) =>
      request(`/v1/publish/${pub!.id}`, { method: "PUT", body: JSON.stringify({ cover_image_url: url }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["publication", storyId] }),
  });

  const unpublish = useMutation({
    mutationFn: () =>
      request(`/v1/publish/${pub!.id}/unpublish`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["publication", storyId] }),
  });

  const toggleChapter = useCallback((num: number) => {
    setSelectedChapters(prev => {
      const next = new Set(prev);
      next.has(num) ? next.delete(num) : next.add(num);
      return next;
    });
  }, []);

  const toggleWarning = (w: string) => {
    setWarnings(prev =>
      prev.includes(w) ? prev.filter(x => x !== w) : [...prev, w]
    );
  };

  const pushedNums = new Set(pushedChapters.map(c => c.chapter_number));

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-40">
        <div className="w-5 h-5 border-2 border-ink-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // ── No publication yet ────────────────────────────────────────────────────
  if (!pub) {
    return (
      <div className="max-w-lg mx-auto py-12 px-4 text-center">
        <div className="text-4xl mb-4">📖</div>
        <h3 className="text-xl font-semibold text-ink-text mb-2">
          Publish "{storyTitle}"
        </h3>
        <p className="text-ink-text2 text-sm mb-8 leading-relaxed">
          Create a public page for your story. Readers can discover, read, and
          leave feedback. Your studio data is never touched — readers see a
          separate published snapshot.
        </p>
        <div className="flex gap-3 justify-center mb-6">
          {(["complete", "serial"] as const).map(t => (
            <button
              key={t}
              onClick={() => setRelType(t)}
              className={`px-5 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                releaseType === t
                  ? "bg-ink-gold text-ink-bg border-ink-gold"
                  : "bg-transparent text-ink-text2 border-ink-text2/30 hover:border-ink-gold/50"
              }`}
            >
              {t === "complete" ? "Complete story" : "Serial (chapters over time)"}
            </button>
          ))}
        </div>
        <button
          onClick={() => createPub.mutate()}
          disabled={createPub.isPending}
          className="px-8 py-3 bg-ink-gold text-ink-bg rounded-lg font-medium hover:opacity-90 transition disabled:opacity-50"
        >
          {createPub.isPending ? "Creating…" : "Create publication draft"}
        </button>
      </div>
    );
  }

  // ── Has publication ────────────────────────────────────────────────────────
  return (
    <div className="space-y-5">
      {/* Status bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className={`text-xs font-medium px-3 py-1 rounded-full border ${STATUS_COLORS[pub.status]}`}>
            {pub.status}
          </span>
          <span className="text-ink-text2 text-sm">
            {pub.view_count.toLocaleString()} view{pub.view_count !== 1 ? "s" : ""}
          </span>
          {pub.status === "published" && (
            <a
              href={`/read/${pub.slug}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-ink-gold hover:underline"
            >
              /read/{pub.slug} ↗
            </a>
          )}
        </div>
        <div className="flex gap-2">
          {pub.status === "draft" && (
            <button
              onClick={() => goLive.mutate()}
              disabled={goLive.isPending || pushedChapters.length === 0}
              className="px-4 py-1.5 bg-ink-gold text-ink-bg text-sm rounded-lg font-medium hover:opacity-90 transition disabled:opacity-40"
            >
              {goLive.isPending ? "Publishing…" : "Publish"}
            </button>
          )}
          {pub.status === "published" && (
            <button
              onClick={() => unpublish.mutate()}
              disabled={unpublish.isPending}
              className="px-4 py-1.5 border border-ink-text2/30 text-ink-text2 text-sm rounded-lg hover:border-red-400/50 hover:text-red-400 transition"
            >
              {unpublish.isPending ? "Unlisting…" : "Unlist"}
            </button>
          )}
          {pub.status === "unlisted" && (
            <button
              onClick={() => goLive.mutate()}
              disabled={goLive.isPending}
              className="px-4 py-1.5 bg-ink-gold text-ink-bg text-sm rounded-lg font-medium hover:opacity-90 transition disabled:opacity-40"
            >
              {goLive.isPending ? "Publishing…" : "Re-publish"}
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-ink-text2/15">
        {(["overview", "chapters", "settings"] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-5 py-2.5 text-sm font-medium capitalize transition border-b-2 -mb-px ${
              activeTab === tab
                ? "border-ink-gold text-ink-gold"
                : "border-transparent text-ink-text2 hover:text-ink-text"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ── Overview ── */}
      {activeTab === "overview" && (
        <div className="space-y-3">
        {/* Cover + ready-to-publish hero */}
        <div className="flex flex-col sm:flex-row gap-4 items-start bg-ink-bg2 rounded-xl p-4 border border-ink-text2/10">
          <div className="w-28 shrink-0 rounded-lg overflow-hidden border border-ink-text2/15 bg-ink-surface2" style={{ aspectRatio: "3 / 4" }}>
            {mediaUrl(pub.cover_image_url) ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={mediaUrl(pub.cover_image_url)} alt="cover" className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full grid place-items-center text-2xl">📖</div>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-display text-lg text-ink-text">{storyTitle}</h3>
            <p className="text-sm text-ink-text2 mt-0.5">{pub.tagline ? `“${pub.tagline}”` : "Add a tagline + cover in Settings to make your story pop on discovery."}</p>
            {pub.status === "draft" && (
              <button
                onClick={() => goLive.mutate()}
                disabled={goLive.isPending || pushedChapters.length === 0}
                className="mt-3 px-5 py-2.5 bg-ink-gold text-ink-bg rounded-lg font-semibold hover:opacity-90 transition disabled:opacity-40"
              >
                {goLive.isPending ? "Publishing…" : pushedChapters.length === 0 ? "Push a chapter first →" : "🚀 Publish now"}
              </button>
            )}
            {pub.status === "published" && (
              <a href={`/read/${pub.slug}`} target="_blank" rel="noopener noreferrer"
                 className="mt-3 inline-block px-5 py-2.5 bg-ink-gold text-ink-bg rounded-lg font-semibold hover:opacity-90 transition">
                View public page ↗
              </a>
            )}
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Status",   value: pub.status },
            { label: "Type",     value: pub.release_type },
            { label: "Chapters", value: `${pushedChapters.length} published` },
            { label: "Views",    value: pub.view_count.toLocaleString() },
          ].map(({ label, value }) => (
            <div key={label} className="bg-ink-bg2 rounded-xl p-4 border border-ink-text2/10">
              <div className="text-xs text-ink-text2 uppercase tracking-wide mb-1">{label}</div>
              <div className="text-ink-text font-semibold capitalize">{value}</div>
            </div>
          ))}
          {pub.tagline && (
            <div className="col-span-2 md:col-span-4 bg-ink-bg2 rounded-xl p-4 border border-ink-text2/10">
              <div className="text-xs text-ink-text2 uppercase tracking-wide mb-1">Tagline</div>
              <div className="text-ink-text text-sm italic">"{pub.tagline}"</div>
            </div>
          )}
          {pub.status === "draft" && pushedChapters.length === 0 && (
            <div className="col-span-2 md:col-span-4 bg-ink-gold/5 border border-ink-gold/20 rounded-xl p-4 text-sm text-ink-gold">
              ⚡ Push at least one chapter from the Chapters tab before publishing.
            </div>
          )}
        </div>
        </div>
      )}

      {/* ── Chapters tab ── */}
      {activeTab === "chapters" && (
        <div className="space-y-4">
          <p className="text-sm text-ink-text2">
            Select studio chapters to push to your public publication. Pushing
            creates an immutable snapshot — future edits in the studio won't
            affect what readers see until you push again.
          </p>
          <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
            {storyChapters.map(ch => {
              const isPushed  = pushedNums.has(ch.number);
              const isChecked = selectedChapters.has(ch.number);
              return (
                <label
                  key={ch.number}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition ${
                    isChecked
                      ? "border-ink-gold/50 bg-ink-gold/5"
                      : "border-ink-text2/15 hover:border-ink-text2/30"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => toggleChapter(ch.number)}
                    className="accent-ink-gold"
                  />
                  <span className="flex-1 text-sm text-ink-text">
                    <span className="text-ink-text2 mr-2">#{ch.number}</span>
                    {ch.title || `Chapter ${ch.number}`}
                  </span>
                  {isPushed && (
                    <span className="text-xs text-ink-text2 border border-ink-text2/20 rounded px-2 py-0.5">
                      published
                    </span>
                  )}
                </label>
              );
            })}
          </div>
          <button
            onClick={() => pushChapters.mutate()}
            disabled={selectedChapters.size === 0 || pushChapters.isPending}
            className="px-5 py-2 bg-ink-gold text-ink-bg text-sm rounded-lg font-medium hover:opacity-90 transition disabled:opacity-40"
          >
            {pushChapters.isPending
              ? "Pushing…"
              : `Push ${selectedChapters.size} chapter${selectedChapters.size !== 1 ? "s" : ""}`}
          </button>

          {pushedChapters.length > 0 && (
            <div className="mt-4">
              <div className="text-xs text-ink-text2 uppercase tracking-wide mb-2">
                Currently published
              </div>
              <div className="space-y-1.5">
                {pushedChapters.map(c => (
                  <div
                    key={c.chapter_number}
                    className="flex justify-between items-center text-sm text-ink-text2 py-1"
                  >
                    <span>
                      #{c.chapter_number} {c.title}
                      {c.version > 1 && (
                        <span className="ml-1 text-xs text-ink-gold">v{c.version}</span>
                      )}
                    </span>
                    <span className="text-xs">
                      {new Date(c.pushed_at).toLocaleDateString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Settings tab ── */}
      {activeTab === "settings" && (
        <div className="space-y-5 max-w-lg">
          <div>
            <label className="block text-sm text-ink-text2 mb-2">Cover image</label>
            <CoverUploader
              value={pub.cover_image_url}
              onChange={(url) => setCover.mutate(url)}
              label=""
            />
          </div>
          <div>
            <label className="block text-sm text-ink-text2 mb-1.5">Tagline</label>
            <textarea
              value={tagline || pub.tagline || ""}
              onChange={e => setTagline(e.target.value)}
              maxLength={300}
              rows={2}
              placeholder="A compelling one-liner for the discovery page…"
              className="w-full bg-ink-bg2 border border-ink-text2/20 rounded-lg px-3 py-2.5 text-sm text-ink-text resize-none focus:outline-none focus:border-ink-gold/50 placeholder-ink-text2/50"
            />
          </div>
          <div>
            <label className="block text-sm text-ink-text2 mb-1.5">Genre</label>
            <select
              value={genre || pub.genre || ""}
              onChange={e => setGenre(e.target.value)}
              className="w-full bg-ink-bg2 border border-ink-text2/20 rounded-lg px-3 py-2.5 text-sm text-ink-text focus:outline-none focus:border-ink-gold/50"
            >
              <option value="">Select genre</option>
              {["fantasy","sci-fi","thriller","romance","literary","mystery",
                "horror","historical","adventure","young-adult","other"].map(g => (
                <option key={g} value={g}>{g}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-ink-text2 mb-2">Content warnings</label>
            <div className="flex flex-wrap gap-2">
              {WARNING_OPTIONS.map(w => (
                <button
                  key={w}
                  onClick={() => toggleWarning(w)}
                  className={`text-xs px-3 py-1.5 rounded-full border transition ${
                    warnings.includes(w) || (pub.content_warnings || []).includes(w)
                      ? "bg-red-500/10 text-red-400 border-red-400/30"
                      : "bg-transparent text-ink-text2 border-ink-text2/25 hover:border-ink-text2/50"
                  }`}
                >
                  {w}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={() => updateSettings.mutate()}
            disabled={updateSettings.isPending}
            className="px-5 py-2 bg-ink-gold text-ink-bg text-sm rounded-lg font-medium hover:opacity-90 transition disabled:opacity-40"
          >
            {updateSettings.isPending
              ? "Saving…"
              : settingsSaved
              ? "✓ Saved"
              : "Save settings"}
          </button>
        </div>
      )}
    </div>
  );
}
