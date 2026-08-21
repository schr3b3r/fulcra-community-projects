# Intake Brief: Engineering Journey

## Stated goal
Build a Hermes skill that ingests a developer's GitHub activity history
(commits, PRs, PR reviews, PR/issue discussion) going back approximately
3 years, and produces a single, well-formatted, engaging markdown
document telling the story of their engineering journey over that
period — something they could read for themselves, or share with others,
that captures how their work/focus/scope evolved over time.

This is explicitly a showcase/reference project: the point is to
demonstrate Fulcra's value as a durable, owner-scoped context backend for
an agent-built tool, not just to produce a nice document. The
architecture should make deliberate, visible use of Fulcra's primitives
(durable records, custom annotation types, layered derived context) —
see "Why Fulcra, specifically" below.

## What "done" looks like for v1
A Hermes skill (installable, not a one-off script) that:
1. Given a GitHub identity (see "GitHub authentication" below), backfills
   ~3 years of that account's activity into Fulcra as durable records.
2. Builds a layered rollup structure on top of the raw activity: recent
   history (last ~30-90 days) is summarized at daily granularity; older
   history is summarized directly at a coarser bucket (weekly or
   monthly) without ever materializing individual days for that older
   period. See "Decaying granularity" below for the reasoning.
3. Computes a "notability" signal for each rollup period (see "Notability
   signal" below) — a cheap, derived measure of how eventful that period
   was relative to the person's own baseline, used to drive pacing in the
   final narrative (linger on eventful periods, compress quiet ones).
4. Generates a single markdown document — the "journey" — that reads like
   a paced narrative, not a flat list of digests: quarters/years with
   real signal get real narrative space; quiet stretches get a sentence
   or a clause, not padding.
5. Is resumable at every stage: the backfill in particular is a
   long-running, potentially interruptible job (could be pulling 3 years
   across many repos) and must be safely restartable from a completely
   fresh process/session, picking up exactly where it left off, using a
   durable progress marker stored in Fulcra — not in-memory or local-file
   state. This should be demonstrably testable (kill the process
   mid-backfill, restart from scratch, confirm it resumes correctly
   rather than re-doing already-completed work or losing progress).

## Explicitly NOT in scope for v1
- No web app, no hosting, no UI beyond the generated markdown file itself.
- No video/animation/interactive-timeline output — markdown only.
- No "share this publicly via a hosted link" mechanism — the shareability
  requirement is satisfied by producing a well-formatted, portable
  markdown file a person can send/post themselves.
- No ongoing daily/weekly digest delivery (no cron, no chat delivery) —
  this is a point-in-time retrospective tool, not a running habit
  tracker. (A future pass could add ongoing digests reusing the same
  underlying layered structure, but that's explicitly out of scope here.)
- No org-wide analysis — scoped to a single developer's own account/
  activity for v1.

## GitHub authentication (a real, explicit requirement — not an
implementation detail to figure out later)
The skill MUST accept a GitHub identity (username + token, or an
equivalent auth mechanism) as configurable input at runtime — it must
NOT assume or hardcode "whichever GitHub account this machine's `gh` CLI
happens to be logged into." This matters because the skill is meant to
be installed and run by other people against their own GitHub accounts,
on their own machines, potentially with `gh` authenticated as a
completely different identity than the one whose journey they want to
generate (this was raised explicitly during intake, since the initial
build environment's `gh` session is authenticated as a different account
than the one intended for actual testing).

## Decaying granularity (backfill strategy)
1-2+ years of daily-granularity digests is both expensive (LLM calls) and
mostly uninteresting (nobody cares about a specific unremarkable
Tuesday from 14 months ago). Recent history (last ~30-90 days, exact
window TBD during Architecture) gets real daily-then-weekly rollups, same
as an ongoing/live-tracking system would produce. Everything older than
that window is summarized directly at a coarser bucket (weekly or
monthly — TBD during Architecture) without an intermediate daily layer
ever being materialized for that older period. This mirrors how memory/
narrative actually compresses over distance and is also the practical
answer to backfill cost/time.

## Layered rollup structure (the core "why Fulcra" architecture)
Raw activity (commits/PRs/reviews/comments) -> day (recent window only)
-> week -> quarter/year, each layer a real, durable, attributed Fulcra
record built FROM the layer below it (not recomputed from raw source
each time it's needed). This is deliberate: the demo/showcase value is
being able to point at any period in the final narrative and trace it
back down through real stored intermediate records to the actual
commits/PRs that produced it — genuine derived-context provenance, not
just "an LLM summarized some GitHub data once."

## Notability signal
Every rollup period gets a cheap, computed "how eventful was this"
signal, used later to drive narrative pacing. Starting hypothesis
(explicitly to be iterated on — the user wants to try several passes and
see what feels best, not commit to one formula up front):
- Activity volume/variance relative to that person's own historical
  baseline (not an absolute threshold — a quiet-by-nature contributor's
  "busy" period looks different from a high-volume contributor's).
- Detected "firsts" (first commit in a new language/repo/org, first
  merged PR, first solo-owned project).
- Detected project/repo/focus switches.
- Long streaks or long gaps.
This signal itself should be stored as its own derived-context record
(attributed, referencing what it was computed from), not just an
in-memory number used once and discarded — consistent with the rest of
the architecture.

## Narrative generation
A final pass reads the full layered structure (which periods are
notable, what happened in them, what the quiet stretches were) and
writes ONE cohesive markdown document with real pacing: notable periods
get genuine narrative treatment, quiet ones are glossed over quickly.
This is an LLM doing what LLMs are good at (reading structured,
already-synthesized data and making pacing/emphasis decisions) — it is
NOT expected to invent facts; every claim in the narrative should be
traceable back to real underlying records.

## Data scope
All GitHub activity types: commits, pull requests (opened/merged/
reviewed), and PR/issue discussion (comments). Richer signal than
commits alone, more representative of the actual shape of someone's
contribution over time (a lot of senior engineering work shows up in
reviews and discussion, not just commits).

## Delivery format
A single markdown file, well-formatted, meant to be genuinely enjoyable
to read — not a bulleted digest dump. This is explicitly the intended
personality of the output: "fun and easy for others to read," per the
user directly.

## Why Fulcra, specifically (for the Architecture phase to build on)
This project is a deliberate showcase of:
- **Context-Compute Separation**: the entire layered structure (raw
  activity through to quarter/year rollups and notability signals)
  outlives any single agent process/session. The narrative-generation
  pass should be re-runnable from a fresh session against already-built
  Fulcra state without needing to re-ingest anything.
- **Resumable Discovery**: the backfill's durable progress marker is the
  literal mechanism, and should be demoable as such (kill mid-backfill,
  resume cleanly from a new process).
- **Derived Context**: every rollup layer and the notability signal are
  attributed conclusions referencing the observations they came from,
  not opaque final outputs — a defining, checkable property of this
  build, not just a nice-to-have.

## Background: how this idea evolved (for provenance/context, not a
requirement)
This idea is a generalization of an earlier prototype ("Flow State" — an
audio-marker-triggered musical-idea capture tool) that used the same
underlying shape (continuous stream -> bounded extraction -> light
enrichment -> durable, queryable record -> a feed that shows the
extraction in context) but was judged too narrow an audience (musicians).
Several intermediate ideas (marker-tagged GitHub commits/PRs, daily/
weekly developer activity digests) were explored and discarded in favor
of this retrospective/narrative framing, which needs no behavior change
from the user (no "remember to tag this" friction) and produces a more
compelling, ownable artifact (a personal narrative) than a recurring
digest would.
