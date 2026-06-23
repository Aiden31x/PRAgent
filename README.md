# PRAgent — Autonomous PR Review Agent

> An AI-powered pull request reviewer that reads your code, thinks through it, and posts detailed inline feedback directly on GitHub — automatically.

---

## What is PRAgent?

PRAgent is a full-stack web application that **automatically reviews GitHub pull requests** using an AI agent powered by **Google Gemini** (or **Anthropic Claude**) and the **GitHub MCP server**. You connect your GitHub repos, and every time a PR is opened or updated, the agent spins up, reads the diff and files, reasons through the changes, and posts structured review comments back to GitHub — including inline code comments and issues for critical findings.

No more waiting for a teammate to find time for a review. PRAgent gives every PR an immediate first-pass review with real analysis.

---

## Features

### GitHub Integration
- **GitHub OAuth sign-in** — authenticate with your GitHub account; no passwords stored
- **Webhook-driven reviews** — register any repo and PRAgent installs a webhook automatically; every `pull_request` `opened` or `synchronize` event triggers a review
- **Posts back to GitHub** — review comments, inline annotations on changed lines, and GitHub Issues for critical findings are all posted directly to the PR via the GitHub API
- **Retry posting** — if a review ran successfully but failed to post, you can re-post it without re-running the agent

