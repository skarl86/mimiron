---
name: mimiron-execute
description: Mimiron 파이프라인의 *director* phase. plan.yaml의 DAG를 drain — `mimiron scan`으로 ready[] 받아 worker tier별 Task 도구로 *병렬* dispatch (기본 4개), 각 워커 산출(`result.md` + `artifacts.json`)을 `mimiron commit-task`로 검증 + 마킹. 모든 task가 completed면 phase=evaluate 전이 후 evaluate skill 자동 발동. evaluate fail로 plan에 fix-task가 append되면 같은 loop가 자연스럽게 처리.
---

# execute — Mimiron Phase 4 (Director)

## 사용자 응답 언어

`.mimiron/<slug>/state.json`의 `user_language` 필드를 *시작 시 한 번* 읽어, 사용자에게 보내는 자연어 산문(진행 알림, dispatch/commit 보고)을 그 언어로 작성한다. `null` 이면 가장 최근 사용자 메시지 언어를 자동 감지해 매칭. **dispatch하는 Agent 프롬프트에도 `user_language: <값>` 한 줄을 명시해 worker/tester가 result.md를 같은 언어로 쓰도록 전달.** *task id, 파일 경로, hash 등 결정적 토큰은 영어 유지.*

## 진입 조건

- `state.phase == "execute"` (plan_integrity 게이트 통과 직후)
- `.mimiron/<slug>/plan.yaml` 존재 + `validate()` 통과 (cycle-free, owned_files conflict-free)
- `state.spec_unlocked == false` (spec freeze contract)

## 산출물

- `.mimiron/<slug>/tasks/<task_id>/result.md` (워커가 작성, skill은 검수만)
- `.mimiron/<slug>/tasks/<task_id>/artifacts.json` (워커가 작성, commit-task가 검증)
- `state.completed_task_ids` 갱신 (CLI 책임)
- `state.in_flight_task_ids` 임시 마킹 → completion 시 제거 (CLI 책임)
- 모든 task done → state.phase=evaluate (CLI scan이 phase_done 반환 시 evaluate skill이 다음 phase 운영)

## DAG drain 루프 (skill 본업)

```
┌─ scan ─ ready[] / in_flight[] / phase_done? ──────────────┐
│           │                                                │
│           ▼ (phase_done=true)                              │
│         evaluate skill 자동 발동, exit loop                │
│           │                                                │
│           ▼ (else)                                         │
│       pick ready[0..N] (N = max_parallel, default 4)       │
│           │                                                │
│           ▼                                                │
│       worker tier 결정 (task.worker: worker|tester|reviewer)│
│           │                                                │
│           ▼                                                │
│       Task 도구로 병렬 dispatch                            │
│           │                                                │
│           ▼ (각 워커 응답 도착)                            │
│       mimiron commit-task <slug> <task_id>                 │
│           │                                                │
│           ├─ ok       → completed_task_ids 에 들어감       │
│           └─ reject   → state.retries[task_id]++          │
│                          (3회 도달 → state.phase=stuck)    │
└────────────────────────────────────────────────────────────┘
                            반복
```

### 1) Scan & 종료 판정

1. `mimiron scan <slug>` 호출. 출력 JSON:
   ```json
   {"ready":[..], "in_flight":[..], "pending":[..], "phase_done": bool}
   ```
2. `phase_done == true`:
   - state.phase는 CLI가 자동 전이하지 않음 → *이 skill이* evaluate skill에게 인계.
   - "evaluate skill 진입" 알리고 *현 loop 종료*. 다음 iter는 evaluate.
3. `ready == []` *이고* `in_flight != []`:
   - 다른 in-flight worker 응답을 기다리는 중. 이미 dispatch된 Task의 응답을 받아 commit-task 처리하고 다음 scan으로.

### 2) Tier 별 dispatch

각 ready task의 `task.worker` 값으로 agent 결정:

| `task.worker` | agent | 비고 |
|---|---|---|
| `worker` (default) | `mimiron-worker` | 일반 구현 |
| `tester` | `mimiron-tester` | `tests/**`, `*_test.*` 만 편집 (agent 측 가드) |
| `reviewer` | `mimiron-reviewer` | 평가용 — execute 단계에서 직접 안 부르는 게 정상. plan이 이런 task를 박았다면 의도된 *판정 task*. |

