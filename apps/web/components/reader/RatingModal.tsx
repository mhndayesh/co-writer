"use client";
// apps/web/components/reader/RatingModal.tsx
//
// Full 5-dimension rating UI with optional detail scores.
// Overall star rating required; dimension scores are optional.

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { request } from "@/lib/api";

interface RatingModalProps {
  pubId: string;
  storyTitle: string;
  onClose: () => void;
}

const DIMENSIONS = [
  { key: "score_story",      label: "Story",       hint: "Plot, structure, pacing" },
  { key: "score_craft",      label: "Writing",     hint: "Prose quality, style, voice" },
  { key: "score_characters", label: "Characters",  hint: "Depth, believability, growth" },
  { key: "score_pacing",     label: "Pacing",      hint: "Flow and momentum" },
  { key: "score_world",      label: "World",       hint: "Setting, atmosphere, detail" },
] as const;

type DimKey = (typeof DIMENSIONS)[number]["key"];

function StarPicker({
  value,
  onChange,
  size = "normal",
}: {
  value: number;
  onChange: (v: number) => void;
  size?: "normal" | "large";
}) {
  const [hovered, setHovered] = useState(0);
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map(star => (
        <button
          key={star}
          onMouseEnter={() => setHovered(star)}
          onMouseLeave={() => setHovered(0)}
          onClick={() => onChange(star === value ? 0 : star)}
          className={`transition-transform hover:scale-110 ${
            size === "large" ? "text-3xl" : "text-lg"
          }`}
          style={{
            color:
              star <= (hovered || value)
                ? "#F59E0B"
                : "rgba(255,255,255,0.15)",
          }}
        >
          ★
        </button>
      ))}
    </div>
  );
}

const STAR_LABELS = ["", "Didn't like it", "It was okay", "Liked it", "Really liked it", "Loved it!"];

export default function RatingModal({ pubId, storyTitle, onClose }: RatingModalProps) {
  const qc = useQueryClient();
  const [overall, setOverall]     = useState(0);
  const [dims, setDims]           = useState<Partial<Record<DimKey, number>>>({});
  const [showDims, setShowDims]   = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const setDim = (key: DimKey, val: number) =>
    setDims(prev => ({ ...prev, [key]: val || undefined }));

  const [error, setError] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: () =>
      request(`/v1/social/${pubId}/rate`, {
        method: "POST",
        body: JSON.stringify({
          overall,
          ...dims,
        }),
      }),
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["landing"] });
      qc.invalidateQueries({ queryKey: ["ratings", pubId] });
      setSubmitted(true);
    },
    // The backend rejects ratings from readers who haven't opened a chapter yet
    // ("read chapter 1 first"). Without surfacing it the button just stops
    // spinning and looks broken — show the reason instead.
    onError: (e: unknown) =>
      setError(e instanceof Error ? e.message : "Couldn't save your rating. Please try again."),
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.75)" }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-sm bg-[#16140F] border border-white/10 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
          <h2 className="text-base font-semibold text-white">Rate this story</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition text-lg leading-none"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {submitted ? (
            /* Success state */
            <div className="text-center py-6 space-y-3">
              <div className="text-4xl">✨</div>
              <p className="text-base font-medium text-white">Rating saved!</p>
              <p className="text-sm text-gray-400">
                Thank you for rating "{storyTitle}".
              </p>
              <button
                onClick={onClose}
                className="mt-2 px-6 py-2 text-sm bg-amber-500 hover:bg-amber-400 text-black font-medium rounded-xl transition"
              >
                Done
              </button>
            </div>
          ) : (
            <>
              {/* Overall */}
              <div className="space-y-3">
                <p className="text-sm text-gray-400">Overall rating</p>
                <StarPicker value={overall} onChange={setOverall} size="large" />
                {overall > 0 && (
                  <p className="text-xs text-amber-400/80">{STAR_LABELS[overall]}</p>
                )}
              </div>

              {/* Toggle detailed ratings */}
              <button
                onClick={() => setShowDims(s => !s)}
                className="text-xs text-gray-500 hover:text-gray-300 transition flex items-center gap-1.5"
              >
                <span>{showDims ? "−" : "+"}</span>
                Rate specific dimensions (optional)
              </button>

              {/* Dimension ratings */}
              {showDims && (
                <div className="space-y-3 pt-1">
                  {DIMENSIONS.map(({ key, label, hint }) => (
                    <div key={key} className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm text-gray-300 leading-none">{label}</p>
                        <p className="text-xs text-gray-600 mt-0.5">{hint}</p>
                      </div>
                      <StarPicker
                        value={dims[key] ?? 0}
                        onChange={v => setDim(key, v)}
                      />
                    </div>
                  ))}
                </div>
              )}

              {/* Error surface (e.g. "read chapter 1 first") */}
              {error && (
                <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              {/* Submit */}
              <button
                onClick={() => submit.mutate()}
                disabled={overall === 0 || submit.isPending}
                className="w-full py-3 text-sm font-semibold rounded-xl transition disabled:opacity-40"
                style={{
                  background: overall > 0 ? "#F59E0B" : "rgba(255,255,255,0.05)",
                  color: overall > 0 ? "#000" : "rgba(255,255,255,0.3)",
                }}
              >
                {submit.isPending ? "Saving…" : "Submit rating"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
