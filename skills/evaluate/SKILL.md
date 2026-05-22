---
name: mimiron-evaluate
description: Mimiron 파이프라인의 evaluate phase. execute 페이즈가 *DAG drain* 완료(모든 task completed)된 직후 자동 발동, mechanical + semantic 두 게이트를 순서대로 운영. mechanical은 결정적 CLI(`mimiron gate <slug> mechanical`)에 위임, semantic은 *이 skill*이 reviewer agent를 dispatch 해 4-fold judge defense(median-of-3, certainty band, acceptance contract, mutation opt-in)로 판정. semantic 결과는 `.mimiron/<slug>/evaluation/semantic.{md,json}`에 기록되어 다음 단계(`mimiron gate <slug> semantic`)가 verdict로 합산. 게이트 실패 시 `plan.yaml`에 `T<원본>-fix` task를 append 해 execute 회귀.
---

# evaluate — Mimiron Phase 5

## 진입 조건

- `state.phase == "execute"` *이고* `mimiron scan <slug>`이 `phase_done: true` 반환 (모든 task completed)
- 또는 외부 시그널 (사용자 / hook)이 evaluate 진입을 요구

## 산출물

- `.mimiron/<slug>/evaluation/mechanical.json` — 결정적 (cmd: `mimiron gate <slug> mechanical`)
- `.mimiron/<slug>/evaluation/semantic.md` — 사람이 읽는 reviewer 보고서
- `.mimiron/<slug>/evaluation/semantic.json` — 스키마는 verdict.json (§ 12.4) 준수. CLI가 다음 단계에서 그대로 읽음.
- 실패 시: `plan.yaml`에 `T<원본>-fix` task append + state.gate_history 한 줄

## 흐름

### 0) Sanity 진입

1. `mimiron status <slug>` → phase=execute 확인.
2. `mimiron scan <slug>` → `phase_done: true` 확인. 아니면 execute로 *돌려보내고* 끝.

### 1) Mechanical gate (deterministic 위임)

3. `mimiron gate <slug> mechanical` 실행. CLI가 `_global/mechanical.toml`의 build/test/lint 명령을 spawn.
4. 결과는 `.mimiron/<slug>/evaluation/mechanical.json`에 자동 기록 + state.gate_history 한 줄.
5. **mechanical fail → fix-task 추가 후 종료** (아래 § 4 참조). semantic까지 갈 필요 없음 — build/test 깨진 코드를 reviewer에게 보여주는 건 token 낭비.

### 2) Semantic gate (creative — *이 skill의 본업*)

6. spec.yaml의 `acceptance_criteria[]`를 읽기. 각 AC의 `verify.kind`별 처리:
   - `kind: test` → AC.verify.command를 `subprocess`로 실행. exit 0이면 pass. (LLM 호출 없음)
   - `kind: grep` → AC.verify.pattern을 owned 파일에 grep. 매치되면 pass. (LLM 호출 없음)
   - `kind: in` → AC.verify.expected 값이 산출에 있으면 pass.
   - `kind: pattern` → 정규식 매치.
   - `kind: reviewer` → mimiron-reviewer agent dispatch (아래 § 3).
7. 모든 AC 결과를 모아 `ac_results: [{id, verdict, note}]`로 정리.
8. **종합 점수** 산출:
   - `score = (passed_ac_count) / (total_ac_count)`
   - reviewer 판정 점수가 있다면 그것의 median을 별도 reviewer_score로 보존.
9. **4-fold judge defense** 적용 (이미 spec 단계서 일부 적용됐어도 evaluate에서 *재적용*):
   - **Median-of-3 + temp=0**: reviewer-kind AC는 모두 3회 호출, median.
   - **Certainty band**: `score ∈ [cutoff - 0.05, cutoff + 0.05]`이면 `verdict: needs_review` 강제.
   - **Acceptance contract**: spec.yaml에 reviewer-kind가 50% 초과면 *spec 단계*에서 페널티가 이미 박혔어야 함 — evaluate에서 재차 페널티 적용 *금지* (double count 방지).
   - **Mutation 룰** (`--mutate-tests` 플래그 / `_global/thresholds.yaml.enable_mutation=true`): 활성 시 reviewer에게 *implementation 5종 변형* 요청, 각 mutant에 test 실행. `mutation_score = killed/total`이 0.6 미만이면 test 보강 fix-task 자동 추가.

### 3) Reviewer agent dispatch (kind=reviewer AC 처리)

10. 각 reviewer-kind AC에 대해 `mimiron-reviewer` agent를 Task 도구로 3회 dispatch (median-of-3):
    ```
    prompt: |
      acceptance criterion: <AC.desc>
      verify.contract: <AC.verify.contract — reviewer 판단 룰브릭>
      changed files (task artifacts.json 기준): <file list>
      worker summaries: <task result.md 모음>
      ---
      0~1 점수 + 한 줄 rationale로 답하라. 코드 *수정 금지*.
    ```
