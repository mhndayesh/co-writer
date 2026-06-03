// Typed API client. Every method returns the unwrapped `data` payload from the
// envelope `{ok, data, error}`. Throws ApiError on non-ok.

import { getToken, signOut } from "./auth";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080";

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;
  constructor(code: string, message: string, status: number, details: unknown = null) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
  const token = await getToken();
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) {
    if (!res.ok) throw new ApiError("network_error", await res.text(), res.status);
    return (await res.blob()) as unknown as T;
  }
  const body = await res.json();
  if (!body.ok) {
    const err = body.error || {};
    throw new ApiError(err.code || "error", err.message || res.statusText, res.status, err.details);
  }
  return body.data as T;
}

// ── Auth ─────────────────────────────────────────────────────────────
// Sign-in / sign-up are handled by Clerk's <SignIn>/<SignUp> components, not
// here. `me()` resolves the local user row that sits behind the Clerk session.
export async function me() {
  return request<{ user: User }>("/v1/auth/me");
}
export async function logout() {
  // Clerk owns the session — signing out clears it everywhere (cookies + token).
  await signOut();
}

// ── Billing / subscriptions ──────────────────────────────────────────────
// "owner" is a runtime-only effective tier (unlimited; site owner/admins) — not
// a purchasable plan, so it never appears in the /plans catalog or checkout.
export type Tier = "free" | "dev_ai" | "byok" | "owner";

export type User = {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
  plan_tier: Tier;
  plan_status: string;
  is_admin: boolean;
};

export type Plan = {
  tier: Tier;
  name: string;
  blurb: string;
  key_source: "server" | "user";
  period: "lifetime" | "month";
  max_actions: number | null;
  max_tokens: number | null;
  requires_subscription: boolean;
  price: number | null;
  price_label: string;
};

export type Entitlement = {
  plan_tier: Tier;
  plan_status: string;
  effective_tier: Tier;
  key_source: "server" | "user";
  metered: boolean;
  period: "lifetime" | "month";
  limits: { max_actions: number | null; max_tokens: number | null };
  usage: {
    actions_used: number;
    tokens_used: number;
    actions_remaining: number | null;
    tokens_remaining: number | null;
  };
  ai_available: boolean;
  // Owner-only "shape-shift": the tier the owner is currently viewing as (null
  // when not in test mode). `is_owner` is the REAL owner flag, kept separate so
  // owner-only UI persists even while simulating a lower tier.
  acting_as: Tier | null;
  is_owner: boolean;
};

// Error codes the backend uses to signal an AI action was blocked by the plan.
export const AI_GATE_CODES = ["subscription_required", "quota_exceeded", "byok_key_missing"] as const;
export function isAiGateError(e: unknown): e is ApiError {
  return e instanceof ApiError && (AI_GATE_CODES as readonly string[]).includes(e.code);
}

export async function billingPlans() {
  return (await request<{ plans: Plan[] }>("/v1/billing/plans")).plans;
}
export async function billingMe() {
  return request<Entitlement>("/v1/billing/me");
}
export async function billingCheckout(tier: Tier, urls: { success_url?: string; cancel_url?: string } = {}) {
  return request<{ provider: string; url: string | null; activated: boolean; tier: string }>(
    "/v1/billing/checkout",
    { method: "POST", body: JSON.stringify({ tier, ...urls }) },
  );
}
export async function billingPortal() {
  return request<{ provider: string; url: string | null; message: string }>("/v1/billing/portal", { method: "POST" });
}

export type TokenStats = {
  runs: number;
  tokens_in: number;   // sent to the model (prompt)
  tokens_out: number;  // returned by the model (completion)
  total: number;
  avg_in: number;
  avg_out: number;
  avg_total: number;
};
export async function tokenStats() {
  return request<TokenStats>("/v1/billing/token-stats");
}

// ── Stories ──────────────────────────────────────────────────────────
export async function listStories() {
  return (await request<{ stories: any[] }>("/v1/stories")).stories;
}
export async function createStory(payload: { title?: string; genre?: string; palette_idx?: number }) {
  return (await request<{ story: any }>("/v1/stories", { method: "POST", body: JSON.stringify(payload) })).story;
}
export async function getStory(id: string) {
  return (await request<{ story: any }>(`/v1/stories/${id}`)).story;
}
export async function updateStory(id: string, patch: { title?: string; genre?: string; palette_idx?: number; cover_image_url?: string | null }) {
  return (await request<{ story: any }>(`/v1/stories/${id}`, { method: "PATCH", body: JSON.stringify(patch) })).story;
}
export async function deleteStory(id: string) {
  return request<{ deleted: string }>(`/v1/stories/${id}`, { method: "DELETE" });
}

