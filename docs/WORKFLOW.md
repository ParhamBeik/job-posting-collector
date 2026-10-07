# How this project was built

Each build step went through the same loop, so the history shows planning, review and decisions,
not only the final code.

```
issue #N: one build step (what, why, done when)
   │
   ▼
branch step-N-<name>: Claude Code reads the issue and writes the code and tests
   │
   ▼
pull request "Closes #N" ──▶ CI runs the tests
   │
   ▼
Codex review: reviews the PR against PLAN.md, the issue and AGENTS.md, leaves a comment
   │
   ▼
Claude reads the review and keeps what is a real insight:
   useful   → fix commit that names the finding, reply "Fixed in <sha>"
   not      → reply with evidence (brief line, test, or observed site fact)
   unsure   → "Needs Parham"
   │
   ▼
Parham reads the PR, settles open points, merges with a merge commit (never squashed)
```

## Roles

| Who | Does | Where to see it |
|---|---|---|
| Claude Code | Writes the plan, issues, code and tests | Issues, commits |
| Codex (OpenAI) | Independent review of each PR; comments only, never pushes code | PR review comments |
| Claude Code | Acts on each Codex finding: fixes, or replies with evidence | Fix commits, PR replies |
| Parham | Settles disagreements, checks the result, merges | PR replies, merge commits |

The PR thread is the shared record, so every finding and its resolution stays visible.
The reviewer's instructions are in [`AGENTS.md`](../AGENTS.md) under "Review guidelines", so the
review criteria are versioned with the code.
