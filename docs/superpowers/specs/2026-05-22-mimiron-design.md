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
│   ├── mimiron.py                         # deterministic CLI
│   └── mimiron-bench.py                   # self-evaluation CLI (outer loop)
├── benchmarks/                            # self-eval fixtures (real merged PRs)
│   ├── _cutoff.yaml                       # cutoff_global, weights, version
│   ├── B01-<topic>/{benchmark.yaml, issue.md, expected.diff}
│   └── B0N-.../...
├── dogfood/                               # archived self-built features (inner-loop logs)
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

**Spec freeze contract**: plan.yaml은 `spec_hash: <sha256(spec.yaml)>` 필드를 보존(§ 12.3). CLI `scan`/`commit-task`/`gate`가 매번 spec.yaml의 현재 해시를 비교 → 불일치면 *즉시 stuck*. spec을 다시 만지려면 `unstuck` 경로로 `state.spec_unlocked=true`를 명시적으로 켜야 함. plan 진입 후 spec mutation을 *구조적으로* 차단.

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

#### 무한 루프 방어 6겹 (default-on persistence의 보호장치)

Persistence가 default-on이라 *완성도 관점에서 강한 캡*이 필수.

1. Gate가 phase 전이를 막음 → resume이 *같은 작업*을 반복할 수 없음 (gate 통과 못 하면 다음 phase로 못 감)
2. Task 재시도 카운터 ≤ 3 (state.retries[task_id])
3. Gate 연속 실패 ≥ 3 → phase=stuck
4. `unstuck` skill 발동 → paused=true, stop-hook 비활성
5. **Wall-clock cap** (default-on에서 *자동 활성*): 슬러그당 wall-clock ≤ 4h (`_global/thresholds.yaml.wall_clock_max_s` 조정). 초과 시 paused.
6. **Token budget cap** (default-on에서 *자동 활성*): 슬러그당 LLM 입력+출력 토큰 ≤ 500K (`thresholds.yaml.token_budget`). 초과 시 paused.

5·6번은 `persistent=true`인 슬러그에서만 자동 발동. opt-in `--persist` 호출이면 사용자 명시 — 그 경우에도 cap은 기본 활성, 끄려면 `--no-cap`.

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

### 6.4 Judge 비결정성 방어 (4겹)

LLM 게이트는 같은 입력이라도 점수가 흔들린다. 이걸 *4겹*으로 방어한다.

1. **Median-of-3 + temperature=0**: 모든 LLM 게이트(ambiguity, quality, semantic_verdict, semantic_similarity)는 `temperature=0`으로 *3회 호출*해 median 사용. `verdict.json.samples` 필드에 raw 3개 보존(§ 12.4).
2. **Certainty band**: 점수가 `[cutoff - 0.05, cutoff + 0.05]` 안이면 자동 `verdict: needs_review` → state=paused, 사용자 승인 대기. 그레이존을 LLM 단독 판단에 안 맡김.
3. **Acceptance criteria 검증 컨트랙트**: spec.yaml의 각 `acceptance_criteria[].verify.kind`가 `test` / `grep` / `reviewer` 중 하나. *reviewer 단독*이 50% 초과면 spec quality_score에 페널티(0.1 차감). 주관적 검증을 *구조적으로* 제한.
4. **Test mutation 룰** (`--mutate-tests` 옵션, v0 default off): evaluate 단계가 reviewer에게 *implementation을 변형해* 5종 mutant 생성 요청, 각 mutant에 test 실행. `mutation_score = killed/total`이 임계(0.6) 미만이면 *test 보강* fix-task 자동 추가. LLM 호출 5~10배 증가하므로 v0에선 opt-in.

### 6.5 Unstuck Skill (안전핀의 인격화)

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

**v0.1.0 (form complete) 충족 현황** (2026-05-23):

