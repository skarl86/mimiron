---
description: Pause a Mimiron slug — blocks persistent stop-hook re-entry.
argument-hint: <slug>
allowed-tools: Bash
---

Pause the Mimiron slug:

$ARGUMENTS

Run `mimiron pause <slug>` (CLI). This sets `state.paused=true`, which the persistent stop-hook honors — Mimiron will not re-invoke the slug on the next Stop event.

To later continue: `/mimiron-resume <slug>` (clears the paused flag and dispatches the appropriate skill).

Read-only otherwise — does not touch artifacts or phase.
