# Plan: Engineering Journey

**Sequencing philosophy:** Resumable backfill checkpointing is both the
riskiest unproven piece (Architecture risk #3) and the mechanism
everything else depends on — if it's wrong, every layer built on top
inherits the mistake. It goes first, proven in isolation with a real
kill/restart test, before any real GitHub data ingestion or rollup logic
is built on top of it. This mirrors how flow-state-v2 was built: prove
the foundational plumbing (WebSocket streaming, in that case) end-to-end
before layering DSP/publishing logic on top of it.

Milestones below are also the harness's task-by-task build sequence —
each one is scoped to be a single harness task (see
fulcra-agent-harness-starter's SKILL.md step 4: the first task prompt is
generated from this plan's first milestone).

## Milestone 1: Resumable backfill checkpoint, proven in isolation
Build the `GitHubBackfillProgress` Fulcra record type and the
read-checkpoint / write-checkpoint functions around it, tested against
FAKE work items (not real GitHub data yet) — e.g. "process items 1
through 100," kill the process at item 47, restart from a fresh process,
confirm it resumes at 48 and doesn't reprocess 1-47 or skip anything.
This directly and literally tests Architecture risk #3 before anything
else is built on top of it. No GitHub API calls in this milestone at all
— pure Fulcra checkpoint plumbing, kept deliberately decoupled from what
it will eventually checkpoint.

## Milestone 2: GitHub ingestion — raw activity, real API calls
Build the actual GitHub client (GraphQL `contributionsCollection` for
volume/breakdown, REST Search API for content), accepting a
username+token as runtime config (per the Interview auth requirement —
verify this explicitly: run it with a token for an account other than
whatever `gh` is locally authenticated as, and confirm it works).
Ingest raw activity for a small, real, bounded window (e.g. one real
month of one real account) into `GitHubActivityRaw` records. Wire this
INTO the Milestone 1 checkpoint mechanism (checkpointing by repo+date-
range), rather than building ingestion standalone and integrating later.

## Milestone 3: Full 3-year backfill, with the real resumability demo
Extend Milestone 2 to actually walk the full ~3-year window across all
repos the account has contributed to, using the decaying-granularity
boundary from Interview (real API calls, real checkpointing, real
multi-repo enumeration). This is where the "kill it mid-backfill,
resume from a fresh session" demo becomes real and end-to-end, not just
the isolated Milestone 1 version — validate it as such (actually kill a
real backfill run partway through, actually restart it, confirm correct
resumption) before calling this milestone done. Also where Architecture
risk #2 (real LLM/API call counts and runtime for a real 3-year pull)
gets measured for real, not estimated.

## Milestone 4: Rollup layer — day/week (recent 90 days)
Build the `ActivityRollup` (`period_type=day`/`week`) generation logic
for the recent-90-day window: read raw activity for a period, produce an
LLM-summarized rollup record that references the raw records it was
built from (the provenance requirement from Architecture/the brief).
Testable independently of the 3-year backfill by running against
whatever raw data Milestone 2/3 already ingested for a real recent
window.

## Milestone 5: Rollup layer — month (older history) + quarter/year (both)
Build the `period_type=month` rollup for history older than 90 days
(skipping the weekly layer per the Interview decision), and the
`period_type=quarter`/`year` rollups that sit on top of BOTH the
recent (week-based) and older (month-based) layers — same output shape,
different lower-layer inputs. This is the piece that makes the "uniform
top of the pyramid, differently-grained base" design from Interview
concrete and testable.

## Milestone 6: Notability signal (first pass)
Implement the notability signal from Architecture/Interview (activity
volume/variance vs. personal baseline, detected firsts/switches,
streaks/gaps) as its own `NotabilitySignal` record type, computed per
rollup period and referencing what it was computed from. Explicitly
scoped as "first pass, expected to be revised" per the Interview
decision to try several formulas — keep this step isolated/swappable
(mirrors how flow-state-v2's marker-detection was explicitly built
behind a swappable interface) so trying a second or third formula later
doesn't require touching ingestion or rollup logic.

## Milestone 7: Narrative generation — the final markdown output
Build the pass that reads the full layered structure (all rollup levels
+ notability signals) and generates the single paced markdown document:
notable periods get real narrative space, quiet ones get a clause. This
is the actual deliverable from the user's perspective — validate it by
actually reading the generated output for a real account's real history,
not just confirming it produced *some* markdown file.

## Milestone 8: Packaging as an installable Hermes skill
Wrap the above into an actual SKILL.md + supporting scripts, following
the same "skill, not raw script" bar as fulcra-agent-harness-starter
itself — installation instructions, clear entrypoint(s) (e.g. "run
backfill," "generate journey from already-ingested data" as a separate,
faster re-runnable step per Architecture's Context-Compute Separation
point), and a README a stranger could follow.

## Milestone 9: Migrate to real custom Fulcra data types
Added after real fresh-account test feedback surfaced that every
persistence path in this codebase (raw activity, rollups, notability
signals, backfill checkpoints) writes to the generic built-in
`MomentAnnotation` type, with the actual semantic type hidden as a
`"record_type"` string key inside the JSON `note` blob — not a real,
registered Fulcra data type. This directly contradicts this project's
own "why Fulcra, specifically" rationale in `intake/brief.md` (custom
annotation types as a deliberate, visible primitive). Create one real
custom data type per record kind (`GitHubBackfillProgress`,
`GitHubActivityRaw`, `ActivityRollup`, `NotabilitySignal`), and change
every write/read function to use the confirmed real mechanism (see
`app/CONTEXT.md`'s "Custom annotation data types" SDK usage note) —
write to the base type with a `sources` tag identifying the custom
type's UUID, read back filtered by that same `source`. Existing
already-written records (plain `MomentAnnotation`, no source tag)
should remain readable for backward compatibility during the
transition, not silently orphaned.

## Milestone 10: Fix private repo discovery
Corrected scope after independently re-verifying the original live-test
report against 3 real private repos in a real account (see
`app/CONTEXT.md`'s Decisions Log for the full re-verification writeup):
the actual confirmed gap is that `GitHubClient.enumerate_repositories()`
relies entirely on GraphQL `contributionsCollection`, which genuinely
misses real private repos with real contributions -- NOT that the REST
Search API can't see private repo content (confirmed directly that it
can, for both commits and issues, given a normal `repo`-scoped PAT).
Fix: add an explicit `GET /user/repos?affiliation=owner,collaborator,
organization_member` listing pass, unioned with `contributionsCollection`'s
results, filtered to repos whose `pushed_at` falls in the requested
window. This is the single change needed so a real account's private
work is actually discovered and backfilled -- no rewrite of the
fetch layer, since it already works correctly once repos are found.

## Milestone 11: Fix stale checkpoints masking improved discovery
A second real fresh-account test (GitHub user with ~90+ private repos)
found that Milestone 10's private-repo discovery fix, while correct in
isolation, is unreachable via the documented `backfill` CLI path in
practice: `backfill_full_github_activity`'s checkpoint `task_id`
depends only on username + date range, never on which repos were
actually discovered, so a `"completed"` checkpoint from an EARLIER,
narrower backfill (e.g. run before Milestone 10's fix, or before the
user had access to new repos) silently short-circuits every later
backfill attempt for the same username+range -- even one using improved
discovery logic -- with no warning that the "completed" result only
ever covered a fraction of the real repo set. Since `write_raw_activities`
has no deduplication, the fix must be delta-aware, not a blind
reprocess: store the actual discovered repo list (not just a count) in
checkpoint metadata, detect when a fresh discovery finds repos the old
checkpoint didn't cover, and run a distinctly-tracked delta backfill for
only those new repos -- never reprocessing repos already covered. See
`app/CONTEXT.md`'s Decisions Log for the full diagnosis and planned fix
direction. Add a real live integration test exercising this exact
"stale narrower checkpoint, then expanded real repo set" scenario end
to end, not just a unit test of `enumerate_repositories()` in isolation
(which already passed and didn't catch this).

## Deferred / explicitly out of scope for this Plan
Everything under "Explicitly NOT in scope for v1" in the Intake brief
(web app, hosting, video/interactive output, ongoing digest delivery,
org-wide analysis, smart incremental re-runs) stays deferred — not
represented as milestones here, and not to be picked up opportunistically
mid-build without deliberately revisiting scope first.

One further real gap surfaced by the first live fresh-account test
(tracked, not yet scoped as a milestone here — pick up deliberately, not
opportunistically): the GitHub auth device-code flow was added to
`SKILL.md` (see Decisions Log) but its actual smoothness in practice on
a genuinely fresh machine is still only doc-reviewed, not yet
live-verified end to end.