- [x] Tier 1 단위 테스트 통과 — **197 passing** (ruff + mypy clean)
- [x] Tier 2 happy + drift + retry + stuck 시나리오 통과 — `test_hooks.py` (drift), `test_cli_commit_task.py` (retry), `test_cli_gate_semantic.py` (stuck), 모든 unit으로 커버
- [ ] **`mimiron-bench suite` aggregate score ≥ 0.75** (cutoff_global) — *부분 충족*: B01 stub score 0.94. real LLM judge 미적용 (v1.0.0 → real judge interactive dogfood 필요)
- [ ] **최소 3개 benchmark가 `solved`** (deferred 아님) — *부분 충족*: B01 passed (stub), B02/B03 deferred. v1.0.0에 real judge 박힌 후 충족 가능
- [x] Dogfood 3건 이상 archive에 보존 — `dogfood/001-b01-manual-run/`, `dogfood/002-bench-list-json-defects.md`, `dogfood/003-status-json-flag-verify.md`
- [x] README 한/영 1쌍 — v0.1.0 트렌디 재작성 (signature image, badges, quick start, architecture)
- [x] 보류 결정을 dogfood 근거로 명시 확정 — § 8 참고: 5/7 확정, 2개 v1으로 deferral

**v0.1.0 → v1.0.0 남은 두 항**은 real LLM judge interactive dogfood 1회로 충족 가능. 본 spec의 *형태(form)*는 완성, *기능 완성(function complete)*은 v1.0.0 milestone.

## 7.5 Self-Evaluation Harness & Ralph-Loop Termination

Mimiron 자체의 개발을 ralph-loop로 자동 진행하기 위한 *outer loop* 의 평가 인프라. **inner loop**(Mimiron이 한 feature를 구동) 와 분리된 별개의 메커니즘이다.

### 7.5.1 두 루프의 분리

| 차원 | Outer loop (ralph-loop) | Inner loop (Mimiron persistent) |
|---|---|---|
| 목적 | "Mimiron 자체를 완성도 있게" | "이 feature를 끝까지 구현" |
| 구동자 | ralph-loop 플러그인 | `stop-hook.py` |
| 종료 조건 | bench suite aggregate ≥ cutoff | inner phase=done OR phase=stuck |
| 각 iter | benchmark 한 건 실행 + 코드 수정 | 다음 phase로 진행 |
| 실패 시 | Mimiron 자체 코드 수정 후 retry | gate retry or unstuck |

### 7.5.2 Benchmark Fixture 포맷

`benchmarks/<id>/benchmark.yaml`:
```yaml
id: B01-flask-version-endpoint
repo: ../harness-sample             # 로컬 레포 경로 (worktree 격리 사용)
base_ref: abc123                    # PR 직전 커밋
target_ref: def456                  # PR 머지 커밋
issue_text_file: issue.md           # Mimiron에 주는 입력
expected_diff_file: expected.diff   # 원본 PR diff (similarity 비교용)
test_command: "pytest tests/test_version.py"
difficulty: easy
notes: |
  PR 원문 링크나 컨텍스트 메모.
```

### 7.5.3 Scoring Formula

```
bench_score(case) = (test_pass_rate × w_test) + (semantic_similarity × w_sim)
case_passed       = bench_score ≥ cutoff_case
suite_aggregate   = mean(bench_score for all non-deferred cases)
ralph_terminate   = suite_aggregate ≥ cutoff_global
                  OR all_cases ∈ {solved, deferred}
```

**기본값** (`_cutoff.yaml`):
- `w_test = 0.6`, `w_sim = 0.4`
- `cutoff_case = 0.75`, `cutoff_global = 0.75`
- 테스트 없는 PR(문서·설정): `w_test=0` 자동 재정규화, `w_sim=1.0`

**점수 정의**:
- `test_pass_rate` (0~1): `target_ref`의 테스트(또는 PR이 추가한 테스트)를 Mimiron 산출물에 대해 실행. *위조 어려운* 신호.
- `semantic_similarity` (0~1): reviewer agent가 Mimiron diff와 expected diff를 비교. 항목: (1) intent alignment, (2) interface compatibility, (3) test coverage parity, (4) code organization. v0는 LLM 자가 평가, v1+에서 AST 기반 정량 보강.

