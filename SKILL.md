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

Walk the user through this ONE step at a time, in conversation -- do NOT
front-load all three requirements (GitHub, Fulcra, Gemini) into a single
big message with a numbered list before doing anything. Handle GitHub
fully (check, then remediate if needed, then confirm), THEN move to
Fulcra, THEN move to Gemini. Each is check-first, remediate-only-if-needed:
do not ask the user for credentials before actually checking whether
usable ones already exist.

#### 1a. GitHub Authentication

- First check whether `GITHUB_TOKEN` and `GITHUB_USERNAME` are already
  set (env vars, or already present in a local `.env`). If so, confirm
  with the user this is the right account (their `gh` session or env
  vars may belong to a different account than the one they want a ~3-4
  year journey for) and move on to Fulcra.
- If not, check whether the `gh` CLI is installed and already
  authenticated: `gh auth status`. If so, offer to use that identity
  (derive a token via `gh auth token`, username via `gh api user --jq
  .login`) rather than starting a fresh login -- again confirming it's
  the right account, not just whatever happens to be logged in.
- Otherwise, log the user in fresh. **Default to the OAuth device-code
  browser flow** (open a browser, enter a short code at
  github.com/login/device) rather than asking them to manually create a
  Personal Access Token -- it's the lower-friction default for a human
  sitting at a fresh machine. If the bundled `github-auth` skill is
  available in this session, prefer it (`skill_view(name="github-auth")`,
  then its "Manual OAuth Device Flow" method) since it's a maintained,
  more thoroughly proven implementation (handles slow_down/expiry/
  headless-keyring edge cases). If that skill isn't available in this
  session, run the device flow directly instead of falling back to a
  manual PAT -- it's a small, self-contained flow:
  ```bash
  # 1. Request a device code (gh's public client_id; scope: repo + read:org)
  RESP=$(curl -s -X POST -H "Accept: application/json" \
    -d "client_id=178c6fc778ccc68e1d6a&scope=repo,read:org" \
    https://github.com/login/device/code)
  DEVICE_CODE=$(echo "$RESP" | sed 's/.*"device_code":"\([^"]*\)".*/\1/')
  USER_CODE=$(echo "$RESP" | sed 's/.*"user_code":"\([^"]*\)".*/\1/')
  INTERVAL=$(echo "$RESP" | sed 's/.*"interval":\([0-9]*\).*/\1/'); INTERVAL=${INTERVAL:-5}
  # Tell the user: open https://github.com/login/device and enter $USER_CODE

  # 2. Poll for the token (respect interval; back off +5s on slow_down)
  while true; do
    sleep "$INTERVAL"
    POLL=$(curl -s -X POST -H "Accept: application/json" \
      -d "client_id=178c6fc778ccc68e1d6a&device_code=${DEVICE_CODE}&grant_type=urn:ietf:params:oauth:grant-type:device_code" \
      https://github.com/login/oauth/access_token)
    case "$POLL" in
      *access_token*)
        TOKEN=$(echo "$POLL" | sed 's/.*"access_token":"\([^"]*\)".*/\1/')
        break ;;
      *authorization_pending*) ;;                      # keep polling
      *slow_down*) INTERVAL=$((INTERVAL + 5)) ;;
      *expired_token*) echo "CODE_EXPIRED — restart the flow"; exit 1 ;;
      *access_denied*) echo "USER_DENIED"; exit 1 ;;
    esac
  done
  # Never echo $TOKEN to the user; use it directly to resolve the username below.
  ```
  Only fall back to asking for a manually-created PAT if the device flow
  genuinely can't run in this environment (no outbound network to
  github.com, etc.) -- don't offer it as an equal first option.
- Once authenticated, resolve the username too (`gh api user --jq
  .login` if using `gh`, or `curl -s -H "Authorization: token $TOKEN"
  https://api.github.com/user` if not) and write both
  `GITHUB_TOKEN`/`GITHUB_USERNAME` into `.env` so later steps/commands
  in this session don't need them repeated.
- Confirm out loud to the user which GitHub account is now
  authenticated before moving on.

#### 1b. Fulcra Authentication

- Check whether valid Fulcra credentials already exist -- e.g. confirm
  `~/.config/fulcra/credentials.json` (or the path in
  `FULCRA_CREDENTIALS_PATH`) exists and is non-expired/refreshable.
  `app/fulcra_client.py`'s `get_fulcra_client()` will raise a clear
  `FulcraAuthError` if not; that's a fine way to check this for real
  rather than guessing from file presence alone.
- Only if that fails, walk the user through the `fulcra-connect` skill
  to log in: `skill_view(name="https://raw.githubusercontent.com/fulcradynamics/agent-skills/refs/heads/main/skills/fulcra-connect/SKILL.md")`.
  Do this as its own step -- don't combine it with the GitHub ask above.
  Confirm Fulcra auth is genuinely working before moving on to Gemini.

#### 1c. Gemini API Key & Python Environment

- Ask the user for a `GEMINI_API_KEY` specifically at this point, if one
  isn't already set (env or `.env`) -- there's no way to detect/reuse an
  existing key the way GitHub/Fulcra auth can be detected, so this one
  has to be a direct ask, but keep it its own short exchange rather than
  bundling it into the earlier GitHub/Fulcra asks.
- Then set up the Python environment yourself (don't just hand the user
  a command to run):
  ```bash
  python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  ```

Once all three (GitHub, Fulcra, Gemini) are confirmed working, tell the
user briefly that setup is complete and you're ready to run `backfill`.

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
