const BUILD_API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const KEY = "mediscan_api_url";

/** API base URL: a value saved in this browser (Dashboard → API connection) overrides the build-time default. */
export function getApiUrl(): string {
  if (typeof window !== "undefined") {
    try {
      const v = window.localStorage.getItem(KEY);
      if (v) return v.replace(/\/$/, "");
    } catch { /* storage unavailable */ }
  }
  return BUILD_API_URL;
}

export function setApiUrl(url: string) {
  try {
    if (url.trim()) window.localStorage.setItem(KEY, url.trim().replace(/\/$/, ""));
    else window.localStorage.removeItem(KEY);
  } catch { /* ignore */ }
}
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message || `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

function headers(extra?: HeadersInit): HeadersInit {
  return { ...(API_KEY ? { "X-API-Key": API_KEY } : {}), ...(extra || {}) };
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail ?? j;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string): Promise<T> {
  return handle<T>(await fetch(`${getApiUrl()}${path}`, { headers: headers(), cache: "no-store" }));
}

export async function apiSend<T>(path: string, method: "POST" | "PUT" | "DELETE", body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(`${getApiUrl()}${path}`, {
      method,
      headers: headers(body !== undefined ? { "Content-Type": "application/json" } : undefined),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  );
}

export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  return handle<T>(await fetch(`${getApiUrl()}${path}`, { method: "POST", headers: headers(), body: form }));
}

export async function apiBlob(path: string): Promise<Blob> {
  const res = await fetch(`${getApiUrl()}${path}`, { headers: headers() });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.blob();
}

export async function download(path: string, filename: string) {
  const blob = await apiBlob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export const fmt = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : Number(v.toFixed(digits)).toString();