11. 3 응답에서 median 점수 + rationale.

### 4) 종료 처리

- **pass** (`score ≥ cutoff_evaluate`, default 0.80, certainty band 밖):
  - `semantic.json` 작성 (verdict.json schema, kind=semantic, verdict=pass)
  - `semantic.md` 작성 (사람이 읽는 보고서: 어떤 AC가 어떻게 검증됐는지)
  - **다음 액션 안내**: `mimiron gate <slug> semantic` (deterministic CLI가 verdict.json 합산 + state.phase=finalize 전이)
- **fail** (`score < cutoff_evaluate - 0.05`):
  - `semantic.{md,json}` 작성 (verdict=fail)
  - 실패 AC를 분석해 `plan.yaml`에 fix-task append:
    ```yaml
    tasks:
      - ...기존...
      - id: T03-fix              # 원본이 T03인 경우
        title: "fix(T03): <실패 AC.desc> 보완"
        worker: worker            # 또는 tester (test 보강 시)
        depends_on: [T03]
        owned_files: [<원본 owned_files 유지>]
        expected_artifacts: [<해당 산출물>]
        timeout_s: 900
    ```
  - state.gate_history에 한 줄 + state.consecutive_gate_fails++
  - **3연속 fail이면 phase=stuck → unstuck skill 자동 발동**.
  - 그 외엔 state.phase=execute로 회귀 → director가 fix-task 처리.
- **needs_review** (certainty band 안):
  - `semantic.{md,json}` 작성 (verdict=needs_review)
  - state.paused = true
  - 사용자에게 한 줄 보고:
    ```
    evaluate <slug>: needs_review (score=0.XX, samples=[..], band=[0.75, 0.85])
    → mimiron unstuck <slug> 으로 결정
    ```

## 산출 형식

### `semantic.json` (verdict.json schema § 12.4 준수)

```json
{
  "schema_version": 1,
  "slug": "<slug>",
  "phase": "execute",
  "kind": "semantic",
  "verdict": "pass" | "fail" | "needs_review",
  "score": 0.0,
  "samples": [s1, s2, s3],
  "ts": "<ISO8601>",
  "details": {
    "ac_results": [
      {"id": "AC01", "kind": "test",     "verdict": "pass", "note": "exit 0"},
      {"id": "AC02", "kind": "reviewer", "verdict": "pass", "note": "interfaces match spec ontology"},
      {"id": "AC03", "kind": "reviewer", "verdict": "fail", "note": "edge case X not handled"}
    ],
    "reviewer_score_median": 0.78,
    "reviewer_score_samples": [0.75, 0.78, 0.82],
    "rationale": "<200자 미만 정리>"
  }
}
```

### `semantic.md` (사람용 보고서)

```markdown
# evaluate — <slug>

- **Verdict**: pass/fail/needs_review
- **Score**: 0.XX (samples=[..])
- **Cutoff**: 0.80 (certainty band ±0.05)

## Acceptance Criteria 검증 결과

### AC01 — test
- 명령: `<cmd>`
- 결과: pass (exit 0)

### AC02 — reviewer
- 룰브릭: <AC.verify.contract>
- 점수: 0.85 (median of [0.80, 0.85, 0.90])
- 판정: pass
- 근거: <reviewer rationale>

### AC03 — reviewer
- 점수: 0.40 (median of [0.35, 0.40, 0.45])
- 판정: fail
- 근거: 엣지 케이스 X 미처리
- **다음 액션**: T03-fix 추가됨

## 종합

<한 단락 요약>
```

## 가드

- ❌ **spec.yaml mutate 금지**. 평가 결과로 acceptance criteria를 *완화*하지 말 것. spec 변경은 unstuck flow의 `state.spec_unlocked=true` 경유만.
- ❌ **owned_files 침범 금지**. evaluate는 *판정*만, 코드 수정은 fix-task 통해 worker에게 위임.
- ❌ **mechanical 통과 전에 semantic 실행 금지**. build/test 깨진 코드를 reviewer가 평가하면 신호가 노이즈에 묻힘.
- ❌ **reviewer-kind AC가 acceptance criteria의 100%**: spec 단계서 잡혀야 함. 만약 누락이면 evaluate에서 *경고 + 사용자 결정* 요청 (자동 진행 금지).
- ✅ **median-of-3 + temp=0 강제**. reviewer dispatch 3회 모두 같은 prompt + temperature=0.
- ✅ **fix-task append는 *원자적*** (plan.yaml mutate 시 임시 파일에 write 후 rename).

## 다음

- pass → `mimiron gate <slug> semantic` → 결정적 verdict.json 작성 + phase=finalize → finalize skill 진입.
- fail → state.phase=execute 회귀 → director (execute skill) 가 fix-task 처리.
- needs_review → state.paused → 사용자 결정 (unstuck skill).
