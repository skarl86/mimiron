---
name: swebench-lite-adapter
date: 2026-05-24
status: draft
authors: [namgee]
supersedes: none
related: ./2026-05-22-mimiron-design.md
---

# SWE-bench Lite Adapter — PoC

## Summary

SWE-bench Lite (300개 GitHub issue) 의 20개 stratified subset 으로 mimiron 을
*외부 표준 벤치마크* 에 노출시키는 어댑터 PoC. mimiron 의 기존 bench 인프라
(`benchmarks/<id>/benchmark.yaml`, `worktree_iso`, `runner`, `judge`) 를 재활용하고,
신규 컴포넌트는 **dataset importer + non-interactive entry flag + suite-runner skill**
세 가지에 한정. 채점은 **hybrid**: SWE-bench 의 `FAIL_TO_PASS`/`PASS_TO_PASS`
test verdict 와 mimiron 의 semantic similarity 두 축을 동시 기록.

목표: mimiron 의 6-phase pipeline 이 *외부 데이터셋* 에서 어떻게 작동하는지 측정.

## 1. Why (decision context)

mimiron 은 v0.3.0 까지 자체 `benchmarks/B01-B05` 5개 fixture 로 self-eval 을 돌려왔다.
이건 *제어된 환경* 에서 인프라 검증에는 좋지만, mimiron 의 6-phase pipeline 이
*낯선 코드베이스 + 외부 issue text* 에서 어떻게 작동하는지 측정할 수가 없다.

SWE-bench Lite 는 그 갭을 메운다:
- 실제 GitHub issue + 실제 PR patch + 실제 pytest 셀렉터를 가진 300개 instance
- mimiron 의 `benchmark.yaml` 스키마와 **거의 1:1 매핑** (instance_id, repo, base_commit,
  problem_statement, patch, FAIL_TO_PASS/PASS_TO_PASS)
- 표준이라 다른 agent 와 비교 가능

이번 PoC 는 *공식 리더보드 등재* 가 아니라 **mimiron 의 강점/약점 패턴 발견** 이 목표.

## 2. Goals & Non-Goals

### Goals
- SWE-bench Lite 의 20개 stratified instance 를 mimiron fixture 로 변환
- mimiron 을 semi-auto 로 순회 실행 (clarify phase 만 skip, 나머지 6-phase 보존)
- Hybrid verdict 산출: `resolved` (공식 정의) + `bench_score` (mimiron 정의) 동시 기록
- 기존 mimiron core 의 3-Lane 분리 (Creative / Deterministic / Persistence) 유지
- 197 → 210+ passing tests

### Non-Goals (PoC)
- SWE-bench 공식 Docker evaluation harness 통합
- Full 300 instances batch 실행
- mimiron-bench 웹 대시보드 / 시각화
- Multi-language repo 지원 (Java, JS) — Lite 는 Python 전용
- `--clarification-from` 외 phase 의 skip flag (spec-from, plan-from 등)

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ HuggingFace: princeton-nlp/SWE-bench_Lite (300 instances)   │
└─────────────────────┬───────────────────────────────────────┘
                      │  mimiron-bench swebench import --stratified 20
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  benchmarks/SWE-LITE-{instance_id}/                         │
│  ├── benchmark.yaml   (id, repo, base_ref, issue, tests…)   │
│  ├── issue.md         (= problem_statement)                 │
│  ├── expected.diff    (= gold patch)                        │
│  └── _swebench.json   (FAIL_TO_PASS, PASS_TO_PASS, raw …)   │
└─────────────────────┬───────────────────────────────────────┘
                      │  /mimiron-swebench run-suite
                      │   (skill: Claude Code session loop)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  for each fixture (sequential, max parallel = 1):           │
