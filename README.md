<div align="center">

<img src="electron/assets/icon.svg" alt="apply-bot logo" width="128" height="128" />

# Apply Bot

**Script-first job search, application automation pipeline, and ATS management hub.**

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react&logoColor=black)](https://react.dev)
[![Electron](https://img.shields.io/badge/Electron-43-47848F.svg?logo=electron&logoColor=white)](https://www.electronjs.org)

A deterministic Python pipeline and full application tracker for Jobstreet Indonesia.
Replaces brittle agent workflows with structured scraping, deterministic filtering, selective LLM scoring, dynamic cover letter generation, automated Playwright submission, and complete job application lifecycle management.

[Features](#features) • [Architecture](#pipeline-architecture) • [Quick Start](#quick-start) • [Desktop & Web UI](#desktop--web-ui) • [CLI Usage](#cli-usage) • [Configuration](#configuration) • [License](#license)

</div>

---

## Features

- **Platform Focus (Jobstreet / SEEK):** Tailored specifically for Jobstreet Indonesia / SEEK platform applications (more platforms planned in future releases).
- **Deterministic Pipeline:** Zero-token scraping and rule-based filtering before any LLM is invoked.
- **BYOK & Subscription OAuth:** Bring your own API key (OpenAI, Claude, Gemini, DeepSeek, Groq, OpenRouter) or use existing subscription OAuth (Google Cloud Code / Gemini CLI, GitHub Copilot).
- **Local & Offline Mode:** Complete zero-token offline keyword heuristic scoring or use local OpenAI-compatible endpoints (Ollama, LM Studio, vLLM).
- **Tailored Cover Letters:** Dynamic cover letter generation customized to your profile, candidate background, and specific job requirements.
- **Automated Applications:** Playwright-driven form filling with safe interactive login sessions and dry-run modes.
- **Complete Application Management (ATS Tracker):**
  - **Status Lifecycle:** Track and update stages (`Submitted`, `Process`, `Interview`, `Offering`, `Declined`, `Rejected`).
  - **Manual Entry & Row Editing:** Add external or offline job applications and edit details inline.
  - **External Jobs Bridge:** Bookmark and mark external company portal applications as applied with one click.
  - **Import & Export:** Export and import applications via native Excel (`.xlsx`), CSV, and TSV with automated duplicate detection.
- **Modern Web & Desktop UI:** Full-featured React SPA and Electron desktop wrapper with onboarding wizard, CV parser, and real-time execution logs.
- **Local-First SQLite Storage:** Self-contained SQLite database tracking job history, statuses, scores, and application metrics.

---

## Pipeline Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  discover   │ ──► │   filter    │ ──► │    score    │ ──► │   letter    │ ──► │    apply    │
│  (scrape)   │     │   (rules)   │     │ (LLM/rules) │     │  (dynamic)  │     │(Playwright) │
│  0 tokens   │     │  0 tokens   │     │  text only  │     │  tailored   │     │  0 tokens   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

1. **Discover:** Scrapes job listings and descriptions from Jobstreet Indonesia without consuming LLM tokens.
2. **Filter:** Applies deterministic rules (keywords, salary ranges, job types, blacklists).
3. **Score:** Scores candidate match quality using offline keyword heuristics or an LLM.
4. **Letter:** Generates tailored cover letters for shortlisted positions based on candidate CV data.
5. **Apply:** Navigates application forms and submits or previews submissions via Playwright.

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`
- [Bun](https://bun.sh) (for building UI and Electron desktop app)

### Installation

```bash
# Clone the repository
git clone https://github.com/Einzigart/apply-bot.git
cd apply-bot

# Install dependencies using uv
uv sync

# Install Playwright browser binaries
uv run playwright install chromium

# Set up initial configuration
cp data/profile.example.yaml data/profile.yaml
cp data/secrets.example.yaml data/secrets.yaml
```

---

## Desktop & Web UI

### Desktop App (Electron)

```bash
# Start desktop app in development
cd electron
bun install
bun run dev

# Build standalone distribution bundle
bun run build
bun run package
```

> **macOS Note:** If macOS blocks the packaged or downloaded `.app` due to Gatekeeper quarantine, remove the quarantine attribute:
> ```bash
> xattr -cr "/path/to/Apply Bot.app"
> ```

### Web Application Server

You can also launch the FastAPI backend and web interface independently:

```bash
uv run python -m src.run serve --port 5139
```

Visit `http://localhost:5139` to access:
- **Interactive Dashboard:** Real-time metrics and application funnels.
- **Job Management:** Filter, inspect, and approve job postings.
- **Onboarding Wizard:** Upload CV PDF with automated background extraction.
- **LLM Settings:** Multi-provider API keys and OAuth model picker.
- **Live Run Runner:** Real-time stdout logs and pipeline cancellation controls.

---

## CLI Usage

### 1. Interactive Login
Authenticate once interactively to store browser session cookies safely in `data/storage_state.json`:

```bash
uv run python -m src.run login
```

### 2. Discover Jobs
Scrape search listings and job descriptions:

```bash
uv run python -m src.run discover --pages 2
```

### 3. Score Shortlisted Jobs
Evaluate job relevance using offline scoring or LLM:

```bash
# Offline heuristic scorer (0 tokens)
uv run python -m src.run score --offline

# LLM-based scoring
uv run python -m src.run score
```

### 4. Review Borderline Queue
Inspect and manually resolve jobs flagged for review:

```bash
uv run python -m src.run review
```

### 5. Submit Applications

```bash
# Dry run: fills forms and verifies without submitting
uv run python -m src.run apply

# Live run: submits applications
uv run python -m src.run apply --execute
```

### 6. Full End-to-End Pipeline

```bash
uv run python -m src.run pipeline --pages 2
```

---

## Configuration

Configuration files reside in `data/`:

| File | Description | Committed to Git |
| --- | --- | --- |
| `data/config.yaml` | Scraping query, filter criteria, and search locations | Yes |
| `data/profile.yaml` | Candidate profile information, experiences, and answers | No (Ignored) |
| `data/secrets.yaml` | API keys and OAuth credentials | No (Ignored) |
| `data/jobs.db` | Local SQLite database containing job details and run history | No (Ignored) |
| `data/storage_state.json` | Browser session cookies for automated actions | No (Ignored) |

---

## Privacy & Safety

- **Zero Guessing Policy:** If an unexpected question, ambiguous prompt, or missing element occurs during application, the bot captures a screenshot to `logs/` and skips the job without submitting invalid information.
- **Local Data Storage:** All credentials, CV files, profiles, and tokens remain strictly on your local machine.

---

## License

This project is licensed under the Apache 2.0 License. See the [LICENSE](LICENSE) file for details.
