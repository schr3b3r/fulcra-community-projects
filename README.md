# Engineering Journey

**Engineering Journey** is an installable Hermes skill and command-line tool that ingests a developer's GitHub activity history going back approximately 3–4 years, stores structured, checkpointed records and multi-layer rollups in [Fulcra](https://fulcra.design/), computes personal baseline notability signals, and synthesizes a single, well-formatted, engaging Markdown document telling the story of their engineering journey.

---

## Features

- **Durable & Resumable Ingestion**: Backfills commits, pull requests, issues, and reviews across all public and private repositories. All progress is checkpointed in Fulcra so backfills can safely pause and resume without duplicating data or re-querying APIs.
- **Layered Activity Rollups**: Builds hierarchical rollups across time horizons (daily and weekly for the recent 90 days; monthly, quarterly, and yearly beyond) with grounded LLM narrative summaries.
- **Notability Signal Scoring**: Compares activity periods against personal statistical baselines to detect volume surges, new repository appearances, primary repository focus switches, sustained activity streaks, and low-volume gaps.
- **Paced Narrative Synthesis**: Generates cohesive, multi-paragraph Markdown narratives where notable stretches receive rich detail and quiet periods are gracefully compressed into concise transition clauses.
- **Full Provenance Tracing**: Every section includes an explicit provenance table mapping narrative claims directly back to underlying Fulcra `ActivityRollup` and `NotabilitySignal` record IDs.

---

## Prerequisites

1. **Python 3.11+**
2. **GitHub Personal Access Token (PAT)**:
   - Needs `repo` and `read:org` scopes.
   - Set as `GITHUB_TOKEN` environment variable or pass via `--token`.
3. **Fulcra Credentials**:
   - Authenticate with Fulcra (`~/.config/fulcra/credentials.json` or `FULCRA_CREDENTIALS_PATH`).
4. **Gemini API Key**:
   - Required for LLM narrative summarization. Set `GEMINI_API_KEY` in environment or `.env`.

---

## Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/fulcradynamics/engineering-journey.git
cd engineering-journey
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in GEMINI_API_KEY, GITHUB_TOKEN, GITHUB_USERNAME
```

---

## Usage

Engineering Journey separates ingestion/rollups from narrative generation following the **Context-Compute Separation** pattern:

### 1. Backfill GitHub Activity & Generate Rollups (`backfill`)

The `backfill` subcommand ingests raw GitHub history, creates hierarchical period rollups, and calculates notability signals in Fulcra.

```bash
python app/engineering_journey.py backfill   --username <your-github-username>   --years 3.0
```

#### CLI Options:
- `--username`: GitHub login (defaults to `GITHUB_USERNAME` env var).
- `--token`: GitHub Personal Access Token (defaults to `GITHUB_TOKEN` env var).
- `--years`: Number of years back to backfill (default: `3.0`, e.g., `4.0` for 4 years).
- `--start-date`: Explicit start date in `YYYY-MM-DD` format (overrides `--years`).
- `--end-date`: Explicit end date in `YYYY-MM-DD` format (defaults to current UTC date).
- `--repo`: Limit backfill to specific repository (`owner/repo`). Can be specified multiple times.

*Note on Backfill Duration:* Backfilling ~3 years of history for a typical multi-repository account takes ~25–30 minutes due to GitHub Search API rate-limit backoffs. Checkpoints are automatically saved to Fulcra, so if interrupted, re-running the command resumes immediately where it left off.

---

### 2. Synthesize Journey Narrative Document (`generate`)

The `generate` subcommand reads stored rollups and notability signals from Fulcra and synthesizes the Markdown document. This step runs locally without hitting GitHub APIs and can be re-run freely.

```bash
python app/engineering_journey.py generate   --username <your-github-username>   --years 3.0   --output engineering_journey.md
```

#### CLI Options:
- `--username`: GitHub login.
- `--years` / `--start-date` / `--end-date`: Timeframe filter to include in the narrative.
- `--output`: Path where the output Markdown file will be saved (defaults to `engineering_journey_<username>.md`).

---

## Output Example

The resulting Markdown document contains:
1. **Executive Overview**: High-level synthesis of major milestones, focus shifts, and activity volume over the entire timeframe.
2. **Chronological Period Sections**: Paced chapters (Quarters or Months) with deep narrative prose for high-notability periods and brief transition clauses for quiet stretches.
3. **Appendix: Provenance & Data References**: A complete mapping table tracing each narrative section back to its Fulcra `ActivityRollup` and `NotabilitySignal` IDs.

---

## Architecture

- `app/engineering_journey.py`: Unified CLI entrypoint for `backfill` and `generate`.
- `app/github_activity.py`: Raw GitHub activity record model and resumable backfill chunking.
- `app/github_client.py`: GitHub REST & GraphQL API client with automatic search rate-limit retry backoff.
- `app/rollup.py`: Day, week, month, quarter, and year rollup generation with Gemini LLM summarization.
- `app/notability.py`: Personal baseline statistical comparison and notability signal scoring.
- `app/narrative.py`: Chronological sectioning, pacing heuristics, overview synthesis, and Markdown generation.
- `app/checkpoint.py`: Generic Fulcra checkpoint runner powering resumability across all stages.
- `app/fulcra_client.py`: Centralized Fulcra SDK authentication helper.
