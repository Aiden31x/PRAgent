"use client";

import { useState } from "react";
import { Header } from "@/components/header";
import { ReviewTable } from "@/components/review-table";
import { mockReviews } from "@/lib/mock-data";
import { Search } from "lucide-react";

export default function ReviewsPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const filtered = mockReviews.filter((r) => {
    const matchSearch =
      !search ||
      r.pr_title.toLowerCase().includes(search.toLowerCase()) ||
      (r.repo?.full_name ?? "").toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === "all" || r.status === statusFilter;
    return matchSearch && matchStatus;
  });

  return (
    <div className="min-h-screen">
      <Header title="Recent Reviews" />

      <div className="space-y-6 p-8">
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

        <ReviewTable reviews={filtered} showAll />

        {filtered.length === 0 && (
          <div className="py-12 text-center text-zinc-400">
            No reviews found matching your filters.
          </div>
        )}
      </div>
    </div>
  );
}
