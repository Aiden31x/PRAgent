"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Header } from "@/components/header";
import { StatsCard } from "@/components/stats-card";
import { ReviewTable } from "@/components/review-table";
import { mockStats, mockReviews } from "@/lib/mock-data";
import { formatNumber } from "@/lib/utils";
import { Link2 } from "lucide-react";

export default function DashboardPage() {
  const [prUrl, setPrUrl] = useState("");
  const router = useRouter();

  function handleReview() {
    if (!prUrl.trim()) return;
    router.push(`/review/1?pr=${encodeURIComponent(prUrl)}`);
  }

  return (
    <div className="min-h-screen">
      <Header title="AI PR Review Dashboard" />

      <div className="space-y-6 p-8">
        {/* PR URL Input */}
        <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-6 dark:border-zinc-800 dark:bg-zinc-900">
          <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
            GitHub PR URL
          </label>
          <div className="flex gap-3">
            <input
              type="url"
              value={prUrl}
              onChange={(e) => setPrUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleReview()}
              placeholder="https://github.com/owner/repo/pull/123"
              className="flex-1 rounded-lg border border-zinc-300 bg-white px-4 py-2.5 font-mono text-sm text-zinc-900 placeholder-zinc-400 outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-zinc-700 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-500 dark:focus:border-blue-500"
            />
            <button
              onClick={handleReview}
              className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              Run Review
            </button>
          </div>
          <div className="mt-2 flex items-center justify-between text-xs text-zinc-400">
            <span className="font-mono">Padding: JetBrains Mono</span>
            <a
              href="/settings#webhook"
              className="flex items-center gap-1 transition-colors hover:text-zinc-600 dark:hover:text-zinc-300"
            >
              <Link2 className="h-3 w-3" />
              connect webhook
            </a>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatsCard
            label="Total Reviews"
            value={formatNumber(mockStats.total_reviews)}
          />
          <StatsCard
            label="Critical Issues Found"
            value={formatNumber(mockStats.critical_issues)}
          />
          <StatsCard
            label="PRs This Week"
            value={formatNumber(mockStats.prs_this_week)}
          />
          <StatsCard label="Avg Review Time" value={mockStats.avg_review_time} />
        </div>

        {/* Recent Reviews */}
        <div>
          <h2 className="mb-4 text-lg font-semibold">Recent Reviews</h2>
          <ReviewTable reviews={mockReviews} />
        </div>
      </div>
    </div>
  );
}