// ── World ────────────────────────────────────────────────────────────
export async function getWorld(id: string) {
  return (await request<{ world: any }>(`/v1/stories/${id}/world`)).world;
}
export async function patchWorld(id: string, patch: any) {
  return (await request<{ world: any }>(`/v1/stories/${id}/world`, { method: "PATCH", body: JSON.stringify(patch) })).world;
}

// ── Characters ───────────────────────────────────────────────────────
export async function listCharacters(id: string) {
  return (await request<{ characters: any[] }>(`/v1/stories/${id}/characters`)).characters;
}
export async function createCharacter(id: string, payload: any) {
  return (await request<{ character: any }>(`/v1/stories/${id}/characters`, { method: "POST", body: JSON.stringify(payload) })).character;
}
export async function patchCharacter(id: string, charId: string, patch: any) {
  return (await request<{ character: any }>(`/v1/stories/${id}/characters/${charId}`, { method: "PATCH", body: JSON.stringify(patch) })).character;
}
export async function deleteCharacter(id: string, charId: string) {
  return request(`/v1/stories/${id}/characters/${charId}`, { method: "DELETE" });
}
export async function listRelationships(id: string, charId: string) {
  return (await request<{ relationships: any[] }>(`/v1/stories/${id}/characters/${charId}/relationships`)).relationships;
}
export async function addRelationship(id: string, charId: string, payload: { target_id: string; type: string; description?: string }) {
  return (await request<{ relationship: any }>(`/v1/stories/${id}/characters/${charId}/relationships`, { method: "POST", body: JSON.stringify(payload) })).relationship;
}
export async function deleteRelationship(id: string, relId: string) {
  return request(`/v1/stories/${id}/relationships/${relId}`, { method: "DELETE" });
}

// ── Character Voice Studio (Narrative Fidelity Engine) ───────────────────
// Identity uses the /identity prefix (NOT /voice — that namespace is the existing
// deterministic voice-profile endpoints).
export async function getIdentity(id: string, charId: string) {
  return request<{ identity: any; masks: any[]; states: any[] }>(`/v1/stories/${id}/identity/${charId}`);
}
export async function patchIdentityLayer(id: string, charId: string, layer: string, payload: any, buildMethod?: string) {
  return (await request<{ identity: any }>(`/v1/stories/${id}/identity/${charId}/layer/${layer}`, {
    method: "PATCH", body: JSON.stringify({ payload, build_method: buildMethod ?? null }),
  })).identity;
}
export async function listMasks(id: string, charId: string) {
  return (await request<{ masks: any[] }>(`/v1/stories/${id}/identity/${charId}/masks`)).masks;
}
export async function addMask(id: string, charId: string, payload: any) {
  return (await request<{ mask: any }>(`/v1/stories/${id}/identity/${charId}/masks`, { method: "POST", body: JSON.stringify(payload) })).mask;
}
export async function patchMask(id: string, maskId: string, payload: any) {
  return (await request<{ mask: any }>(`/v1/stories/${id}/identity/masks/${maskId}`, { method: "PATCH", body: JSON.stringify(payload) })).mask;
}
export async function deleteMask(id: string, maskId: string) {
  return request(`/v1/stories/${id}/identity/masks/${maskId}`, { method: "DELETE" });
}
export async function listStates(id: string, charId: string, activeOnly = false) {
  return (await request<{ states: any[] }>(`/v1/stories/${id}/identity/${charId}/states${activeOnly ? "?active_only=true" : ""}`)).states;
}
export async function setState(id: string, charId: string, payload: any) {
  return (await request<{ state: any }>(`/v1/stories/${id}/identity/${charId}/states`, { method: "POST", body: JSON.stringify(payload) })).state;
}
export async function clearState(id: string, stateId: string) {
  return request(`/v1/stories/${id}/identity/states/${stateId}`, { method: "DELETE" });
}
export async function listIdentityVersions(id: string, charId: string, kind?: string) {
  return (await request<{ versions: any[] }>(`/v1/stories/${id}/identity/${charId}/versions${kind ? `?kind=${kind}` : ""}`)).versions;
}
export async function getArc(id: string, charId: string) {
  return (await request<{ arc: any[] }>(`/v1/stories/${id}/identity/${charId}/arc`)).arc;
}

