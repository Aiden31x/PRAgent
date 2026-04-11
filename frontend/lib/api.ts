const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function startReview(prUrl: string) {
  return apiFetch("/reviews", {
    method: "POST",
    body: JSON.stringify({ pr_url: prUrl }),
  });
}

export function wsUrl(reviewId: number): string {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}/ws/review/${reviewId}`;
}
