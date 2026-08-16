# apply-bot

Script-first automation for Jobstreet Indonesia applications. Replaces the
AI-agent-drives-a-browser workflow (see `../apply-agents`) with a deterministic
Python pipeline. An LLM is used only for two things: scoring shortlisted jobs
(text-only, cheap) and — optionally — tailoring cover letters.

See `PLAN.md` for the full design and phased rollout.
The historical application log (129 submissions) is imported into
`data/jobs.db`; the original stays in the old `../apply-agents` repo.

## Pipeline

```
discover ──► filter ──► score ──► letter ──► apply
(scrape,     (rules,     (LLM or    (dynamic    (Playwright,
 0 tokens)    0 tokens)   offline)   LLM / tmpl) 0 tokens)
```

## Setup

```bash
# Using uv (recommended)
uv sync
uv run playwright install chromium
cp data/profile.example.yaml data/profile.yaml   # then fill in your details

# Or using standard pip
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,api,llm]'
.venv/bin/playwright install chromium
cp data/profile.example.yaml data/profile.yaml
```

## Usage

```bash
# authenticate once interactively (saves cookies to data/storage_state.json)
uv run python -m src.run login

# one-time: import the 129-row history from the old repo
uv run python -m src.run migrate-log --log ../apply-agents/application-log.md

# scrape search results + job details (read-only, anonymous OK)
uv run python -m src.run discover --pages 2

# score shortlisted jobs (offline keyword scorer or configured LLM)
uv run python -m src.run score --offline

# inspect the borderline review queue
uv run python -m src.run review

# run full end-to-end pipeline
uv run python -m src.run pipeline --pages 2

# dry-run applications (fills forms, never submits)
uv run python -m src.run apply            # dry-run
uv run python -m src.run apply --execute  # real submission
```

## Desktop & Web UI

### Desktop App (Electron + React)

```bash
# Run desktop app in development
cd electron && bun run dev

# Or build standalone desktop bundle
cd electron && bun run build
```

### FastAPI API & Web UI Server

```bash
uv run python -m src.run serve --port 5139
# or
uv run python -m src.api.main --port 5139
```

Features:
- **FastAPI backend** with typed REST endpoints for dashboard, jobs, applications, runs, profile, and settings.
- **Modern React SPA** (Tailwind CSS, TanStack Table & Query, Lucide icons, Motion animations).
- **Onboarding Setup Wizard** with CV PDF upload and AI-powered parsing.
- **LLM Settings & Dynamic Models**: Native integrations and OAuth support for OpenAI, Claude, Google Gemini / Antigravity, and GitHub Copilot.
- **Dynamic Cover Letters**: Tailors cover letters using candidate background, job descriptions, and custom instructions.
- **Live Run Streaming**: Subprocess runner with live log streaming and run cancellations.

## Rules of the house

- `data/jobs.db` (SQLite) is the source of truth; `application-log.md` in the
  old repo stays the human-readable history.
- The script never guesses: unknown employer question, unexpected screen, or
  missing selector → screenshot to `logs/`, skip, move on.
- All personal data stays out of git: `data/profile.yaml` (gitignored; copy
  `profile.example.yaml`), saved employer answers (`answers` table in
  jobs.db), the CV (`*.pdf`), and `data/storage_state.json`.