// Method 1 — analyze existing writing (pasted text and/or selected chapters)
export async function analyzeWriting(id: string, charId: string, opts: { text?: string; chapter_ids?: string[] }) {
  return request<{ traits: any[]; representative_dialogue: string[]; uncertain_areas: string[]; used_chapters: { id: string; number: number; title: string }[]; truncated: boolean; fallback: boolean }>(
    `/v1/stories/${id}/identity/${charId}/analyze`,
    { method: "POST", body: JSON.stringify({ text: opts.text ?? "", chapter_ids: opts.chapter_ids ?? [] }) });
}
export async function approveTraits(id: string, charId: string, decisions: any[]) {
  return (await request<{ identity: any }>(`/v1/stories/${id}/identity/${charId}/analyze/approve`, { method: "POST", body: JSON.stringify({ decisions }) })).identity;
}
// Method 2 — guided interview
export async function getInterview(id: string, tier: string) {
  return request<{ tier: string; questions: any[] }>(`/v1/stories/${id}/identity/interview?tier=${tier}`);
}
export async function submitInterview(id: string, charId: string, answers: Record<string, any>, tier: string) {
  return (await request<{ identity: any }>(`/v1/stories/${id}/identity/${charId}/interview`, { method: "POST", body: JSON.stringify({ answers, tier }) })).identity;
}

// Place Identity (Part 1C)
export async function getPlaceIdentity(id: string, locId: string) {
  return (await request<{ place: any }>(`/v1/stories/${id}/place/${locId}`)).place;
}
export async function patchPlaceIdentity(id: string, locId: string, patch: any) {
  return (await request<{ place: any }>(`/v1/stories/${id}/place/${locId}`, { method: "PATCH", body: JSON.stringify(patch) })).place;
}
export async function getPlaceQuestions(id: string) {
  return request<{ questions: any[] }>(`/v1/stories/${id}/place/questions`);
}
export async function buildPlace(id: string, locId: string, answers: Record<string, any>) {
  return (await request<{ place: any }>(`/v1/stories/${id}/place/${locId}/build`, { method: "POST", body: JSON.stringify({ answers }) })).place;
}

// Observer + Dialogue Writer (Part 2)
export async function observeCritique(id: string, draft: string, strictness: string, chapterId?: string) {
  return request<{ notes: any[]; fallback: boolean }>(`/v1/stories/${id}/observer/critique`, {
    method: "POST", body: JSON.stringify({ draft, strictness, chapter_id: chapterId || null }),
  });
}
export async function rewriteDialogue(id: string, payload: { draft?: string; instruction?: string; participants?: string[]; objective?: string; strictness?: string; chapter_id?: string | null }) {
  return request<{ rewritten: string; fallback: boolean }>(`/v1/stories/${id}/observer/rewrite`, { method: "POST", body: JSON.stringify(payload) });
}
export async function markIntentional(id: string, payload: { line: string; note_kind?: string; reason?: string; chapter_id?: string | null; character_id?: string | null }) {
  return request<{ exception_id: string }>(`/v1/stories/${id}/observer/mark-intentional`, { method: "POST", body: JSON.stringify(payload) });
}
export async function updateProfileFromNote(id: string, payload: { character_id: string; layer: string; field: string; value: any }) {
  return (await request<{ identity: any }>(`/v1/stories/${id}/observer/update-profile`, { method: "POST", body: JSON.stringify(payload) })).identity;
}

// Post-scene evolve
export async function evolveSuggestions(id: string, text: string, chapterId?: string) {
  return request<{ suggestions: any[]; fallback: boolean }>(`/v1/stories/${id}/identity/evolve`, { method: "POST", body: JSON.stringify({ text, chapter_id: chapterId || null }) });
}
export async function applyEvolution(id: string, decisions: any[]) {
  return request<{ applied: number }>(`/v1/stories/${id}/identity/evolve/apply`, { method: "POST", body: JSON.stringify({ decisions }) });
}

