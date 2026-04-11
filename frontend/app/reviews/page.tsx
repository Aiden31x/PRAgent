"use client";

import { useEffect, useState } from "react";
import { Header } from "@/components/header";
import { ReviewTable } from "@/components/review-table";
import { StatsCard } from "@/components/stats-card";
import { apiFetch } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import type { Review } from "@/lib/types";
import { Search, Loader2 } from "lucide-react";

export default function ReviewsPage() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [repoFilter, setRepoFilter] = useState("all");

  useEffect(() => {
    loadReviews();
  }, []);

  async function loadReviews() {
    setLoading(true);
    try {
      const data = await apiFetch<Review[]>("/reviews");
      setReviews(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load reviews");
    } finally {
      setLoading(false);
    }
  }

  const repoNames = [...new Set(reviews.map((r) => r.repo_full_name))];

  const filtered = reviews.filter((r) => {
    const matchSearch =
      !search ||
      r.pr_title.toLowerCase().includes(search.toLowerCase()) ||
      r.repo_full_name.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === "all" || r.status === statusFilter;
    const matchRepo = repoFilter === "all" || r.repo_full_name === repoFilter;
    return matchSearch && matchStatus && matchRepo;
  });

  const completed = reviews.filter((r) => r.status === "completed");
  const totalComments = completed.reduce((s, r) => s + r.total_comments, 0);
  const avgIssues =
    completed.length > 0
      ? (totalComments / completed.length).toFixed(1)
      : "0";

  const categoryCounts: Record<string, number> = {};
  for (const r of reviews) {
    for (const c of r.comments ?? []) {
      categoryCounts[c.category] = (categoryCounts[c.category] ?? 0) + 1;
    }
  }
  const topCategory =
    Object.entries(categoryCounts).sort((a, b) => b[1] - a[1])[0]?.[0]?.replace(
      /_/g,
      " "
    ) ?? "—";

  return (
    <div className="min-h-screen">
      <Header title="Review History" />

      <div className="space-y-6 p-8">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatsCard
            label="Total Reviews"
            value={loading ? "—" : formatNumber(reviews.length)}
          />
          <StatsCard
            label="Avg Issues / PR"
            value={loading ? "—" : avgIssues}
          />
          <StatsCard
            label="Top Category"
            value={loading ? "—" : topCategory}
          />
        </div>

        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by PR title or repo..."
              className="w-full rounded-lg border border-zinc-300 bg-white py-2.5 pl-10 pr-4 text-sm outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-zinc-700 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-500"
            />
          </div>
          <select
            value={repoFilter}
            onChange={(e) => setRepoFilter(e.target.value)}
            className="rounded-lg border border-zinc-300 bg-white px-4 py-2.5 text-sm outline-none transition-colors focus:border-blue-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-white"
          >
            <option value="all">All Repos</option>
            {repoNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-zinc-300 bg-white px-4 py-2.5 text-sm outline-none transition-colors focus:border-blue-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-white"
          >
            <option value="all">All Status</option>
            <option value="completed">Complete</option>
            <option value="reviewing">Reviewing</option>
            <option value="failed">Failed</option>
            <option value="pending">Pending</option>
          </select>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
          </div>
        ) : (
          <>
            <ReviewTable reviews={filtered} showAll />
            {filtered.length === 0 && (
              <div className="py-12 text-center text-zinc-400">
                {reviews.length === 0
                  ? "No reviews yet. Trigger a review from the dashboard."
                  : "No reviews found matching your filters."}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
