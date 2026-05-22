---
description: Recover a stuck Mimiron slug — invokes the unstuck skill (sefety-pin personified).
argument-hint: <slug>
allowed-tools: Skill, Bash, Read, Write, AskUserQuestion
---

Recover the stuck Mimiron slug:

$ARGUMENTS

Steps:

1. **Verify slug exists** and is actually stuck (`mimiron status <slug>` → phase=stuck OR consecutive_gate_fails ≥ 3). If not stuck, tell the user the slug doesn't need unstuck — use `/mimiron-resume <slug>` instead.
2. **Hand off to `mimiron-unstuck` skill** via the Skill tool. The skill:
   - Writes a human-readable report at `.mimiron/<slug>/unstuck.md` (where it got stuck, retry history, three suggested next actions)
   - Sets `state.paused=true` to block stop-hook re-entry
   - Waits for user decision (no auto-recovery)
3. **Show the report path** so the user can read it.

Common next actions the unstuck skill will propose:
- Lower a threshold (`_global/thresholds.yaml`) and retry the gate
- Edit `plan.yaml` to add/remove tasks
- Archive the slug as-is (`mimiron archive <slug>`)
- Open `state.spec_unlocked=true` for a controlled spec edit, then re-enter from spec phase

Do NOT auto-pick an action — surface the three options and ask the user.
