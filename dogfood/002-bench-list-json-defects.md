# Dogfood Run 002 — Defect Report

- **Date**: 2026-05-23
- **Subject**: `bench-list-json` slug (Add --json flag to mimiron-bench list)
- **Mode**: 수동 시뮬레이션 (background session — Claude가 worker/reviewer 역할까지 *대신*)
- **Outcome**: 종주 성공 (done phase 도달), 8 defects 발견.

## 흐름 실증

```
init → clarify (ambiguity 0.08 pass)
     → spec (quality 0.92 pass, spec_hash 박힘)
     → plan (DAG 2 tasks: T01 worker + T02 tester depends_on=[T01])
     → execute (T01 commit ok → T02 commit ok → phase_done)
     → evaluate (mechanical pytest+ruff+mypy pass, semantic score 1.00 with 4 ACs)
     → finalize (COMPLETION.md 작성)
     → archive (phase=done, persistent=false)
```

기능적으로 굴러간다. 그러나 *마찰*이 있었음 — 아래 결함 8건.

## 발견된 결함

### 🔴 Critical (블로커 — 사용자가 *수동 우회* 필요)

#### Defect #1 — `.mimiron/_global/` 부트스트랩 없음

- **증상**: `mimiron init <slug>`은 슬러그 디렉토리만 만들고 `_global/`은 안 만든다. `mechanical.toml`/`thresholds.yaml`이 *반드시 필요*한 단계(quality gate, mechanical gate)에서 사용자가 *수동으로* evals/ fixture 복사 + thresholds.yaml 작성해야 한다.
- **임팩트**: 첫 `mimiron init` 후 *gate 호출* 단계에서 막힘. 신규 사용자 onboarding 실패.
- **권장 fix**: `mimiron init`에 `--bootstrap-toolchain=<python-uv|python-pip|node-npm|go>` 옵션. 해당 evals fixture를 `_global/mechanical.toml`로 복사 + 기본 `thresholds.yaml` 작성.
- **우선순위**: ★★★ (실 사용자 첫 경험 막음)

#### Defect #6 — plan → execute phase transition 메커니즘 없음

- **증상**: quality gate 통과 후 phase=plan. plan.yaml 작성 + scan 통과 후에도 phase는 *여전히 plan*. execute phase로 가는 *CLI 명령*도 *자동 hook*도 없음.
- **임팩트**: 사용자가 `state.json`을 *직접 편집* 하지 않으면 execute로 못 들어감 (3-Lane 분리 위반 강제).
- **권장 fix**: `mimiron gate <slug> plan_integrity` 분기 추가 (현재 deferred). `_maybe_transition`에 `("plan", "plan_integrity"): "execute"` 등록.
- **우선순위**: ★★★ (흐름이 *깨짐*, 1차 사용자가 즉시 막힘)

#### Defect #8 — execute → evaluate phase transition 메커니즘 없음

- **증상**: `scan`이 `phase_done: true`를 반환해도 phase는 *여전히 execute*. evaluate skill 진입을 누가 시작하나?
- **임팩트**: 동일 — 사용자가 `state.json`을 직접 편집해야.
- **권장 fix 옵션**:
  - (a) `commit-task`가 *마지막 task* 커밋 시 phase=evaluate 자동 전이
  - (b) 새 CLI 명령 `mimiron gate <slug> artifacts` (spec § 5.2 "a=artifacts gate") — phase_done 검증 후 evaluate 전이
- **우선순위**: ★★★

### 🟡 Documentation gaps (작업은 가능하지만 *어휘 발견*에 시행착오 필요)

#### Defect #3 — `hypothesis` 필드 스키마 미문서화

- **증상**: `spec/SKILL.md`의 spec.yaml 예시에 `hypothesis` 항목이 *없다*. Spec.load는 `Hypothesis(**h)`로 dict 리스트를 기대 (`id`, `claim`, `confidence`). 사용자가 string 리스트로 적으면 `TypeError`.
- **임팩트**: 작성 → 첫 quality gate 호출 → 크래시 → 다시 schema 추측.
- **권장 fix**: `spec/SKILL.md` spec.yaml 예시에 `hypothesis` 섹션 추가 (id/claim/confidence 모두 명시).
- **우선순위**: ★★

#### Defect #4 & #5 — verify-kind `grep` 필드명 미문서화

- **증상**: `spec/SKILL.md`에 `kind: grep, pattern, in` 한 줄. 그러나 `in`이 *YAML 키*인지 *예약어 회피로 `in_`* 인지 명시 안 됨. 실제론 yaml 키 `in:`이 맞고 Python 내부 attr는 `in_`로 매핑된다.
- **임팩트**: 사용자가 `file:`/`path:` 같은 *상식적인 키*를 적으면 reject. 메시지(`verify.kind=grep requires pattern+in`)에서 `in`이 *키 이름*임을 추론해야.
- **권장 fix**: `spec/SKILL.md`에 verify-kind 별 *정확한* yaml schema 표 추가. 예시: `grep: pattern + in (file path)`.
- **우선순위**: ★★

#### Defect #7 — `sha256_file`이 Path만 수용 (agent doc 예시 fail)

- **증상**: `agents/mimiron-worker.md`의 예시 `sha256_file('path/to/file')`이 *바로* `AttributeError: 'str' object has no attribute 'open'`. Path()로 감싸야 함.
- **임팩트**: worker가 artifacts.json 작성 시 hash 계산 첫 시도에서 실패. retry로 회복은 가능하지만 *불필요한 마찰*.
- **권장 fix 옵션**:
  - (a) `sha256_file`이 `str | Path` 둘 다 수용 (signature 확장)
  - (b) agent doc 예시를 `sha256_file(Path('...'))`로 수정
- **우선순위**: ★ (작은 친절)

### 🟢 Minor (편의성)

#### Defect #2 — `Thresholds.load_or_default` schema_version 키 reject

- **증상**: `thresholds.yaml`에 `schema_version: 1`을 적으면 `TypeError: __init__() got an unexpected keyword argument`. State.load는 forward-compat로 unknown keys 필터링하는데 Thresholds는 안 함.
- **임팩트**: spec § 13의 schema versioning policy를 *thresholds.yaml에 적용 못 함*. 향후 migration 어려움.
- **권장 fix**: `Thresholds.load_or_default`에 `_dc_fields(cls)` 필터링 추가 (State.load 패턴 복사).
- **우선순위**: ★★ (schema versioning policy 일관성)

## 권장 fix 순서 (v0 → v1 졸업 전)

1. **#1 + #6 + #8** 묶음 (★★★) — *흐름이 깨짐*. 사용자 진입부터 종착까지 *수동 우회 없이* 굴러가게.
2. **#3 + #4/#5** (★★) — skill/agent .md 문서 패치. 작은 슬라이스.
3. **#2** (★★) — Thresholds forward-compat.
4. **#7** (★) — Path 친화 또는 doc fix.

## 긍정 시그널

- **mechanical gate** — pytest+ruff+mypy 모두 *바로* 통과. python-uv.toml fixture가 mimiron 자체에 *그대로* 적용됨. self-host signal.
- **semantic gate** — 4 AC 결정적 검증(test 3 + grep 1) — reviewer dispatch 없이 score 1.00. spec § 6.4의 "acceptance contract" (reviewer-kind 비율 페널티)가 *spec quality를 올리는 인센티브*로 잘 작동.
- **archive** — phase=done + persistent=false 마킹, COMPLETED.json 잘 박힘. stop-hook 재진입 차단 의도대로.
- **회귀 zero** — 본 dogfood 변경 (--json 플래그) 후 165 → 169 tests (+4), ruff/mypy clean.