### 7.5.4 Bench CLI

| 명령 | 역할 |
|---|---|
| `mimiron-bench run <id>` | 단일 케이스 실행, JSON verdict (`{test_pass_rate, semantic_similarity, bench_score, passed, deferred}`) |
| `mimiron-bench suite` | 전체 benchmarks/ 실행, aggregate + 케이스별 표 |
| `mimiron-bench list` | 케이스 상태 목록 (solved / failed / deferred / pending) |
| `mimiron-bench compare <ref1> <ref2>` | 두 브랜치 점수 비교 (regression 감지) |

각 케이스 실행은 다음 시퀀스:
1. `repo`를 워크트리로 격리, `base_ref`로 reset
2. Mimiron 파이프라인 자동 실행 (`issue_text`를 입력)
3. inner loop가 phase=done 또는 stuck/paused까지 진행
4. 산출 diff 수집 → `expected_diff` 비교 → similarity
5. `test_command` 실행 → test_pass_rate
6. `bench_score` 계산, verdict.json 작성

### 7.5.5 Ralph-Loop Iteration Model

`ralph-loop:ralph-loop`이 구동하는 외부 사이클:

```
while suite_aggregate < cutoff_global:
    1. next_case = mimiron-bench list --status pending,failed --next
    2. result   = mimiron-bench run <next_case>
    3. if result.passed:
         → mark solved, continue
       else:
         → 실패 진단 (어느 phase, 어느 gate, worker drift 등)
         → Mimiron 자체에 최소 변경 적용
         → 같은 case 재실행 (≤ 3회)
         → 3회 실패 시: deferred 마킹, 다음 case로
    4. 매 N iteration마다 mimiron-bench suite로 regression 체크
```

#### Outer Loop Meta Safety Pins

Ralph-loop이 영영 안 멈추는 시나리오를 방어한다. 5겹:

1. **Iteration hard cap**: outer loop 총 iteration ≤ 30. 도달 시 정지, 사용자 호출.
2. **점근 정체 감지**: 직전 5 iteration의 `suite_aggregate` 변화가 모두 < 0.02 → 정지, *"변화가 없습니다"* 보고.
3. **All-deferred 정지**: `mimiron-bench list`가 모든 케이스를 deferred로 표시하면 정지, *"벤치마크 재큐레이션 필요"* 보고.
4. **Wall-clock budget**: outer loop 총 wall-clock ≤ 24h (configurable). 도달 시 정지.
5. **사용자 abort**: `mimiron-bench --abort` — 다음 iteration 시작 전에 우아하게 정지, 진행 보존.

각 정지마다 `.mimiron/_outer/halt-report.md`에 *다음 액션 제안 3가지* 자동 작성.

### 7.5.6 Bootstrap Problem (Phase A / B 분리)

Mimiron이 *조금이라도* 돌아야 bench가 의미 있다. 그래서 implementation plan은 두 단계로 나눈다.

**Phase A — 수동 구현 (ralph-loop 불가)**

6개 체크포인트로 분해. 각 체크포인트는 *독립 PR로 머지 가능*하고, *그 자체로 test 가능*. 다음 체크포인트는 이전 게 안정될 때 진입.

| 체크포인트 | 결과물 | 졸업 조건 |
|---|---|---|
| **A1** | `mimiron init/ls/status` 동작 | state.json 읽기/쓰기 unit test 통과 (schema § 12.1 준수) |
| **A2** | `mimiron scan` + plan.yaml 파싱 | 가짜 plan.yaml로 DAG 스캔 + 파일 충돌 검사 unit test 통과 |
| **A3** | `mimiron gate mechanical` + `commit-task` | 가짜 mechanical.toml + mtime 검증 통합 테스트 |
| **A4** | `clarify` skill (LLM stub) | `MIMIRON_STUB=1` fixture로 happy path 통합 |
| **A5** | `spec` skill + spec gate (ambiguity·quality) | spec.yaml 결정화 → quality_score gate (median-of-3) 통과 |
| **A6** | `mimiron-bench run B01` 인프라 + B01 수동 종주 | `bench run B01`이 *deferred 아닌* JSON verdict 반환 (점수 무관) |

