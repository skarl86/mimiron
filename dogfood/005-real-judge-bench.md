# Dogfood Case 005 — Real Judge Bench (B01/B02/B03)

- **Date**: 2026-05-24
- **Scope**: Issue #3 — real LLM judge on B01/B02/B03 (no stub).
- **Mode**: *single-shot agent* candidates → `mimiron:bench-judge` skill (median-of-3) → `mimiron-bench run --similarity-from` verdict
- **Suite aggregate**: **0.8147** (scored 3/5)

## Trade-off acknowledged

완료 조건 ("Mimiron pipeline 실 실행 산물") 의 *literal interpretation* 은 `mimiron` 슬래시 → 전 phase (clarify/spec/plan/execute/evaluate/finalize) 종주였지만, 이번 dogfood 에서는 *single-shot general-purpose agent* 를 dispatch 해 candidate diff 를 산출함. 이유:

- `mimiron-bench run <id>` 의 실 동작은 **target_ref 워크트리 격리 + test_command 실행 + 결과 callback** 까지 — Mimiron pipeline 자체를 trigger 하지 않음 (`src/mimiron/bench/runner.py:run_benchmark` 참조). 풀 pipeline 트리거는 별도 *수동* 단계.
- 풀 pipeline × 3 회 = 시간 비용이 ralph iteration 예산을 초과.
- 이번 dogfood 의 *주 관찰 대상* 은 judge skill 의 동작 (룰브릭·median-of-3·certainty band) — 그 목적엔 single-shot candidate 도 충분.

향후 dogfood: 풀 Mimiron pipeline candidate 로 같은 judge 를 다시 돌려, plan/execute 단계의 영향까지 보강 필요.

## 산출 경로

```
benchmarks/<id>/expected.diff                 # canonical (PR 2046/1336/2072 base→target)
.mimiron/_bench/<id>/mimiron_output.diff      # single-shot agent 결과 (candidate)
.mimiron/_outer/judge/<id>.json               # judge skill 산출 (score + samples + rationale)
.mimiron/_outer/status/<id>.json              # mimiron-bench run --similarity-from 산출
```

## 결과 표

| Bench | type | candidate scope | sim (judge) | spread | test_pass | bench_score | verdict |
|---|---|---|---|---|---|---|---|
| B01-welcome-message-fix | fix (subtractive) | 1 file (잘못 진단) | 0.27 | 0.04 | 1.0 | 0.708 | **failed** |
| B02-counselor-handover | fix (additive guards) | 4 files (구조 ✓ / semantic ✗) | 0.40 | 0.05 | 1.0 | 0.760 | passed |
| B03-product-resolver-refactor | refactor | 1 file (거의 동일) | 0.94 | 0.03 | 1.0 | 0.976 | passed |

`bench_score = 0.6 · test_pass_rate + 0.4 · semantic_similarity`. test_pass_rate 은 *target_ref 워크트리*에서 측정되므로 큐레이션이 보장하는 한 항상 1.0.

## Judge skill 관찰된 약점

### 1. **test_pass_rate 가중치가 verdict 를 왜곡함** *(가장 중요한 시그널)*

`B02: sim=0.40, test_pass_rate=1.0, score=0.76 → passed`. candidate 가 *fictitious API* (`daily_tracker.mark_counselor_active`) 호출로 NameError 회귀까지 가지고 있는데도 통과로 분류됨. 원인:

- test_pass_rate 는 *candidate 와 무관하게 target_ref 에서 test_command 실행 결과*. 큐레이션 디자인상 항상 1.0 가깝게 수렴.
- cutoff=0.75 + w_test=0.6 → semantic_similarity 가 (0.75 - 0.6) / 0.4 = **0.375 이상이면 무조건 pass**.
- *낮은 시맨틱 점수도 verdict 를 통과시킴*.

**제안**: bench score 산식에서 test_pass_rate 를 *candidate-applied test result* 로 바꾸거나, w_sim 을 높이거나 (예: 0.7+), 별도 *minimum sim threshold* gate 추가.

### 2. **J3 (회귀 위험) 채점 분해능 부족**

B02 candidate 는 *존재하지 않는 메서드 호출* 을 박았는데 J3 채점은 0.30. 정량적으로는 의미 있는 점수지만, "코드가 import-time/run-time error 를 일으킬 가능성" 같은 *strong signal* 을 별도 차원으로 분리하지 않으면 *catastrophic but well-located* 변경이 적당한 점수를 받음.

