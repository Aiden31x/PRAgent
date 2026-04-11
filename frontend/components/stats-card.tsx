import { cn } from "@/lib/utils";

interface StatsCardProps {
  label: string;
  value: string | number;
  className?: string;
}

export function StatsCard({ label, value, className }: StatsCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-zinc-200 bg-zinc-50 p-5 dark:border-zinc-800 dark:bg-zinc-900",
        className
      )}
    >
      <p className="text-sm text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
    </div>
  );
}
