# Dogfood Run 003 — Verification Run

- **Date**: 2026-05-23
- **Subject**: `status-json-flag` slug (Add --json flag to mimiron status)
- **Purpose**: dogfood 002에서 발견된 8 defects의 fix 효과 검증
- **Outcome**: **종주 성공, 새 결함 0건, workaround 0건**.

## 흐름

```
init                       (auto)
   ↓
clarify (ambiguity 0.10)   ✓
   ↓
spec (quality 0.91)        ✓
   ↓
plan                       ✓
   ↓
★ gate plan_integrity      ✓  ← 이전엔 수동 state.phase=execute 편집 필요
   ↓
execute                    ✓
  T01 worker commit ok
  T02 tester commit ok
   ↓
★ gate artifacts           ✓  ← 이전엔 수동 state.phase=evaluate 편집 필요
   ↓
evaluate (mechanical+semantic 1.00)  ✓
   ↓
finalize                   ✓
   ↓
archive (done)             ✓
```

## 8 defects fix 효과 (전후 비교)

| # | dogfood 002 (전) | dogfood 003 (후) |
|---|---|---|
| #1 bootstrap | 수동 `cp evals/python-uv.toml .mimiron/_global/mechanical.toml` + thresholds.yaml 작성 | `init --bootstrap-toolchain=python-uv` 한 줄 |
| #2 Thresholds schema_version | TypeError → schema_version 줄 삭제 우회 | 무시 + 정상 동작 |
| #3 hypothesis 스키마 | TypeError → Hypothesis class 추측 후 dict 형식 | spec/SKILL.md hypothesis 섹션 보고 *바로* 작성 |
| #4/5 verify-kind `in:` | `file:` 추측 → reject 메시지 → `in:` 추측 → 통과 | verify-kind 표 참조해 *첫 시도에 통과* |
| #6 plan→execute | `python -c "..."`로 state.json 직접 편집 | `mimiron gate plan_integrity` 호출 |
| #7 sha256_file Path-only | AttributeError → Path() 감싸기 | `sha256_file('path')` *그대로* 작동 |
| #8 execute→evaluate | state.json 직접 편집 (workaround #2) | `mimiron gate artifacts` 호출 |
| (#9) python3 vs venv | 시행착오 발견 | worker .md 참조해 `.venv/bin/python` |

**Workaround 0건**. 사용자가 spec/SKILL.md + agents/*.md 만 보고 *수동 우회 없이* 종주.

## 측정

- Wall-clock: ~15 minutes (dogfood 002의 ~5 minutes보다 *길어진* 이유: spec.yaml 작성 자체가 단순하지 않음. 흐름 마찰이 아니라 *작성 분량*.)
- 새 commits: 1 feature (status --json) + 3 new tests + 0 fix commits
- 회귀 zero: 194 → 197 tests (+3)

## 새로 발견된 결함

**없음**. 8개 fix가 *완전*했고, 새 dogfood subject에서 *추가 결함이 안 드러남*.

## 다음 가능 작업

1. **Phase B 추가 미충족 해결** (소소한 polish):
   - `mimiron unstuck <slug>` CLI 명령 (현재 skill만 — CLI side는 manual paused)
   - `plan` skill의 plan-notes.md template 보강
   - benchmark suite의 *real Claude judge*가 실제 점수 측정 (사용자가 interactive에서 bench-judge skill 호출)

2. **v0 → v1 졸업 후보** (spec § 7.4 DoD 확인):
   - 5+ benchmarks (현재 3 — B04, B05 큐레이션 1-2 iter)
   - real judge score (interactive dogfood)
   - Live use through real user feature (사용자가 진짜 자기 작업에 굴려보기)

3. **외부 자동화** (v1+ 영역, 이번 v0에선 deferral):
   - GitHub Actions로 nightly bench
   - 그 때는 anthropic SDK 필요

## 결론

**Mimiron v0의 *형태 + 흐름* 둘 다 완성**. 두 번의 dogfood 종주 (002 = 결함 발견, 003 = fix 검증)로 *피드백 루프 완성*. 다음 사용자가 진짜로 굴려도 기존 marginal한 결함은 안 나올 가능성 높음 — 새 결함은 *real interactive use*에서만 드러남.
