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
  user_id: number;
  full_name: string;
  webhook_id: number | null;
  created_at: string;
}

export interface Review {
  id: number;
  repo_id: number;
  pr_number: number;
  pr_title: string;
  status: ReviewStatus;
  total_comments: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  created_at: string;
  repo?: Repo;
  comments?: ReviewComment[];
  agent_logs?: AgentLog[];
}

export interface ReviewComment {
  id: number;
  review_id: number;
  file_path: string;
  line_number: number;
  category: ReviewCategory;
  severity: Severity;
  body: string;
  fix_suggestion: string | null;
  created_at: string;
}

export interface AgentLog {
  id: number;
  review_id: number;
  event_type: AgentEventType;
  content: string;
  created_at: string;
}

export interface DashboardStats {
  total_reviews: number;
  critical_issues: number;
  prs_this_week: number;
  avg_review_time: string;
}
