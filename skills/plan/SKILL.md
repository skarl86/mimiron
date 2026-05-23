---
name: mimiron-plan
description: |
  Mimiron 파이프라인의 plan phase. spec.yaml(acceptance_criteria + ontology + constraints)을 입력으로 plan.yaml(DAG of tasks)을 결정화. 각 task는 id, title, worker tier, depends_on, owned_files, expected_artifacts, timeout_s 필드를 가진다. cycle-free + ownership conflict-free + dangling depends_on 없음. spec_hash 필드를 state.spec_hash에서 복사해 freeze contract 준수. `mimiron scan <slug>`이 결정적 검증을 수행하고, plan_integrity 게이트 통과 시 phase=execute 전이.
---

# plan — Mimiron Phase 3

## 사용자 응답 언어

`.mimiron/<slug>/state.json`의 `user_language` 필드를 *시작 시 한 번* 읽어, 사용자에게 보내는 자연어 산문(진행 알림, plan.yaml의 `title`·`description` 등 사람이 읽는 텍스트)을 그 언어로 작성한다. `null` 이면 가장 최근 사용자 메시지 언어를 자동 감지해 매칭. *task id, owned_files, worker tier 등 결정적 토큰은 영어 유지* — 자연어 산문에만 적용.

## 진입 조건

- `state.phase == "plan"` (quality gate 통과 직후)
- `.mimiron/<slug>/spec.yaml` 존재 + validated
- `state.spec_hash != null` (quality gate가 박았어야)

## 산출물

- `.mimiron/<slug>/plan.yaml` — schema § 12.3 준수
- (옵션) `.mimiron/<slug>/plan-notes.md` — 사람용 설계 메모 (task split rationale, DAG 모양 설명)

## 흐름

### 1) Spec 흡수

1. `spec.yaml` 읽기. `acceptance_criteria`, `constraints`, `ontology` 모두 손에 잡힘.
2. 각 AC를 *어느 task가* 만족시킬지 *역방향*으로 매핑:
   - 같은 코드 경로를 손대는 AC는 *하나의 task*로 통합
   - 독립적인 AC는 *분리된 task*로 — 병렬화 + retry 격리
   - test AC (verify.kind=test/grep)는 tester tier task로 분리

### 2) DAG 작성

각 task 행:

```yaml
- id: T01                           # 단조 증가 (T01, T02, ...)
  title: "<무엇을 하는 task인가>"
  worker: worker | tester | reviewer  # default "worker"
  depends_on: [task_id, ...]
  owned_files: [<상대경로>, ...]    # 이 task만 편집
  expected_artifacts: [<상대경로>, ...]  # 끝나면 *반드시* 존재해야 할 파일
  timeout_s: 600                     # 기본 600, 큰 task는 1200
```

**owned_files 룰**:
- 같은 파일을 *두 task*가 owned 하면 plan.validate()가 reject (cycle-free 다음 검사).
- 같은 파일 변경이 정말 두 task에 걸쳐 필요하면 → *한 task로 합치거나*, 두 번째 task의 `depends_on`에 첫 번째를 넣고 owned_files를 *분할*(예: 함수 단위) — 단 owned는 파일 단위라 분할 어려움 → 보통 합침이 답.

**worker tier 선택**:
- 기본 `worker` — 일반 구현.
- 테스트만 다루는 task → `tester` — agent가 *_test.*, tests/** 외 편집 거부.
- 평가용 task가 plan에 들어가는 건 *드물지만 가능* → `reviewer`. 다만 일반적으로 reviewer dispatch는 evaluate skill 책임.

### 3) spec_hash 박기

```yaml
schema_version: 1
slug: <slug>
spec_hash: <state.spec_hash 그대로 복사>
tasks:
  - ...
```

**중요**: `spec_hash`를 *재계산하지 말 것*. state.spec_hash는 quality gate가 박은 *그 시점의* spec.yaml 해시. plan은 그 spec을 기준으로 만들어진 것. 재계산하면 plan-time spec 가능성이 들어와 freeze contract 의미가 약해짐.

### 4) Validation (skill 내부)

작성한 plan.yaml을 `Plan.load + validate()` (또는 결과 동일한 `mimiron scan <slug>` 호출)로 *결정적* 검증:

- **Cycle**: depends_on의 DAG가 사이클 없음 (DFS WHITE/GRAY/BLACK)
- **Ownership conflict**: 두 task가 같은 파일을 owned 하면 reject
- **Dangling depends_on**: 존재하지 않는 task id를 depends_on에 적었으면 reject
- **spec_hash 일치**: plan.spec_hash와 state.spec_hash 비교

`mimiron scan <slug>`이 `phase` 외 위 모든 검증을 자동 수행 — 출력 JSON 또는 exit code로 판단.

### 5) Plan integrity gate

- *현재 v0*: scan이 reject 없이 ScanResult를 반환하면 *plan integrity OK*로 간주.
- *예정 v1*: `mimiron gate <slug> plan_integrity` 분기 (CLI에 미구현, deferred — 추가되면 verdict.json 박힘).

### 6) 종료 처리

- pass → 사용자에게 한 줄 보고:
  ```
  plan <slug> committed: N tasks (T01..T0N), DAG depth=<d>, ready=[T01, T02]
  ```
- 자동 진입: execute skill (CLI가 state.phase=execute 박는 단계가 v0에 *없음*; 사용자 수동 호출 또는 다음 phase 자동 발동 전제. v1에서 plan_integrity gate가 채울 자리).

## 가드

- ❌ **spec.yaml mutate 금지**. plan은 *spec을 입력으로* 받는다, 출력 아님.
- ❌ **owned_files 중복 금지**. plan.validate가 강제하지만, 작성 단계에서 *의식적*으로 피할 것.
- ❌ **task당 owned_files >5 권장 안 함**. 큰 task는 retry 비용 큼. 5개 이상이면 분할 고려.
- ❌ **task 100개 이상**. plan이 너무 크면 evaluate가 분석 비용 폭발. 25 이하 권장.
- ❌ **expected_artifacts에 *상위 디렉토리* 추가 금지**. 파일 단위로 명시 (worker가 디렉토리 생성도 자동으로 함).
- ✅ **task title에 *동작 동사*로 시작** ("add ...", "extract ...", "fix ..."). 사용자 status 화면이 읽힘.
- ✅ **timeout_s는 worker tier 별 보수적으로**. tester는 600, worker는 600~900, 복잡한 worker는 1200.

## 룰브릭 (plan integrity 자가 평가, 옵션)

각 0~1, 평균을 *plan_score*로 (CLI 게이트 아님, 사람용 self-check):

- P1: AC ↔ task 매핑 *완전성* (모든 AC가 ≥1 task로 커버되는가)
- P2: 병렬화 *효율* (depends_on이 *진짜 의존*만, 과도하게 직렬화 안 됨)
- P3: owned_files 분할 *균등* (한 task가 너무 큰 owned 갖지 않음)
- P4: tester task *적절한 비율* (test가 spec에 있는데 worker 단독 task만 있으면 ↓)

`plan_score < 0.7`이면 plan-notes.md에 *왜 이렇게 짰는지* 적기.

## 다음

- plan.yaml + scan ok → execute skill 진입 (사용자 또는 stop-hook 재투입).
- plan.validate fail → 같은 skill에서 *다시 작성*. 3회 실패 → unstuck 권유.
