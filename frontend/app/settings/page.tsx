"use client";

import { useEffect, useState } from "react";
import { Header } from "@/components/header";
import { Key, Webhook, Bell } from "lucide-react";
import { GithubIcon } from "@/components/icons";
import { cn } from "@/lib/utils";
import { isAuthenticated, getCurrentUser, clearToken, type TokenUser } from "@/lib/auth";
import { getLoginUrl } from "@/lib/api";

export default function SettingsPage() {
  const [authed, setAuthed] = useState(false);
  const [user, setUser] = useState<TokenUser | null>(null);

  useEffect(() => {
    setAuthed(isAuthenticated());
    setUser(getCurrentUser());
  }, []);

  async function handleConnect() {
    const res = await fetch(getLoginUrl());
    const data = await res.json();
    window.location.href = data.url;
  }

  function handleDisconnect() {
    clearToken();
    window.location.href = "/";
  }

  return (
    <div className="min-h-screen">
      <Header title="Settings" />

      <div className="mx-auto max-w-2xl space-y-6 p-8">
        {/* GitHub Connection */}
        <section
          id="connect"
          className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800"
        >
          <div className="flex items-center gap-3">
            <GithubIcon className="h-5 w-5" />
            <h3 className="text-sm font-semibold">GitHub Connection</h3>
          </div>
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            Connect your GitHub account to enable PR reviews and webhook
            integration.
          </p>
          <button
            onClick={authed ? handleDisconnect : handleConnect}
            className={cn(
              "mt-4 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
              authed
                ? "bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300"
                : "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
            )}
          >
            {authed ? "Disconnect GitHub" : "Connect GitHub"}
          </button>
          {authed && user && (
            <div className="mt-3 flex items-center gap-2 text-sm text-emerald-500">
              <div className="h-2 w-2 rounded-full bg-emerald-500" />
              Connected as @{user.username}
            </div>
          )}
        </section>

        {/* API Keys */}
        <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
          <div className="flex items-center gap-3">
            <Key className="h-5 w-5" />
            <h3 className="text-sm font-semibold">API Keys</h3>
          </div>
          <div className="mt-4 space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-500">
                Gemini API Key
              </label>
              <input
                type="password"
                defaultValue="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
                readOnly
                className="w-full rounded-lg border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-500">
                GitHub Token
              </label>
              <input
                type="password"
                defaultValue="ghp_xxxxxxxxxxxxxxxxxxxx"
                readOnly
                className="w-full rounded-lg border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
              />
            </div>
          </div>
        </section>

        {/* Webhook Config */}
        <section
          id="webhook"
          className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800"
        >
          <div className="flex items-center gap-3">
            <Webhook className="h-5 w-5" />
            <h3 className="text-sm font-semibold">Webhook Configuration</h3>
          </div>
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            Webhooks are automatically created when you add a repository from the
            dashboard. PRAgent will review new PRs as they are opened.
          </p>
        </section>

        {/* Notifications */}
        <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
          <div className="flex items-center gap-3">
            <Bell className="h-5 w-5" />
            <h3 className="text-sm font-semibold">Notifications</h3>
          </div>
          <div className="mt-4 space-y-3">
            {[
              "Email me when a review completes",
              "Email me when critical issues are found",
              "Send Slack notifications",
            ].map((label) => (
              <label key={label} className="flex items-center gap-3 text-sm">
                <input
                  type="checkbox"
                  defaultChecked={label.includes("critical")}
                  className="h-4 w-4 rounded border-zinc-300 dark:border-zinc-600"
                />
                <span className="text-zinc-700 dark:text-zinc-300">
                  {label}
                </span>
              </label>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