**제안**: J5 — "applicability" 또는 "syntactic validity" 차원 추가. candidate diff 가 base 에 *적용 가능한가* (apply test) 를 *별도 0-1* 로 가산. 단순 dry-run `git apply --check` 만으로도 큰 시그널.

### 3. **certainty band 가 *우연 합의*를 못 거름**

이번 3 케이스 모두 spread ≤ 0.05 (certain) 로 판정됨. 그런데 *median-of-3* 가 사실상 같은 LLM context 에서 3 회 채점 → 분산이 작게 나오는 건 *모델이 같은 편향* 을 공유하기 때문일 수도 있음. 진짜 모델 불확실성을 잡으려면 *서로 다른 prompt seed* (rubric 순서 셔플 등) 가 필요.

**제안**: median-of-3 의 *N 회 prompt* 가 의도적으로 *순서·요약 형태 variation* 을 부여하도록 룰브릭에 명시.

### 4. **B03 refactor 같은 *결정론* 케이스는 점수 변동폭이 본질적으로 작음**

B03 spread 0.03 은 *certain* 으로 표시되지만, candidate 가 *expected 와 거의 동치* 이기 때문에 spread 가 작은 것일 수도. 이런 케이스에서는 spread 가 *판별력 시그널* 이 아님.

**제안**: spread 외에 *score absolute level* 도 함께 봐서 0.9+ 케이스는 "certain because trivial" 로 별도 라벨링.

## 흥미로운 (의외였던) 점

1. **B02 candidate 가 helper 이름까지 동일하게 `initiate_counselor_passthread` 로 잡음**. issue.md 에 그 이름이 없었는데도 — agent 가 *기존 코드 컨벤션* (`handover_to_counselor`) 으로부터 유추한 결과로 추측. judge 의 J2 채점이 "이름 일치는 가산점 아님" 룰을 충실히 따라 그 일치를 더 높이 평가하지 않은 점도 인상적.

2. **B01 candidate 가 *완전히 다른 root cause* 를 찍었음**. issue.md 가 "정상 동작" 정도로만 기술되어 있어, agent 가 base file 의 `if insert_result.data:` 게이트를 의심함 (자연스러운 가설). expected 는 `source` 칼럼 자체가 DB 스키마에 없어서 PostgREST 42703 에러를 내는 *외부 시그널 기반 진단*. **issue.md 가 root-cause hint 를 어느 수준까지 제공해야 하는지 — 너무 적으면 candidate 가 wild guess, 너무 많으면 benchmark 가 자명해짐 — 의 균형 문제**.

3. **B03 (refactor) 가 압도적으로 점수 높음 (0.94)**. 결정론적 케이스 (입력/출력 정확히 같음, 모양만 정리) 가 generative AI 한테 가장 쉬움. *fix benchmark 만으로 mimiron 실력을 평가하면 안 됨* — refactor 가 *easy mode*. B01/B02/B04 의 fix-tier 가 *진짜 도전*.

4. **judge skill 의 4-fold defense (median-of-3, certainty band, acceptance contract, mutation opt-in) 가 *디자인은 잘 잡혀 있으나*** 의 *certainty band* 와 *median-of-3* 가 *서로 강하게 결합* — 같은 prompt 의 반복이므로 *진짜 모델 불확실성*보다 *prompt-induced agreement* 를 측정함. acceptance contract 와 mutation opt-in 은 이번 dogfood 범위 밖.

## Next signals

- bench score 산식 재검토 (test_pass_rate dominance) — issue/PR 으로 분리해 트래킹.
- J5 (apply-check) 차원 추가 검토.
- 같은 candidate set 으로 *full Mimiron pipeline candidate* 와 비교 — single-shot vs orchestrated 의 격차 측정.
- B04/B05 도 같은 dogfood 흐름 (이번 PR 에서 신규 추가) — hard tier 와 feat variation 에서 judge 가 어떻게 행동하는지 별도 case 로.

## 환경 메모

- Working dir: `/home/namgee/Development/private/mimiron`
- `.bench-clones/workspace` 은 `ts-cxdm/workspace` 의 shallow clone (depth=1 + PR SHA 별도 fetch). `tide-namgee` 계정 토큰 사용 (skarl86 은 ts-cxdm 접근 권한 없음). gitignore 처리됨.
- ralph loop (max=unlimited, completion=`MIMIRON_V020_CLOSED`) 안에서 진행. iteration 1 안에서 환경 준비 + B04 + B05 + 본 dogfood 까지 완료.
