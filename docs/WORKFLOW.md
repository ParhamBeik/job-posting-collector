# How this project was built

Each build step went through the same loop, so the history shows planning, review and decisions,
not only the final code.

```
issue #N: plan for one step (what, why, done when)
   │
   ▼
branch step-N-<name>: small commits, written with Claude Code
   │
   ▼
pull request "Closes #N" ──▶ CI runs the tests
   │
   ▼
Codex review (@codex review): checks the diff against PLAN.md, the issue and AGENTS.md
   │
   ▼
Claude triages each finding and replies in the PR thread:
   agree    → fix commit that names the finding
   disagree → reply with evidence (brief line, test, or observed site fact)
   unsure   → flagged for Parham
   │
   ▼
Parham reads the replies and decides any disagreement or open question
   │
   ▼
merge commit into main (never squashed, so every commit stays visible)
```

## Roles

| Who | Does | Where to see it |
|---|---|---|
| Claude Code | Drafts the plan, issues, code and tests | Issues, commits |
| Codex (OpenAI) | Independent review of each PR; comments only, never pushes code | PR review comments |
| Claude Code | Triages every Codex finding: fixes, or pushes back with evidence | Fix commits, PR replies |
| Parham | Approves the plan, settles disagreements, runs the tests, merges | PR replies, merge commits |

Codex and Claude never talk directly: the PR thread is the shared record, so every
disagreement and its resolution is visible.

The reviewer's instructions are in [`AGENTS.md`](../AGENTS.md) under "Review guidelines", so
the review criteria are versioned with the code.

The plan itself was reviewed the same way: `PLAN.md` was added in its own pull request and
reviewed by Codex before any code was written.

## Where to look

- Plan review: PR #_ (filled in once opened)
- Example review findings and decisions: see the AI-use note in the README.
