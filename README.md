# PRAgent — Autonomous PR Review Agent

> An AI-powered pull request reviewer that reads your code, thinks through it, and posts detailed inline feedback directly on GitHub — automatically.

---

## What is PRAgent?

PRAgent is a full-stack web application that **automatically reviews GitHub pull requests** using an AI agent powered by **Google Gemini** and the **GitHub MCP server**. You connect your GitHub repos, and every time a PR is opened or updated, the agent spins up, reads the diff and files, reasons through the changes, and posts structured review comments back to GitHub — including inline code comments and issues for critical findings.

No more waiting for a teammate to find time for a review. PRAgent gives every PR an immediate first-pass review with real analysis.

---

## Features

### GitHub Integration
- **GitHub OAuth sign-in** — authenticate with your GitHub account; no passwords stored
- **Webhook-driven reviews** — register any repo and PRAgent installs a webhook automatically; every `pull_request` `opened` or `synchronize` event triggers a review
- **Posts back to GitHub** — review comments, inline annotations on changed lines, and GitHub Issues for critical findings are all posted directly to the PR via the GitHub API
- **Retry posting** — if a review ran successfully but failed to post, you can re-post it without re-running the agent

### AI Review Engine
- **ReAct-style agent loop** — Gemini reasons step-by-step, calling GitHub MCP tools to read PR metadata, changed files, and diffs before producing findings
- **Structured findings** — comments are categorized (bug, security, performance, style, etc.) and assigned a severity level (info / warning / critical)
- **Agent thought stream** — every reasoning step and tool call is logged so you can see exactly how the agent reached its conclusions
- **Inline suggestions** — where applicable the agent proposes a concrete code fix alongside the comment

### Dashboard UI
- **Repo management** — add repos, view registered webhooks, remove repos (webhook is deleted from GitHub too)
- **PR browser** — see all open pull requests for a registered repo with changed file names
- **Review history** — browse all past reviews with their status, comment counts, and per-review detail pages
- **Comment viewer** — see every comment the agent produced, grouped by file and severity
- **Log viewer** — inspect the full agent reasoning trace for any review
- **Dark / light mode** — theme toggle powered by `next-themes`

### Manual Reviews
- Trigger a review on any PR on-demand from the dashboard without waiting for a webhook event

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS 4, `next-themes`, `lucide-react` |
| **Backend** | Python, FastAPI, Uvicorn, SQLAlchemy 2 (async), asyncpg, Alembic, Pydantic Settings |
| **AI / Agent** | Google Gemini (`google-genai`), GitHub MCP server (`ghcr.io/github/github-mcp-server` via Docker) |
| **Auth** | GitHub OAuth 2.0, JWT (`python-jose`) |
| **Database** | PostgreSQL (designed for [Neon](https://neon.tech)) |
| **External** | GitHub REST API, GitHub Webhooks, Google Gemini API, Docker (for MCP server) |

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
      └── Agent Orchestrator (Gemini ReAct loop)
                │
                └── GitHub MCP Server (Docker) ──► GitHub REST API
                          reads PR metadata, diffs, files
                          posts review + inline comments + issues
```

1. User signs in with GitHub OAuth → backend stores token, issues JWT
2. User registers a repo → backend creates a GitHub webhook on that repo
3. PR opened/updated → GitHub POSTs to `/webhooks/github` → backend verifies HMAC signature → background task runs the agent
4. Agent calls Gemini with PR context → Gemini uses MCP tools to read the diff → produces structured findings
5. Backend stores findings in Postgres and posts them back to GitHub as a review
6. User can view all reviews, comments, and agent logs in the dashboard

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL database (or a [Neon](https://neon.tech) connection string)
- Docker (required at runtime for the GitHub MCP server)
- A GitHub OAuth App
- A Google Gemini API key

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
| `GET` | `/reviews/{review_id}/logs` | Agent reasoning logs |
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
│   │   ├── agent/               # Gemini ReAct orchestrator + prompts + schemas
│   │   └── mcp/                 # GitHub MCP server client + bridge
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
