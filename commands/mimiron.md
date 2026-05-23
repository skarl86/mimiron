---
description: Start a new Mimiron feature run — clarify → spec → plan → execute → evaluate → finalize.
argument-hint: <feature description in natural language>
allowed-tools: Skill, Bash, Read, Write, Edit, Grep, Glob, Task, AskUserQuestion
---

Start a new Mimiron pipeline run for this feature request:

$ARGUMENTS

Steps:

1. **Pick a slug** — a short kebab-case identifier derived from the feature request (e.g., "flask-version-endpoint"). Confirm it matches `^[a-z0-9][a-z0-9-]{0,62}$`. If the user supplied no clear name, ask via AskUserQuestion.
2. **Pick the user language** — this gets persisted to `state.user_language` and every downstream skill/agent honors it when speaking to the user:
   - *Detect* the dominant natural-language script in `$ARGUMENTS` (Hangul → Korean, Latin → English, etc.). Treat the detection as a *suggestion*, not a decision.
   - Use **AskUserQuestion** with up to 4 options to confirm. Put the detected language first as "(추천 / Recommended)". Always include at least one other major option and an "Auto-detect each session" (`user_language=null`) escape. Example option set for a Korean-looking request:
     - "한국어 (Recommended)" — `Korean`
     - "English" — `English`
     - "Auto-detect each session" — leave `null`, every skill picks up the latest user message's language at runtime
   - If the user picks an "Other" option, capture the free-form string as-is (e.g. `日本語`, `Spanish`) — it's a hint to Claude, not a code.
3. **Initialize**: run `mimiron init <slug>` (CLI). Pass `--language "<value>"` *unless* the user chose auto-detect (then omit the flag entirely). This creates `.mimiron/<slug>/state.json` with `phase=clarify, persistent=true, user_language=<value-or-null>`.
4. **Hand off to `mimiron-clarify` skill** via the Skill tool. The clarify skill reads `state.user_language` at start and conducts the Socratic interview in that language. It writes `clarification.md`, runs `mimiron gate <slug> ambiguity`, and transitions to spec.
5. **Continue down the pipeline** — each skill takes over after its predecessor's gate passes, all honoring `state.user_language`. The persistent stop-hook will re-invoke `/mimiron-resume <slug>` if the session ends mid-pipeline; resume preserves the language choice because it's stored in state.json.

If `.mimiron/<slug>/` already exists, do NOT silently overwrite — ask the user whether to continue that slug (`/mimiron-resume <slug>`) or pick a different name.
