# Intake Brief: Engineering Journey v2

## Stated goal
Ingest a user-provided number of years of a developer's GitHub activity
(from their own authenticated account) into Fulcra as durable, queryable
records, and support turning that raw activity into different kinds of
readable output — a paced narrative "story," a resume-style overview
blurb, or the data backing a future custom dashboard. This is a ground-up
rebuild, not an iteration on any prior implementation: no existing
codebase, prior architecture, or prior lessons-learned are being carried
forward into this brief or into any later phase of this engagement.

## What "done" looks like for v1 of this rebuild
1. Given one authenticated GitHub identity, backfill a user-specified
   number of years of that account's activity across all public and
   private repositories they have contributed to — not just repos they
   own, and not just repos they've pushed commits to. "Contributed to"
   is intentionally broad: commits, PR opens/merges, PR reviews, and
   issue/PR comments/discussion all count.
2. Before doing any real per-period ingestion work for a given repo, run
   a cheap existence pre-check confirming the authenticated user has
   *any* real activity in that repo across the entire requested
   timeframe. Do not assume every repo associated with the user (e.g.
   via org membership) actually has activity worth fetching — verify it
   first. This matters concretely: a user may belong to orgs with 500+
   repos while having only ever touched a handful of them, and the
   backfill must not spend hundreds/thousands of wasted API calls
   discovering that the hard way, one bucket at a time, per repo.
3. Store raw activity as durable Fulcra records at a uniform daily
   granularity across the entire requested range (no decaying/coarser
   granularity for older history in this rebuild). Every record
   explicitly captures its activity type (commit, PR opened, PR merged,
   PR review, issue/PR comment, etc.) as a real, filterable dimension —
   not folded into an opaque blob — so later consumers can slice by
   activity type.
4. The backfill must be extensible in both directions after an initial
   run completes, without redoing already-ingested work:
   - Backward: later extend an existing backfill further into the past
     than it originally covered.
   - Forward: later extend an existing backfill to pick up newer
     activity that occurred after the original run.
5. The backfill must be safely interruptible and resumable — a real
   hard requirement, not a nice-to-have, given multi-year/multi-repo
   runs can legitimately take a long time. A durable progress marker
   stored in Fulcra (not local/in-memory state) must allow a killed
   process to resume, from a completely fresh session, exactly where it
   left off, without re-doing completed work or losing progress.
6. Build a layered rollup structure on top of the raw daily records:
   day, week, month, quarter, and year rollups, each a precomputed,
   durable Fulcra record (not computed fresh at read time) that any
   consumer can query directly. Because the raw layer is uniform daily
   granularity, rollups at any interval should be straightforward to
   derive from it. (Explicitly deferred, not in scope for this build:
   a "recompute an existing rollup" feature — worth keeping the schema
   from actively blocking it, but not building it now.)
7. Compute a "notability"/eventfulness signal per rollup period, stored
   as its own derived, attributed record — the concrete formula is an
   Architecture-phase decision, not fixed here in Intake.
8. Ship a lightweight markdown narrative generator as part of this same
   skill/project (its own module/layer, not entangled with ingestion
   logic) that reads the stored rollups/signals and produces a
   readable markdown document. At generation time, the tool asks the
   user what range they want covered (the full ingested history, or a
   sub-range/specific period), and names the output file accordingly.
   Richer output types (a resume-overview generator, an interactive
   dashboard) are explicitly deferred to a separate, future consumer
   project that would read the same Fulcra records — not built here.

## Explicitly NOT in scope for this v1 rebuild
- Decaying/coarser granularity for older history — this rebuild uses
  uniform daily granularity for raw records across the whole requested
  range, a deliberate change from how a similarly-scoped prior concept
  might have approached it.
- Ingesting multiple GitHub identities into one combined backfill run.
  v1 ingestion targets exactly one GitHub identity per run. If/when
  multi-identity "combined journey" support is tackled, the intended
  approach is merging separately-ingested record sets together after
  the fact, not one ingestion process juggling multiple identities at
  once — Architecture should make sure the schema doesn't actively
  block this later approach, without building the merge tooling now.
- A "recompute an existing rollup" feature.
- Resume-overview generation, interactive dashboards, or any other
  richer output format beyond the lightweight markdown narrative — these
  are explicitly future, separate-project work consuming the same
  underlying Fulcra records.