### 3) Worker prompt 구조 (Task tool 호출)

```
description: <task.title>
subagent_type: <agent name>
prompt: |
  ## Slug
  <slug>

  ## Task
  - id: <task.id>
  - title: <task.title>
  - owned_files: <task.owned_files>   ← 이 *밖*은 편집 금지
  - expected_artifacts: <task.expected_artifacts>
  - timeout_s: <task.timeout_s>

  ## Spec excerpt
  <spec.yaml의 *관련* acceptance_criteria + ontology subset>

  ## Dependencies
  - depends_on: <task.depends_on>
  - 위 task들의 result.md 요약 (있다면)

  ## Definition of Done
  - owned_files 안의 변경만
  - expected_artifacts 모두 생성/수정
  - 사람용 result.md 작성 (.mimiron/<slug>/tasks/<task.id>/result.md)
  - 결정적 artifacts.json 작성 (declared_files post_hash 정확)
  - commit-task 가 reject 하지 않도록 *실제로* 파일 mtime 갱신
```

### 4) commit-task 검증

워커 응답이 도착하면 즉시:

```bash
mimiron commit-task <slug> <task.id>
```

- exit 0: task completed → 다음 scan
- exit !=0:
  - stderr에 "reject" 또는 "spec_hash mismatch" 메시지
  - `state.retries[task.id]` 가 ≤ 3 이면 같은 task를 다시 dispatch (워커에게 *재시도* prompt — "이전 결과가 거부됐다. 이유: <stderr>")
  - retry > 3 이면 stuck (CLI가 마킹)

### 5) Fix-task 처리 (evaluate가 plan에 append한 task)

evaluate가 fail로 끝나면 plan.yaml에 `T<원본>-fix` task를 추가하고 state.phase=execute로 회귀시킨다. 이 skill의 다음 iter scan에서 그 task가 자연스럽게 ready로 들어옴 → 동일 흐름.

## 가드

- ❌ **owned_files 밖 편집 금지** — agent prompt에 *강하게* 박고, hooks/post-toolwrite.py 가 위반 시 drift.log에 기록.
- ❌ **spec.yaml mutate 금지** — execute 단계에서 spec freeze contract가 박혀 있음 (commit-task가 매번 검증).
- ❌ **commit-task 우회 금지** — 워커가 "completed" 보고해도 mimiron commit-task 호출 *전에* 다음 scan으로 가지 말 것. 거짓 보고 detection이 이 단계에서 일어남.
- ❌ **agent prompt에 raw spec.yaml 전체 dump 금지** — 관련 acceptance_criteria + ontology subset만. 토큰 절약 + drift 방지.
- ❌ **max_parallel 초과 dispatch 금지** — `_global/thresholds.yaml.max_parallel_workers` (기본 4). 동시 in-flight > N 이면 다음 scan까지 대기.
- ✅ **모든 in-flight task의 응답을 *한 batch*에서 다 수거*하고* 다음 scan**. 부분 수거 후 scan하면 owned_files 계산이 비일관.

## 종료 처리

- `phase_done == true`:
  1. 사용자에게 한 줄 보고: `execute <slug> 완료, 다음: evaluate`.
  2. **evaluate skill에 인계**. 자동 진입 가능 — Claude session이 같은 Stop 응답 안에서 evaluate skill을 발동하면 OK.
- `retry > 3` 또는 `consecutive_gate_fails >= 3`:
  - CLI가 phase=stuck 마킹.
  - unstuck skill 발동 가이드 (`/mimiron unstuck <slug>`).

## 가시성

매 scan-dispatch-commit cycle마다 사용자에게 한 줄:

```
execute <slug>: ▷ T03 (worker, retry 1/3)  ✓ T01  ✓ T02   pending: [T04]
```

(`mimiron status <slug>`의 ASCII와 일치하는 포맷.)

## 다음

- pass → evaluate skill.
- 부분 실패 → 같은 loop의 다음 iter.
- 영구 stuck → unstuck skill (사용자 결정).
