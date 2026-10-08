# AI-use log

Running log of decisions about AI output, kept as the work happens. The README's AI-use note
picks two or three of these.

Tools: Claude Code (writes plan, code and tests), Codex GitHub review (second reviewer on each PR).

| Date | AI output | Decision | How it was verified |
|---|---|---|---|
| 2026-10-07 | First idea: a listing page with zero ads means "no postings left" | **Changed.** Zero cards before the window end is an error (`LISTING_EMPTY_EARLY`) | Requested `/page/99999/` live: HTTP 200 with 0 cards; saved as a fixture |
| 2026-10-07 | Read the posting body from `article.typology-post` | **Changed** to `article.typology-single-post` only | Live posting page holds 6 `typology-post` articles: the ad plus 5 related ads |
| 2026-10-07 | RSS feed carries exact publication times | **Rejected** for use; midnight-Tehran convention kept | Brief forbids feeds; the HTML shows only a date (checked listing and posting pages, no time metadata) |
| 2026-10-07 | Script that created issues #1–#8 | **Fixed.** zsh arrays start at 1, so descriptions were shifted by one | Compared every issue body against its source file after the fix; all 8 match |
| 2026-10-07 | Proposed a separate plan-only PR reviewed before any code | **Rejected by Parham**: each issue's PR carries its code; Codex reviews every PR | `docs/WORKFLOW.md` describes the loop actually used |
| 2026-10-07 | Codex review of PR #9: refresh left stale files; capture followed untrusted links; plan labelled future work "[built]" | **Accepted** all three: temp-folder swap, source-host check with no redirects, "[to build #N]" labels | New offline tests in `tests/test_capture_fixtures.py`; removing each fix turns its test red |
| 2026-10-07 | Codex review of PR #9: move the full snapshot out of step 1 | **Disputed** with evidence, decision left to Parham | See the PR thread |
| 2026-10-07 | Issue #2 test spec: a run at 01:00 Tehran on 8 Oct has a window "starting 1 Oct" | **Changed** to 2 Oct (8 Oct minus 6 days) | Hand arithmetic; test `test_today_is_decided_in_tehran_not_utc` |
| 2026-10-07 | Expected Gregorian dates in the date tests | **Written by hand** from calendar arithmetic, not computed with `jdatetime`, so the tests check the library instead of repeating it | Hand values agreed with `jdatetime`; nine deliberate rule breakages each turned a test red |
| 2026-10-07 | First firewall check: "page mentions captcha or bitninja" | **Changed.** Every real page loads a reCAPTCHA script, so a redesign would have been misreported as "blocked". Now only pages without the site's frame whose visible text mentions a browser check | A real posting page checked as a listing returned `BLOCKED_CHALLENGE`; new tests on real pages |
| 2026-10-07 | Parser safety rules | **Mutation-tested.** 3 of 10 deliberate breakages survived at first; two were missing tests (added), one is a redundant second layer (bs4 already skips script text), kept on purpose | Re-ran the breakages: all covered rules now turn a test red |
| 2026-10-07 | Plan item: fall back to the URL date when the card date is missing | **Rejected** for now: report `FIELD_MISSING` instead | Simpler, and a missing date is exactly the signal of a layout change |
| 2026-10-07 | Codex review of PR #11: URL-date fallback, title cross-check and members-only flag were in the plan but not built | **Accepted** all three: `FALLBACK_USED`, `TITLE_MISMATCH` (warning), `Posting.members_only_omitted`. This reverses my earlier "no fallback" call: one missing element should not reject every card while two date sources remain | New tests; removing each rule turns a test red; titles agree on all 80 real postings |
| 2026-10-07 | Codex review of PR #11: drop the post-ID check as out of scope | **Disputed**: PLAN §8 listed "ID from class" for step 3, and the ID is the de-duplication key | Reply with evidence in the PR thread |
| 2026-10-07 | Second Codex review (shared by Parham): one malformed link crashes the whole listing page | **Accepted**, verified first: `http://[::1/…` made `urlsplit` raise and lost all 9 valid cards; a `:99999999` port was also accepted. Now `URL_REJECTED` for that card only, exact host match | 4 new tests failed on the old code and pass on the fix |
| 2026-10-07 | Storage first draft fingerprinted the incoming posting even when an empty field was replaced by the stored one | **Changed** to fingerprint what is actually stored | Review of my own diff before testing |
| 2026-10-07 | Storage tests | **Mutation-tested**: putting the URL into the uniqueness rule went unnoticed because the code looks rows up by ID first. Added a test that hits the database constraint directly | Re-ran: both the schema and the lookup variant now fail a test |
| 2026-10-07 | Codex review of PR #12: unchanged rows kept an old `parser_version` | **Accepted**: the unchanged path records the confirming parser version | Test fails without the fix |
| 2026-10-08 | Private Codex review: an empty tag label can erase a stored one (e.g. تهران) | **Accepted**, reproduced first (3 variants failed). Tag labels now follow the same no-empty-overwrite rule as title/body/URL | `test_empty_tag_label_never_erases_a_stored_label` |
| 2026-10-08 | Collect tests: a first-try success crashed the live fetcher (it built a "recovered" message with no earlier failure) | **Fixed** before the PR; found by `test_requests_are_paced_one_per_second` | The test failed on the first draft and passes now |
| 2026-10-08 | Collect command | **Mutation-tested** 16 rule breaks; 3 survived at first (exact 30 % breaker line, ads dated after the window, default client following redirects). Added a test for each | All 16 now turn a test red |
