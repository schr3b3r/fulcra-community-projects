Task: Milestone 9: Migrate to real custom Fulcra data types

Context
Engineering Journey: a Hermes skill that ingests a developer's GitHub
activity history going back approximately 3-4 years, and produces a
single, well-formatted, engaging markdown document telling the story of
their engineering journey over that period.

Milestones 1-8 are done and committed -- see checkpoint.py,
github_client.py, github_activity.py, rollup.py, notability.py,
narrative.py, engineering_journey.py, and app/CONTEXT.md's Decisions
Log and "Fulcra SDK usage notes" section.

Your task right now
Real feedback from the first fresh-account live test (shared as a
markdown file, see app/CONTEXT.md's Decisions Log entry about it) found
that NO custom Fulcra data types exist anywhere in this codebase. Every
persistence path -- `checkpoint.py` (GitHubBackfillProgress),
`github_activity.py` (GitHubActivityRaw), `rollup.py` (ActivityRollup),
`notability.py` (NotabilitySignal) -- calls
`client.record_data_type("MomentAnnotation", batch, api_version="v1alpha1")`
with the real semantic type hidden as a `"record_type"` string key
inside a JSON blob stuffed into MomentAnnotation's generic `note` field.
There is no real, registered Fulcra data type for any of these. This
directly contradicts this project's own stated "why Fulcra,
specifically" rationale in `intake/brief.md` (custom annotation types
as a deliberate, visible primitive, not just generic notes).

**Read app/CONTEXT.md's "Custom annotation data types" entry in the
"Fulcra SDK usage notes" section FIRST, in full, before writing any
code.** It documents the exact, already-verified-live mechanism (not a
guess): a custom data type is created via `fulcra-api data-type create
<BaseType> <Name>` (or find the underlying HTTP call in
`fulcra_api.cli.data_types` if you want a pure-SDK path -- the CLI is a
thin wrapper), which returns a real assigned UUID. Records are then
written to the BASE type (e.g. still `"MomentAnnotation"`) but with a
`"sources": ["com.fulcradynamics.annotation.<uuid>"]` field added to
each record dict -- NOT by writing directly to
`"MomentAnnotation/<uuid>"` as a data-type name (that returns a 404,
confirmed). Records are read back filtered to just that custom type via
`client.moment_annotations(start, end, source="com.fulcradynamics.annotation.<uuid>")`.

Specifically:

1. For each of the four record kinds (`GitHubBackfillProgress`,
   `GitHubActivityRaw`, `ActivityRollup`, `NotabilitySignal`), create a
   REAL custom Fulcra data type once, using `fulcra-api data-type
   create MomentAnnotation <Name> -d "<description>"` (or the SDK
   equivalent if you find one). Do this creation idempotently -- check
   whether the type already exists first (e.g. `client.v1_catalog(name=...)`
   or `client.resolve_data_type(...)`) rather than blindly recreating it
   every time code runs; a second `create` call for the same name is
   not guaranteed to be a no-op and could create a duplicate type.

2. Store each type's real UUID durably and accessibly to the running
   code -- e.g. a small constants module, or values resolved once at
   startup and cached, or entries in `.env`/a config file checked into
   the app's own setup (NOT hardcoded as a bare guess -- these are
   real, environment-specific UUIDs that must come from an actual
   `create`/lookup call, not be invented). Design this so a fresh
   Fulcra account running this skill for the first time creates its own
   real types with its own real UUIDs, rather than assuming one fixed
   UUID works for every user's Fulcra account.

3. Update every `write_*` function in `checkpoint.py`, `github_activity.py`,
   `rollup.py`, `notability.py` to add the correct `sources` tag
   (pointing at that record kind's custom type UUID) to each record
   before calling `record_data_type`. The JSON `note` payload and its
   embedded `"record_type"` key can stay exactly as they are -- this is
   additive, not a payload format change.

4. Update every `read_*` function in the same four files to pass the
   matching `source=` filter to `moment_annotations()` instead of (or
   in addition to, for backward compatibility -- see point 6) relying
   purely on client-side filtering by the embedded `"record_type"` JSON
   key.

5. Update every `clear_*`/tombstone function similarly, so cleanup still
   correctly finds and removes records written under the new source-tagged
   convention.

6. Backward compatibility: there is REAL existing data in Fulcra right
   now (from Milestones 1-8's own testing and the live fresh-account
   test) written under the OLD convention (plain `MomentAnnotation`, no
   `sources` tag, relying only on the `record_type` JSON key). Do not
   silently orphan it. Read functions should be able to find/return
   records written either the old way or the new way during this
   transition -- document clearly in code/CONTEXT.md whether this means
   querying without a source filter and doing client-side
   `record_type` filtering as a fallback path, or some other approach,
   but make a deliberate choice and test it, don't just leave old data
   invisible without noticing.

7. Prove this end-to-end on REAL data: create the real custom types in
   this environment's real Fulcra account, write and read back real
   records of at least two of the four kinds through the new mechanism,
   and confirm via `fulcra-api catalog` (or the SDK's `v1_catalog`) that
   the created types are now genuinely visible in the catalog as their
   own named types -- not just that a record round-tripped successfully.
   Also confirm old-format records already in Fulcra from before this
   migration are still readable.

Keep it minimal and correct rather than elaborate -- this is a real but
mechanical migration across existing persistence functions, not new
product logic. Don't touch rollup/notability/narrative computation
logic itself, only how records get written/read/cleared. When you're
done, give a short summary of the files you changed, the real custom
type UUIDs created (and confirmation they show up in the real catalog),
and the test results.

Reminders (see app/ENGINEERING_STANDARDS.md for the full list)
- Type hints throughout.
- Automated tests (pytest) covering this task's acceptance criteria
  (creation idempotency, write/read/clear through the new mechanism,
  backward-compatible reads of old-format records), and the FULL test
  suite passes -- not just tests for what you just changed. Budget
  several minutes for a full run (it includes real, live API tests from
  prior milestones).
- app/tests/conftest.py already loads .env for the pytest suite.
- Use the fulcra-api Python SDK (not raw subprocess calls to the CLI,
  except possibly for the one-time type-creation step if no pure-SDK
  method exists -- check first) for any Fulcra integration this task
  touches.
- Do not commit any real GitHub token, username, Fulcra credentials, or
  other secret into a file tracked by git. Real Fulcra data-type UUIDs
  created by this task are NOT secrets and are fine to reference in
  code/config, but don't hardcode a specific user's already-created
  UUID as if it's universal -- the creation/lookup logic must work for
  any Fulcra account this skill runs against.
- Update app/features/INDEX.md and add a new app/features/*.md file for
  this feature (following the pattern of the existing eight feature
  files).
- Commit your work with git_commit once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.
- Clean up any real Fulcra test records (and any throwaway custom data
  types) you create during manual exploration/testing (not ones covered
  by a test's own try/finally cleanup) before finishing -- this has been
  a real, repeated issue on this project (see app/CONTEXT.md's Decisions
  Log).
