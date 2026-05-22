---
description: Resume an existing Mimiron slug from wherever it left off.
argument-hint: <slug>
allowed-tools: Skill, Bash, Read, Write, Edit, Grep, Glob, Task, AskUserQuestion
---

Resume the Mimiron slug named:

$ARGUMENTS

Steps:

1. **Verify slug exists**: `mimiron status <slug>`. If it fails with "not initialized", tell the user and stop.
2. **Inspect the current `phase`** from the status output:
   - `clarify` → invoke `mimiron-clarify` skill
   - `spec` → invoke `mimiron-spec` skill
   - `plan` → invoke `mimiron-plan` skill
   - `execute` → invoke `mimiron-execute` skill
   - `evaluate` → invoke `mimiron-evaluate` skill
   - `finalize` → invoke `mimiron-finalize` skill
   - `stuck` → STOP and tell user to run `/mimiron-unstuck <slug>` instead
   - `done` → STOP and tell user the run is complete (suggest reviewing `archive/COMPLETION.md`)
3. **Clear paused flag** if it was set: `mimiron resume <slug>` (CLI, idempotent).
4. **Hand off** to the appropriate skill via the Skill tool.

If the slug is paused due to wall-clock or token-budget cap, the user may need to adjust `_global/thresholds.yaml` before resuming — surface that gap.
