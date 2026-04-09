import type { ReviewComment, Severity, ReviewCategory } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  ShieldAlert,
  Bug,
  Zap,
  AlertTriangle,
  Code,
  TestTube2,
} from "lucide-react";

const severityConfig: Record<Severity, { color: string; border: string }> = {
  critical: { color: "text-red-400", border: "border-l-red-500" },
  warning: { color: "text-amber-400", border: "border-l-amber-500" },
  info: { color: "text-blue-400", border: "border-l-blue-500" },
};

const categoryIcons: Record<ReviewCategory, typeof ShieldAlert> = {
  security: ShieldAlert,
  bug: Bug,
  performance: Zap,
  error_handling: AlertTriangle,
  code_quality: Code,
  test_coverage: TestTube2,
};

export function ReviewPanel({ comments }: { comments: ReviewComment[] }) {
  const grouped = comments.reduce<Record<string, ReviewComment[]>>(
    (acc, c) => {
      (acc[c.file_path] ??= []).push(c);
      return acc;
    },
    {}
  );

  return (
    <div className="space-y-4 overflow-y-auto p-4">
      {Object.entries(grouped).map(([filePath, fileComments]) => (
        <div
          key={filePath}
          className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800"
        >
          <div className="border-b border-zinc-200 bg-zinc-50 px-4 py-2.5 dark:border-zinc-800 dark:bg-zinc-900/50">
            <code className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              {filePath}
            </code>
          </div>
          <div className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {fileComments.map((comment) => {
              const sev = severityConfig[comment.severity];
              const CatIcon = categoryIcons[comment.category] ?? Code;
              return (
                <div
                  key={comment.id}
                  className={cn("border-l-2 p-4", sev.border)}
                >
                  <div className="flex items-center gap-2">
                    <CatIcon className={cn("h-4 w-4", sev.color)} />
                    <span
                      className={cn(
                        "text-xs font-semibold uppercase",
                        sev.color
                      )}
                    >
                      {comment.severity}
                    </span>
                    <span className="text-xs text-zinc-500">
                      Line {comment.line_number}
                    </span>
                    <span className="rounded bg-zinc-200 px-1.5 py-0.5 text-[10px] font-medium text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400">
                      {comment.category.replace(/_/g, " ")}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
                    {comment.body}
                  </p>
                  {comment.fix_suggestion && (
                    <div className="mt-2 rounded-lg bg-zinc-100 p-3 dark:bg-zinc-800/60">
                      <p className="mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        Suggested fix
                      </p>
                      <code className="text-xs text-emerald-600 dark:text-emerald-400">
                        {comment.fix_suggestion}
                      </code>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