│    /mimiron --clarification-from issue.md \                 │
│             --repo <path-from-yaml> \                       │
│             --output-diff .mimiron/_outer/swebench/...      │
│  (clarify skip → spec → plan → execute → evaluate → patch)  │
└─────────────────────┬───────────────────────────────────────┘
                      │  mimiron-bench run <id> --swebench-tests \
                      │                          --similarity-from <judge.json>
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Hybrid verdict (2-axis):                                   │
│   • test_pass_rate   ← FAIL_TO_PASS + PASS_TO_PASS pytest   │
│   • semantic_sim     ← judge(candidate, gold)               │
│   • resolved         ← test_pass_rate == 1.0  (SWE-bench)   │
│   • bench_score      ← 0.6*test + 0.4*sim     (mimiron)     │
└─────────────────────────────────────────────────────────────┘
```

## 4. Components

| 파일 | 종류 | 책임 |
|---|---|---|
| `src/mimiron/bench/swebench_import.py` | 신규 | HF dataset → `benchmarks/SWE-LITE-XX/` 변환 + stratify 알고리즘 |
| `src/mimiron/bench/swebench_runner.py` | 신규 | `FAIL_TO_PASS` + `PASS_TO_PASS` pytest 실행 → test_pass_rate |
| `skills/mimiron-swebench/SKILL.md` | 신규 | Claude Code 세션에서 fixture 순회 + `/mimiron --clarification-from` 발화 + 집계 |
| `commands/mimiron-swebench.md` | 신규 | `/mimiron-swebench` slash command (skill trigger) |
| `src/mimiron/bench/cli.py` | 수정 | `swebench import` sub-command + `run --swebench-tests` flag |
| `src/mimiron/cli.py` | 수정 | `--clarification-from <file>` flag (clarify skip → state.json 직주입) |
| `pyproject.toml` | 수정 | optional extra `[swebench]` = `["datasets>=2.14"]` |

## 5. Data model

### 5.1 Fixture YAML 확장 (forward-compatible)

```yaml
# benchmarks/SWE-LITE-django__django-11099/benchmark.yaml
id: SWE-LITE-django__django-11099
repo: ../../.bench-clones/swebench/django__django
base_ref: 419a78300f7cd27611196e1e464d50fd0385ff27
target_ref: null                                    # SWE-bench 엔 없음 (gold patch 가 대체)
issue_text_file: issue.md
expected_diff_file: expected.diff
test_command: 'pytest <FAIL_TO_PASS> <PASS_TO_PASS> -q'
difficulty: medium                                  # stratify 계산값
swebench_meta: _swebench.json                       # 신규 필드 (옵셔널)
notes: |
  Imported from princeton-nlp/SWE-bench_Lite
  Original: django/django PR #11099
```

신규 필드는 `swebench_meta` 하나. 기존 fixture (B01-B05) 와 100% forward-compatible.

### 5.2 `_swebench.json` (인스턴스 원본 메타)

```json
{
  "instance_id": "django__django-11099",
  "FAIL_TO_PASS": ["tests/auth_tests/test_validators.py::UsernameValidatorsTests::test_unicode_validator"],
  "PASS_TO_PASS": ["tests/auth_tests/test_validators.py::UsernameValidatorsTests::test_ascii_validator"],
  "version": "3.0",
  "environment_setup_commit": "..."
}
```

## 6. Execution flow (semi-auto loop)

`/mimiron-swebench run-suite` skill 이 Claude Code 세션 안에서:

```
1. List fixtures: glob benchmarks/SWE-LITE-*
2. For each fixture (sequential):
   a. Verify repo cloned at base_ref (importer 가 미리 함, 여기선 sanity check)
   b. Invoke /mimiron --clarification-from <issue.md> --repo <path>
      → mimiron 6-phase 자동 진행, finalize 시 patch 추출
   c. Patch → .mimiron/_outer/swebench/<id>.diff
   d. /bench-judge 로 (gold, candidate) semantic similarity 산출 → judge.json
   e. mimiron-bench run <id> --swebench-tests --similarity-from <judge.json>
      → hybrid verdict 기록 → .mimiron/_outer/status/<id>.json
3. Aggregate: .mimiron/_outer/swebench/REPORT.md
   (per-instance verdict + resolved% + 평균 bench_score + 실패 패턴)
```

Stuck/fail 처리: 한 fixture 가 phase=stuck 가면 그 fixture skip 하고 REPORT 에 표기.
다른 fixture 진행에 영향 없음.

## 7. Hybrid scoring 정의

```
test_pass_rate = pytest(FAIL_TO_PASS ∪ PASS_TO_PASS, on candidate-applied tree) / total
semantic_sim   = judge(candidate.diff, expected.diff)  ∈ [0, 1]
resolved       = (test_pass_rate == 1.0)               ← SWE-bench 공식 정의
bench_score    = 0.6 * test_pass_rate + 0.4 * semantic_sim  ← mimiron 정의
status         = "passed" if bench_score >= 0.75 and resolved else "failed"
```

두 축 다 기록 — `resolved` 는 공식 리더보드 호환, `bench_score` 는 mimiron 자체 비교용.

### 7.1 알려진 빡셈 (PoC 후 튜닝 가능)

- `bench_score >= 0.75 AND resolved` 는 보수적 — `resolved` 가 단 1개 PASS 빠져도 false.
  의미적으로 옳은 패치가 binary 채점에서 실패할 수 있음. 실험 후 cutoff 조정 검토.

## 8. Stratification 알고리즘

SWE-bench Lite 에 `difficulty` 필드가 없으므로 다음 신호로 stratify:

```
size_score    = len(patch)           # 작은 patch ↔ easy
test_score    = len(FAIL_TO_PASS)    # 적은 테스트 ↔ easy
file_score    = patch 가 건드리는 파일 수

