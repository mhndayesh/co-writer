// Typed API client. Every method returns the unwrapped `data` payload from the
// envelope `{ok, data, error}`. Throws ApiError on non-ok.

import { getAccessToken, setTokens, clearTokens } from "./auth";

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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
  const token = getAccessToken();
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
    if (res.status === 401) clearTokens();
    throw new ApiError(err.code || "error", err.message || res.statusText, res.status, err.details);
  }
  return body.data as T;
}

// ── Auth ─────────────────────────────────────────────────────────────
export async function signup(email: string, password: string, displayName = "") {
  const data = await request<{ user: any; tokens: { access_token: string; refresh_token: string } }>("/v1/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
  setTokens(data.tokens);
  return data.user;
}
export async function login(email: string, password: string) {
  const data = await request<{ user: any; tokens: { access_token: string; refresh_token: string } }>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setTokens(data.tokens);
  return data.user;
}
export async function me() {
  return request<{ user: any }>("/v1/auth/me");
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
export async function updateStory(id: string, patch: { title?: string; genre?: string; palette_idx?: number }) {
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
export async function flowPolish(id: string, raw: string, notes = "") {
  return request<{ polished: string; fallback: boolean }>(`/v1/stories/${id}/flow/polish`, { method: "POST", body: JSON.stringify({ raw, notes }) });
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

// ── Story Check ──────────────────────────────────────────────────────
export async function storyCheck(id: string, chapterId: string) {
  return request<any>(`/v1/stories/${id}/check`, { method: "POST", body: JSON.stringify({ chapter_id: chapterId }) });
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

export async function listThreads(id: string) { return (await request<{ threads: any[] }>(`/v1/stories/${id}/threads`)).threads; }
export async function createThread(id: string, payload: any) { return (await request<{ thread: any }>(`/v1/stories/${id}/threads`, { method: "POST", body: JSON.stringify(payload) })).thread; }
export async function patchThread(id: string, threadId: string, patch: any) { return (await request<{ thread: any }>(`/v1/stories/${id}/threads/${threadId}`, { method: "PATCH", body: JSON.stringify(patch) })).thread; }
export async function deleteThread(id: string, threadId: string) { return request(`/v1/stories/${id}/threads/${threadId}`, { method: "DELETE" }); }

// ── LLM ──────────────────────────────────────────────────────────────
export type LLMProfile = { provider: string; base_url: string; model: string; embed_model: string; has_api_key: boolean };
export type LLMConfig = {
  mode: "single" | "split" | "custom";
  default: LLMProfile;
  creative?: LLMProfile | null;
  technical?: LLMProfile | null;
  embedding?: LLMProfile | null;
  tasks: Record<string, LLMProfile>;
};
export type LLMStatusItem = { provider: string; model: string; reachable: boolean; detail: string; role: string };

export async function llmGetSettings() { return request<any>("/v1/llm/settings"); }
export async function llmPutSettings(payload: any) { return request<any>("/v1/llm/settings", { method: "PUT", body: JSON.stringify(payload) }); }
export async function llmGetConfig() { return request<LLMConfig>("/v1/llm/config"); }
export async function llmPutConfig(payload: any) { return request<LLMConfig>("/v1/llm/config", { method: "PUT", body: JSON.stringify(payload) }); }
export async function llmStatus() { return request<LLMStatusItem & { statuses: LLMStatusItem[] }>("/v1/llm/status"); }
export async function llmTest(opts: { prompt?: string; role?: string; page?: string } = {}) {
  return request<{ text: string; model: string; fallback: boolean }>("/v1/llm/test", { method: "POST", body: JSON.stringify(opts) });
}

// ── Export / Import ──────────────────────────────────────────────────
export async function exportMarkdown(id: string) {
  const token = getAccessToken();
  return fetch(`${BASE}/v1/stories/${id}/export/markdown`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.blob());
}
export async function exportBundle(id: string) { return request<any>(`/v1/stories/${id}/export/bundle`); }
export async function importBundle(payload: any) { return request<{ story_id: string }>("/v1/stories/import", { method: "POST", body: JSON.stringify(payload) }); }