// Voice comparison
export async function compareVoices(id: string, characterIds: string[], situation: string) {
  return request<{ entries: any[]; fallback: boolean }>(`/v1/stories/${id}/identity/compare`, { method: "POST", body: JSON.stringify({ character_ids: characterIds, situation }) });
}

// ── Chapters ─────────────────────────────────────────────────────────
export async function listChapters(id: string) {
  return (await request<{ chapters: any[] }>(`/v1/stories/${id}/chapters`)).chapters;
}
export async function getChapter(id: string, chapterId: string) {
  return (await request<{ chapter: any }>(`/v1/stories/${id}/chapters/${chapterId}`)).chapter;
}
export async function createChapter(id: string, payload: any) {
  return (await request<{ chapter: any }>(`/v1/stories/${id}/chapters`, { method: "POST", body: JSON.stringify(payload) })).chapter;
}
export async function patchChapter(id: string, chapterId: string, patch: any) {
  return (await request<{ chapter: any }>(`/v1/stories/${id}/chapters/${chapterId}`, { method: "PATCH", body: JSON.stringify(patch) })).chapter;
}
export async function deleteChapter(id: string, chapterId: string) {
  return request(`/v1/stories/${id}/chapters/${chapterId}`, { method: "DELETE" });
}

// ── Flow ─────────────────────────────────────────────────────────────
export async function flowPolish(id: string, raw: string, notes = "", scene?: { scene_character_ids?: string[]; scene_location_id?: string | null }) {
  return request<{ polished: string; fallback: boolean }>(`/v1/stories/${id}/flow/polish`, {
    method: "POST",
    body: JSON.stringify({ raw, notes, scene_character_ids: scene?.scene_character_ids ?? [], scene_location_id: scene?.scene_location_id ?? null }),
  });
}
export async function flowExtract(id: string, polished: string) {
  return request<any>(`/v1/stories/${id}/flow/extract`, { method: "POST", body: JSON.stringify({ polished }) });
}
export async function flowApprove(id: string, payload: {
  raw: string;
  polished: string;
  extracted: any;
  include_character_names?: string[];
  chapter_title?: string;
  chapter_summary?: string;
  target_chapter_id?: string | null;
  target_chapter_number?: number | null;
}) {
  return request<{ chapter_id: string; new_character_ids: string[]; added_themes: string[]; version_no: number }>(
    `/v1/stories/${id}/flow/approve`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}
export async function flowEnhance(id: string, raw: string) {
  return request<{ language: string; enhanced: string; notes: string; fallback: boolean }>(
    `/v1/stories/${id}/flow/enhance`,
    { method: "POST", body: JSON.stringify({ raw }) },
  );
}
export async function flowSaveDraft(id: string, payload: any) {
  return request<{ draft_id: string }>(`/v1/stories/${id}/flow/draft`, { method: "POST", body: JSON.stringify(payload) });
}
export async function flowGetDraft(id: string) {
  return (await request<{ draft: any }>(`/v1/stories/${id}/flow/draft`)).draft;
}
export async function flowClearDraft(id: string) {
  return request<{ cleared: number }>(`/v1/stories/${id}/flow/draft`, { method: "DELETE" });
}
export async function writingCompanion(id: string, instruction: string, chapterId?: string) {
  return request<{ draft: string; fallback: boolean }>(`/v1/stories/${id}/flow/companion`, {
    method: "POST",
    body: JSON.stringify({ instruction, chapter_id: chapterId || null }),
  });
}
// Streaming variant: invokes onDelta(text) for each chunk as it arrives (SSE).
// Resolves when the stream completes; throws ApiError on a gate/HTTP error.
export async function writingCompanionStream(
  id: string,
  instruction: string,
  onDelta: (text: string) => void,
  chapterId?: string,
  signal?: AbortSignal,
): Promise<void> {
  const token = await getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE}/v1/stories/${id}/flow/companion/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ instruction, chapter_id: chapterId || null }),
    signal,
  });
  if (!res.ok || !res.body) {
    let code = "stream_error", message = res.statusText;
    try { const j = await res.json(); code = j?.error?.code || code; message = j?.error?.message || message; } catch { /* non-JSON */ }
    throw new ApiError(code, message, res.status);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const frames = buf.split("\n\n");
      buf = frames.pop() || "";  // keep the trailing partial frame
      for (const frame of frames) {
        const line = frame.trim();
        if (!line.startsWith("data:")) continue;
        let obj: any;
        try { obj = JSON.parse(line.slice(5).trim()); } catch { continue; }
        if (obj.error) throw new ApiError("stream_error", String(obj.error), 500);
        if (typeof obj.delta === "string") onDelta(obj.delta);
      }
    }
  } catch (e: any) {
    if (e?.name === "AbortError") return; // user stopped — not an error
    throw e;
  }
}

