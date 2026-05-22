---
name: mimiron
date: 2026-05-22
status: draft
authors: [namgee]
supersedes: none
related: ../../../../../harness  # v1 harness sibling project, not replaced
---

# Mimiron — Adaptive Multi-Agent Harness for Claude Code

## Summary

Mimiron은 Claude Code용 *멀티 에이전트 하네스 플러그인*이다.
요청 → 명세 → 계획 → 병렬 실행 → 평가 → 마무리의 6-페이즈 파이프라인을
**Creative / Deterministic / Persistence 3-레인 아키텍처**로 분리해 운영하며,
페이즈 전이는 *정량 게이트*만이 결정하고, 세션이 끊겨도 *Stop hook 자가 재시작*으로
이어지되, 무한 루프를 막는 4-겹 안전핀과 일급 `unstuck` 안전핀을 갖춘다.

이름은 워크래프트의 키퍼-엔지니어 **Mimiron**에서 따왔다. 그의 설화에는
"정교한 자동화는 자기 자신을 가둘 수 있다, 그래서 외부 구조가 필요하다"
라는 본 디자인의 핵심 모순이 그대로 박혀 있다.

## 1. Why Mimiron (not a v1 successor)

사용자는 이미 `private/harness/`에 5-페이즈(Clarify → Context → Plan → Generate → Evaluate) 파이프라인 플러그인 v1을 가지고 있다. Mimiron은 그것을 *대체하지 않는다*. v1을 건드리지 않고 완전히 별도 프로젝트로 만든다.

차별점은 **실행 단계**다. v1은 단일 에이전트 순차 실행이지만 Mimiron은 DAG 기반 병렬 실행 + 워커 역할 분리 + Stop hook persistent loop를 가진다. spec rigor(ouroboros 영향)는 유지하면서, 실행에서 OMC의 멀티 에이전트 패턴을, 평가에서 superpowers의 verification-before-completion 사상을 흡수한다.

벤치마크 결과는 별도 파일로 분리 예정 (`docs/superpowers/specs/benchmarks/`).

## 2. Goals & Non-Goals

### Goals
- 한 슬래시 커맨드로 spec → 병렬 실행 → 평가까지 자동 진행
- 페이즈 전이가 *정량 게이트*만으로 결정되어 재현 가능
- 세션이 끊겨도 자동 재개. 단, 무한 루프 방어 4겹 + `unstuck` 안전핀
- 결정적 장부와 창의 작업의 분리(레인 계약) — v1의 핵심 가치 계승
- v0 → v1 졸업까지 dogfood만으로 검증

### Non-Goals (v0)
- 멀티 프로바이더 오케스트레이션(codex/gemini와의 협업) — 별도 플러그인
- 웹 대시보드 / 슬랙 알림 — 파일 + CLI로 충분
- Prometheus / OTel 같은 메트릭 수집
- 일반 Claude Code 워크플로 대체 — 의도된 사용 케이스에만 발동

## 3. The 3-Lane Architecture

기존 v1의 2-레인(Creative + Deterministic)을 확장한다.

| 레인 | 누가 | 무엇을 | 절대 안 함 |
|---|---|---|---|
| **Creative** | Claude skills + subagents | clarify·spec·plan·구현·평가 추론 | sidecar/state.json 쓰기 금지 |
| **Deterministic** | `mimiron` CLI (Python stdlib + PyYAML) | DAG 스캔, 재개 지점 계산, gate 통과 판정, 파일 소유권 충돌 감지, 아카이브 | LLM 호출 금지 |
| **Persistence** | `stop-hook.py` | state.json을 보고 phase ≠ done이면 resume 프롬프트 재투입 | 그 외 일체 금지 (가볍게) |

### 6-Phase Pipeline

```
clarify ──gate(ambiguity≤τ)──▶ spec ──gate(quality≥0.85)──▶ plan
                                                              │
                              ┌───────────────────────────────┘
                              ▼
                          execute (DAG) ──gate(artifacts present)──▶ evaluate
                              ▲                                       │
                              │                                       │ pass
                              │ retry(≤3)                             ▼
                              └────────fail───── gate(mech+sem) ── finalize
```

**핵심 원칙**
1. 각 페이즈는 *다음 페이즈를 자동 시작*하지만 gate 미통과 시 멈춤
2. `unstuck` 발동 조건: gate 3회 연속 실패 / 동일 task 재시도 3회 / state 손상

