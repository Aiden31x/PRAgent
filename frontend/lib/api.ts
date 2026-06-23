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

export interface PaginatedReviewsParams {
  skip?: number;
  limit?: number;
  status?: string;
}

export function buildReviewsUrl(params: PaginatedReviewsParams = {}): string {
  const query = new URLSearchParams();
  if (params.skip !== undefined) query.set("skip", String(params.skip));
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.status) query.set("status", params.status);
  const qs = query.toString();
  return qs ? `/reviews?${qs}` : "/reviews";
}

export async function fetchReviews<T>(params: PaginatedReviewsParams = {}): Promise<T> {
  return apiFetch<T>(buildReviewsUrl(params));
}

export async function deleteReview(reviewId: number): Promise<void> {
  await apiFetch<void>(`/reviews/${reviewId}`, { method: "DELETE" });
}
