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

---

## Execution Steps

Follow these steps in order when invoked by a user:

### Step 1: Verify Authentication & Prerequisites

1. **GitHub Authentication**:
   - Obtain a GitHub Personal Access Token (PAT) with `repo` and `read:org` scopes.
   - Do NOT depend on `gh` CLI session identity.
   - Ensure `GITHUB_TOKEN` and `GITHUB_USERNAME` environment variables are set or passed as parameters.

2. **Fulcra Authentication**:
   - Confirm the user is logged into Fulcra.
   - Use the `fulcra-connect` skill if needed: `skill_view(name="https://raw.githubusercontent.com/fulcradynamics/agent-skills/refs/heads/main/skills/fulcra-connect/SKILL.md")`.
   - Verify credentials exist at `~/.config/fulcra/credentials.json` or path in `FULCRA_CREDENTIALS_PATH`.

3. **Python Environment**:
   - Ensure dependencies are installed:
     ```bash
     pip install -r requirements.txt
     ```
   - Ensure `GEMINI_API_KEY` is set in environment or `.env` for LLM narrative synthesis.

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