// ── Story Check ──────────────────────────────────────────────────────
export async function storyCheck(id: string, chapterId: string | null, passType = "logic") {
  return request<any>(`/v1/stories/${id}/check`, { method: "POST", body: JSON.stringify({ chapter_id: chapterId, pass_type: passType }) });
}

// ── Graph ────────────────────────────────────────────────────────────
export async function graphView(id: string) {
  return request<{ nodes: any[]; links: any[]; source: string }>(`/v1/stories/${id}/graph/view`);
}
export async function graphReproject(id: string) {
  return request<any>(`/v1/stories/${id}/graph/reproject`, { method: "POST" });
}

// ── RAG ──────────────────────────────────────────────────────────────
export async function ragPreview(id: string, q: string) {
  return request<{ query: string; block: string }>(`/v1/stories/${id}/rag/preview?q=${encodeURIComponent(q)}`);
}
export async function ragReindex(id: string) {
  return request<any>(`/v1/stories/${id}/rag/reindex`, { method: "POST" });
}

// ── Locations / Factions / Scenes / Threads ──────────────────────────
export async function listLocations(id: string) { return (await request<{ locations: any[] }>(`/v1/stories/${id}/locations`)).locations; }
export async function createLocation(id: string, payload: any) { return (await request<{ location: any }>(`/v1/stories/${id}/locations`, { method: "POST", body: JSON.stringify(payload) })).location; }
export async function patchLocation(id: string, locId: string, patch: any) { return (await request<{ location: any }>(`/v1/stories/${id}/locations/${locId}`, { method: "PATCH", body: JSON.stringify(patch) })).location; }
export async function deleteLocation(id: string, locId: string) { return request(`/v1/stories/${id}/locations/${locId}`, { method: "DELETE" }); }

export async function listFactions(id: string) { return (await request<{ factions: any[] }>(`/v1/stories/${id}/factions`)).factions; }
export async function createFaction(id: string, payload: any) { return (await request<{ faction: any }>(`/v1/stories/${id}/factions`, { method: "POST", body: JSON.stringify(payload) })).faction; }
export async function patchFaction(id: string, facId: string, patch: any) { return (await request<{ faction: any }>(`/v1/stories/${id}/factions/${facId}`, { method: "PATCH", body: JSON.stringify(patch) })).faction; }
export async function deleteFaction(id: string, facId: string) { return request(`/v1/stories/${id}/factions/${facId}`, { method: "DELETE" }); }

export async function listScenes(id: string) { return (await request<{ scenes: any[] }>(`/v1/stories/${id}/scenes`)).scenes; }
export async function createScene(id: string, payload: any) { return (await request<{ scene: any }>(`/v1/stories/${id}/scenes`, { method: "POST", body: JSON.stringify(payload) })).scene; }
export async function patchScene(id: string, sceneId: string, patch: any) { return (await request<{ scene: any }>(`/v1/stories/${id}/scenes/${sceneId}`, { method: "PATCH", body: JSON.stringify(patch) })).scene; }
export async function deleteScene(id: string, sceneId: string) { return request(`/v1/stories/${id}/scenes/${sceneId}`, { method: "DELETE" }); }

