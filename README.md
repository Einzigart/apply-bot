# apply-bot

Script-first automation for Jobstreet Indonesia applications. Replaces the
AI-agent-drives-a-browser workflow (see `../apply-agents`) with a deterministic
Python pipeline. An LLM is used only for two things: scoring shortlisted jobs
(text-only, cheap) and — optionally — tailoring cover letters.

See `AUTOMATION-PLAN.md` for the full design and phased rollout.
Legacy workflow docs and the historical application log (129 submissions)
live in `docs/legacy/` for reference and migration.

## Pipeline

```
discover ──► filter ──► score ──► letter ──► apply
(scrape,     (rules,     (LLM or    (template   (Playwright,
 0 tokens)    0 tokens)   offline)   or LLM)     0 tokens)
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'        # add 'llm' extra for LLM scoring
.venv/bin/playwright install chromium    # or rely on installed Chrome
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

## Rules of the house

- `data/jobs.db` (SQLite) is the source of truth; `application-log.md` in the
  old repo stays the human-readable history.
- The script never guesses: unknown employer question, unexpected screen, or
  missing selector → screenshot to `logs/`, skip, move on.
- The CV (`*.pdf`) and `data/storage_state.json` are gitignored — this repo
  must stay private anyway.
