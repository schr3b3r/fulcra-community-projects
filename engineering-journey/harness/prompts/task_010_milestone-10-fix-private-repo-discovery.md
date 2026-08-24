Task: Milestone 10: Fix private repo discovery

Context
Engineering Journey: a Hermes skill that ingests a developer's GitHub
activity history going back approximately 3-4 years, and produces a
single, well-formatted, engaging markdown document telling the story of
their engineering journey over that period. The whole point of this
project is that someone should be able to try this skill out and have
it include ALL of their real activity -- including private repos, which
for many working engineers is the majority of their real output.

Milestones 1-9 are done and committed -- see checkpoint.py,
github_client.py, github_activity.py, rollup.py, notability.py,
narrative.py, engineering_journey.py, fulcra_types.py, and
app/CONTEXT.md's Decisions Log and "Fulcra SDK usage notes" section.

**Read app/CONTEXT.md's Decisions Log entry titled "Real gap
independently re-verified, scope corrected" FIRST, in full, before
writing any code.** It documents an important correction: a live test's
issue report originally claimed GitHub's REST Search API "cannot index
private repository content at all, regardless of token scope" and
proposed replacing Search API calls with per-repo REST endpoints
everywhere. That claim was independently re-tested against 3 real
private repos in a real account and does NOT hold -- `search/commits`
and `search/issues` DID find real commits/issues in private repos given
a normal `repo`-scoped PAT. The ACTUAL confirmed gap is narrower and
upstream: `GitHubClient.enumerate_repositories()` (the only repo
discovery mechanism `backfill_full_github_activity` uses) relies
entirely on GraphQL `contributionsCollection`, which genuinely misses
real private repos with real contributions. Do NOT rewrite the
Search-API-based fetch functions (`fetch_commits`/`fetch_pull_requests`/
`fetch_issues` in github_client.py) -- they already work correctly for
private repos once those repos are actually in the `repo_names` list.
This task is scoped narrowly and deliberately; do not expand it back
into the originally (incorrectly) diagnosed larger rewrite.

Your task right now

1. Add a new method to `GitHubClient` (github_client.py), e.g.
   `list_accessible_repositories(pushed_after=None, pushed_before=None)`,
   that calls `GET /user/repos?affiliation=owner,collaborator,organization_member`
   (paginated -- GitHub returns this paginated, don't assume one page is
   everything) and returns repo full names (`owner/repo`), optionally
   filtered to repos whose `pushed_at` falls within a given date window.
   This surfaces private repos regardless of whether GraphQL's
   contribution graph currently counts them.

2. Update `enumerate_repositories()` to UNION this new listing-based
   discovery with the existing `contributionsCollection`-based
   discovery, rather than replacing it (the contribution graph is still
   useful/cheap for the common public-activity case; the new listing
   pass is what catches what it currently misses). Deduplicate the
   combined result. Filtering by `pushed_at` in-window is a coarse,
   correct prefilter (a repo not pushed to at all in the window
   definitely has no in-window activity by anyone; a repo pushed to
   could still have zero activity *by this specific user*, which the
   existing per-repo `author:`/`committer-date:` search-based fetch
   functions already correctly filter for downstream) -- it is NOT a
   source of false negatives for repos that genuinely have this user's
   activity in-window, and don't second-guess that reasoning by making
   the prefilter narrower than "pushed_at falls in window."

3. This should require NO changes to `fetch_commits`/`fetch_pull_requests`/
   `fetch_issues`/`_paginate_search` -- those are confirmed already
   working correctly for private repos once such a repo is in the
   `repo_names` list passed to `backfill_full_github_activity`. If you
   find a real reason during this task that they DO need changes,
   stop and document the specific real evidence (not a re-assumption
   of the original, now-corrected claim) before changing them -- don't
   silently expand scope back to the original larger rewrite.

4. Prove this end-to-end on REAL data: this environment's real GitHub
   account (schr3b3r) has real private repos with real commit/issue
   activity that the CURRENT `enumerate_repositories()` misses (verify
   this yourself first, e.g. by calling the current
   `enumerate_repositories()` over a window covering that activity and
   confirming a known-private, known-active repo is absent from the
   result) -- then confirm your fix makes it appear. Do not use a
   synthetic/fake example for this proof; use real repos and real
   activity in this real account.
   - After the fix, run a REAL small-scope backfill (a narrow date
     window, not a full 3-4 year one -- this is a discovery fix, not a
     full backfill demo) that includes a real private repo, and confirm
     real `GitHubActivityRaw` records for that private repo's real
     activity actually get ingested into Fulcra.
   - Clean up any real Fulcra records created during this verification
     that aren't covered by a test's own try/finally cleanup.

5. Automated tests: add tests for the new listing method and the
   updated union logic. Since hitting the real GitHub API for repo
   listing is cheap/fast (unlike full backfills), prefer a REAL test
   over the account's real repos where practical (per this project's
   own "prefer real Fulcra/API data in tests" standard) -- e.g. assert
   that a known real private repo with known real activity appears in
   `enumerate_repositories()`'s result for a window covering that
   activity, which would have failed before this fix and should pass
   after it. Skip gracefully (not fail) if no GitHub token is available
   in the test environment, matching the existing pattern in
   test_github_client.py/test_github_activity.py.

Keep it minimal and correct rather than elaborate -- this is a narrowly
scoped discovery fix, not new product logic, and not the sweeping
rewrite the original (incorrect) report proposed. When you're done,
give a short summary of the files you changed, the real before/after
proof (which real private repo was missing before, confirmed present
after), and the test results.

Reminders (see app/ENGINEERING_STANDARDS.md for the full list)
- Type hints throughout.
- Automated tests (pytest) covering this task's acceptance criteria, and
  the FULL test suite passes -- not just tests for what you just
  changed. Budget several minutes for a full run (it includes real,
  live API tests from prior milestones).
- Use `requests` directly against GitHub's REST API (already the
  established pattern in github_client.py) -- do NOT shell out to the
  `gh` CLI.
- Do not commit any real GitHub token, username, or other credential
  into a file tracked by git.
- Update app/features/INDEX.md and add a new app/features/*.md file for
  this feature (following the pattern of the existing nine feature
  files).
- Commit your work with git_commit once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.
- Clean up any real Fulcra test records you create during manual
  exploration/testing (not ones covered by a test's own try/finally
  cleanup) before finishing -- this has been a real, repeated issue on
  this project (see app/CONTEXT.md's Decisions Log).
