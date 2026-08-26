# Architecture: Engineering Journey v2

## Summary
A ground-up rebuild (see `intake/brief.md` for full scope) that backfills
a user-specified span of one GitHub identity's activity (all contribution
types, public and private repos) into Fulcra as durable, per-item, real
custom-typed records; builds precomputed day/week/month/quarter/year
rollups and a per-period notability signal on top; and ships a lightweight
markdown narrative generator reading that structure. Ingestion/rollup math
is fully deterministic; only rollup-summary text and narrative generation
invoke a model, and only whatever model is already running the skill --
no bundled LLM provider dependency.

## Capability map: what exists vs. what's a gap

### GitHub (data source)
No live GitHub API verification has been done yet in this engagement
(that is Prototype-phase work, not Architecture) -- this section records
only the ingestion-shape decisions made during Intake:
- Scope: commits, PR opens/merges, PR reviews, issue/PR comments across
  all public and private repos the authenticated identity has
  contributed to (not just owned repos). GitHub Actions/CI, gists,
  wikis, and project-board activity are explicitly out of scope.
- Existence pre-check requirement: before any per-period ingestion for a
  given repo, a cheap check must confirm the identity has *any* real
  activity in that repo across the whole requested range. This is a
  GitHub-API-side concern (which endpoint cheaply answers "any activity
  from user X in repo Y, ever, in this window") to be resolved as a
  Plan-phase spike, not decided here.
- Auth: browser-based OAuth device-code flow by default; if a `gh`
  CLI session or other GitHub auth already exists locally, confirm with
  the user it's the intended identity rather than assuming it.

### Fulcra (durable storage + queryable index) -- verified live
Checked the real, live catalog for this account (`fulcra catalog`,
matching on `name`/`description`, not `id` -- see the note at the end of
this section) before assuming a gap: no existing Fulcra data type covers
developer/GitHub activity. The closest primitives are the generic
annotation base types. This requires custom data types.

**Real, verified platform constraints that shape the schema below (not
assumptions):**
- Every custom annotation type has one of two fixed record shapes
  depending on its base type. Event-class types (`MomentAnnotation`,
  `DurationAnnotation`) get exactly `id`, `tags` (array of tag UUIDs),
  `sources` (array of strings), `recorded_at` (a single instant for
  `MomentAnnotation`; a `{start_time, end_time}` range for
  `DurationAnnotation`), and `note` (a single free-text string) -- no
  mechanism to define additional structured/typed fields beyond those.
  Metric-class types (`NumericAnnotation`, `ScaleAnnotation`,
  `BooleanAnnotation`) get that same base set PLUS a real, required
  `value` field (a number) and an optional `unit` string -- confirmed
  live via `fulcra data-type schema` against real disposable custom
  types of each kind. This distinction matters: it means a genuinely
  scalar piece of data (see "Notability Signal" below) has a real,
  non-`note` home, while multi-dimensional/free-text data does not and
  must still go through tags + `note`.
- Given that constraint, the schema principle for this project is:
  **anything meaningfully filterable/groupable becomes a real Fulcra
  tag, not a note field** (activity type, repo name, GitHub identity/
  username, period type, notability flags). `note` is reserved for
  genuinely free-text/non-filterable payload only (commit message text,
  PR title, comment body, numeric counts, LLM-generated summary text).
  This is as close as the platform allows to avoiding "everything
  crammed into an opaque JSON blob."
- `metric-time-series` (Fulcra's built-in metric aggregation) is
  restricted to API v0 built-in metric types -- confirmed live that an
  existing v1alpha1 custom metric type in this account is NOT listed as
  supporting it (`related_cli_commands` includes only `get-records`).
  Not usable for our custom types.
- However, a real, working, general per-time-bucket **count aggregation
  endpoint does exist** for custom event types, even though it isn't
  wrapped by a named SDK method or CLI subcommand yet:
  `GET /data/v1alpha1/event/{BaseType}/{UUID}/agg/{resolution}?start_time=...&end_time=...`
  (resolutions include `day`, `15m`, `60m`, etc.). Verified live end to
  end: wrote 3 real records to a disposable custom `MomentAnnotation`
  type across 2 real days, called this endpoint with `resolution=day`,
  and got back the correct `record_count` per day bucket. Reachable from
  Python via the SDK's generic `fulcra_v1_api_path()` method (no new
  dependency). **What it does NOT do**: no groupby (can't split counts
  by tag/activity-type in one call), and only returns `record_count`
  plus meaningless duration stats for instant-based events -- it cannot
  replace rollup content generation (which activity types occurred,
  which repos, notability inputs), only cheap existence/volume checks.
  **Where this project will use it**: the existence pre-check (a cheap
  "does this repo have any real activity in this range" signal) and
  potentially as a corroborating volume signal for day-level rollups.
  Rollup content aggregation (per-type/per-repo breakdowns, notability
  math) remains genuinely hand-rolled, reading real records via
  `get-records`/the SDK's `moment_annotations()`/`duration_annotations()`
  over the relevant range.
- Custom-type discovery pitfall (recorded here because it directly
  shaped this section): `fulcra catalog` output mixes platform built-in
  types (where `id` is the human-readable name) with user-defined custom
  types (where `id` is an opaque `<BaseType>/<UUID>` string -- the real
  name is in the separate `name` field). Matching on `id` alone during
  this Architecture pass initially and incorrectly concluded "no
  existing type" while missing five real pre-existing custom types from
  an unrelated earlier project in this same Fulcra account
  (`GitHubBackfillProgress`, `GitHubActivityRaw`, `ActivityRollup`,
  `NotabilitySignal`, `GitHubBackfillProgressV2`). Those five have since
  been archived (`fulcra data-type archive`) specifically so this
  project's own type names don't collide with stale leftovers, and are
  confirmed no longer present in the live catalog. This pitfall was
  significant enough that a correction was also filed against the
  `fulcra-prototype-grill-me` skill itself (see that skill's PR history)
  so it isn't rediscovered on a future project.
- Stale tags (`commit`, `pull_request`, `focus_switch`, `new_repo`, etc.)
  also exist in this account from that same earlier project. Not
  archived (tags have no archive mechanism and are effectively free-text
  labels) -- not a real collision risk as long as this project's own tag
  names aren't deliberately reused for a different meaning. Tag creation
  is idempotent by name (`fulcra tag create` / `create_tags()`), so this
  project will simply create/reuse tags under its own chosen names.

### LLM (enrichment + narrative) -- deliberate divergence from a bundled provider
Per Intake, this project does NOT bundle a dedicated LLM provider
integration (no Gemini API key requirement). Rollup-summary text and
narrative generation should use whatever model is already running the
skill at that point in the flow.

Concretely, this means: the rollup-summarization and narrative-generation
steps are **agent-harness-side operations** -- i.e., when the running
harness task reaches the point of summarizing a rollup period or
generating narrative prose, that step is performed by the agent process
itself (the model already executing the task), which then writes the
resulting text into the relevant Fulcra record's `note` field via the
deterministic write path -- NOT a standalone script that calls out to a
separate model API on its own initiative. The ingestion/rollup-math
scripts remain fully deterministic and produce structured inputs (raw
counts, activity breakdowns, period boundaries); the summarization/
narrative step is a distinct, explicitly-model-driven task step that
consumes those structured inputs and produces text, then hands the
result back to a deterministic write call. This keeps "the model
decides what to write" and "the code decides how/where it's persisted"
cleanly separated, and means no API-key prerequisite gate is needed for
this project's Gemini-equivalent step, unlike a typical
`fulcra-rapid-prototype`-scaffolded harness.

## Custom data types

All four types below are new (the same-named types from an unrelated
earlier project have been archived; see above). All are
`user_configured` custom types created via `fulcra data-type create`.
Names use natural spacing (e.g. "GitHub Activity Raw") rather than
PascalCase/camelCase -- confirmed live that `fulcra data-type create`
accepts spaced names without issue, and camelCase adds no real benefit
since these are just the `name` field's display value, not a code
identifier.

### 1. "GitHub Activity Raw" (base type: `MomentAnnotation`)
One record per individual raw activity item (one commit, one PR
open/merge event, one PR review, one issue/PR comment) -- confirmed via
Intake this is per-item, not pre-aggregated, so real provenance survives
down to the individual GitHub item.
- **`recorded_at` semantics:** the real GitHub event timestamp (commit
  authored/committed time, PR/review/comment creation time) -- never
  ingestion time. This is what makes the existence pre-check and
  range-scoped queries meaningful, and is the exact class of mistake
  documented as a real, previously-fixed bug in a prior unrelated
  project's lessons (a `recorded_at`-as-ingestion-time mistake silently
  defeats time-range queries) -- called out here as a binding rule for
  this type specifically, verified independently against this project's
  own Intake requirements rather than assumed from that prior project.
- **Tags:** `activity_type` (`commit` | `pr_opened` | `pr_merged` |
  `pr_review` | `comment`), `repo` (owner/repo string), `github_identity`
  (the authenticated GitHub username/login this record belongs to --
  included from day one specifically so a future multi-identity
  "combined journey" can be built by merging separately-ingested record
  sets and filtering/grouping by this tag, without needing a schema
  change later, per Intake's explicit ask).
- **Sources:** `["github:<owner>/<repo>", "com.fulcradynamics.cli"]`-style
  chain (exact string convention to be finalized during Prototype) --
  records this item's real GitHub origin, not just "this is
  GitHubActivityRaw."
- **`note`:** JSON blob with the item's non-filterable content: commit
  message / PR title+body / review body / comment body, plus whatever
  minimal structured metadata (e.g. PR number, SHA) is needed to
  construct a real link back to GitHub, but is not itself a dimension
  anyone would filter/group by.

### 2. "Activity Rollup" (base type: `DurationAnnotation`)
One record per rollup period (day/week/month/quarter/year), precomputed
and stored durably (never computed fresh at generation time, per
Intake).
- **`recorded_at` semantics:** the period's own real `{start_time,
  end_time}` (e.g. a day rollup's actual calendar day, a quarter
  rollup's actual quarter bounds) -- using `DurationAnnotation`'s native
  range field rather than reusing a `MomentAnnotation` and inventing a
  parallel note-field date range. Verified live that
  `DurationAnnotation`'s `recorded_at` is natively a
  `{start_time, end_time}` object, making this the correct base type
  for anything period-shaped (confirmed via `fulcra data-type schema
  DurationAnnotation`).
- **Tags:** `period_type` (`day`|`week`|`month`|`quarter`|`year`),
  `repo` (when a rollup is scoped to a single repo; a combined
  all-repos rollup for the period may omit this or use a sentinel),
  `github_identity`.
- **Sources:** references the "GitHub Activity Raw" record IDs (or, for
  higher-order rollups, the lower-layer "Activity Rollup" record IDs)
  this rollup was built from -- the literal provenance chain Intake
  requires.
- **`note`:** JSON blob with computed counts per activity type, and the
  model-generated summary text for this period (written by the
  harness-side summarization step described above, not by the
  deterministic aggregation script).

### 3. "Notability Signal" (base type: `NumericAnnotation`)
One record per rollup period, holding the computed eventfulness score
plus what it was computed from. The concrete scoring formula is
explicitly deferred to Plan/Prototype (per Intake, "first pass, expected
to be revised" was the spirit even though this rebuild doesn't inherit
any specific prior formula).

Uses `NumericAnnotation`, not `MomentAnnotation`, specifically because
this record's whole purpose is a single computed scalar score --
confirmed live that `NumericAnnotation` (like `ScaleAnnotation` and
`BooleanAnnotation`) has a real, required, non-`note` `value` field
(plus an optional `unit`), distinct from the fixed `{id, tags, sources,
recorded_at, note}` shape shared by event-class types. Putting the score
in `value` instead of burying it in a `note` JSON blob is a genuinely
better fit, not just a stylistic choice -- it's the one type in this
project's schema where the record's entire content really is a single
number. (This is deliberately NOT extended to "Activity Rollup": that
record is inherently multi-dimensional -- several per-activity-type
counts plus summary text for one period -- so no single `value` field
represents it well, and exploding it into one scalar metric record per
activity-type-per-period was considered and rejected as unnecessary
record-volume growth for unclear benefit. "GitHub Activity Raw" and
"GitHub Backfill Checkpoint" are genuinely event/duration-shaped, not
scalar-shaped, so they stay on their original base types too.)
- **`recorded_at` semantics:** the same period start (a single instant,
  since this is a derived summary judgment about a period, not itself a
  duration) -- specifically the period's `start_time`, for consistent
  chronological ordering against "Activity Rollup" records. Confirmed
  `NumericAnnotation`'s `recorded_at` is a single instant, same as
  `MomentAnnotation`, not a range.
- **`value`:** the computed notability score itself (scale/bounds to be
  finalized during Plan/Prototype once the formula exists).
- **Tags:** `period_type`, `repo` (if scoped), `github_identity`, plus
  whatever notability-category tags the eventual formula produces (e.g.
  `volume_surge`, `new_repo`, `focus_switch`, `streak`, `gap`) --
  decided concretely during Plan/Prototype once the formula exists, but
  the intent to make these real tags (not note-only flags) is locked in
  now.
- **Sources:** references the "Activity Rollup" record ID(s) this signal
  was computed from.
- **`note`:** still available and used -- `value` holds only the bare
  score, so `note` carries the intermediate baseline-comparison detail
  that explains how that score was derived (e.g. the personal-baseline
  average it was compared against, which specific "firsts"/streak/gap
  condition fired). Using `value` for the score doesn't mean `note`
  goes unused; a metric-class type still has both fields, and this is
  a genuine case for using both together rather than treating them as
  mutually exclusive.

### 4. "GitHub Backfill Checkpoint" (base type: `DurationAnnotation`)
Resumable backfill progress marker. Named distinctly from the archived
prior project's "GitHub Backfill Progress"/"GitHub Backfill Progress V2"
to avoid any ambiguity about lineage, even though those names are free
again after archiving.
- **`recorded_at` semantics:** the real `{start_time, end_time}` of the
  date range this checkpoint covers (using `DurationAnnotation`'s native
  range field) -- NOT the moment the checkpoint was written. Even though
  a checkpoint is inherently a "progress marker" (the one case Intake's
  own `recorded_at` guidance flags as a legitimate ingestion-time use),
  this project's checkpoints are scoped to a specific historical range
  being backfilled, so the range itself is the more useful, query-
  relevant timestamp; genuine last-write/ingestion time belongs in a
  separate `updated_at` field inside the JSON `note` payload instead,
  kept distinct from `recorded_at`.
- **Tags:** `repo` (checkpoints are tracked per repo, so that extending
  a backfill -- forward or backward -- can determine per-repo which
  ranges are already covered without re-deriving it from a single
  monolithic marker), `github_identity`, `status`
  (`in_progress`|`completed`).
- **Sources:** none beyond identifying this record's own type; not a
  derived record.
- **`note`:** JSON blob with the actual discovered repo list state,
  last-processed-item cursor, and `updated_at` (real last-write time,
  kept separate from `recorded_at` per above).

## Tenancy
Single Fulcra account, single GitHub identity per ingestion run (per
Intake). The `github_identity` tag on every type is the concrete,
query-usable seam that would let a future, separate effort merge
multiple identities' separately-ingested record sets into one combined
journey, without this build needing to implement that merge itself.

## Open items carried into Plan (not resolved here)
- Concrete GitHub API endpoint(s) for the existence pre-check and for
  per-item ingestion (GraphQL vs. REST Search vs. some combination) --
  needs live verification against a real account, not assumed.
- Exact `sources` string convention/format.
- Concrete notability signal formula.
- Whether the `agg/day` endpoint's count is used as a genuine input to
  the existence pre-check (cheap enough to call before any GitHub API
  work) or purely a corroborating signal after raw records already
  exist -- needs a Prototype-phase spike given it's an unwrapped/
  undocumented-by-SDK endpoint being used somewhat off the beaten path.
