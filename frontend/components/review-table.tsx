import Link from "next/link";
import type { Review } from "@/lib/types";
import { StatusBadge } from "./status-badge";
import { formatDate, cn } from "@/lib/utils";

function IssuesBadge({ count }: { count: number }) {
  const color =
    count === 0
      ? "bg-zinc-200 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300"
      : count <= 2
        ? "bg-emerald-500 text-white"
        : count <= 4
          ? "bg-amber-500 text-white"
          : "bg-blue-500 text-white";

  return (
    <span
      className={cn(
        "inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold",
        color
      )}
    >
      {count}
    </span>
  );
}

interface ReviewTableProps {
  reviews: Review[];
  showAll?: boolean;
}

export function ReviewTable({ reviews, showAll }: ReviewTableProps) {
  const display = showAll ? reviews : reviews.slice(0, 5);

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
            <th className="px-5 py-3.5 text-left font-medium text-zinc-500 dark:text-zinc-400">
              PR Title
            </th>
            <th className="px-5 py-3.5 text-left font-medium text-zinc-500 dark:text-zinc-400">
              Repo
            </th>
            <th className="px-5 py-3.5 text-left font-medium text-zinc-500 dark:text-zinc-400">
              Status
            </th>
            <th className="px-5 py-3.5 text-center font-medium text-zinc-500 dark:text-zinc-400">
              Issues Found
            </th>
            <th className="px-5 py-3.5 text-left font-medium text-zinc-500 dark:text-zinc-400">
              Timestamp
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
          {display.map((r) => (
            <tr
              key={r.id}
              className="transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-900/40"
            >
              <td className="px-5 py-4">
                <Link
                  href={`/review/${r.id}`}
                  className="font-medium hover:underline"
                >
                  {r.pr_title}
                </Link>
              </td>
              <td className="px-5 py-4 text-zinc-500 dark:text-zinc-400">
                {r.repo_full_name ?? "—"}
              </td>
              <td className="px-5 py-4">
                <StatusBadge status={r.status} />
              </td>
              <td className="px-5 py-4 text-center">
                <IssuesBadge count={r.total_comments} />
              </td>
              <td className="px-5 py-4 text-zinc-500 dark:text-zinc-400">
                {formatDate(r.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
