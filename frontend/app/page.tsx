"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Header } from "@/components/header";
import { StatsCard } from "@/components/stats-card";
import { ReviewTable } from "@/components/review-table";
import { apiFetch } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import { isAuthenticated } from "@/lib/auth";
import type { Repo, Review, PRSummary, TriggerReviewResponse } from "@/lib/types";
import { Plus, Loader2, FolderGit2 } from "lucide-react";

export default function DashboardPage() {
  const router = useRouter();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<Repo | null>(null);
  const [pulls, setPulls] = useState<PRSummary[]>([]);
  const [newRepoName, setNewRepoName] = useState("");
  const [loading, setLoading] = useState(true);
  const [addingRepo, setAddingRepo] = useState(false);
  const [triggeringPr, setTriggeringPr] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isAuthenticated()) return;
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [repoList, reviewList] = await Promise.all([
        apiFetch<Repo[]>("/repos"),
        apiFetch<Review[]>("/reviews"),
      ]);
      setRepos(repoList);
      setReviews(reviewList);
      if (repoList.length > 0 && !selectedRepo) {
        setSelectedRepo(repoList[0]);
        loadPulls(repoList[0].id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }

  async function loadPulls(repoId: number) {
    try {
      const prs = await apiFetch<PRSummary[]>(`/repos/${repoId}/pulls`);
      setPulls(prs);
    } catch {
      setPulls([]);
    }
  }

  async function handleAddRepo() {
    if (!newRepoName.trim()) return;
    setAddingRepo(true);
    setError("");
    try {
      const repo = await apiFetch<Repo>("/repos", {
        method: "POST",
        body: JSON.stringify({ full_name: newRepoName.trim() }),
      });
      setRepos((prev) => [repo, ...prev]);
      setSelectedRepo(repo);
      setNewRepoName("");
      loadPulls(repo.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add repo");
    } finally {
      setAddingRepo(false);
    }
  }

  async function handleTriggerReview(pr: PRSummary) {
    if (!selectedRepo) return;
    setTriggeringPr(pr.number);
    try {
      const result = await apiFetch<TriggerReviewResponse>("/reviews", {
        method: "POST",
        body: JSON.stringify({
          repo_id: selectedRepo.id,
          pr_number: pr.number,
          pr_title: pr.title,
          pr_description: pr.description,
          base_branch: pr.base_branch,
          head_branch: pr.head_branch,
          changed_files: pr.changed_files,
        }),
      });
      router.push(`/review/${result.review_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to trigger review");
    } finally {
      setTriggeringPr(null);
    }
  }

  function selectRepo(repo: Repo) {
    setSelectedRepo(repo);
    loadPulls(repo.id);
  }

  const completedReviews = reviews.filter((r) => r.status === "completed");
  const totalComments = completedReviews.reduce((s, r) => s + r.total_comments, 0);
  const totalCritical = reviews.reduce((s, r) => s + r.critical_count, 0);
  const avgIssues =
    completedReviews.length > 0
      ? (totalComments / completedReviews.length).toFixed(1)
      : "0";

  if (!isAuthenticated()) {
    return (
      <div className="min-h-screen">
        <Header title="AI PR Review Dashboard" />
        <div className="flex flex-col items-center justify-center gap-4 p-16 text-center">
          <FolderGit2 className="h-12 w-12 text-zinc-300 dark:text-zinc-600" />
          <h2 className="text-lg font-semibold">Welcome to PRAgent</h2>
          <p className="text-sm text-zinc-500">
            Connect your GitHub account to get started.
          </p>
          <a
            href="/settings#connect"
            className="rounded-lg bg-zinc-900 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-zinc-800 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-100"
          >
            Connect GitHub
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header title="AI PR Review Dashboard" />

      <div className="space-y-6 p-8">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </div>
        )}

        {/* Add Repo */}
        <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-6 dark:border-zinc-800 dark:bg-zinc-900">
          <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Add a Repository
          </label>
          <div className="flex gap-3">
            <input
              type="text"
              value={newRepoName}
              onChange={(e) => setNewRepoName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAddRepo()}
              placeholder="owner/repo (e.g. Aiden31x/PRAgent)"
              className="flex-1 rounded-lg border border-zinc-300 bg-white px-4 py-2.5 font-mono text-sm text-zinc-900 placeholder-zinc-400 outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-zinc-700 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-500 dark:focus:border-blue-500"
            />
            <button
              onClick={handleAddRepo}
              disabled={addingRepo}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {addingRepo ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Add Repo
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatsCard
            label="Total Reviews"
            value={loading ? "—" : formatNumber(reviews.length)}
          />
          <StatsCard
            label="Critical Issues"
            value={loading ? "—" : formatNumber(totalCritical)}
          />
          <StatsCard
            label="Connected Repos"
            value={loading ? "—" : formatNumber(repos.length)}
          />
          <StatsCard
            label="Avg Issues / PR"
            value={loading ? "—" : avgIssues}
          />
        </div>

        {/* Repo selector + PRs */}
        {repos.length > 0 && (
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800">
            <div className="flex items-center gap-2 border-b border-zinc-200 p-4 dark:border-zinc-800">
              <FolderGit2 className="h-4 w-4 text-zinc-400" />
              <span className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                Repositories
              </span>
            </div>
            <div className="flex flex-wrap gap-2 p-4">
              {repos.map((repo) => (
                <button
                  key={repo.id}
                  onClick={() => selectRepo(repo)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                    selectedRepo?.id === repo.id
                      ? "bg-blue-600 text-white"
                      : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                  }`}
                >
                  {repo.full_name}
                  {repo.webhook_id && (
                    <span className="ml-1.5 text-[10px] opacity-70">⚡</span>
                  )}
                </button>
              ))}
            </div>

            {/* Open PRs for selected repo */}
            {selectedRepo && pulls.length > 0 && (
              <div className="border-t border-zinc-200 p-4 dark:border-zinc-800">
                <h4 className="mb-3 text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  Open PRs — {selectedRepo.full_name}
                </h4>
                <div className="space-y-2">
                  {pulls.map((pr) => (
                    <div
                      key={pr.number}
                      className="flex items-center justify-between rounded-lg bg-zinc-50 p-3 dark:bg-zinc-900/50"
                    >
                      <div className="min-w-0 flex-1">
                        <span className="text-sm font-medium">
                          #{pr.number}
                        </span>{" "}
                        <span className="text-sm text-zinc-600 dark:text-zinc-400">
                          {pr.title}
                        </span>
                        <div className="mt-0.5 text-xs text-zinc-400">
                          {pr.base_branch} ← {pr.head_branch} · {pr.changed_files.length} files
                        </div>
                      </div>
                      <button
                        onClick={() => handleTriggerReview(pr)}
                        disabled={triggeringPr === pr.number}
                        className="ml-3 shrink-0 rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
                      >
                        {triggeringPr === pr.number ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          "Review"
                        )}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {selectedRepo && pulls.length === 0 && !loading && (
              <div className="border-t border-zinc-200 p-6 text-center text-sm text-zinc-400 dark:border-zinc-800">
                No open PRs for {selectedRepo.full_name}
              </div>
            )}
          </div>
        )}

        {repos.length === 0 && !loading && (
          <div className="rounded-xl border border-dashed border-zinc-300 p-12 text-center dark:border-zinc-700">
            <FolderGit2 className="mx-auto h-8 w-8 text-zinc-300 dark:text-zinc-600" />
            <p className="mt-3 text-sm text-zinc-500">
              No repositories connected yet. Add one above to get started.
            </p>
          </div>
        )}

        {/* Recent Reviews */}
        {reviews.length > 0 && (
          <div>
            <h2 className="mb-4 text-lg font-semibold">Recent Reviews</h2>
            <ReviewTable reviews={reviews} />
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
          </div>
        )}
      </div>
    </div>
  );
}
