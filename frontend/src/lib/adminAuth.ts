const ADMIN_TOKEN_STORAGE_KEY = "heyblog.adminToken";

function canUseSessionStorage() {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined";
}

export function getAdminToken(): string | null {
  if (!canUseSessionStorage()) {
    return null;
  }
  const token = window.sessionStorage.getItem(ADMIN_TOKEN_STORAGE_KEY)?.trim() ?? "";
  return token || null;
}

export function setAdminToken(token: string) {
  if (!canUseSessionStorage()) {
    return;
  }
  const normalized = token.trim();
  if (!normalized) {
    window.sessionStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
    return;
  }
  window.sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, normalized);
}

export function clearAdminToken() {
  if (!canUseSessionStorage()) {
    return;
  }
  window.sessionStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
}