export async function listTimeline(id: string, order: "story" | "reading" = "story") {
  return (await request<{ scenes: any[] }>(`/v1/stories/${id}/timeline?order=${order}`)).scenes;
}
export async function listWeave(id: string) { return request<{ threads: any[]; scenes: any[] }>(`/v1/stories/${id}/weave`); }
export async function listRevelations(id: string) { return (await request<{ revelations: any[] }>(`/v1/stories/${id}/revelations`)).revelations; }
export async function createRevelation(id: string, payload: any) {
  return (await request<{ revelation: any }>(`/v1/stories/${id}/revelations`, { method: "POST", body: JSON.stringify(payload) })).revelation;
}
export async function patchRevelation(id: string, revelationId: string, patch: any) {
  return (await request<{ revelation: any }>(`/v1/stories/${id}/revelations/${revelationId}`, { method: "PATCH", body: JSON.stringify(patch) })).revelation;
}
export async function deleteRevelation(id: string, revelationId: string) {
  return request(`/v1/stories/${id}/revelations/${revelationId}`, { method: "DELETE" });
}
export async function listVoiceProfiles(id: string) { return (await request<{ profiles: any[] }>(`/v1/stories/${id}/voice`)).profiles; }
export async function rebuildVoiceProfiles(id: string) {
  return (await request<{ profiles: any[] }>(`/v1/stories/${id}/voice/rebuild`, { method: "POST" })).profiles;
}

export async function listThreads(id: string) { return (await request<{ threads: any[] }>(`/v1/stories/${id}/threads`)).threads; }
export async function createThread(id: string, payload: any) { return (await request<{ thread: any }>(`/v1/stories/${id}/threads`, { method: "POST", body: JSON.stringify(payload) })).thread; }
export async function patchThread(id: string, threadId: string, patch: any) { return (await request<{ thread: any }>(`/v1/stories/${id}/threads/${threadId}`, { method: "PATCH", body: JSON.stringify(patch) })).thread; }
export async function deleteThread(id: string, threadId: string) { return request(`/v1/stories/${id}/threads/${threadId}`, { method: "DELETE" }); }

// ── LLM ──────────────────────────────────────────────────────────────
export type LaneConfig = { provider: string; base_url: string; model: string; embed_model: string; has_api_key: boolean };
export type LLMConfig = { creative: LaneConfig; technical: LaneConfig; embedding: LaneConfig };
export type LLMStatusItem = { provider: string; model: string; reachable: boolean; detail: string; lane: string };
export type ProviderInfo = { name: string; base_url: string; default_model: string; default_embed_model: string; can_embed: boolean };

export async function llmGetConfig() { return request<LLMConfig>("/v1/llm/config"); }
export async function llmPutConfig(payload: any) { return request<LLMConfig>("/v1/llm/config", { method: "PUT", body: JSON.stringify(payload) }); }
export async function llmProviders() { return (await request<{ providers: ProviderInfo[] }>("/v1/llm/providers")).providers; }
export async function llmStatus() { return request<LLMStatusItem & { statuses: LLMStatusItem[] }>("/v1/llm/status"); }
export async function llmTest(opts: { prompt?: string; lane?: string } = {}) {
  return request<{ text: string; model: string; fallback: boolean }>("/v1/llm/test", { method: "POST", body: JSON.stringify(opts) });
}
export type ModelInfo = { id: string; label: string; kind: "chat" | "embed" };
export async function llmListModels(opts: { provider: string; base_url?: string; api_key?: string; lane?: string }) {
  return request<{ provider: string; models: ModelInfo[]; count: number; error?: string }>(
    "/v1/llm/models", { method: "POST", body: JSON.stringify(opts) });
}

// ── Export / Import ──────────────────────────────────────────────────
export async function exportMarkdown(id: string) {
  const token = await getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;  // avoid sending "Bearer null"
  return fetch(`${BASE}/v1/stories/${id}/export/markdown`, { headers }).then(r => r.blob());
}
export async function exportBundle(id: string) { return request<any>(`/v1/stories/${id}/export/bundle`); }
export async function importBundle(payload: any) { return request<{ story_id: string }>("/v1/stories/import", { method: "POST", body: JSON.stringify(payload) }); }

// ── Publishing platform ───────────────────────────────────────────────────────

export async function getPublication(storyId: string) { return request<any>(`/v1/publish/${storyId}`); }
export async function listPublications() { return request<any[]>("/v1/publish/"); }
export async function createPublication(payload: any) { return request<any>("/v1/publish/", { method: "POST", body: JSON.stringify(payload) }); }
export async function updatePublication(pubId: string, patch: any) { return request<any>(`/v1/publish/${pubId}`, { method: "PUT", body: JSON.stringify(patch) }); }
export async function pushChapters(pubId: string, chapterNumbers: number[]) { return request<any>(`/v1/publish/${pubId}/push`, { method: "POST", body: JSON.stringify({ chapter_numbers: chapterNumbers }) }); }
export async function goLive(pubId: string) { return request<any>(`/v1/publish/${pubId}/go-live`, { method: "POST" }); }
export async function unpublish(pubId: string) { return request<any>(`/v1/publish/${pubId}/unpublish`, { method: "POST" }); }
export async function archivePublication(pubId: string) { return request<any>(`/v1/publish/${pubId}/archive`, { method: "POST" }); }
export async function deletePublication(pubId: string) { return request<any>(`/v1/publish/${pubId}`, { method: "DELETE" }); }