A6 졸업이 Phase A 졸업이고, Phase B 진입 자격.

**Phase B — ralph-loop 가능**

- outer loop 진입, B01 정식 평가
- 미해결(execute director, evaluate, finalize, persistence loop, unstuck, drift hook, bench suite 큐레이션)을 ralph가 iterative하게 보완
- 종료: § 7.5.5의 5겹 메타 안전핀 중 하나 발동, OR `suite_aggregate ≥ 0.75` + 최소 3개 solved

대략 Phase A = plan의 앞 40~50%(체크포인트 6개), Phase B = 나머지.

### 7.5.7 Goodhart 방지 가드

- **Benchmark suite는 *다양하게* 큐레이션**: easy/medium/hard, 코드/문서/리팩터, 단일 파일/다중 파일이 골고루.
- **Similarity는 *보조*, test 통과는 *주***: similarity만 높고 test fail이면 절대 passed 아님 (`w_sim`만으로 cutoff 못 넘게 가중치 설계).
- **신규 benchmark 추가 시 *기존 score 재계산*** 필수 — 추가만으로 점수 인플레 방지.
- **reviewer agent에 ground-truth 정답을 노출 안 함** — Mimiron diff만 보고 그 자체로 acceptance criteria 충족 여부 판단 후, *별도로* similarity 산출.

### 7.5.8 Benchmark Suite (v0 후보)

| ID | 출처 | 난이도 | 가설 |
|---|---|---|---|
| B01 | `harness-sample` 작은 endpoint 추가 PR | easy | 10~30 LOC, single file |
| B02 | `harness` 자체 옵션 추가 PR (메타) | easy | 기존 함수에 flag 추가 + test |
| B03 | `harness-sample` 작은 리팩터 | medium | ~100 LOC, behavior preserve |
| B04 | 외부 OSS bug fix | medium | regression test 포함 |
| B05 | 새 모듈 도입 | hard | ~200 LOC, multi-file |

후보 PR은 사용자의 기존 레포 git log에서 발굴 (Phase A 마지막에 큐레이션).

## 8. Deferred Decisions (재확정 예정)

dogfood 근거로 확정. 모두 v0의 *기본값은 정해져 있고*, 보정만 dogfood 후.

> **v0.1.0 (2026-05-23) 업데이트**: 7개 결정 중 **5개는 dogfood 002+003 근거로 확정**, **2개는 v1.0.0까지 재배치**(real LLM judge 의존성).

1. 🟢 **Gate를 phase 전이의 *유일한* 게이트키퍼로 유지할지** — **확정: yes**. dogfood 002/003 모두 5개 gate(ambiguity/quality/plan_integrity/artifacts/semantic) 단독으로 깔끔한 phase 전이 운영. *조건부 강제* 필요한 시그널 없음.
2. 🟢 **Persistence cap 임계값** — **확정: `wall_clock_max_s=14400`(4h), `token_budget=500K` 유지**. dogfood 002 (~5분) + 003 (~15분) 모두 임계 훨씬 아래. 정상 작업 끊김 시그널 0건.
3. 🟢 **PostToolUse 드리프트 가드 강도** — **확정: v0는 warn+log 유지**. dogfood 002/003 모두 owned_files 안에서 작업 — drift 감지 발동 안 됨. *드리프트 시 사용자 반응* 측정 데이터 부족, v1+ 재평가.
4. 🟡 **Benchmark cutoff 및 가중치** — **v1까지 deferred**. real LLM judge 없이 stub 점수로만 측정 — false-pos/neg 비율 신뢰 불가. v0.1.0의 `cutoff_case=0.75, cutoff_global=0.75, w_test=0.6, w_sim=0.4` 유지.
5. 🟢 **Benchmark suite 큐레이션** — **v0.1.0 확정: 3개(B01/B02/B03)**. 모두 *tide-namgee 작성, `naver-smartstore` 라벨* 머지 PR. 외부 OSS 후보는 v0.2.0에서 B04+B05로 추가.
6. 🟡 **Test mutation 룰 활성화 여부** — **v1까지 deferred**. dogfood 002/003은 mutation 없이 통과 — *가치 대비 비용* 측정 필요. v0는 `--mutate-tests` opt-in 유지.
7. 🟢 **Component count 트리밍** — **확정: 22 components 유지**. dogfood 003에서 전체 layout이 *마찰 없이* 작동. resume/pause/status를 command 흡수하려 했던 v0 회고 대안은 *현재 흐름이 깨끗하므로* 불필요.

