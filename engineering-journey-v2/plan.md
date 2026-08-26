# Plan: Engineering Journey v2

**Sequencing philosophy:** Two genuinely unproven design bets exist in
this rebuild (identified explicitly during Architecture review, not
carried over from any prior project): (1) uniform daily-granularity raw
ingestion across a multi-year range, at real scale, and (2)
harness-side/agent-driven LLM summarization instead of a bundled
provider script. Both get spiked early, before any real backfill volume
is committed to, because every later milestone (rollups, notability,
narrative) depends on the raw layer and the summarization mechanism
being real and working, not just designed on paper. Resumable
checkpointing is the third foundational risk (same reasoning any
backfill-shaped project would apply) and is proven in isolation before
real GitHub data touches it.

## Milestone 1: Resumable backfill checkpoint, proven in isolation
Build the "GitHub Backfill Checkpoint" Fulcra record type and
read/write-checkpoint functions, tested against FAKE work items (not
real GitHub data) -- process items 1 through N, kill the process
partway through, restart from a fresh process, confirm correct resume
without reprocessing or skipping. Also proves the per-repo tag-based
tracking design (Architecture's `repo` tag on this type) actually
supports the "detect which repos are already covered when extending
backward/forward" requirement from Intake, using fake repo names before
any real GitHub enumeration exists. No GitHub API calls in this
milestone.

## Milestone 2: GitHub API spike -- existence pre-check and per-item ingestion shape
A real, live spike (not yet wired into the checkpoint or Fulcra writes)
against a real GitHub account: determine and verify the concrete
endpoint(s) for (a) the existence pre-check ("does this repo have any
activity from this user, ever, in this window" cheaply) and (b) per-item
retrieval for each activity type in scope (commits, PR opens/merges, PR
reviews, issue/PR comments). This is explicitly a research spike with a
written-down verified answer, not assumed API knowledge -- the
Architecture doc left this open on purpose. Also spike whether the
`agg/day` Fulcra endpoint is fast/cheap enough to serve as a
corroborating or primary existence-check signal once some data already
exists (per Architecture's open item), though this can't be tested until
after Milestone 3 writes real records.

## Milestone 3: Real raw ingestion -- one repo, real Fulcra writes
Using Milestone 2's verified endpoints, ingest one real, bounded window
(e.g. one real recent month) of one real repo's activity into "GitHub
Activity Raw" records -- real per-item records, real tags
(`activity_type`, `repo`, `github_identity`), real `sources`, real
event-time `recorded_at`. Wire this into Milestone 1's checkpoint
mechanism (checkpointing by repo, per Architecture). Validates the
schema decisions from Architecture against real data before scaling up.

## Milestone 4: Full multi-repo, multi-year backfill at real scale
Extend Milestone 3 to the real multi-repo, multi-year case: real repo
enumeration (public + private, contributed-to only) using the real
account context from Intake (multiple orgs, hundreds of associated
repos, real existence-pre-check payoff), uniform daily-granularity
ingestion across a real multi-year window, and genuine
kill-mid-backfill/resume-from-fresh-session validation at this real
scale -- not just Milestone 1's fake-item version. Also where the
uniform-daily-granularity volume/cost tradeoff (flagged as an unproven
bet during Architecture review) gets measured for real: how many raw
records, how long, how many API calls for a real 1/2/3-year window
against this specific test account.

## Milestone 5: Backward/forward extension
Prove the "extend an existing backfill without redoing completed work"
requirement from Intake, in both directions: run a real backfill for a
bounded window, then extend it further into the past, then separately
extend it to pick up newer activity -- confirming via checkpoint state
that neither direction reprocesses or duplicates already-covered
ranges/repos.

## Milestone 6: Rollup layer -- day through year, real hand-rolled aggregation
Build "Activity Rollup" generation for all five period types (day, week,
month, quarter, year) reading real "GitHub Activity Raw" records over a
range, per Architecture's confirmed constraint that rollup content
aggregation (per-activity-type counts, per-repo breakdowns) is
hand-rolled, not delegated to any Fulcra aggregation endpoint. Real
provenance chains (`sources` referencing the raw/lower-layer record IDs
actually read). Numeric aggregation only in this milestone -- no model
call yet; the `note` summary-text field is left for Milestone 7.

## Milestone 7: Harness-side rollup summarization -- the LLM-usage spike
This is the second major unproven bet from Architecture: prove
concretely what "the model already running the skill performs the
summarization step" looks like as an actual mechanism, not just a
sentence in architecture.md. Spike this against a handful of real
rollup periods from Milestone 6 before treating it as a solved pattern:
what does a task prompt asking an agent to "summarize this period and
write it back" actually look like, how is the structured input (counts,
activity breakdown) handed to that step, and how does the resulting text
get back into the real "Activity Rollup" record's `note` field via a
deterministic write call. Validate that this genuinely doesn't require a
bundled provider API key anywhere in the path.

## Milestone 8: Notability signal (first pass)
Implement a first-pass notability/eventfulness formula (volume vs.
personal baseline, firsts, focus switches, streaks/gaps -- concrete
formula decided here, not assumed from Architecture) as "Notability
Signal" records (`NumericAnnotation`, `value` = score, `note` =
baseline-comparison detail, per Architecture). Explicitly a first pass,
expected to be revisable independently of ingestion/rollup logic since
it's its own record type.

## Milestone 9: Narrative generation -- markdown output
Build the generation-time flow: ask the user for the desired range
(full history or a sub-range), read the relevant "Activity Rollup" +
"Notability Signal" records for that range, and produce one paced
markdown document (notable periods get real narrative space, quiet ones
get compressed) with a provenance appendix, naming the output file
according to the chosen range. Uses the same harness-side
model-invocation mechanism proven in Milestone 7. Validate by actually
reading a real generated document end to end, not just confirming a
file was produced.

## Milestone 10: Packaging as an installable, agent-agnostic skill
Package the above into the actual deliverable shape locked in during
Intake: a root-level `SKILL.md` (sibling to `harness/` and `app/`) that
a fresh agent session can be pointed at directly, plus a README and a
directly-runnable `app/` CLI that works the same with or without an
agent involved. Validate the concrete first-usage test from Intake: a
genuinely fresh environment, agent installed, pointed at this repo,
"I want to try this skill out," with no other setup assumed --
including the GitHub device-code auth walkthrough (with the
already-logged-in-`gh`-session confirmation step from Intake) and
Fulcra auth.

## Deferred / explicitly out of scope for this Plan
Everything under "Explicitly NOT in scope for this v1 rebuild" in the
Intake brief (multi-identity single-run ingestion, rollup
recomputation, resume-overview/dashboard generation, a bundled LLM
provider) stays deferred -- not represented as milestones here, and not
picked up opportunistically mid-build without deliberately revisiting
scope first.
