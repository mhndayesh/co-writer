"use client";
import { useMutationState } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";

// Friendly labels for each AI mutation, keyed by mutationKey[1].
// Any AI mutation should be tagged: mutationKey: ["llm", "<name>"]
const LABELS: Record<string, string> = {
  "flow.polish": "Shaping your scene…",
  "flow.enhance": "Checking the language…",
  "flow.extract": "Reading the scene…",
  "flow.skip-polish": "Filing your scene…",
  "flow.approve": "Filing characters, places, threads…",
  "flow.companion": "Drafting the scene…",
  "story-check": "Reading the chapter against your world…",
  "llm.test": "Talking to the LLM…",
  "rag.preview": "Retrieving graph context…",
  "rag.reindex": "Re-indexing story vectors…",
  "graph.reproject": "Re-projecting the graph…",
  "voice.analyze": "Reading the sample for voice traits…",
  "voice.interview": "Building the character profile…",
  "voice.place": "Sensing the place…",
  "voice.observe": "Listening for off-key lines…",
  "voice.rewrite": "Rewriting in character…",
  "voice.evolve": "Noticing what changed…",
  "voice.compare": "Putting voices side by side…",
};

const HINTS: Record<string, string> = {
  "flow.polish": "The model is rewriting your draft as polished prose.",
  "flow.enhance": "Detecting the language and improving grammar, word choice, and flow — story unchanged.",
  "flow.extract": "The model is reading the scene and listing characters, places, themes, events.",
  "flow.skip-polish": "The model is listing characters, places, themes, events from your text.",
  "flow.approve": "Adding new entities to your story and snapshotting the version.",
  "flow.companion": "The Writing Companion is drafting using the full story context.",
  "story-check": "Cross-checking against your world bible, cast, and prior chapters.",
  "voice.analyze": "Extracting personality, behavior and speech traits — each with a confidence score for you to approve.",
  "voice.interview": "Synthesizing a readable profile and structured layers from your answers.",
  "voice.place": "Turning your answers into a sensory, atmospheric place profile.",
  "voice.observe": "Checking each line against the character's identity, masks and state.",
  "voice.rewrite": "Rewriting the dialogue to match voice, masks and current state.",
  "voice.evolve": "Spotting what this scene reveals or changes about the cast.",
  "voice.compare": "Generating each character's response to the same situation.",
};

export function BusyOverlay() {
  // Pull every in-flight mutation tagged with ["llm", …] and surface the topmost.
  const active = useMutationState({
    filters: {
      status: "pending",
      predicate: (m) => Array.isArray(m.options.mutationKey) && m.options.mutationKey[0] === "llm",
    },
    select: (m) => (m.options.mutationKey?.[1] as string | undefined) ?? "unknown",
  });

  if (active.length === 0) return null;

  const key = active[active.length - 1];
  const label = LABELS[key] ?? "Working…";
  const hint = HINTS[key] ?? "Hold on a moment.";

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-deep/55 backdrop-blur-[2px] busy-fade-in"
      onMouseDownCapture={(e) => e.preventDefault()}
      onClickCapture={(e) => e.preventDefault()}
      onKeyDownCapture={(e) => e.preventDefault()}
    >
      <div className="card-ink px-6 py-5 max-w-md w-[90%] flex items-start gap-4">
        <div className="relative shrink-0">
          <Sparkles className="text-ink-goldLight" size={22} />
          <Loader2 className="absolute inset-0 m-auto text-ink-gold animate-spin" size={32} />
        </div>
        <div>
          <p className="font-display text-lg leading-tight">{label}</p>
          <p className="text-sm text-ink-text2 mt-1">{hint}</p>
          {active.length > 1 && (
            <p className="text-xs text-ink-text3 mt-2">+ {active.length - 1} more task{active.length > 2 ? "s" : ""} queued</p>
          )}
        </div>
      </div>
    </div>
  );
}
