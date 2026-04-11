"use client";

import { useParams } from "next/navigation";
import { useEffect, useState, useRef, useCallback } from "react";
import { Header } from "@/components/header";
import { AgentStream } from "@/components/agent-stream";
import { ReviewPanel } from "@/components/review-panel";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch } from "@/lib/api";
import type { Review, AgentLog, ReviewComment } from "@/lib/types";
import { Loader2 } from "lucide-react";

export default function ReviewDetailPage() {
  const params = useParams();
  const id = Number(params.id);

  const [review, setReview] = useState<Review | null>(null);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [comments, setComments] = useState<ReviewComment[]>([]);
  const [error, setError] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isLive = review?.status === "pending" || review?.status === "reviewing";

  const fetchData = useCallback(async () => {
    try {
      const [reviewData, logsData, commentsData] = await Promise.all([
        apiFetch<Review>(`/reviews/${id}`),
        apiFetch<AgentLog[]>(`/reviews/${id}/logs`),
        apiFetch<ReviewComment[]>(`/reviews/${id}/comments`),
      ]);
      setReview(reviewData);
      setLogs(logsData);
      setComments(commentsData);
      setError("");
      return reviewData;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load review");
      return null;
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!isLive) {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }

    pollRef.current = setInterval(async () => {
      const data = await fetchData();
      if (data && data.status !== "pending" && data.status !== "reviewing") {
        if (pollRef.current) clearInterval(pollRef.current);
      }
    }, 3000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [isLive, fetchData]);

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
