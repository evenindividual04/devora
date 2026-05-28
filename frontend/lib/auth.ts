"use client";

const KEY_ACCESS = "devora_access_token";
const KEY_REFRESH = "devora_refresh_token";

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(KEY_ACCESS, access);
  localStorage.setItem(KEY_REFRESH, refresh);
}

export function getAccessToken(): string {
  return localStorage.getItem(KEY_ACCESS) || "";
}

export function getRefreshToken(): string {
  return localStorage.getItem(KEY_REFRESH) || "";
}

export function clearTokens() {
  localStorage.removeItem(KEY_ACCESS);
  localStorage.removeItem(KEY_REFRESH);
}
