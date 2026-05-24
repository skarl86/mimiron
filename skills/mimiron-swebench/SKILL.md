---
name: mimiron-swebench
description: SWE-bench Lite suite 를 mimiron pipeline 으로 순회 실행 + hybrid verdict 집계. `/mimiron-swebench` 슬래시 커맨드로 트리거되며, benchmarks/SWE-LITE-* fixture 들을 sequential 하게 돌리고 .mimiron/_outer/swebench/REPORT.md 를 생성한다. Importer 가 이미 돌아 fixture 가 준비된 상태가 전제.
---

# mimiron-swebench — SWE-bench Lite suite runner

## 사용자 응답 언어

이 skill 은 outer orchestrator 라 호출 컨텍스트에 `user_language` 단서가 있으면 그걸 따른다 (각 fixture 의 inner mimiron run 은 자체 `state.user_language` 를 가짐 — 영향 없음). 없으면 사용자 메시지 언어를 자동 감지. REPORT.md 의 헤더/푸터/스키프 reason 같은 사람 읽는 산문이 그 언어 적용 대상. 파일 경로, fixture id, JSON 키, status enum 은 영어 유지.

## When to invoke

User invokes `/mimiron-swebench` (or asks "SWE-bench 돌려" / "swebench suite run").

전제: `benchmarks/SWE-LITE-*/` fixture 들이 이미 존재. 없으면 먼저 사용자에게 안내:

```
mimiron-bench swebench import --from-jsonl <path> --stratified 20 --seed 42
```

또는 `--from-hf <dataset>` 옵션. fixture 가 0 개면 skill 종료 (REPORT 생성 안 함).

## Execution loop

```
1. List fixtures: glob benchmarks/SWE-LITE-* (정렬, deterministic order)
2. State file: .mimiron/_outer/swebench/cursor.json
   {"completed": [...], "skipped": [...], "current": null}
   재개 시 이 파일 읽어서 이미 끝난 건 skip
3. For each remaining fixture (sequential):
   a. Verify repo clone: benchmark.yaml 의 repo 경로 + base_ref 존재 확인
      → 없으면 cursor 에 skip 기록 + reason="missing_clone", 다음 fixture
   b. mimiron init <slug> --clarification-from <fixture>/issue.md
      (slug = SWE-LITE-XX 의 소문자/dash 정규화)
   c. /mimiron-resume <slug>  로 6-phase 자동 진행
      (clarify 는 skip, spec → plan → execute → evaluate → finalize 진행)
   d. finalize 직후 .mimiron/<slug>/result.diff 추출
      → .mimiron/_outer/swebench/<fixture>.diff 로 복사
      → .mimiron/_bench/_input/<fixture>.diff 로도 복사 (T7 wiring 호환)
   e. bench-judge skill 호출:
      input: (expected.diff, candidate.diff)
      output: .mimiron/_outer/judge/<fixture>.json {score: 0~1, rationale}
   f. mimiron-bench run <fixture> --swebench-tests --similarity-from <judge.json>
      → .mimiron/_outer/status/<fixture>.json 작성
   g. cursor.json 업데이트 (completed 에 추가)
4. Aggregate → .mimiron/_outer/swebench/REPORT.md:
   - Header: Suite, N instances, M completed, K skipped
   - Per-instance row: id | resolved | bench_score | test_pass_rate | semantic_sim | reason
   - Footer:
     - resolved%: M_resolved / M_completed
     - avg bench_score (completed)
     - skipped reasons distribution
```

## Stuck / fail handling

- `phase=stuck` 도달 fixture: cursor 에 skip 추가, `reason="mimiron_stuck"`, 다음 fixture 진행
- spec phase 게이트 실패 (quality_score 낮음): skip, `reason="spec_quality"`
- 환경 에러 (clone 없음, 의존성 충돌): skip, `reason="env_error"`
- 0 retry 정책 (PoC). retry 는 사용자가 명시적으로 `/mimiron-resume <slug>` 호출.

## Output format

`.mimiron/_outer/swebench/REPORT.md`:

```
# SWE-bench Lite — Mimiron PoC Run

Generated: 2026-05-24T10:00:00Z
Mimiron: v0.X.0
Fixtures: 20 (7 easy / 7 medium / 6 hard)

## Aggregate

- Completed: 18 / 20
- Skipped: 2 (env_error: 1, mimiron_stuck: 1)
- Resolved: 4 / 18 (22.2%)
- Avg bench_score: 0.413

## Per-instance

| ID                              | resolved | score | test | sim   | reason |
| SWE-LITE-django__django-11099   | ✓        | 0.92  | 1.0  | 0.80  | ok     |
| SWE-LITE-sympy__sympy-13441     | ✗        | 0.40  | 0.5  | 0.25  | ok     |
| SWE-LITE-astropy__astropy-7166  | -        | -     | -    | -     | env_error |
| ...                             |          |       |      |       |        |
```

## Don'ts

- 절대 mimiron core code 수정하지 말 것 — 이 skill 은 orchestrator 일 뿐
- 한 fixture 가 stuck 됐다고 unstuck skill 자동 호출하지 말 것 (사용자 결정 영역)
- 결과 파일을 deleting 으로 정리하지 말 것 (debugging 용 보존)
- 병렬 실행 금지 (PoC 는 sequential — 워크트리 충돌·자원 폭주 회피)