// ── Discovery & reading ───────────────────────────────────────────────────────

export async function getDiscoveryFeed(params: { page?: number; per_page?: number; genre?: string; sort?: string; q?: string } = {}) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined) as [string, string][]).toString();
  return request<any>(`/v1/read/${qs ? "?" + qs : ""}`);
}
export async function getGenres() { return request<string[]>("/v1/read/genres"); }
export async function getMyLibrary() { return request<any>("/v1/read/my/library"); }
export async function getStoryLanding(slug: string) { return request<any>(`/v1/read/${slug}`); }
export async function readChapter(slug: string, chapterNumber: number) { return request<any>(`/v1/read/${slug}/chapters/${chapterNumber}`); }
export async function updateReadingProgress(slug: string, payload: { chapter_number: number; completion_percentage: number }) { return request<any>(`/v1/read/${slug}/progress`, { method: "PUT", body: JSON.stringify(payload) }); }
export async function followStory(slug: string) { return request<any>(`/v1/read/${slug}/follow`, { method: "POST" }); }
export async function unfollowStory(slug: string) { return request<any>(`/v1/read/${slug}/follow`, { method: "DELETE" }); }

// ── Image upload (cover art) ───────────────────────────────────────────────────
// FormData must NOT carry an application/json Content-Type (the browser sets the
// multipart boundary itself), so this bypasses request<T> and fetches directly.
export async function uploadImage(file: File): Promise<{ url: string }> {
  const form = new FormData();
  form.append("file", file);
  const headers = new Headers();
  const token = await getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE}/v1/uploads/image`, { method: "POST", body: form, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body?.ok === false) {
    throw new ApiError(body?.error?.code || "upload_failed", body?.error?.message || "Upload failed", res.status);
  }
  return body.data;
}

// Resolve a cover URL (uploaded paths are same-origin /v1/media/… served by the API).
export function mediaUrl(url?: string | null): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("/")) return `${BASE}${url}`;
  return url;
}

// ── Notifications (in-app) ──────────────────────────────────────────────────────
export async function listNotifications(opts: { limit?: number; unreadOnly?: boolean } = {}) {
  const q = new URLSearchParams();
  if (opts.limit) q.set("limit", String(opts.limit));
  if (opts.unreadOnly) q.set("unread_only", "true");
  return request<{ items: any[]; unread_count: number }>(`/v1/notifications${q.toString() ? `?${q}` : ""}`);
}
export async function getNotificationUnreadCount() { return (await request<{ unread_count: number }>("/v1/notifications/unread-count")).unread_count; }
export async function markNotificationsRead(payload: { ids?: string[]; all?: boolean }) { return request<any>("/v1/notifications/read", { method: "POST", body: JSON.stringify(payload) }); }

// ── Social ────────────────────────────────────────────────────────────────────

export async function ratePublication(pubId: string, payload: any) { return request<any>(`/v1/social/${pubId}/rate`, { method: "POST", body: JSON.stringify(payload) }); }
export async function deleteRating(pubId: string) { return request<any>(`/v1/social/${pubId}/rate`, { method: "DELETE" }); }
export async function getRatingStats(pubId: string) { return request<any>(`/v1/social/${pubId}/ratings`); }
export async function submitReview(pubId: string, body: string) { return request<any>(`/v1/social/${pubId}/review`, { method: "POST", body: JSON.stringify({ body }) }); }
export async function getPublicReviews(pubId: string) { return request<any[]>(`/v1/social/${pubId}/reviews`); }
export async function approveReview(reviewId: string) { return request<any>(`/v1/social/reviews/${reviewId}/approve`, { method: "POST" }); }
export async function declineReview(reviewId: string) { return request<any>(`/v1/social/reviews/${reviewId}/decline`, { method: "POST" }); }
export async function sendNote(pubId: string, payload: any) { return request<any>(`/v1/social/${pubId}/note`, { method: "POST", body: JSON.stringify(payload) }); }
export async function replyToNote(noteId: string, reply: string) { return request<any>(`/v1/social/notes/${noteId}/reply`, { method: "POST", body: JSON.stringify({ reply }) }); }
export async function markNoteRead(noteId: string) { return request<any>(`/v1/social/notes/${noteId}/read`, { method: "PUT" }); }

// ── Inbox ─────────────────────────────────────────────────────────────────────

export async function getInbox() { return request<any>("/v1/inbox/"); }
export async function getUnreadCount() { return request<{ count: number }>("/v1/inbox/unread-count"); }

// ── New-format exports (PDF/EPUB/DOCX) ────────────────────────────────────────

export function exportPdfUrl(storyId: string) { return `${BASE}/v1/export/${storyId}/pdf`; }

// ── Writer profiles ───────────────────────────────────────────────────────────

export async function getMyProfile() { return request<any>("/v1/u/me"); }
export async function updateMyProfile(payload: { display_name?: string; bio?: string; avatar_url?: string; profile_public?: boolean }) {
  return request<any>("/v1/u/me", { method: "PUT", body: JSON.stringify(payload) });
}
export async function getPublicProfile(userId: string) { return request<any>(`/v1/u/${userId}`); }
export function exportEpubUrl(storyId: string) { return `${BASE}/v1/export/${storyId}/epub`; }
export function exportDocxUrl(storyId: string) { return `${BASE}/v1/export/${storyId}/docx`; }
export function exportPackageUrl(storyId: string) { return `${BASE}/v1/export/${storyId}/package`; }

// ── Admin ─────────────────────────────────────────────────────────────────────

export async function adminGetUserUsage(userId: string) {
  return request<any>(`/v1/admin/users/${userId}/usage`);
}
export async function adminSetUserPlan(userId: string, tier: string, status: string) {
  return request<any>(`/v1/admin/users/${userId}/plan`, {
    method: "POST",
    body: JSON.stringify({ tier, status }),
  });
}

// ── Promo / gift codes ──────────────────────────────────────────────────────
export async function adminListCodes() { return (await request<{ codes: any[] }>("/v1/admin/codes")).codes; }
export async function adminCreateCode(payload: { tier: string; duration_days: number | null; max_uses: number | null; note?: string; code?: string | null }) {
  return request<any>("/v1/admin/codes", { method: "POST", body: JSON.stringify(payload) });
}
export async function adminDeactivateCode(id: string) { return request<any>(`/v1/admin/codes/${id}/deactivate`, { method: "POST" }); }
// User-facing: redeem a code for a free subscription.
export async function redeemCode(code: string) { return request<{ tier: string; lifetime: boolean; expires_at: string | null; extended: boolean; entitlement: any }>("/v1/billing/redeem", { method: "POST", body: JSON.stringify({ code }) }); }

// Owner "shape-shift": simulate a tier (null/"owner" exits test mode). Returns
// the now-simulated entitlement (same shape as /v1/billing/me).
export async function adminSetActAs(tier: Tier | null) {
  return request<Entitlement>("/v1/admin/act-as", { method: "PUT", body: JSON.stringify({ tier }) });
}
export async function adminClearActAs() {
  return request<Entitlement>("/v1/admin/act-as", { method: "DELETE" });
}

// Owner control panel: house default AI + tunable caps.
export type SiteConfigCaps = {
  dev_ai_max_actions: number | null;
  dev_ai_max_tokens: number | null;
  free_trial_max_actions: number | null;
  free_trial_max_tokens: number | null;
};
export type SiteConfig = {
  house: { provider: string | null; base_url: string; model: string; embed_model: string; has_api_key: boolean };
  caps: SiteConfigCaps;
  defaults: SiteConfigCaps & { env_house_provider: string };
};
export async function adminGetSiteConfig() {
  return request<SiteConfig>("/v1/admin/site-config");
}
export async function adminPutSiteConfig(payload: {
  house: { provider: string | null; base_url?: string; model?: string; embed_model?: string; api_key?: string };
  caps: SiteConfigCaps;
}) {
  return request<SiteConfig>("/v1/admin/site-config", { method: "PUT", body: JSON.stringify(payload) });
}