difficulty = quantile(size_score + 2*test_score + 3*file_score):
  bottom 33% → easy   (7개)
  middle 34% → medium (7개)
  top    33% → hard   (6개)

repo diversity: 한 repo 당 최대 4개 instance 만 sample
```

결정성: importer 는 `--seed` flag 지원, 동일 seed 면 동일 20개 fixture 생성.

## 9. `--clarification-from` 동작 정의

```
1. mimiron CLI 가 --clarification-from <file> 받음
2. clarify skill 의 quality_score 게이트는 unconditional pass (warning 만 stderr)
3. <file> 내용이 .mimiron/<slug>/clarification.md 로 직접 박힘
4. state.phase = "spec" 로 점프 (clarify skip)
5. 나머지 phase (spec → plan → execute → evaluate → finalize) 정상 진행
```

이유: SWE-bench problem_statement 는 보통 충분히 자세하므로 ambiguity_score ≤ 0.2
게이트를 통과시키려고 LLM 호출하는 건 낭비. PoC 외 일반 회귀 테스트 fixture 로도 재활용 가능.

## 10. Testing

| 테스트 | 위치 | 검증 |
|---|---|---|
| Importer unit | `tests/bench/test_swebench_import.py` | mock HF dataset → fixture YAML 결정성 + stratify 분포 정확성 |
| Runner unit | `tests/bench/test_swebench_runner.py` | FAIL_TO_PASS/PASS_TO_PASS 분리 측정, 부분 통과 비율 정확성 |
| CLI flag | `tests/test_cli_clarification_from.py` | `--clarification-from` → state.json 에 clarification.md 박힘 + phase=spec 점프 |
| Integration | `tests/integration/test_swebench_smoke.py` | mock fixture 1개 end-to-end (importer → run → verdict) |

목표: 197 → 210+ tests passing.

## 11. Risks & Mitigations

| 리스크 | 영향 | 완화 |
|---|---|---|
| HF dataset 다운로드 실패 (오프라인) | Importer 동작 안 됨 | `--from-jsonl <path>` flag 로 로컬 파일 대체 경로 |
| 일부 repo 의 base_ref 클론이 GB 단위 | 디스크 / 시간 폭발 | `--shallow` flag (default ON, depth=1) + `.bench-clones/` 캐시 |
| `--clarification-from` 으로 만든 spec 품질 낮음 | spec phase 실패 → fixture skip | §9 의 quality_score unconditional pass + warning 정책. fixture skip 은 REPORT 에 명시. |
| mimiron pipeline 이 한 fixture 당 5-15분 → 20개 = 1.5-5h | 한 세션 길이 초과 가능 | sequential 진행 + state.json 으로 재개 가능. skill 이 중단 지점 기억 |
| Docker 없이 pytest 실행 → repo 의존성 충돌 | False negative (테스트 환경 문제로 실패) | `worktree_iso` 격리 + uv venv per fixture. 실패 시 REPORT 에 "env_error" 카테고리 |

## 12. Open questions (PoC 중 결정)

- mimiron 이 한 fixture 에서 stuck 갔을 때 unstuck skill 을 자동 호출할지 vs skip 할지
  (현재 안: skip — PoC 는 자동성 우선)
- `resolved=False, bench_score>=0.75` 인 케이스의 분류 — partial credit 줄지 fail 처리할지
  (현재 안: REPORT 에 `partial` 카테고리 별도 표기, status 는 failed)
- 실패 fixture 의 retry 정책 — 1회 vs N회 (현재 안: 0회, PoC 라 결과 재현성 우선)

## 13. Out of scope

- SWE-bench 공식 evaluation harness 통합 (Docker)
- Full 300 instances 자동 batch
- 결과 시각화 / 웹 대시보드
- 비용 추적 (token usage per fixture)
- Multi-language repo
