# Plan: Engineering Journey

## Sequencing philosophy
Resumable backfill checkpointing is both the riskiest unproven piece
(Architecture risk #3) and the mechanism everything else depends on — if
it's wrong, every layer built on top inherits the mistake. It goes first,
proven in isolation with a real kill/restart test, before any real
GitHub data ingestion or rollup logic is built on top of it. This mirrors
how flow-state-v2 was built: prove the foundational plumbing (WebSocket
streaming, in that case) end-to-end before layering DSP/publishing logic
on top of it.

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

## Deferred / explicitly out of scope for this Plan
Everything under "Explicitly NOT in scope for v1" in the Intake brief
(web app, hosting, video/interactive output, ongoing digest delivery,
org-wide analysis, smart incremental re-runs) stays deferred — not
represented as milestones here, and not to be picked up opportunistically
mid-build without deliberately revisiting scope first.
