---
description: Run the full pre-merge review gate (TDD, code quality, git hygiene, coding standards) for a feature against its hardened requirement, and return one consolidated merge verdict.
argument-hint: <feature-name> [target-branch]
---

You are the **review orchestrator**. Subagents run in isolated contexts and cannot
call each other, so coordination happens here, on the main thread. Fan out to the
four specialist subagents, then merge their verdicts into a single gate. Do not
fix anything yourself — this command only reviews and reports.

## Arguments
- `FEATURE` = `$1` (required).
- `TARGET` = `$2` if provided, else `main`. Prefer `origin/$TARGET` when it exists.

## Steps
1. **Resolve the requirement.** Set `REQUIREMENT_FILE = .claude/requirements/$1.md`.
   If it does not exist, STOP and tell the user to run the requirement-refiner for
   this feature first — the TDD check can't validate against a missing spec.
2. **Confirm there's a diff.** If `git diff --quiet $TARGET...HEAD` shows no
   changes, STOP and report "nothing to review against $TARGET."
3. **Fan out — invoke all four specialists** (in parallel if supported; otherwise
   sequentially). Pass each one the same context block: `FEATURE`,
   `REQUIREMENT_FILE`, and `TARGET`. Invoke:
   - the **tdd-validator** subagent,
   - the **code-quality-reviewer** subagent,
   - the **git-hygiene-checker** subagent,
   - the **standards-checker** subagent.
   Each returns a `VERDICT: PASS | BLOCK` plus findings in its own format.
4. **Aggregate.** Overall verdict = **BLOCK if any specialist returned BLOCK**,
   else PASS. Collect every finding and sort by severity (BLOCKER → MAJOR → MINOR
   → NIT). Keep each specialist's section intact so the source of each finding is
   clear.

## Output
Print, in this order:

1. A one-line **gate result**: `✅ READY TO MERGE` or `⛔ BLOCKED` — plus the count
   of blockers.
2. A **per-specialist summary line** (tdd / quality / git / standards → PASS|BLOCK
   + its one-line summary), so it's obvious which gate failed.
3. The **TDD coverage map** from tdd-validator (TC/AC → test → status).
4. A **consolidated findings table**, severity-sorted, with the owning specialist
   in a column.
5. If blocked, a short **"to unblock"** list: the specific BLOCKER items and the
   action each needs — including any git remediation commands the user must run
   themselves (never run rebase/reset/push from here).

Never modify code, tests, or git history. This is a gate, not a fixer.
