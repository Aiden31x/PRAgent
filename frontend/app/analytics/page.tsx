"use client";

import { Header } from "@/components/header";
import { StatsCard } from "@/components/stats-card";
import { cn } from "@/lib/utils";

const categoryData = [
  { name: "Security", count: 34, color: "bg-red-500" },
  { name: "Bug", count: 28, color: "bg-amber-500" },
  { name: "Performance", count: 15, color: "bg-blue-500" },
  { name: "Error Handling", count: 22, color: "bg-orange-500" },
  { name: "Code Quality", count: 45, color: "bg-purple-500" },
  { name: "Test Coverage", count: 19, color: "bg-emerald-500" },
];

const weeklyData = [
  { day: "Mon", reviews: 8 },
  { day: "Tue", reviews: 12 },
  { day: "Wed", reviews: 6 },
  { day: "Thu", reviews: 15 },
  { day: "Fri", reviews: 10 },
  { day: "Sat", reviews: 3 },
  { day: "Sun", reviews: 2 },
];

const maxCategory = Math.max(...categoryData.map((d) => d.count));
const maxWeekly = Math.max(...weeklyData.map((d) => d.reviews));

export default function AnalyticsPage() {
  return (
    <div className="min-h-screen">
      <Header title="Analytics" />

      <div className="space-y-6 p-8">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatsCard label="Reviews This Month" value="163" />
          <StatsCard label="Avg Issues / PR" value="3.8" />
          <StatsCard label="Critical Issue Rate" value="12%" />
          <StatsCard label="Auto-Fix Suggestions" value="89%" />
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Issues by Category */}
          <div className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
            <h3 className="mb-5 text-sm font-semibold text-zinc-500 dark:text-zinc-400">
              Issues by Category
            </h3>
            <div className="space-y-3">
              {categoryData.map((cat) => (
                <div key={cat.name} className="flex items-center gap-3">
                  <span className="w-28 shrink-0 text-sm text-zinc-600 dark:text-zinc-300">
                    {cat.name}
                  </span>
                  <div className="flex-1">
                    <div className="h-6 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                      <div
                        className={cn(
                          "h-6 rounded-full transition-all duration-700",
                          cat.color
                        )}
                        style={{
                          width: `${(cat.count / maxCategory) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                  <span className="w-8 text-right text-sm font-medium">
                    {cat.count}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Weekly Activity */}
          <div className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
            <h3 className="mb-5 text-sm font-semibold text-zinc-500 dark:text-zinc-400">
              Weekly Activity
            </h3>
            <div
              className="flex items-end justify-between gap-3"
              style={{ height: 200 }}
            >
              {weeklyData.map((d) => (
                <div
                  key={d.day}
                  className="flex flex-1 flex-col items-center gap-1"
                >
                  <span className="text-xs font-medium">{d.reviews}</span>
                  <div
                    className="w-full rounded-t-md bg-blue-500 transition-all duration-700"
                    style={{ height: `${(d.reviews / maxWeekly) * 160}px` }}
                  />
                  <span className="text-xs text-zinc-500">{d.day}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Severity Distribution */}
        <div className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
          <h3 className="mb-5 text-sm font-semibold text-zinc-500 dark:text-zinc-400">
            Severity Distribution
          </h3>
          <div className="flex gap-8">
            {[
              { label: "Critical", count: 89, total: 1247, color: "bg-red-500" },
              { label: "Warning", count: 342, total: 1247, color: "bg-amber-500" },
              { label: "Info", count: 816, total: 1247, color: "bg-blue-500" },
            ].map((sev) => (
              <div key={sev.label} className="flex-1">
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-medium">{sev.label}</span>
                  <span className="text-2xl font-bold">{sev.count}</span>
                </div>
                <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                  <div
                    className={cn(
                      "h-2 rounded-full transition-all duration-700",
                      sev.color
                    )}
                    style={{
                      width: `${(sev.count / sev.total) * 100}%`,
                    }}
                  />
                </div>
                <p className="mt-1 text-xs text-zinc-500">
                  {((sev.count / sev.total) * 100).toFixed(1)}% of all issues
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
