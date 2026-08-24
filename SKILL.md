---
name: engineering-journey
description: "Ingests 3+ years of GitHub developer activity history into Fulcra and generates an engaging, paced Markdown document telling the story of their engineering journey."
author: schr3b3r
version: 1.0.0
metadata:
  tags: [fulcra, github, journey, story, narrative, llm, engineering]
---

# Engineering Journey Skill

You are tasked with ingesting a developer's GitHub activity history (commits, PRs, PR reviews, issues) into Fulcra and synthesizing a single, well-formatted, engaging Markdown document that tells the story of their engineering journey over time.

This skill is split into two clean steps following Context-Compute Separation:
1. `backfill`: Slow, durable ingestion pass. Ingests raw GitHub activity into Fulcra, generates day/week/month/quarter/year activity rollups, and computes personal baseline notability signals. Run once per date range.
2. `generate`: Fast, re-runnable narrative generation pass. Reads stored rollups and notability signals from Fulcra and synthesizes the Markdown journey document without hitting GitHub APIs.

**If you were pointed directly at this repo** (a URL, a local path, or
"try this skill out") rather than invoked via an installed Hermes skill,
this file IS the skill definition -- follow it as such. First locate the
repo root (the directory containing this `SKILL.md`, `README.md`, and
`app/`) and treat all paths/commands below as relative to it; clone it
first if you were only given a URL/reference, not a local path.

---

## Execution Steps

Follow these steps in order when invoked by a user. Do not skip to
Step 2/3 before Step 1's checks are genuinely confirmed, even if the
user seems eager to jump straight to running something -- an
unauthenticated `backfill` run partway through is a worse experience
than a few seconds of upfront checking.


### Step 1: Verify Authentication & Prerequisites

Check-first, remediate-only-if-needed for both. Do not ask the user for
credentials before actually checking whether usable ones already exist.

1. **GitHub Authentication** (check before asking):
   - First check whether `GITHUB_TOKEN` and `GITHUB_USERNAME` are already
     set (env vars, or already present in a local `.env`).
   - If not, check whether the `gh` CLI is installed and already
     authenticated: `gh auth status`. If so, you can derive a usable
     token via `gh auth token` and the username via `gh api user --jq
     .login` -- offer to use that identity rather than asking the user
     to create a new PAT from scratch, unless they want a different
     account than whatever `gh` is currently logged in as.
   - Only if neither of the above yields a usable identity, ask the user
     for a GitHub Personal Access Token (PAT) with `repo` and
     `read:org` scopes (https://github.com/settings/tokens), and which
     username it belongs to.
   - Do NOT hardcode or assume the host machine's `gh` session is
     necessarily the right identity to run this skill as -- confirm it's
     the account the user actually wants a journey for, since `gh` may be
     logged in as a different account than the one whose ~20 years of
     history they want covered.
   - Write the resolved token/username into `.env` (`GITHUB_TOKEN=...`,
     `GITHUB_USERNAME=...`) so subsequent commands in this session don't
     need them repeated.

2. **Fulcra Authentication** (check before asking):
   - Check whether valid Fulcra credentials already exist, e.g. by
     confirming `~/.config/fulcra/credentials.json` (or the path in
     `FULCRA_CREDENTIALS_PATH`) exists and is non-expired/refreshable --
     `app/fulcra_client.py`'s `get_fulcra_client()` will raise a clear
     `FulcraAuthError` if not, which is a fine way to check this for
     real rather than guessing from file presence alone.
   - Only if that fails, walk the user through the `fulcra-connect` skill
     to log in: `skill_view(name="https://raw.githubusercontent.com/fulcradynamics/agent-skills/refs/heads/main/skills/fulcra-connect/SKILL.md")`.
     Do not proceed past this step until Fulcra auth is confirmed working.

3. **Python Environment** (set this up yourself, don't just hand the user
   a command to run):
   - Create/activate a venv and install dependencies:
     ```bash
     python -m venv .venv && source .venv/bin/activate
     pip install -r requirements.txt
     ```
   - Ensure `GEMINI_API_KEY` is set (env or `.env`) for LLM narrative
     synthesis -- ask the user for this one specifically if it's not
     already present anywhere; there's no way to detect/reuse an
     existing key the way GitHub/Fulcra auth can be detected.

### Step 2: Execute Ingestion & Rollups (`backfill`)

Run the full backfill pipeline using the CLI:
```bash
python app/engineering_journey.py backfill   --username <GITHUB_USERNAME>   --years 3.0
```

**Options & Parameters**:
- `--username`: GitHub username (defaults to `GITHUB_USERNAME` env var).
- `--token`: GitHub PAT (defaults to `GITHUB_TOKEN` env var).
- `--years`: Number of years of history to cover (default: `3.0`; supports multi-year history like `3.5` or `4.0`).
- `--start-date` / `--end-date`: Explicit YYYY-MM-DD bounds (overrides `--years`).
- `--repo`: Restrict to specific repository (`owner/repo`). Can be repeated. Omit to discover all repos automatically.

**Expectations**:
- The `backfill` step processes history in chunks with decaying granularity (weekly for the recent 90 days, monthly older).
- For a typical ~3-year account with ~8 active repos, backfill takes approximately **25–30 minutes** due to GitHub Search API rate-limit backoff rules.
- Execution is fully checkpointed and resumable in Fulcra. If interrupted, re-running the command resumes immediately from the last completed work item without duplicating data.

### Step 3: Synthesize Journey Narrative (`generate`)

Once backfill is complete (or if reading previously ingested data), run the narrative generator:
```bash
python app/engineering_journey.py generate   --username <GITHUB_USERNAME>   --years 3.0   --output engineering_journey_<username>.md
```

**Options & Parameters**:
- `--username`: GitHub username.
- `--years` / `--start-date` / `--end-date`: Timeframe to synthesize.
- `--output`: File path where the Markdown document will be saved (defaults to `engineering_journey_<username>.md`).

**Performance**:
- Narrative synthesis takes **30–60 seconds** (reads durably stored records from Fulcra and invokes Gemini for section prose synthesis).
- Can be re-run freely with different timeframe bounds or output paths without re-hitting GitHub.

### Step 4: Deliver Output

Present the resulting Markdown file to the user:
- Path: `engineering_journey_<username>.md`
- Features: Executive Overview, chronological Quarter/Month sections with paced depth based on notability signals, and an Appendix with full Fulcra record provenance mapping.
