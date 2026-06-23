import { getToken, clearToken } from "./auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/";
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `API error: ${res.status}`);
  }

  return res.json();
}

export function getLoginUrl(): string {
  return `${API_BASE}/auth/github/login`;
}

export interface SSELogEvent {
  id: number;
  event_type: string;
  content: string;
  created_at: string;
}

export interface SSEStatusEvent {
  status: string;
}

export interface SSEDoneEvent {
  status: string;
  total_comments: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
}

export interface SSEHandlers {
  onLog?: (data: SSELogEvent) => void;
  onStatus?: (data: SSEStatusEvent) => void;
  onDone?: (data: SSEDoneEvent) => void;
  onError?: (err: Error) => void;
}

/**
 * Connect to the review SSE stream. Returns a cleanup function that aborts
 * the connection. Uses fetch (not native EventSource) so we can send the
 * Authorization header.
 */
export function streamReview(reviewId: number, handlers: SSEHandlers): () => void {
  const controller = new AbortController();

  (async () => {
    const token = getToken();
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/reviews/${reviewId}/stream`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        signal: controller.signal,
      });
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        handlers.onError?.(err instanceof Error ? err : new Error(String(err)));
      }
      return;
    }

    if (!res.ok || !res.body) {
      handlers.onError?.(new Error(`SSE stream failed: ${res.status}`));
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE messages are separated by double newlines
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          if (!part.trim() || part.startsWith(":")) continue; // skip comments/keepalives

          let eventType = "message";
          let dataLine = "";

          for (const line of part.split("\n")) {
            if (line.startsWith("event: ")) eventType = line.slice(7).trim();
            else if (line.startsWith("data: ")) dataLine = line.slice(6).trim();
          }

          if (!dataLine) continue;

          try {
            const parsed = JSON.parse(dataLine);
            if (eventType === "log") handlers.onLog?.(parsed as SSELogEvent);
            else if (eventType === "status") handlers.onStatus?.(parsed as SSEStatusEvent);
            else if (eventType === "done") handlers.onDone?.(parsed as SSEDoneEvent);
          } catch {
            // ignore malformed SSE data
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        handlers.onError?.(err instanceof Error ? err : new Error(String(err)));
      }
    }
  })();

  return () => controller.abort();
}
