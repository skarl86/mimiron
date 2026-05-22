---
description: Start a new Mimiron feature run — clarify → spec → plan → execute → evaluate → finalize.
argument-hint: <feature description in natural language>
allowed-tools: Skill, Bash, Read, Write, Edit, Grep, Glob, Task, AskUserQuestion
---

Start a new Mimiron pipeline run for this feature request:

$ARGUMENTS

Steps:

1. **Pick a slug** — a short kebab-case identifier derived from the feature request (e.g., "flask-version-endpoint"). Confirm it matches `^[a-z0-9][a-z0-9-]{0,62}$`. If the user supplied no clear name, ask via AskUserQuestion.
2. **Initialize**: run `mimiron init <slug>` (CLI). This creates `.mimiron/<slug>/state.json` with `phase=clarify, persistent=true`.
3. **Hand off to `mimiron-clarify` skill** via the Skill tool. The clarify skill conducts the Socratic interview, writes `clarification.md`, runs `mimiron gate <slug> ambiguity`, and transitions to spec.
4. **Continue down the pipeline** — each skill takes over after its predecessor's gate passes. The persistent stop-hook will re-invoke `/mimiron-resume <slug>` if the session ends mid-pipeline.

If `.mimiron/<slug>/` already exists, do NOT silently overwrite — ask the user whether to continue that slug (`/mimiron-resume <slug>`) or pick a different name.