## 4. Components

### 4.1 Plugin Directory Layout

```
mimiron/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── commands/                              # thin wrappers (5)
│   ├── mimiron.md                         # /mimiron <feature>
│   ├── mimiron-resume.md
│   ├── mimiron-status.md
│   ├── mimiron-pause.md
│   └── mimiron-unstuck.md
├── skills/                                # creative-lane logic (9)
│   ├── clarify/SKILL.md
│   ├── spec/SKILL.md
│   ├── plan/SKILL.md
│   ├── execute/SKILL.md                   # director
│   ├── evaluate/SKILL.md
│   ├── finalize/SKILL.md
│   ├── resume/SKILL.md
│   ├── status/SKILL.md
│   └── unstuck/SKILL.md
├── agents/                                # worker tiers (3)
│   ├── mimiron-worker.md                  # default: 일반 구현
│   ├── mimiron-tester.md                  # test 페이즈 전용, 구현 파일 편집 금지 가드
│   └── mimiron-reviewer.md                # semantic gate 심판, 코드 수정 금지
├── hooks/
│   ├── hooks.json                         # SessionStart, Stop, PostToolUse
│   ├── session-start.py                   # 진행 중 slug 컨텍스트 주입
│   ├── stop-hook.py                       # persistent 모드 자동 재투입
│   └── post-toolwrite.py                  # drift 감지 (v0: warn, v1+: reject)
├── scripts/
│   └── mimiron.py                         # deterministic CLI
├── dogfood/                               # archived self-built features
├── evals/                                 # mechanical gate fixtures
└── tests/                                 # cli/hooks/integration
```

### 4.2 Per-Project Sidecar Layout

```
<프로젝트 루트>/
└── .mimiron/
    ├── <slug>/
    │   ├── state.json                  # CLI-only deterministic ledger
    │   ├── clarification.md            # clarify 단계 산출
    │   ├── spec.yaml                   # acceptance criteria, ontology
    │   ├── plan.yaml                   # DAG: tasks, depends_on, owned_files
    │   ├── tasks/<task_id>/
    │   │   ├── prompt.md               # worker input
    │   │   ├── result.md               # worker summary
    │   │   └── artifacts.json          # touched files + lines
    │   ├── evaluation/
    │   │   ├── mechanical.json
    │   │   ├── semantic.md
    │   │   └── verdict.json
    │   └── archive/
    └── _global/
        ├── thresholds.yaml             # ambiguity_max, spec_quality_min 등
        └── mechanical.toml             # 프로젝트 build/test/lint 명령
```

`_global/`은 팀 공유용으로 git 커밋. `<slug>/`는 기본 `.gitignore` (개인 환경에 머무름).

### 4.3 CLI Commands (LLM 호출 0개)

| 명령 | 역할 |
|---|---|
| `mimiron init <slug>` | sidecar 디렉토리 생성, state 초기화 |
| `mimiron scan <slug>` | ready task JSON 반환 (DAG + 파일 충돌 검사) |
| `mimiron commit-task <slug> <task_id> --artifacts <files…>` | mtime + content hash 검증 → state 갱신 (v0는 mtime만, v1+에서 content hash 도입) |
| `mimiron gate <slug> <phase>` | mechanical은 `mechanical.toml` 실행, semantic은 외부 입력 받음 |
| `mimiron next <slug>` | 사람·skill용 한 줄 요약 |
| `mimiron archive <slug>` | sidecar를 `archive/`로 이동 |
| `mimiron unstuck <slug> --reason "..."` | state=paused, persistence 차단, 보고서 생성 |
| `mimiron ls` | 진행중/완료/막힘 슬러그 목록 |
| `mimiron inspect <slug> <task_id>` | 한 task 풀 컨텍스트 한 화면 |
| `mimiron replay <slug> --from <phase>` | 특정 phase 재실행 |
| `mimiron export <slug>` | tar.gz 패키징 (이슈 리포트용) |

### 4.4 Worker Tiers (Hybrid: 단일 + 역할별)

- `mimiron-worker` (default): 일반 구현 task. 모든 컨텍스트는 plan task instruction으로 주입.
- `mimiron-tester`: system prompt에 *강한 가드* — "오직 `*_test.*`, `tests/**` 파일만 편집". `plan.yaml`에서 `worker: tester`로 명시.
- `mimiron-reviewer`: semantic gate 심판 전용. *코드 수정 절대 금지*, 판정 markdown만 생성.