### AI Review Engine
- **ReAct-style agent loop** — the LLM reasons step-by-step, calling GitHub MCP tools to read PR metadata, changed files, and diffs before producing findings
- **Multi-provider** — run reviews with Google Gemini or Anthropic Claude; the provider is swappable per-request without changing any agent logic
- **Language-aware reviews** — the agent detects the programming languages in the PR diff and injects a targeted review checklist before the loop starts, covering language-specific pitfalls the core rubric alone would miss (see [Language-Aware Reviews](#language-aware-reviews))
- **Structured findings** — comments are categorized (bug, security, performance, error handling, code quality, test coverage) and assigned a severity level (info / warning / critical)
- **Agent thought stream** — every reasoning step and tool call is logged so you can see exactly how the agent reached its conclusions
- **Inline suggestions** — where applicable the agent proposes a concrete code fix alongside the comment
- **Production-hardened** — generous dead-man timeouts, tool-result history pruning, and file-list filtering keep reviews reliable and cost-controlled on large PRs (see [Production Safeguards](#production-safeguards))

### Dashboard UI
- **Repo management** — add repos, view registered webhooks, remove repos (webhook is deleted from GitHub too)
- **PR browser** — see all open pull requests for a registered repo with changed file names
- **Review history** — browse all past reviews with their status, comment counts, and per-review detail pages
- **Comment viewer** — see every comment the agent produced, grouped by file and severity
- **Live agent stream** — the review detail page connects to a real-time **Server-Sent Events** stream; every reasoning step and tool call appears the moment it is logged — no page refresh required
- **Dark / light mode** — theme toggle powered by `next-themes`

### Manual Reviews
- Trigger a review on any PR on-demand from the dashboard — the backend starts immediately, the UI navigates to the live review page, and you watch the agent work in real time via the SSE stream

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS 4, `next-themes`, `lucide-react` |
| **Backend** | Python, FastAPI, Uvicorn, SQLAlchemy 2 (async), asyncpg, Alembic, Pydantic Settings |
| **AI / Agent** | Google Gemini (`google-genai`), Anthropic Claude (`anthropic`), GitHub MCP server (`ghcr.io/github/github-mcp-server` via Docker) |
| **Auth** | GitHub OAuth 2.0, JWT (`python-jose`) |
| **Database** | PostgreSQL (designed for [Neon](https://neon.tech)) |
| **External** | GitHub REST API, GitHub Webhooks, Google Gemini API, Anthropic API, Docker (for MCP server) |

---

## Architecture Overview

```
Browser (Next.js)
      │  GitHub OAuth / JWT
      ▼
FastAPI Backend ──► PostgreSQL (Users, Repos, Reviews, Comments, Logs)
      │
      ├── GitHub Webhook ──► auto-trigger review on PR open/sync
      │
      ├── POST /reviews ──► creates Review row, returns review_id immediately
      │         │
      │         └── BackgroundTask: Agent Orchestrator (ReAct loop)
      │                   │  publishes events via asyncio.Queue
      │                   │
      │                   ├── Language Context ──► review-knowledge/ checklists
      │                   │     (injected into first user message before loop)
      │                   │
      │                   └── GitHub MCP Server (Docker) ──► GitHub REST API
      │                             reads PR metadata, diffs, files
      │                             posts review + inline comments + issues
      │
      └── GET /reviews/{id}/stream ──► SSE stream (text/event-stream)
                Browser receives live log / status / done events
```

1. User signs in with GitHub OAuth → backend stores token, issues JWT
2. User registers a repo → backend creates a GitHub webhook on that repo
3. **Manual trigger**: User clicks **Review** on the dashboard → `POST /reviews` returns the `review_id` in ~100 ms → browser navigates immediately to the review detail page
4. **Webhook trigger**: PR opened/updated → GitHub POSTs to `/webhooks/github` → backend verifies HMAC signature → background task runs the agent
5. Review detail page opens a `GET /reviews/{id}/stream` SSE connection — the backend sends a catch-up burst of any logs already written, then pushes `log`, `status`, and `done` events in real time as the agent works
6. Orchestrator detects languages in the changed files, loads the relevant review checklist(s), and injects them into the first LLM message
7. Agent calls the LLM with PR context → LLM uses MCP tools to read the diff → produces structured findings
8. Backend stores findings in Postgres and posts them back to GitHub as a review
9. The SSE `done` event fires; the frontend fetches the final comment set and populates the findings panel

---

## Language-Aware Reviews

Before the ReAct loop starts, the orchestrator inspects the file extensions in the PR diff and injects a language-specific review checklist into the first user message alongside the PR metadata. This directs the agent's attention to pitfalls that are easy to miss in a generic review.

### Supported languages

| Extension(s) | Checklist | What it covers |
|---|---|---|
| `.tsx`, `.jsx` | React / Next.js / TypeScript | Hooks rules, stale `useEffect` deps & closures, state mutation, `use client` boundary mistakes, React 19 Actions, `any` type, floating promises |
| `.ts`, `.js`, `.mts`, `.mjs` | TypeScript | `any` creep, unsafe type assertions, floating promises, `forEach(async)`, array index without guard — React-specific items excluded |
| `.py`, `.pyi` | Python | Mutable defaults, async blocking calls, `CancelledError` re-raise, `__eq__` without `__hash__`, SQLAlchemy lazy-load N+1 in async sessions |
| `.java` | Java | `Optional.get()` without guard, `@Transactional` on private methods, JPA N+1, `@Data` on entities, thread-safety |
| Anything else | — | Falls back to the core rubric with no additional context |

A PR touching multiple languages (e.g. `.py` + `.tsx`) gets both relevant checklists concatenated. If a PR has both `.tsx` and `.ts` files, only the React/TS guide is injected since it already covers TypeScript fundamentals.

The checklists live in `backend/review-knowledge/` as plain Markdown files and are loaded into memory once at server startup — no per-request disk I/O.

---

## Production Safeguards

The agent loop includes several hard limits to prevent runaway cost and stuck reviews:

| Safeguard | Behaviour |
|---|---|
| **Non-blocking review trigger** | `POST /reviews` commits the review row and launches a `BackgroundTask` — the HTTP response returns in ~100 ms regardless of how long the agent takes. The frontend connects to the SSE stream for live progress. |
| **Per-LLM-call timeout** (5 min) | Each Gemini / Claude API call is wrapped in `asyncio.timeout(300)`. Fires only on genuine hung connections, not legitimately slow generations. |
| **Per-MCP-tool-call timeout** (5 min) | Each GitHub MCP tool call is wrapped in `asyncio.wait_for(..., timeout=300)`. On timeout the agent receives an `ERROR:` result and continues rather than crashing the review. |
| **Overall review deadline** (25 min) | The entire `run_review` body runs under `asyncio.timeout(1500)`. If the deadline fires, the review is marked `FAILED` and the MCP Docker container is torn down cleanly. |
| **Tool-result history pruning** | Once the agent moves on to a new round of tool calls, the previous round's raw responses (which can be megabytes of file content) are replaced in the conversation history with compact placeholders. The `tool_result` block structure and `tool_use_id` are preserved so the Claude API does not reject the history; only the content is truncated. |
| **Changed-files filtering** | Lockfiles (`package-lock.json`, `yarn.lock`, `*.lock`, `go.sum`, …), minified assets (`.min.js`, `.min.css`), vendored directories (`/vendor/`, `/dist/`, `/build/`, `/__generated__/`), and generated protobuf files (`.pb.go`) are stripped from the file list shown to the agent. The list is also capped at 150 entries; if files are omitted a note is appended so the agent can fetch them via tool calls if needed. |
| **GitHub issue cap** | At most 3 GitHub Issues are opened per review, regardless of how many critical findings exist. This prevents issue-tracker spam and avoids hitting the GitHub API rate limit on large reviews. |
| **Gemini output cap** | `max_output_tokens=8192` is set on every Gemini call — comfortably above any real REVIEW_COMPLETE JSON output but finite. |
| **Single Docker container** | The MCP Docker container spawned for the review loop is reused for posting the results back to GitHub. Only one container is ever alive per review. |

---

## Running with Docker Compose

The fastest way to get PRAgent running locally — one command after filling in your credentials.

### Prerequisites

- Docker Desktop (Mac / Windows) or Docker Engine + Compose plugin (Linux)
- A [Neon](https://neon.tech) PostgreSQL connection string
- A GitHub OAuth App, a GitHub PAT, and a Gemini API key (same as manual setup)

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/your-username/PRAgent.git
cd PRAgent

# 2. Create your env file and fill in your credentials
cp .env.docker.example .env.docker

# 3. Build and start both services
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000).

The backend is available at [http://localhost:8000](http://localhost:8000) (Swagger UI at `/docs`).

> **Note — `NEXT_PUBLIC_API_URL` is baked in at build time.**
> The frontend Dockerfile passes this as a build arg so the Next.js compiler can inline it into the client bundle. If you need to point the frontend at a different backend URL, change the `NEXT_PUBLIC_API_URL` value under `build.args` in `docker-compose.yml` and rebuild with `docker compose up --build`.

### Troubleshooting

**Docker socket permission denied (Linux only)**
The backend container mounts `/var/run/docker.sock` to spawn the GitHub MCP server. On Linux hosts the socket is owned by the `docker` group, so the container's process needs to be in that group. If you see a `permission denied` error on startup, add your user to the group and re-login:

```bash
sudo usermod -aG docker $USER   # then log out and back in
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL database (or a [Neon](https://neon.tech) connection string)
- Docker (required at runtime for the GitHub MCP server)
- A GitHub OAuth App
- A Google Gemini API key (and/or an Anthropic API key for Claude)

### 1. Clone the repo

```bash
git clone https://github.com/your-username/PRAgent.git
cd PRAgent
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (e.g. Neon `postgresql://...`) |
| `GITHUB_CLIENT_ID` | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App client secret |
| `GITHUB_TOKEN` | GitHub Personal Access Token (used by the MCP server) |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GEMINI_MODEL` | Gemini model to use (e.g. `gemini-3-flash-preview`; see [Gemini models](https://ai.google.dev/gemini-api/docs/models)) |
| `ANTHROPIC_API_KEY` | Anthropic API key (optional — only needed if using Claude) |
| `JWT_SECRET` | Random secret for signing JWTs |
| `WEBHOOK_SECRET` | Secret for verifying GitHub webhook payloads |
| `WEBHOOK_URL` | Public URL for the webhook endpoint (use [smee.io](https://smee.io) for local dev) |
| `FRONTEND_URL` | URL of the frontend (default `http://localhost:3000`) |
| `DEBUG` | Set to `true` for verbose logging |

Run database migrations:

```bash
alembic upgrade head
```

Start the backend:

```bash
uvicorn app.main:app --reload
```

### 3. Frontend setup

```bash
cd frontend
npm install
```

If your backend is not on `http://localhost:8000`, create a `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Start the frontend:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### 4. GitHub OAuth App

In your GitHub OAuth App settings set:
- **Homepage URL**: `http://localhost:3000`
- **Authorization callback URL**: `http://localhost:3000/api/auth/callback`

### 5. Local webhooks (optional)

To receive real webhook events locally, use [smee.io](https://smee.io):

```bash
npx smee-client --url https://smee.io/your-channel --target http://localhost:8000/webhooks/github
```

Set `WEBHOOK_URL=https://smee.io/your-channel` in your `.env`.

---

## API Reference

The backend exposes an interactive **Swagger UI** at [`http://localhost:8000/docs`](http://localhost:8000/docs).

### Key endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/auth/github/login` | Get GitHub OAuth authorization URL |
| `POST` | `/auth/github/callback` | Exchange OAuth code for JWT |
| `GET` | `/auth/me` | Current authenticated user |
| `POST` | `/repos` | Register a repo and create a webhook |
| `GET` | `/repos` | List registered repos |
| `GET` | `/repos/{repo_id}/pulls` | List open PRs for a repo |
| `DELETE` | `/repos/{repo_id}` | Remove repo and delete webhook |
| `POST` | `/reviews` | Manually trigger a PR review |
| `GET` | `/reviews` | List all reviews |
| `GET` | `/reviews/{review_id}` | Review detail |
| `GET` | `/reviews/{review_id}/comments` | Review comments |
| `GET` | `/reviews/{review_id}/logs` | Agent reasoning logs (full history, REST) |
| `GET` | `/reviews/{review_id}/stream` | Live SSE stream of agent events (`log` / `status` / `done`) |
| `POST` | `/reviews/{review_id}/post-to-github` | Re-post a completed review to GitHub |
| `POST` | `/webhooks/github` | GitHub webhook receiver |

---

## Database Schema

| Table | Description |
|---|---|
| `users` | GitHub users (username, token, avatar URL) |
| `repos` | Registered repos linked to a user, with optional webhook ID |
| `reviews` | PR reviews with status (pending / running / completed / failed) and comment counts |
| `review_comments` | Individual findings: file path, line, category, severity, body, suggestion |
| `agent_logs` | Step-by-step agent reasoning trace (thought / tool call / observation / result) |

---

## Project Structure

```
PRAgent/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + router registration
│   │   ├── config.py            # Pydantic settings
│   │   ├── database.py          # Async SQLAlchemy engine + session
│   │   ├── models.py            # ORM models
│   │   ├── auth/                # GitHub OAuth + JWT
│   │   ├── repos/               # Repo registration + GitHub webhook management
│   │   ├── reviews/             # Review CRUD endpoints
│   │   ├── webhooks/            # GitHub webhook handler
│   │   ├── agent/               # ReAct orchestrator, prompts, schemas, LLM providers
│   │   │   ├── orchestrator.py  # Main review loop + production safeguards
│   │   │   ├── prompts.py       # System prompt + first-user-message builder
│   │   │   ├── schemas.py       # Pydantic models for LLM output validation
│   │   │   ├── language_context.py  # Language detection + checklist injection
│   │   │   └── llm/             # Provider adapters (Gemini, Claude)
│   │   └── mcp/                 # GitHub MCP server client + bridge
│   ├── review-knowledge/        # Per-language review checklists (Markdown)
│   │   ├── python.md
│   │   ├── java.md
│   │   ├── react-ts.md          # React + Next.js + TypeScript
│   │   └── typescript.md        # TypeScript-only (no React content)
│   ├── alembic/                 # Database migrations
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/                     # Next.js App Router pages + layouts
    ├── components/              # UI components
    ├── lib/                     # API client, auth helpers, types, utils
    └── package.json
```

---

## License

MIT
