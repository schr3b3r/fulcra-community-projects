# Interview Findings: Engineering Journey

These are working assumptions made to keep momentum, not settled
requirements — flag any of these as wrong and they get revised before
(or during) Architecture with no cost, since nothing has been built yet.

## 1. Backfill window boundary (recent vs. decayed granularity)
**Decision:** last **90 days** get daily-then-weekly rollup treatment
(same shape a live/ongoing system would use). Everything older than 90
days is summarized directly at **monthly** granularity (skipping the
weekly layer entirely for old history, not just skipping daily) — a
3-year backfill produces roughly 3 months of dailies/weeklies plus ~33
months of monthly summaries, which keeps both the record count and LLM
call count reasonable while still preserving genuine texture for the
period closest to "now" (which is usually also the period the reader
cares most about, since it's most recent/relevant to who they are today).
Quarter/year rollups still get built on top of the monthly layer for
everything older than 90 days, and on top of weekly for the recent
window — so the top of the pyramid is uniform even though the base
granularity differs by age. This is exactly the "decaying granularity"
mechanism from the brief, now with concrete numbers.

## 2. Multi-repo / multi-org / visibility scope
**Decision:** v1 scope is **all repos the account has contributed to**
(not just owned repos) that are **visible to the provided token** —
meaning private repo activity IS included if the token has access to it,
since a lot of real engineering work happens in private/employer repos
and excluding it would make the "journey" hollow for most working
engineers. No org-level filtering in v1 (no "only these orgs" allowlist)
— that's a reasonable fast-follow if noise becomes a real problem in
practice, but adding it up front is speculative complexity without having
seen real output yet.

## 3. Sparse/bursty histories (career breaks, short history, etc.)
**Decision:** gaps and breaks are treated as **real, narratively
significant data**, not noise to compress away — a multi-month gap in
an otherwise-active history IS the kind of "notability" signal described
in the brief (a long gap is explicitly called out there already) and the
narrative pass should be free to name it as a gap/pause rather than
silently skip over it. If the account has less than 3 years of history
(e.g. someone earlier in their career), the tool should simply cover
whatever history actually exists rather than erroring or padding —
"your journey so far," not "your journey, forced into a fixed template."

## 4. Idempotency / re-runs
**Decision:** v1 is a **one-shot tool**: run it, get a journey document
covering everything ingested up to that point. Re-running is NOT
required to be smart about "only ingest what's new since last time" for
v1 — however, because the underlying architecture is built on durable,
resumable ingestion by construction (the whole point of the Resumable
Discovery pattern), extending this to "top up and regenerate" later
should be a small addition, not a redesign. This is explicitly deferred,
not designed against.

## 5. LLM cost / call-count / runtime tolerance
**Decision:** "however long it takes, run it once" is acceptable for v1
— this is a showcase/reference build, not a product with SLAs, and a
retrospective tool is inherently an occasional-use, not a
low-latency-critical one. That said, the decaying-granularity decision
above (90-day daily/weekly cutoff, monthly beyond that, skipping weekly
entirely for old history) was chosen specifically to keep the total
LLM-call count for a 3-year backfill in a reasonable range (roughly:
~90 daily + ~13 weekly + ~33 monthly + a handful of quarter/year rollups
+ one final narrative pass — call counts to be validated for real during
Prototype, not assumed correct here).

## Not resolved here, deliberately deferred to Architecture
- Exact GitHub API surface for historical ingestion (Search API vs.
  GraphQL vs. REST, and how commit authorship/repo enumeration actually
  works at the account level) — this is squarely an Architecture-phase
  concern (map to Fulcra + GitHub capabilities), not an Interview one.
- Exact custom Fulcra data type shapes for each layer (raw activity, day,
  week, month, quarter/year, notability signal) — Architecture phase.
- Exact notability-signal formula — the user explicitly wants to try
  several passes and see what feels best; Architecture should design for
  this being iterated on (e.g. keep the signal computation as its own
  swappable step), not lock in one formula.