**v0 → v0.2.0 남은 결정**: #4(cutoff), #6(mutation). 둘 다 real LLM judge interactive dogfood 1회면 측정 가능.

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
- **semantic_similarity** (0~1, `mimiron-bench` 전용): reviewer가 Mimiron diff와 expected diff를 비교. 4축: (1) intent alignment, (2) interface compatibility, (3) test coverage parity, (4) code organization. v0는 LLM 자가 평가, v1+에서 AST 기반 정량 보강.
- **test_pass_rate** (0~1, `mimiron-bench` 전용): `benchmark.yaml.test_command` 실행 결과. `passed_count / total_count`.

룰브릭의 *세부*는 각 skill의 SKILL.md에 작성. v0는 휴리스틱, v1+에서 정량 보정.

## 12. Cross-Component Schemas (v0)

다음 5개 파일이 컴포넌트 간 contract을 형성한다. 모든 파일은 root에 `schema_version: 1` 필수 (§ 13). 형식은 *minimum required* 만 기술 — 추가 필드는 forward-compat 정책에 따라 허용.

### 12.1 state.json (CLI 단독 소유)

```python
{
  "schema_version": 1,
  "slug": str,
  "phase": Literal["clarify", "spec", "plan", "execute", "evaluate", "finalize", "done", "stuck", "paused"],
  "persistent": bool,
  "paused": bool,
  "spec_hash": str | None,            # plan 진입 후 freeze contract
  "spec_unlocked": bool,              # unstuck 경로에서만 true
  "current_task": str | None,
  "completed_task_ids": list[str],
  "in_flight_task_ids": list[str],
  "retries": dict[str, int],          # {task_id: count}
  "gate_history": list[GateRecord],   # § 12.4 verdict.json 동형
  "consecutive_gate_fails": int,
  "wall_clock_started_at": ISO8601,
  "token_usage": int,                  # 누적 입력+출력
  "created_at": ISO8601,
  "updated_at": ISO8601
}
```

### 12.2 spec.yaml

```yaml
schema_version: 1
slug: <str>
goal: <str>                            # 1~3 문장
constraints:
  - id: C01
    desc: <str>
    kind: what | prescribed_implementation   # 후자는 spec gate 면제
acceptance_criteria:
  - id: AC01
    desc: <str>
    verify:
      kind: test | grep | reviewer
      command: <str>                   # kind=test 일 때
      pattern: <str>                   # kind=grep 일 때
      in: <str>                        # kind=grep 일 때
ontology:                              # free-form key:value
  <term>: <definition>
hypothesis:                            # 시그니처 채택 시(현재 v0 보류)
  - id: H01
    claim: <str>
    confidence: 0.0~1.0
quality_score: 0.0~1.0                 # spec gate가 채움
ambiguity_score: 0.0~1.0               # clarify gate가 채움
```

### 12.3 plan.yaml

```yaml
schema_version: 1
slug: <str>
spec_hash: <str>                       # sha256(spec.yaml), freeze contract
tasks:
  - id: T01
    title: <str>
    worker: worker | tester | reviewer # 기본 "worker"
    depends_on: [task_id, ...]
    owned_files: [<path>, ...]
    expected_artifacts: [<path>, ...]  # 워커가 만들어야 할 파일
    timeout_s: int                     # 기본 600
```

### 12.4 verdict.json (per gate 호출)

