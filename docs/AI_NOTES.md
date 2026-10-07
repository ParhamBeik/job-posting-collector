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
