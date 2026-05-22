---
description: Show status of one Mimiron slug (or list all if no arg).
argument-hint: [<slug>]
allowed-tools: Bash, Read
---

Show Mimiron status.

$ARGUMENTS

- If an argument is given, run `mimiron status <slug>` and print the output. Also look for `.mimiron/<slug>/evaluation/verdict.json` and `archive/COMPLETION.md` if they exist; surface the latest verdict score.
- If no argument, run `mimiron ls` (lists all slugs with phase).

Read-only operation — does not modify state.
