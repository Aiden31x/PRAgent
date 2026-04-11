export type ReviewStatus = "pending" | "reviewing" | "completed" | "failed";
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
}
