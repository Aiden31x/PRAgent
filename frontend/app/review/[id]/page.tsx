"use client";

import { useParams } from "next/navigation";
import { Header } from "@/components/header";
import { AgentStream } from "@/components/agent-stream";
import { ReviewPanel } from "@/components/review-panel";
import { StatusBadge } from "@/components/status-badge";
import {
  mockReviews,
  mockAgentLogs,
  mockReviewComments,
} from "@/lib/mock-data";

export default function ReviewDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const review = mockReviews.find((r) => r.id === id) ?? mockReviews[0];
  const isLive = review.status === "reviewing";

  return (
    <div className="flex min-h-screen flex-col">
      <Header title={`Review #${review.id}`} />

      {/* Review meta bar */}
      <div className="flex items-center gap-4 border-b border-zinc-200 px-8 py-4 dark:border-zinc-800">
        <StatusBadge status={review.status} />
        <span className="font-medium">{review.pr_title}</span>
        <span className="text-sm text-zinc-500 dark:text-zinc-400">
          {review.repo?.full_name} #{review.pr_number}
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

      {/* Split view: agent stream | review findings */}
      <div className="grid flex-1 grid-cols-2 divide-x divide-zinc-200 dark:divide-zinc-800">
        <div className="flex flex-col">
          <div className="border-b border-zinc-200 px-4 py-2.5 dark:border-zinc-800">
            <h3 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400">
              Agent Activity
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto">
            <AgentStream logs={mockAgentLogs} isLive={isLive} />
          </div>
        </div>

        <div className="flex flex-col">
          <div className="border-b border-zinc-200 px-4 py-2.5 dark:border-zinc-800">
            <h3 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400">
              Review Findings ({mockReviewComments.length})
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto">
            <ReviewPanel comments={mockReviewComments} />
          </div>
        </div>
      </div>
    </div>
  );
}