도메인별(backend/frontend)로 더 쪼개는 건 dogfood에서 필요해질 때까지 보류.

## 5. Data Flow & Lifecycle

### 5.1 Happy Path

예: `/mimiron "Flask /version 엔드포인트 추가"`

```
[T+0]  /mimiron "Flask /version 엔드포인트 추가"
[T+1]  clarify skill → Socratic 인터뷰 → ambiguity ≤ 0.2 → clarification.md
[T+2]  spec skill → spec.yaml 결정화 → quality_score ≥ 0.85
[T+3]  plan skill → DAG 작성 (T01 route, T02 test, T03 changelog) →
       cycle-free + file-ownership-clean
[T+4]  execute skill (director) → mimiron scan → ready=[T01, T03] →
       Task 도구로 mimiron-worker × 2 병렬 → 끝나면 commit-task →
       ready=[T02] → mimiron-tester가 T02 실행 → commit-task
[T+5]  scan → ready=[], pending=[] → phase=evaluate
[T+6]  evaluate skill → mimiron gate mechanical (pytest, ruff, mypy) →
       mimiron-reviewer가 semantic 판정 → verdict=pass → phase=finalize
[T+7]  finalize skill → mimiron archive → commit 제안
```

### 5.2 State Transition Diagram

```
   clarify ──τ──▶ spec ──q──▶ plan ──c──▶ execute ──a──▶ evaluate ──v──▶ finalize ─▶ done
      ▲             ▲           ▲            ▲│              ▲│
      │             │           │      retry │└── fail ──────┘│
      │             │           │      ≤3    │                │
      │             │           │            ▼                │
      └─────────────┴───────────┴─────── stuck ◀──── fail × 3 ┘
                                            │
                                            ▼
                                         paused (via unstuck)
```

(τ=ambiguity gate, q=quality gate, c=plan integrity gate, a=artifacts gate, v=evaluate gate)

### 5.3 DAG Scheduler Contract

`mimiron scan <slug>` 호출 시:
1. `state.completed_task_ids` ∪ `state.in_flight_task_ids`로 진행 중인 task 파악
2. 각 pending task에 대해:
   - 모든 `depends_on`이 completed인가?
   - `owned_files`가 in-flight task와 충돌 없는가?
3. 위 둘 다 만족하는 task를 `ready[]`로 반환

Director skill은 `ready[]`에서 *최대 `max_parallel_workers`개*(기본 4, `_global/thresholds.yaml`로 조정) 만큼 Task 도구를 병렬로 dispatch. 각 워커는 `result.md` + `artifacts.json`을 적고, `commit-task`가 *artifacts.json 선언 파일이 실제로 mtime 갱신됐는지 검증* → LLM이 거짓 보고하면 reject.

**Fix-task 생성**: gate(evaluate) 실패 시 director skill이 실패 원인을 분석해 `plan.yaml`에 `T<원본>-fix`라는 추가 task를 자동 append (depends_on=원본 task). 이때 retry 카운터는 *원본 task* 기준으로 증가.

### 5.4 Persistent Stop Hook

```
Claude 응답 종료 (Stop event)
    │
    ▼
stop-hook.py: .mimiron/*/state.json 스캔
    │
    ├─ persistent=true AND phase ∉ {done, stuck, paused} → "/mimiron resume <slug>" 재투입
    └─ 그 외 → 종료, 사용자 차례
```

#### 무한 루프 방어 4겹
1. Gate가 phase 전이를 막음 → resume이 *같은 작업*을 반복할 수 없음 (gate 통과 못 하면 다음 phase로 못 감)
2. Task 재시도 카운터 ≤ 3 (state.retries[task_id])
3. Gate 연속 실패 ≥ 3 → phase=stuck
4. `unstuck` skill 발동 → paused=true, stop-hook 비활성

> 🟡 **재확정 예정**: 5번째 안전핀(슬러그당 총 LLM 호출 budget)이 필요한지는 persistent-loop 구현 시점에 결정.

## 6. Error Handling & Observability

### 6.1 Failure Classes

