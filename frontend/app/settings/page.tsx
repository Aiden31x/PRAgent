"use client";

import { useEffect, useState } from "react";
import { Header } from "@/components/header";
import { Key, Webhook, Bell, Bot, CheckCircle2, Loader2 } from "lucide-react";
import { GithubIcon } from "@/components/icons";
import { cn } from "@/lib/utils";
import {
  isAuthenticated,
  getCurrentUser,
  clearToken,
  type TokenUser,
} from "@/lib/auth";
import { apiFetch, getLoginUrl } from "@/lib/api";
import {
  type LLMProvider,
  type User,
  LLM_PROVIDERS,
  LLM_MODELS,
} from "@/lib/types";

export default function SettingsPage() {
  const [authed, setAuthed] = useState(false);
  const [tokenUser, setTokenUser] = useState<TokenUser | null>(null);

  // LLM preference state
  const [selectedProvider, setSelectedProvider] = useState<LLMProvider>("gemini");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    const authenticated = isAuthenticated();
    setAuthed(authenticated);
    setTokenUser(getCurrentUser());

    if (authenticated) {
      apiFetch<User>("/auth/me")
        .then((user) => {
          setSelectedProvider(user.preferred_llm_provider ?? "gemini");
          setSelectedModel(
            user.preferred_llm_model ??
              LLM_MODELS[user.preferred_llm_provider ?? "gemini"][0].id
          );
        })
        .catch(() => {});
    }
  }, []);

  // When provider changes, reset model to the first available for that provider
  function handleProviderChange(p: LLMProvider) {
    setSelectedProvider(p);
    setSelectedModel(LLM_MODELS[p][0].id);
    setSaveSuccess(false);
    setSaveError("");
  }

  async function handleSavePreferences() {
    setSaving(true);
    setSaveSuccess(false);
    setSaveError("");
    try {
      await apiFetch("/auth/me/preferences", {
        method: "PATCH",
        body: JSON.stringify({
          preferred_llm_provider: selectedProvider,
          preferred_llm_model: selectedModel || null,
        }),
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to save preferences");
    } finally {
      setSaving(false);
    }
  }

  async function handleConnect() {
    const res = await fetch(getLoginUrl());
    const data = await res.json();
    window.location.href = data.url;
  }

  function handleDisconnect() {
    clearToken();
    window.location.href = "/";
  }

  const availableModels = LLM_MODELS[selectedProvider] ?? [];

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
          {authed && tokenUser && (
            <div className="mt-3 flex items-center gap-2 text-sm text-emerald-500">
              <div className="h-2 w-2 rounded-full bg-emerald-500" />
              Connected as @{tokenUser.username}
            </div>
          )}
        </section>

        {/* AI Model Preferences */}
        <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
          <div className="flex items-center gap-3">
            <Bot className="h-5 w-5" />
            <h3 className="text-sm font-semibold">AI Model Preferences</h3>
          </div>
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            Choose the default AI model used for all your reviews. You can
            override this per-review from the dashboard.
          </p>

          <div className="mt-4 space-y-4">
            {/* Provider selector */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Provider
              </label>
              <div className="flex gap-2">
                {LLM_PROVIDERS.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => handleProviderChange(p.id)}
                    className={cn(
                      "rounded-lg border px-4 py-2 text-sm font-medium transition-colors",
                      selectedProvider === p.id
                        ? "border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
                        : "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                    )}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Model selector */}
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Model
              </label>
              <select
                value={selectedModel}
                onChange={(e) => {
                  setSelectedModel(e.target.value);
                  setSaveSuccess(false);
                }}
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-zinc-700 dark:bg-zinc-800 dark:text-white"
              >
                {availableModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>

            {selectedProvider === "claude" && (
              <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
                Claude requires <code className="font-mono">ANTHROPIC_API_KEY</code>{" "}
                to be set in the backend <code className="font-mono">.env</code>.
                Contact your server admin if reviews fail.
              </p>
            )}

            {saveError && (
              <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
                {saveError}
              </p>
            )}

            <div className="flex items-center gap-3">
              <button
                onClick={handleSavePreferences}
                disabled={saving || !authed}
                className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
              >
                {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Save Preferences
              </button>
              {saveSuccess && (
                <span className="flex items-center gap-1.5 text-sm text-emerald-500">
                  <CheckCircle2 className="h-4 w-4" />
                  Saved
                </span>
              )}
            </div>
          </div>
        </section>

        {/* API Keys (informational only — set in .env) */}
        <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
          <div className="flex items-center gap-3">
            <Key className="h-5 w-5" />
            <h3 className="text-sm font-semibold">API Keys</h3>
          </div>
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            API keys are configured in the backend{" "}
            <code className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-xs dark:bg-zinc-800">
              .env
            </code>{" "}
            file. They are never exposed to the browser.
          </p>
          <div className="mt-4 space-y-2 text-xs text-zinc-500 dark:text-zinc-400">
            <p className="flex items-center gap-2">
              <span className="font-mono">GEMINI_API_KEY</span>
              <span>— required for Gemini reviews</span>
            </p>
            <p className="flex items-center gap-2">
              <span className="font-mono">ANTHROPIC_API_KEY</span>
              <span>— required for Claude reviews</span>
            </p>
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
            Webhooks are automatically created when you add a repository from
            the dashboard. PRAgent will review new PRs as they are opened using
            your preferred AI model.
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
                <span className="text-zinc-700 dark:text-zinc-300">{label}</span>
              </label>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
