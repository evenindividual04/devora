import { getAccessToken } from "./auth";

export type HonestyMode =
  | "authentic"
  | "polished"
  | "recruiter"
  | "playful"
  | "technical"
  | "brutally_honest";

export type RunPayload = {
  username: string;
  scope: "public" | "private" | "hybrid";
  honesty_mode: HonestyMode;
  output_targets: Array<"readme" | "report" | "signals">;
  include_private: boolean;
};

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function authHeaders(extra?: Record<string, string>) {
  const t = typeof window !== "undefined" ? getAccessToken() : "";
  return { ...(extra || {}), ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

async function apiFetch(path: string, init?: RequestInit) {
  const r = await fetch(`${BASE}${path}`, init);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function register(email: string, password: string) {
  return apiFetch("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string) {
  return apiFetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function runAnalysis(payload: RunPayload) {
  return apiFetch("/analysis/run", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
}

export async function getStatus(id: string) {
  return apiFetch(`/analysis/${id}/status`, { headers: authHeaders() });
}

export async function getSignals(id: string) {
  return apiFetch(`/analysis/${id}/signals`, { headers: authHeaders() });
}

export async function getReport(id: string) {
  return apiFetch(`/analysis/${id}/report`, { headers: authHeaders() });
}

export async function getReadme(id: string) {
  return apiFetch(`/analysis/${id}/readme`, { headers: authHeaders() });
}

export async function createShare(id: string, ttl_minutes = 1440) {
  return apiFetch(`/analysis/${id}/share`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ ttl_minutes }),
  });
}

export async function revokeShare(token: string) {
  return apiFetch(`/shares/${token}/revoke`, {
    method: "POST",
    headers: authHeaders(),
  });
}