| 클래스 | 감지 | 자동 대응 | 사용자 표면 |
|---|---|---|---|
| 드리프트 (owned 밖 쓰기) | PostToolUse hook | warn+log (v0), reject (v1+) | `.mimiron/<slug>/drift.log` |
| 거짓 완료 (artifact 누락) | `commit-task` mtime 검사 | task retry++ | `scan` 결과의 `rejected:` |
| 메커니컬 게이트 실패 | `gate mechanical` | execute로 회귀, fix-task | `evaluation/mechanical.json` |
| 시맨틱 게이트 실패 | reviewer 판정 | spec diff 분석, retry or 사용자 | `evaluation/semantic.md` |
| 재시도 소진 | scan 시 카운터 | phase=stuck, persistence 차단 | unstuck 자동 진입 |
| CLI 자체 오류 | exit≠0 | persistence 즉시 정지 | `mimiron.error.log` (fatal만, 평상시는 `mimiron.log`) |
| 사용자 중단 (`/mimiron pause`, Ctrl-C) | CLI paused=true | stop-hook 비활성 | status에 `paused` 배지 |
| 컨텍스트 오버플로 | 감지 어려움 | 관찰만 | status에 토큰 추정치 |

### 6.2 Observability Surfaces

**`mimiron status <slug>` 사람용 렌더링**
```
flask-version-endpoint  [persistent ✓]
├─ phase:    execute  (DAG draining, 2/3 done)
├─ gates:    spec ✓ (0.91)  plan ✓  mechanical ?  semantic ?
├─ tasks:
│   ✓ T01 add-route          (mimiron-worker,  12s)
│   ✓ T03 changelog          (mimiron-worker,   4s)
│   ▷ T02 add-test           (mimiron-tester,  in_flight, retry 1/3)
└─ next:     scan → wait for T02 completion
```

**`mimiron ls`**: 전체 슬러그 한눈에. **파일 자체**: `.mimiron/<slug>/`는 git log/blame로 history 추적 가능.

### 6.3 Logging Policy

- `mimiron.log`: JSON Lines, CLI 호출별 한 줄. *LLM 출력 안 들어감*.
- `tasks/<id>/result.md`: 워커 산출 요약. Raw transcript는 보존 안 함.
- `drift.log`: PostToolUse hook이 owned 밖 쓰기 감지 시 추가.
- Secret 가드: clarify skill 본문에 "spec에 API key 등 secret을 적지 않는다" 인스트럭션.

### 6.4 Unstuck Skill (안전핀의 인격화)

루프 정책이 default-on이라 unstuck는 *일급 컴포넌트*. 사람을 적극 호출하는 게 본업.

```
/mimiron unstuck flask-version-endpoint
  ├─ state=paused, persistence 차단
  ├─ 사람용 보고서 (.mimiron/<slug>/unstuck.md):
  │   - 어디서 막혔나 (phase, last gate, last task)
  │   - 시도된 retry 이력
  │   - 다음 행동 3가지 ("임계 낮춰 재시도" / "plan 수정" / "archive")
  └─ 사용자 결정 대기
```

## 7. Testing & Dogfood Strategy

### 7.1 3-Tier Pyramid

```
        / E2E (dogfood) \
       /  Integration   \
      / Unit (CLI logic) \
     ─────────────────────
```

- **Tier 1 (Unit)** — `scripts/mimiron.py`는 LLM 호출 0개라 완전 결정적. pytest로 ≥90% 커버.
- **Tier 2 (Stub LLM)** — `MIMIRON_STUB=1` 환경변수로 skill이 LLM 결과 대신 `tests/fixtures/<phase>/<scenario>.md`를 읽음. 시나리오는 YAML 선언:
  ```yaml
  # tests/scenarios/happy_path.yaml
  feature: "add /version endpoint"
  expected_phases: [clarify, spec, plan, execute, evaluate, finalize]
  expected_artifacts: [.mimiron/*/spec.yaml, app/routes.py, ...]
  gate_outcomes: [spec=pass, plan=pass, mechanical=pass, semantic=pass]
  ```
- **Tier 3 (Dogfood)** — Mimiron이 어느 정도 돌면 *자기 자신을 만드는 도구*로 사용. `dogfood/00N-*/` 에 케이스별 sidecar archive 보존. `dogfood/_learnings.md`에 매 케이스 끝나고 한 줄 기록.

### 7.2 Hook & Worker Testing

- Hook: stdin/stdout JSON 픽스처 비교 (`tests/hooks/`).
- Worker (subagent): 체계적 테스트는 비용 대비 부적합. PR template에 transcript 첨부 요구 (superpowers 패턴 차용).

### 7.3 CI

