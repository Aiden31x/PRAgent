import { cn } from "@/lib/utils";
import type { ReviewStatus } from "@/lib/types";

const config: Record<ReviewStatus, { label: string; classes: string }> = {
  completed: {
    label: "Complete",
    classes:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  },
  reviewing: {
    label: "Reviewing",
    classes:
      "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  },
  failed: {
    label: "Failed",
    classes: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
  },
  pending: {
    label: "Pending",
    classes:
      "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  },
};

export function StatusBadge({ status }: { status: ReviewStatus }) {
  const c = config[status];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        c.classes
      )}
    >
      {c.label}
    </span>
  );
}
