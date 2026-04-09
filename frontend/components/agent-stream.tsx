"use client";

import { useEffect, useRef, useState } from "react";
import {
  Brain,
  Download,
  Search,
  MessageSquare,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import type { AgentLog, AgentEventType } from "@/lib/types";
import { cn } from "@/lib/utils";

const eventConfig: Record<
  AgentEventType,
  { icon: typeof Brain; color: string; label: string }
> = {
  thinking: { icon: Brain, color: "text-purple-400", label: "Thinking" },
  fetching: { icon: Download, color: "text-blue-400", label: "Fetching" },
  found: { icon: Search, color: "text-amber-400", label: "Found" },
  posting: { icon: MessageSquare, color: "text-emerald-400", label: "Posting" },
  done: { icon: CheckCircle2, color: "text-green-400", label: "Done" },
  error: { icon: AlertTriangle, color: "text-red-400", label: "Error" },
};

interface AgentStreamProps {
  logs: AgentLog[];
  isLive?: boolean;
}

export function AgentStream({ logs, isLive }: AgentStreamProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const [visibleCount, setVisibleCount] = useState(isLive ? 0 : logs.length);

  useEffect(() => {
    if (!isLive) {
      setVisibleCount(logs.length);
      return;
    }
    if (visibleCount < logs.length) {
      const timer = setTimeout(
        () => setVisibleCount((c) => c + 1),
        800 + Math.random() * 1200
      );
      return () => clearTimeout(timer);
    }
  }, [visibleCount, logs.length, isLive]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visibleCount]);

  const displayed = logs.slice(0, visibleCount);

  return (
    <div className="flex flex-col gap-1 overflow-y-auto p-4">
      {displayed.map((log) => {
        const cfg = eventConfig[log.event_type];
        const Icon = cfg.icon;
        return (
          <div
            key={log.id}
            className="flex items-start gap-3 rounded-lg p-3 transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-800/40"
          >
            <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", cfg.color)} />
            <div className="min-w-0 flex-1">
              <span
                className={cn(
                  "text-xs font-semibold uppercase tracking-wide",
                  cfg.color
                )}
              >
                {cfg.label}
              </span>
              <p className="mt-0.5 text-sm text-zinc-700 dark:text-zinc-300">
                {log.content}
              </p>
            </div>
          </div>
        );
      })}

      {isLive && visibleCount < logs.length && (
        <div className="flex items-center gap-2 p-3 text-sm text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          Agent is working...
        </div>
      )}

      {visibleCount >= logs.length && logs.length > 0 && (
        <div className="flex items-center gap-2 p-3 text-sm text-emerald-400">
          <CheckCircle2 className="h-4 w-4" />
          Review complete
        </div>
      )}

      <div ref={endRef} />
    </div>
  );
}
