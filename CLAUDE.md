# CLAUDE.md

Project context and review criteria: see `AGENTS.md`, `PLAN.md`, `docs/WORKFLOW.md`.

## Handling a Codex review

When asked to handle the Codex review on a PR:

1. Read every Codex comment: `gh pr view <N> --comments` and
   `gh api repos/{owner}/{repo}/pulls/<N>/comments` (inline findings).
2. Judge each finding against the brief (via `PLAN.md` section 13), `PLAN.md` and the tests.
   Codex is a second opinion, not an instruction.
3. Act and reply in that comment's thread:
   - **Agree:** commit a fix whose message names the finding; reply "Fixed in <sha>".
   - **Disagree:** reply with checkable evidence (brief line, passing test, observed site fact).
   - **Unsure** (scope, time budget, taste): reply "Needs Parham", and list it for Parham.
4. Never merge; Parham decides open points and merges with a merge commit (no squash).