```python
{
  "schema_version": 1,
  "slug": str,
  "phase": str,
  "kind": Literal["mechanical", "semantic", "ambiguity", "quality", "plan_integrity", "artifacts", "spec_freeze"],
  "verdict": Literal["pass", "fail", "needs_review"],
  "score": float | None,               # 0.0~1.0
  "samples": list[float],              # median-of-3 raw 점수 (LLM 게이트만)
  "details": dict,                     # kind마다 다름 (mechanical은 exit codes, semantic은 criteria별 채점)
  "ts": ISO8601
}
```

### 12.5 artifacts.json (per task, 워커 산출)

```python
{
  "schema_version": 1,
  "task_id": str,
  "declared_files": [
    {
      "path": str,
      "action": Literal["create", "modify", "delete"],
      "pre_hash": str | None,          # base 시점 sha256
      "post_hash": str,                # commit 시점 sha256
      "pre_mtime": ISO8601 | None,
      "post_mtime": ISO8601
    }
  ],
  "worker_summary": str                # 마크다운, 사람용 요약
}
```

CLI `commit-task`는 `declared_files`를 받아 *실제 파일의 post_hash/mtime을 재계산*해 일치 여부 검증 — 워커가 "고쳤다고만 적고 안 고치는" 거짓 보고를 잡음.

## 13. Schema Versioning & Migration Policy

모든 지속 파일(state.json, spec.yaml, plan.yaml, verdict.json, artifacts.json)이 따른다.

### 변경 정책

| 변경 종류 | version bump | migration script | 예시 |
|---|---|---|---|
| **Additive** (필드 추가, 기본값 있음) | 없음 | 불필요 | `state.token_usage` 추가 |
| **Breaking** (필드 제거, 의미 변경) | +1 | 필수 | `phase` enum 값 이름 바꿈 |

### Load-time 동작 (CLI)

```
expected = CLI_VERSION
read    = file.schema_version

if read == expected:                    → 정상 로드
elif read < expected:                   → migrations/{read}_to_{read+1}.py
                                         차례로 자동 실행, in-place rewrite,
                                         원본은 `.bak` 보존
elif read > expected:                   → ERROR
                                         "CLI가 낡았습니다. mimiron 업그레이드
                                          OR slug archive 후 새로 시작"
```

### Migration scripts

`scripts/migrations/v<N>_to_v<N+1>.py` 형태. 단일 파일 입력 → 단일 파일 출력. 멱등. 실패 시 .bak 복원.

**v0 시점**: 모두 schema_version=1. 마이그레이션 없음. 정책만 자리잡음.

## 14. Glossary

- **slug**: 한 기능 단위의 식별자. `.mimiron/<slug>/` 디렉토리 이름.
- **sidecar**: 프로젝트 루트의 `.mimiron/<slug>/` 디렉토리 전체. state + 산출물.
- **owned_files**: plan task가 *편집할 권한을 선언*한 파일 경로 리스트. 워커는 이 밖을 못 씀.
- **gate**: phase 종료 전에 통과해야 하는 정량 검사. CLI가 verdict 발급.
- **phase**: clarify | spec | plan | execute | evaluate | finalize 중 하나.
- **lane**: Creative | Deterministic | Persistence — 책임 분리 단위.
- **director**: execute skill 본인. 워커 dispatch를 담당.
- **outer loop**: `ralph-loop`이 구동하는 *Mimiron 자체*의 개발 사이클. 종료 조건은 bench suite cutoff.
- **inner loop**: `stop-hook.py`가 구동하는 *Mimiron이 한 feature*를 끝내려는 사이클. 종료 조건은 phase=done OR stuck.
- **benchmark / bench**: `mimiron-bench`가 평가하는 실제 머지된 PR 케이스.
- **bench_score**: `(test_pass_rate × 0.6) + (semantic_similarity × 0.4)` (기본 가중치).
- **cutoff_case** / **cutoff_global**: 단일 케이스가 solved되는 기준 / suite가 합격하는 기준.
- **Phase A / Phase B**: implementation plan 단계 — A는 수동 구현(bench 시동 불가), B는 ralph-loop 가능.
