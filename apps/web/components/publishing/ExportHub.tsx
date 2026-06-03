"use client";
// apps/web/components/publishing/ExportHub.tsx
//
// Writer's export UI. Allows downloading PDF, EPUB, DOCX, and full submission package.

import { useState } from "react";
import { getToken } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080";

interface ExportHubProps {
  storyId: string;
  storyTitle: string;
  chapterCount: number;
  wordCount: number;
}

interface ExportFormat {
  key: "pdf" | "epub" | "docx" | "package";
  label: string;
  description: string;
  icon: string;
  tag?: string;
  color: string;
}

const FORMATS: ExportFormat[] = [
  {
    key:         "pdf",
    label:       "PDF",
    description: "Styled reading copy. Cover page, serif body text, page numbers.",
    icon:        "📄",
    color:       "#E53E3E",
  },
  {
    key:         "epub",
    label:       "EPUB",
    description: "For e-readers (Kindle, Kobo, Apple Books). Properly formatted with TOC.",
    icon:        "📱",
    color:       "#3182CE",
  },
  {
    key:         "docx",
    label:       "Word doc",
    description: "Shunn standard manuscript format — double-spaced Courier, 1″ margins, headers.",
    icon:        "📝",
    tag:         "Agent-ready",
    color:       "#2B6CB0",
  },
  {
    key:         "package",
    label:       "Submission package",
    description: "All three formats + auto-generated synopsis + README, zipped for agent submission.",
    icon:        "📦",
    tag:         "All-in-one",
    color:       "#C0974F",
  },
];

export default function ExportHub({
  storyId, storyTitle, chapterCount, wordCount,
}: ExportHubProps) {
  const [downloading, setDownloading] = useState<string | null>(null);
  const [done, setDone]               = useState<string | null>(null);

  const handleDownload = async (format: ExportFormat["key"]) => {
    setDownloading(format);
    try {
      // Auth via the live Clerk session token (the old localStorage "token" never
      // existed under Clerk, so downloads always 401'd). Hit the API host directly.
      const token = await getToken();
      const res = await fetch(`${API_BASE}/v1/export/${storyId}/${format}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (!res.ok) throw new Error("Export failed");

      const disposition = res.headers.get("content-disposition") || "";
      const match       = disposition.match(/filename="([^"]+)"/);
      const filename    = match ? match[1] : `${storyTitle}.${format}`;

      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);

      setDone(format);
      setTimeout(() => setDone(null), 3000);
    } catch (err) {
      console.error("Export error:", err);
    } finally {
      setDownloading(null);
    }
  };

  const wordCountDisplay =
    wordCount > 999
      ? `${(wordCount / 1000).toFixed(0)}k words`
      : `${wordCount} words`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-ink-text">Export Hub</h3>
        <p className="text-sm text-ink-text2 mt-1">
          Download "{storyTitle}" — {chapterCount} chapter{chapterCount !== 1 ? "s" : ""}, {wordCountDisplay}
        </p>
      </div>

      {/* Format cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {FORMATS.map(fmt => {
          const isLoading = downloading === fmt.key;
          const isDone    = done === fmt.key;

          return (
            <div
              key={fmt.key}
              className="group bg-ink-bg2 rounded-xl border border-ink-text2/10 p-4 hover:border-ink-text2/25 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{fmt.icon}</span>
                    <span className="text-sm font-semibold text-ink-text">{fmt.label}</span>
                    {fmt.tag && (
                      <span
                        className="text-[10px] font-medium px-1.5 py-0.5 rounded-full"
                        style={{
                          background: `${fmt.color}18`,
                          color: fmt.color,
                          border: `1px solid ${fmt.color}30`,
                        }}
                      >
                        {fmt.tag}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-ink-text2 leading-relaxed">{fmt.description}</p>
                </div>

                <button
                  onClick={() => handleDownload(fmt.key)}
                  disabled={!!downloading}
                  className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition disabled:opacity-50"
                  style={
                    isDone
                      ? { background: "#22C55E15", color: "#22C55E", borderColor: "#22C55E30" }
                      : isLoading
                      ? { background: `${fmt.color}10`, color: fmt.color, borderColor: `${fmt.color}25` }
                      : {
                          background: "transparent",
                          color: fmt.color,
                          borderColor: `${fmt.color}35`,
                        }
                  }
                >
                  {isDone ? (
                    "✓ Done"
                  ) : isLoading ? (
                    <>
                      <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.3" />
                        <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                      </svg>
                      Generating…
                    </>
                  ) : (
                    <>
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      Download
                    </>
                  )}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Info note */}
      <p className="text-xs text-ink-text2/60 leading-relaxed">
        Exports include all chapters with content. The submission package contains
        a one-page auto-generated synopsis and a README with word count and metadata.
        Drafts with no content are skipped.
      </p>
    </div>
  );
}
