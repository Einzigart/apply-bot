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
(scrape,     (rules,     (LLM or    (template   (Playwright,
 0 tokens)    0 tokens)   offline)   or LLM)     0 tokens)
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,web]'    # add 'llm' extra for LLM scoring
.venv/bin/playwright install chromium    # or rely on installed Chrome
cp data/profile.example.yaml data/profile.yaml   # then fill in your details
```

## Usage

```bash
# one-time: import the 129-row history from the old repo
.venv/bin/python -m src.run migrate-log --log ../apply-agents/application-log.md

# scrape search results + job details (read-only, anonymous OK)
.venv/bin/python -m src.run discover --pages 2

# score shortlisted jobs (offline keyword scorer by default)
.venv/bin/python -m src.run score --offline

# inspect the borderline review queue
.venv/bin/python -m src.run review

# dry-run applications (fills forms, never submits)
.venv/bin/python -m src.run apply            # dry-run
.venv/bin/python -m src.run apply --execute  # real submission (Phase 4+)
```

## Web UI

```bash
.venv/bin/python -m src.run serve            # http://127.0.0.1:5001
```

A local Flask UI over the same CLI and database: trigger
discover/score/apply/calibrate runs (one at a time, live log tail),
browse scraped jobs and the application history, and view the
profile/config/answers YAML files read-only.

- Runs started from the UI are CLI subprocesses; their output goes to
  `logs/runs/<id>.log`. Terminal runs also appear in the runs list, but
  without a captured log.
- Binds to 127.0.0.1 only and has no auth — do not expose it.
- Port 5001 because macOS AirPlay occupies 5000.

## Rules of the house

- `data/jobs.db` (SQLite) is the source of truth; `application-log.md` in the
  old repo stays the human-readable history.
- The script never guesses: unknown employer question, unexpected screen, or
  missing selector → screenshot to `logs/`, skip, move on.
- All personal data stays out of git: `data/profile.yaml` (gitignored; copy
  `profile.example.yaml`), saved employer answers (`answers` table in
  jobs.db), the CV (`*.pdf`), and `data/storage_state.json`.
