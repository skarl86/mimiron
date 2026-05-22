---
name: mimiron-finalize
description: Mimiron 파이프라인의 *최후* phase. evaluate가 pass(`gate semantic` → state.phase=finalize)로 끝난 직후 자동 발동. archive/COMPLETION.md (사람용 종합 보고서) 작성, 사용자에게 commit 제안 (변경 파일 목록 + 메시지 초안), `mimiron archive <slug>` 호출로 state.phase=done + persistent=false 박아 stop-hook re-entry를 차단. evaluate fail 회귀로 다시 돌아온 슬러그도 같은 흐름.
---

# finalize — Mimiron Phase 6 (종착)

## 진입 조건

- `state.phase == "finalize"` (semantic gate pass 직후)
- `.mimiron/<slug>/evaluation/verdict.json` 또는 `semantic.json`의 `verdict == "pass"`

## 산출물

- `.mimiron/<slug>/archive/COMPLETION.md` — 사람이 읽는 종합 보고서
- `.mimiron/<slug>/archive/COMPLETED.json` — CLI(`mimiron archive`)가 작성하는 결정적 종착 마커
- state.phase = "done", state.persistent = false (CLI 책임)
- 사용자에게 *제안*: `git add` 후보 + commit message 초안

## 흐름

1. **사전 확인**: `mimiron status <slug>` → phase=finalize, gates 마지막 verdict=pass.
2. **변경 합산**:
   - 모든 `.mimiron/<slug>/tasks/<task_id>/artifacts.json` 을 읽고,
   - `declared_files[]` 의 path 들을 *유니크하게* 합집합 → 변경 파일 목록.
   - 각 파일의 action(create/modify/delete) 카운트.
3. **`archive/COMPLETION.md` 작성** (사람이 읽는 보고서):
   - 헤더: 시작/완료 시각, wall-clock, 최종 phase, token usage
   - Gate history 표 (phase / kind / verdict / score)
   - 완료된 task 목록 (id / title / worker / 소요)
   - 변경 파일 목록 (path / action)
   - Acceptance criteria 검증 결과 (id / verdict / note) — semantic.json 의 `details.ac_results` 그대로
   - **Suggested commit** 블록 — `git add <files>` + `git commit -m "<scope>: <goal>"` 초안
   - "Outstanding (Mimiron 밖)" — deferred 항목 (없으면 `(none)`)
4. **`mimiron archive <slug>` 호출** — CLI가 결정적으로 phase=done + persistent=false + COMPLETED.json 박음. 이걸 *반드시* 호출해야 stop-hook 재진입이 멈춤.
5. **사용자 보고** (한 줄):
   ```
   ✓ <slug> finalized. Report: .mimiron/<slug>/archive/COMPLETION.md
   Next: review the suggested commit and run `git commit` yourself.
   ```

## 가드

- ❌ **`git commit` 자동 실행 금지**. 제안만, 결정은 사용자.
- ❌ **`mimiron archive` 호출 *생략* 금지**. skip하면 stop-hook이 무한 재진입 (persistent=true 상태로 phase=finalize).
- ❌ **archive 디렉토리에서 *기존 sidecar 파일 이동/삭제* 금지**. archive는 *snapshot* 목적. 원본은 `.mimiron/<slug>/` 그대로.
- ❌ **spec/plan/state 직접 mutate 금지**. CLI(`mimiron archive`)를 경유.

## 다음 (slug 차원)

- state.phase = "done" → stop-hook 비활성, 슬러그 상 종착.
- 새 feature 작업은 `/mimiron "<새 요청>"` (새 slug)로 시작.

## 다음 (Mimiron 차원, 이 slug와 무관)

- `mimiron-bench run` self-eval 굴려 *방금 만든 변경*이 benchmark suite에 어떻게
  반영되는지 outer-loop 단에서 측정 가능.
