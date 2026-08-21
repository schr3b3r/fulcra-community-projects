# Architecture: Engineering Journey

## Summary
A Hermes skill that backfills ~3 years of a GitHub account's activity
(commits, PRs, reviews, discussion) into Fulcra as durable records,
builds a layered rollup structure on top (day/week for the recent 90
days, month beyond that, quarter/year on top of both), computes a
notability signal per period, and generates one paced markdown narrative
from the whole structure. No web app, no hosting — a skill that produces
a markdown file.

## Capability map: what exists vs. what's a gap

### GitHub (data source)
Verified live against this environment's `gh` CLI during Architecture:
- **GraphQL `contributionsCollection`** (per user, per date range):
  cheap, pre-aggregated counts — commits, PRs opened, PR reviews, issues
  — broken down by repository, for an arbitrary date window. This is the
  right primitive for building month/quarter/year-level *volume* data
  (the input to the notability signal) without enumerating every
  individual item. Confirmed working via `gh api graphql`.
- **REST Search API** (`search/commits`, `search/issues` for PRs):
  needed for actual *content* (commit messages, PR titles/bodies,
  discussion text) for whatever window needs real narrative detail (the
  recent 90-day window, plus any older period the notability signal
  flags as worth a closer look). Confirmed working via `gh api`
  (`search/commits?q=author:...` returned real result counts).
- **Auth**: per the Interview requirement, the skill must accept a
  GitHub identity (username + token) as runtime configuration, not
  assume the host machine's `gh` session. Implementation: accept a PAT
  via an environment variable / config file (mirroring how
  `fulcra_client.py` in the flow-state-v2 reference project loads Fulcra
  credentials from a configurable path rather than hardcoding one), and
  use it directly against GitHub's REST/GraphQL API over HTTPS (e.g. via
  `requests` or Python's stdlib) — NOT by shelling out to `gh`, so the
  skill doesn't depend on the `gh` CLI being installed or logged in as
  the right identity on whatever machine it's installed on. This mirrors
  this project's own standing rule (from the flow-state-v2 reference
  project's engineering standards) of using a real API client rather
  than shelling out to a CLI tool.
- **Gap**: no single endpoint returns "every commit/PR/review/comment for
  an account across all repos in one call with full content" — this
  requires combining the two data sources above (GraphQL for
  breadth/counts, Search API for depth/content on the periods that need
  it). This is a real integration point, not a blocker.

### Fulcra (durable storage + queryable index)
No built-in data type covers developer/GitHub activity (checked the live
catalog: closest built-ins are generic `MomentAnnotation`/
`DurationAnnotation` base types; everything else pre-built is
health/location/mindfulness-specific). This requires custom annotation
types, following the same pattern already proven in the flow-state-v2
reference project (a `MusicalIdea` custom type built on
`MomentAnnotation`) — confirmed live that `create_annotation` +
`record_data_type` + `moment_annotations` (query) work end-to-end for
exactly this kind of custom, structured, queryable record.

Custom data types needed (all `MomentAnnotation`-based, JSON-encoded
structured content in the note field — same pattern as flow-state-v2's
`MusicalIdea`/status-tracking records, not the CLI):
- **`GitHubBackfillProgress`**: the resumability checkpoint. One record
  (or a small, queryable set) tracking which repos/date-ranges have been
  fully ingested, so the backfill can be killed and resumed from a fresh
  process without re-doing completed work or losing progress. This is
  the literal Resumable Discovery mechanism from the brief and needs to
  exist and be correct before anything else is built — see Plan.
- **`GitHubActivityRaw`**: durable record of raw ingested activity
  (commit metadata + message, PR metadata + body, review, comment) —
  the bottom layer everything else derives from.
- **`ActivityRollup`**: one type, parameterized by a `period_type` field
  (`day` | `week` | `month` | `quarter` | `year`) rather than five
  separate Fulcra data types — keeps the schema count manageable and
  querying-by-period-type simple, while still letting each record
  reference which raw/lower-layer records it was built from (the
  provenance chain the brief calls a hard requirement, not a nice-to-
  have).
- **`NotabilitySignal`**: one record per rollup period, holding the
  computed signal + which inputs it was computed from — kept as its own
  record (not a field embedded in `ActivityRollup`) specifically so it
  can be recomputed/iterated on independently, since the user explicitly
  wants to try several notability formulas before settling on one.

### LLM (enrichment + narrative)
Same Gemini-based harness pattern as flow-state-v2 (already proven,
reusable as-is via the fulcra-agent-harness-starter kit) for: (a)
summarizing a period's raw activity into a rollup, (b) computing/
assisting the notability signal, (c) the final narrative-generation pass
reading the whole layered structure. No new provider integration needed.

## No gaps that block this from being built
Every capability this project needs — durable custom records, queryable
history, GitHub read access, LLM summarization — already exists and was
verified live during this Architecture pass, not assumed. The real
engineering work is the layering/rollup logic and the resumable backfill
checkpointing, not any missing platform capability.

## Tenancy
Single-user, single-GitHub-identity per run (per Interview: v1 scope is
one account's own activity, not org-wide). The Fulcra account the
records are written to is whichever account the skill's Fulcra
credentials belong to — same single-tenant-per-run model as
flow-state-v2.

## Key architectural risks to validate during Prototype (not resolved
here — this becomes the Plan phase's spike list)
1. Whether `contributionsCollection`'s per-repository breakdown is
   sufficient to detect "notability" signals like project/focus switches
   without needing to enumerate individual commits for older periods.
2. Real LLM call count/cost for a full 3-year backfill against the
   decaying-granularity numbers estimated during Interview (~90 daily +
   ~13 weekly + ~33 monthly + quarter/year + one narrative pass) — this
   was an estimate, not a measurement.
3. Whether the resumable backfill checkpoint design genuinely survives a
   real kill-and-restart from a fresh process (this needs a real,
   demoable test, not just code that looks resumable).
4. Whether GraphQL's `contributionsCollection` has any practical limits
   on how far back `from`/`to` can query — **validated live during this
   Architecture pass**: queried a real public account's activity for a
   month over 3 years in the past (Jan 2021) and got real non-zero
   commit/PR counts back with no error or truncation. Not exhaustively
   tested (e.g. exact API-documented limits, behavior at 5+ years), but
   this specific risk — "can we even query 3 years back at all" — is
   resolved: yes.
