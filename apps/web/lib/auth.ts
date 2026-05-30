// Token storage. localStorage for v1 — simple and works across tabs.
// (Refresh token rotation can be added later; access token TTL is 8h by default.)

const ACCESS_KEY = "gink_access_token";
const REFRESH_KEY = "gink_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}
export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}
export function setTokens(tokens: { access_token: string; refresh_token: string }) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACCESS_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}
export function clearTokens() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}
export function isAuthed(): boolean {
  return !!getAccessToken();
}
