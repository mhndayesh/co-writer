// Field definitions for the 5-layer character identity editor.
//
// CRITICAL: the `key` of every field IS the interview question id (see backend
// app/services/identity_questions.py). That one shared vocabulary is what makes
// analyze-existing-writing, the guided interview, this editor, and the LLM context
// all read/write the SAME JSON keys. (Earlier these used descriptive names like
// "values"/"sentence_length" that nothing else wrote, so analyze-saved data was
// invisible here.) Keep keys in sync with the question bank.
//
// `kind` controls the input: "text" → single line, "area" → textarea,
// "list" → comma-separated → array.

export type LayerField = { key: string; label: string; kind: "text" | "area" | "list"; hint?: string };

export const CORE_FIELDS: LayerField[] = [
  { key: "want", label: "Want (drives them now)", kind: "area", hint: "What they'll act on now — and why now." },
  { key: "need", label: "Need (resists admitting)", kind: "area", hint: "The internal lack the arc is about." },
  { key: "lie", label: "The lie they believe", kind: "area", hint: "The false belief they organize their life around." },
  { key: "wound", label: "Wound / ghost", kind: "area", hint: "The early event that made the lie feel true." },
  { key: "shame", label: "Core shame", kind: "area", hint: "What they fear others will discover." },
  { key: "value_hierarchy", label: "Value hierarchy", kind: "area", hint: "What they'd sacrifice everything else to protect." },
  { key: "moral_line", label: "Moral line", kind: "area", hint: "The line they won't cross — and what would push them over." },
  { key: "self_gap", label: "Persona vs private self", kind: "area", hint: "How they want to be seen vs how they see themselves." },
];

export const BEHAVIORAL_FIELDS: LayerField[] = [
  { key: "stress_response", label: "Under threat", kind: "area", hint: "fight / flee / freeze / fawn — and the fallback." },
  { key: "vulnerability", label: "When pushed to be honest", kind: "area", hint: "Their attachment defense." },
  { key: "criticism", label: "Reaction to criticism", kind: "area", hint: "From someone they respect." },
  { key: "deception", label: "When they lie", kind: "area", hint: "What deviates from their normal manner." },
  { key: "decision_tempo", label: "Decision tempo", kind: "area", hint: "Fast / slow / defers / freezes under pressure." },
  { key: "anger_tell", label: "Anger tell", kind: "area", hint: "What shows physically before words." },
  { key: "recovery", label: "After failure", kind: "area", hint: "Their resilience ritual in the first hour." },
];

export const VOICE_FIELDS: LayerField[] = [
  { key: "cadence", label: "Cadence", kind: "text", hint: "clipped / short / steady / long cascades" },
  { key: "directness", label: "Directness", kind: "text", hint: "blunt / diplomatic / evasive / commanding" },
  { key: "lexicon", label: "Lexicon", kind: "area", hint: "Words/topics they reach for or avoid; a pet phrase." },
  { key: "emotion_shift", label: "Voice under emotion", kind: "area", hint: "How fear/anger changes pace, length, silence." },
  { key: "register", label: "Register", kind: "text", hint: "formal / plain / slangy / profane / technical" },
  { key: "silence", label: "Silence", kind: "text", hint: "fills it / tolerates it / weaponizes it" },
  { key: "humor", label: "Humor", kind: "text", hint: "to bond / deflect / dominate / self-protect / avoids" },
];

// Nested "how the voice shifts" sub-fields under voice_fingerprint.shifts.
export const VOICE_SHIFTS: LayerField[] = [
  { key: "angry", label: "When angry", kind: "area" },
  { key: "frightened", label: "When frightened", kind: "area" },
  { key: "relaxed", label: "When relaxed", kind: "area" },
  { key: "with_authority", label: "Speaking to authority", kind: "area" },
];

export const LAYER_META: Record<string, { title: string; fields: LayerField[] }> = {
  core: { title: "Core Personality", fields: CORE_FIELDS },
  behavioral: { title: "Behavioral Patterns", fields: BEHAVIORAL_FIELDS },
  voice: { title: "Voice Fingerprint", fields: VOICE_FIELDS },
};
