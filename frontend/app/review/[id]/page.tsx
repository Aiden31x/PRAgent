"use client";

import { useParams } from "next/navigation";
import { useEffect, useState, useRef, useCallback } from "react";
import { Header } from "@/components/header";
import { AgentStream } from "@/components/agent-stream";
import { ReviewPanel } from "@/components/review-panel";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, streamReview } from "@/lib/api";
import type { Review, AgentLog, ReviewComment } from "@/lib/types";
import { Loader2 } from "lucide-react";

export default function ReviewDetailPage() {
  const params = useParams();
  const id = Number(params.id);

  const [review, setReview] = useState<Review | null>(null);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [comments, setComments] = useState<ReviewComment[]>([]);
  const [error, setError] = useState("");
  const cleanupRef = useRef<(() => void) | null>(null);

  const isLive = review?.status === "pending" || review?.status === "reviewing";

  /** Fetch the final review state + comments once the stream says we're done. */
  const fetchFinalState = useCallback(async () => {
    try {
      const [reviewData, commentsData] = await Promise.all([
        apiFetch<Review>(`/reviews/${id}`),
        apiFetch<ReviewComment[]>(`/reviews/${id}/comments`),
      ]);
      setReview(reviewData);
      setComments(commentsData);
    } catch {
      // non-fatal — review header already shows status from SSE
    }
  }, [id]);

  useEffect(() => {
    // 1. Load initial state so we can render something while stream connects
    apiFetch<Review>(`/reviews/${id}`)
      .then((r) => setReview(r))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load review"));

    // 2. Open SSE stream — handles both live and catch-up (already finished) reviews
    const cleanup = streamReview(id, {
      onLog(data) {
        setLogs((prev) => {
          if (prev.some((l) => l.id === data.id)) return prev;
          return [...prev, { ...data, event_type: data.event_type as AgentLog["event_type"] }];
        });
      },
      onStatus(data) {
        setReview((prev) =>
          prev ? { ...prev, status: data.status as Review["status"] } : prev
        );
      },
      onDone(data) {
        setReview((prev) =>
          prev
            ? {
                ...prev,
                status: data.status as Review["status"],
                total_comments: data.total_comments,
                critical_count: data.critical_count,
                warning_count: data.warning_count,
                info_count: data.info_count,
              }
            : prev
        );
        fetchFinalState(); // load inline comments that appear in the right panel
      },
      onError(err) {
        // SSE failed — fall back to a one-time REST poll so UI isn't broken
        console.warn("SSE error, falling back to REST poll:", err.message);
        const interval = setInterval(async () => {
          try {
            const [r, c] = await Promise.all([
              apiFetch<Review>(`/reviews/${id}`),
              apiFetch<ReviewComment[]>(`/reviews/${id}/comments`),
            ]);
            const logsData = await apiFetch<AgentLog[]>(`/reviews/${id}/logs`);
            setReview(r);
            setComments(c);
            setLogs(logsData);
            if (r.status !== "pending" && r.status !== "reviewing") {
              clearInterval(interval);
            }
          } catch {/* ignore */}
        }, 3000);
        cleanupRef.current = () => clearInterval(interval);
      },
    });

    cleanupRef.current = cleanup;
    return () => cleanupRef.current?.();
  }, [id, fetchFinalState]);

  if (error && !review) {
    return (
      <div className="min-h-screen">
        <Header title="Review" />
        <div className="flex items-center justify-center p-16">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </div>
        </div>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="min-h-screen">
        <Header title="Review" />
        <div className="flex items-center justify-center p-16">
          <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <Header title={`Review #${review.id}`} />

      <div className="flex items-center gap-4 border-b border-zinc-200 px-8 py-4 dark:border-zinc-800">
        <StatusBadge status={review.status} />
        <span className="font-medium">{review.pr_title}</span>
        <span className="text-sm text-zinc-500 dark:text-zinc-400">
          {review.repo_full_name} #{review.pr_number}
        </span>
        <div className="ml-auto flex gap-4 text-sm font-medium">
          <span className="text-red-500 dark:text-red-400">
            {review.critical_count} critical
          </span>
          <span className="text-amber-500 dark:text-amber-400">
            {review.warning_count} warning
          </span>
          <span className="text-blue-500 dark:text-blue-400">
            {review.info_count} info
          </span>
        </div>
      </div>

      <div className="grid flex-1 grid-cols-2 divide-x divide-zinc-200 dark:divide-zinc-800">
        <div className="flex flex-col">
          <div className="border-b border-zinc-200 px-4 py-2.5 dark:border-zinc-800">
            <h3 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400">
              Agent Activity
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto">
            {logs.length > 0 ? (
              <AgentStream logs={logs} isLive={isLive} />
            ) : (
              <div className="flex items-center justify-center p-8 text-sm text-zinc-400">
                {isLive ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Waiting for agent activity...
                  </>
                ) : (
                  "No agent logs recorded."
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col">
          <div className="border-b border-zinc-200 px-4 py-2.5 dark:border-zinc-800">
            <h3 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400">
              Review Findings ({comments.length})
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto">
            {comments.length > 0 ? (
              <ReviewPanel comments={comments} />
            ) : (
              <div className="flex items-center justify-center p-8 text-sm text-zinc-400">
                {isLive
                  ? "Findings will appear here as the agent reviews..."
                  : "No findings for this review."}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
