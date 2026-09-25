// The fetch wrapper. Attaches the session token; turns the API's error envelope into ApiError.
import { currentToken } from "./auth";
import type { LiveEvent } from "./types";

const configured = import.meta.env.VITE_API_BASE_URL as string | undefined;
export const API_BASE = configured !== undefined ? configured.replace(/\/$/, "") : "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public correlationId?: string,
    public body?: Record<string, unknown>,
  ) {
    super(message);
  }
}

async function headers(extra?: Record<string, string>): Promise<Record<string, string>> {
  const token = await currentToken();
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(extra ?? {}) };
}

async function request<T>(method: string, path: string, body?: unknown, extra?: Record<string, string>): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: await headers(body !== undefined ? { "Content-Type": "application/json", ...extra } : extra),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const err = (data as { error?: Record<string, unknown> })?.error ?? {};
    throw new ApiError(res.status, String(err.code ?? "error"), String(err.message ?? res.statusText),
      err.correlation_id as string | undefined, err);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown, extra?: Record<string, string>) => request<T>("POST", path, body ?? {}, extra),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  text: (path: string) => request<string>("GET", path),
  async blobUrl(path: string): Promise<string> {
    const res = await fetch(`${API_BASE}${path}`, { headers: await headers() });
    if (!res.ok) throw new ApiError(res.status, "not_found", "unavailable");
    return URL.createObjectURL(await res.blob());
  },
  /** Server-sent events over fetch (EventSource cannot send an Authorization header). Resumes from
   *  the last event id after a dropped connection, so no event is lost (SRS-FR-037). */
  stream(path: string, onEvent: (e: LiveEvent) => void, onState: (s: "open" | "reconnecting" | "closed") => void): () => void {
    let stopped = false;
    let lastId = "";
    const ctrl = new AbortController();
    const run = async () => {
      while (!stopped) {
        try {
          const res = await fetch(`${API_BASE}${path}`, {
            headers: await headers(lastId ? { "Last-Event-ID": lastId } : undefined),
            signal: ctrl.signal,
          });
          if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
          onState("open");
          const reader = res.body.getReader();
          const dec = new TextDecoder();
          let buf = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            let idx: number;
            while ((idx = buf.indexOf("\n\n")) >= 0) {
              const chunk = buf.slice(0, idx);
              buf = buf.slice(idx + 2);
              let id = "";
              let data = "";
              for (const line of chunk.split("\n")) {
                if (line.startsWith("id: ")) id = line.slice(4);
                else if (line.startsWith("data: ")) data += line.slice(6);
              }
              if (data) {
                lastId = id || lastId;
                const parsed = JSON.parse(data);
                onEvent({ id, ...parsed });
                if (parsed.kind === "run.completed" || parsed.kind === "run.failed") {
                  stopped = true;
                }
              }
            }
          }
          if (stopped) break;
        } catch {
          if (stopped) break;
        }
        onState("reconnecting");
        await new Promise((r) => setTimeout(r, 1500));
      }
      onState("closed");
    };
    void run();
    return () => {
      stopped = true;
      ctrl.abort();
    };
  },
};