- Any LLM involvement in the ingestion/backfill/rollup-aggregation math
  itself. That path is fully deterministic (GitHub API calls, existence
  pre-checks, raw record writes, rollup aggregation). The model is only
  invoked for rollup summary text and narrative generation.
- A dedicated/bundled LLM provider integration (e.g. a Gemini API key
  requirement). The explicit preference is for rollup-summary and
  narrative-generation steps to use whatever model is already running
  the skill at that point in the flow, rather than the project shipping
  its own separate provider/API-key dependency. Architecture must work
  out concretely what this means for how those steps are invoked (e.g.
  as agent-harness-side steps the running model performs as part of a
  task, versus a standalone script calling out to a model API on its
  own) — this is a real, deliberate divergence worth calling out
  clearly, not a detail to gloss over.

## GitHub authentication
Default to the browser-based OAuth device-code flow for authenticating
the GitHub identity whose activity will be backfilled. If a `gh` CLI
session (or other pre-existing GitHub auth) is already present, do not
silently assume it's the right account — confirm with the user
explicitly before using it, since the account driving a multi-year
journey backfill may differ from whatever happens to be locally logged
in.

## Multi-year test account context (for Architecture/Prototype planning)
Real live testing will use a different, real, long-lived personal GitHub
account (roughly 10 years of history, multiple org memberships, "at
least hundreds" of repos by org association though not owned/actively
contributed to by the account) — not the account used for hosting this
project's own repository. Test runs will be bounded to 1/2/3-year
windows for iteration speed rather than backfilling the full ~10 years
during Prototype/Build. This account is a genuinely useful real-world
case for validating the existence-pre-check requirement (many
org-associated repos with zero real activity from this user) rather
than a synthetic/hypothetical scenario.

## Data scope
All GitHub activity types tied to the authenticated user's own
contributions: commits, pull requests (opened/merged), PR reviews, and
issue/PR discussion (comments). Explicitly out of scope: GitHub
Actions/CI run activity, gists, wikis, and project-board (Projects)
activity — confirmed as a deliberate boundary, not an oversight.

## Delivery format
Primary shipped output for this project is the lightweight markdown
narrative generator described above. The underlying Fulcra record
structure is the actual deliverable of lasting value — designed to be
generically queryable/sliceable enough that a resume-overview generator
or a custom interactive dashboard could be built as separate future
projects consuming the same records, without needing to touch or
re-ingest anything.

The project itself must be packaged as an installable agent skill in
the same repo the build harness writes to (not a separate repo) —
concretely, a root-level `SKILL.md` (sibling to `harness/` and `app/`)
that a fresh agent session can be pointed at directly (a repo URL or
local path) and follow as the actual skill definition: walking a user
through GitHub/Fulcra authentication, then running the `backfill` and
`generate` entrypoints against `app/`. This is the same pattern
`fulcra-rapid-prototype`'s own `SKILL.md` already documents ("if you
were pointed directly at this repo... this file IS the skill
definition") and the same shape a similarly-scoped prior concept
apparently used (a root-level `SKILL.md` alongside its implementation
and build-harness directories) — not a new convention being invented
here. The `SKILL.md` is a thin instructional wrapper for agent-driven
usage, not a hard runtime dependency: `app/`'s actual CLI must remain a
normal, directly runnable tool (callable by a human with no agent
involved at all) that works the same way regardless of which agent
platform is following the `SKILL.md`, or whether an agent is involved
at all. Nothing about the underlying functionality (GitHub backfill,
Fulcra records, rollups, narrative generation) should assume Hermes
specifically, or any other particular agent runtime — Hermes is simply
the first, concrete environment this will be exercised in. Explicitly
separate from the *build* harness's own SKILL.md (the
`fulcra-rapid-prototype`/`fulcra-prototype-grill-me` skills used to
build this project) — those are build-time tooling, not what an end
user installs to run their own journey backfill. The concrete
first-usage test this must support: spin up a fresh VM, install an
agent runtime (Hermes, for this first test), point it at this
project's repo, and say "I want to try this skill out" — with no other
setup already assumed.

## Process note (why this brief exists in a fresh, isolated context)
This Intake was run as a deliberate ground-up restart: the user
explicitly asked that no prior implementation, architecture, or
lessons-learned be referenced, reused, or allowed to bias any decision
in this engagement, and that this brief and every later phase be
treated as if no prior related project exists. No content, terminology,
or design decisions from any prior project were carried into this
document.
