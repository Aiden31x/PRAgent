"use client";

import { useTheme } from "next-themes";
import { Sun, Moon, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";

export function Header({ title }: { title: string }) {
  const { theme, setTheme } = useTheme();

  return (
    <header className="flex items-center justify-between border-b border-zinc-200 px-8 py-5 dark:border-zinc-800">
      <h1 className="text-xl font-semibold">{title}</h1>
      <div className="flex items-center gap-1">
        <button
          onClick={() => setTheme("light")}
          className={cn(
            "rounded-lg p-2 transition-colors",
            theme === "light"
              ? "bg-zinc-200 text-zinc-900 dark:bg-zinc-700 dark:text-white"
              : "text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          )}
          title="Light mode"
        >
          <Sun className="h-[18px] w-[18px]" />
        </button>
        <button
          onClick={() => setTheme("dark")}
          className={cn(
            "rounded-lg p-2 transition-colors",
            theme === "dark"
              ? "bg-zinc-200 text-zinc-900 dark:bg-zinc-700 dark:text-white"
              : "text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          )}
          title="Dark mode"
        >
          <Moon className="h-[18px] w-[18px]" />
        </button>
        <div className="mx-1 h-5 w-px bg-zinc-200 dark:bg-zinc-700" />
        <button
          className="rounded-lg p-2 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          title="Sign out"
        >
          <LogOut className="h-[18px] w-[18px]" />
        </button>
      </div>
    </header>
  );
}