GitHub Actions 단일 워크플로: unit(~30s) + stub-e2e(~2m) + lint. Dogfood는 CI에 안 넣음 — 로컬 PR 체크리스트로 강제.

### 7.4 v0 → v1 Definition of Done

- [ ] Tier 1 단위 테스트 통과
- [ ] Tier 2 happy + drift + retry + stuck 시나리오 통과
- [ ] Dogfood 3건 이상 archive에 보존
- [ ] README 한/영 1쌍
- [ ] 보류 결정 3개를 dogfood 근거로 명시 확정

## 8. Deferred Decisions (재확정 예정)

persistent-loop 구현 시점에 dogfood 근거로 확정:

1. 🟡 **Gate를 phase 전이의 *유일한* 게이트키퍼로 유지할지** — v0 기본값 yes, dogfood하다 부적합하면 *조건부 강제*로 약화.
2. 🟡 **무한 루프 방어 4겹이 충분한지** — 부족하면 5번째(슬러그당 총 LLM 호출 budget) 추가.
3. 🟡 **PostToolUse 드리프트 가드 강도** — v0는 `warn + log`, dogfood로 신뢰 쌓이면 `hard reject`로 승급.

## 9. Optional: Lore Naming Convention

Mimiron 세계관(워크래프트 키퍼 + 청동용군단)을 컴포넌트 이름으로 확장 가능. *권장이지 강제 아님*.

```
agents/
├── hephaestus-worker.md      # 일반 구현 (제작의 신)
├── apollo-reviewer.md        # semantic gate 심판 (판정)
├── minerva-spec.md           # spec architect (지혜)
└── ...
hooks/
├── algalon-observer.py       # PostToolUse drift 감지 (관찰자)
└── chromie-resume.py         # unstuck steward (시간 위기 도우미)
```

이 컨벤션을 채택하면 README에서 "팀의 캐릭터화"로 디자인 의도를 한눈에 전달 가능.

## 10. Open Questions (디자인 시점 미해결)

- **멀티 프로바이더(codex/gemini)?** — v0는 Claude 단일. 별도 플러그인으로 분리.
- **`.mimiron/<slug>/` 커밋 vs gitignore 기본값?** — v0는 `.gitignore` 추가, 팀이 커밋 원하면 명시적으로.
- **Skill 자동 발동 vs 명시 호출?** — v0는 슬래시 커맨드 5개로 명시. superpowers식 SessionStart 자동 주입은 dogfood 후 검토.

## 11. Scoring Rubrics (v0 정의)

게이트가 사용하는 정량 점수의 v0 정의. 모두 *LLM 자가 평가*(skill 본문에 룰브릭 첨부)로 산출하되, dogfood로 검증·튜닝.

- **ambiguity_score** (0~1): clarify 끝 시점에 reviewer agent가 산출. 1 = 완전 모호, 0 = 완전 명확. *기본 임계 ≤ 0.2*. 평가 항목: missing acceptance criteria, undefined terms, conflicting goals.
- **spec_quality_score** (0~1): spec 끝 시점에 reviewer agent가 산출. 1 = 결함 없음, 0 = 사용 불가. *기본 임계 ≥ 0.85*. 평가 항목: criteria testability, ontology completeness, constraint specificity.
- **mechanical verdict** (pass/fail): `_global/mechanical.toml`의 명령 exit code AND, 모두 0이면 pass.
- **semantic verdict** (pass/fail/needs_review): reviewer agent가 spec.acceptance_criteria 대비 산출물을 항목별 채점한 뒤 결정.

룰브릭의 *세부*는 각 skill의 SKILL.md에 작성. v0는 휴리스틱, v1+에서 정량 보정.

## 12. Glossary

- **slug**: 한 기능 단위의 식별자. `.mimiron/<slug>/` 디렉토리 이름.
- **sidecar**: 프로젝트 루트의 `.mimiron/<slug>/` 디렉토리 전체. state + 산출물.
- **owned_files**: plan task가 *편집할 권한을 선언*한 파일 경로 리스트. 워커는 이 밖을 못 씀.
- **gate**: phase 종료 전에 통과해야 하는 정량 검사. CLI가 verdict 발급.
- **phase**: clarify | spec | plan | execute | evaluate | finalize 중 하나.
- **lane**: Creative | Deterministic | Persistence — 책임 분리 단위.
- **director**: execute skill 본인. 워커 dispatch를 담당.
