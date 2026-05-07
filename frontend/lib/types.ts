export type ReviewStatus = "pending" | "reviewing" | "completed" | "failed";
export type LLMProvider = "gemini" | "claude";
export type Severity = "critical" | "warning" | "info";
export type ReviewCategory =
  | "security"
  | "bug"
  | "performance"
  | "error_handling"
  | "code_quality"
  | "test_coverage";
export type AgentEventType =
  | "thinking"
  | "fetching"
  | "found"
  | "posting"
  | "done"
  | "error";

export interface User {
  id: number;
  github_username: string;
  avatar_url: string | null;
  preferred_llm_provider: LLMProvider;
  preferred_llm_model: string | null;
  created_at: string;
}

export interface Repo {
  id: number;
  full_name: string;
  webhook_id: number | null;
}

export interface Review {
  id: number;
  repo_full_name: string;
  pr_number: number;
  pr_title: string;
  status: ReviewStatus;
  total_comments: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  github_review_posted: boolean;
  llm_provider: LLMProvider;
  llm_model: string;
  created_at: string;
  comments: ReviewComment[];
}

export interface ReviewComment {
  id: number;
  file_path: string;
  line_number: number;
  category: ReviewCategory;
  severity: Severity;
  body: string;
  fix_suggestion: string | null;
}

export interface AgentLog {
  id: number;
  event_type: AgentEventType;
  content: string;
  created_at: string;
}

export interface PRSummary {
  number: number;
  title: string;
  description: string;
  base_branch: string;
  head_branch: string;
  author: string;
  changed_files: string[];
}

export interface TriggerReviewResponse {
  review_id: number;
  status: string;
  findings_count: number;
  llm_provider: LLMProvider;
  llm_model: string;
}

export interface LLMPreferencesRequest {
  preferred_llm_provider: LLMProvider;
  preferred_llm_model: string | null;
}

export const LLM_PROVIDERS: { id: LLMProvider; label: string }[] = [
  { id: "gemini", label: "Google Gemini" },
  { id: "claude", label: "Anthropic Claude" },
];

export const LLM_MODELS: Record<LLMProvider, { id: string; label: string }[]> = {
  gemini: [
    { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
    { id: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
    { id: "gemini-1.5-pro", label: "Gemini 1.5 Pro" },
  ],
  claude: [
    { id: "claude-3-5-sonnet-20241022", label: "Claude 3.5 Sonnet" },
    { id: "claude-3-5-haiku-20241022", label: "Claude 3.5 Haiku" },
    { id: "claude-3-opus-20240229", label: "Claude 3 Opus" },
  ],
};
