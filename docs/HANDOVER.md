# Mimiron — Phase B Handover

> **읽는 Claude에게**: 이 문서는 `/compact` 직후의 너에게 *완전한 컨텍스트*를 주기 위한 것이다. 모든 결정·경로·미해결 항목이 여기 있다. 다른 문서 읽기 전에 *이 문서부터 끝까지* 읽어라.

---

## 0. 너는 어디에 있나

- **CWD**: `/home/namgee/Development/private/mimiron/.claude/worktrees/mimiron-spec/`
- **Branch**: `worktree-mimiron-spec` (main 아님 — worktree 격리됨)
- **Python venv**: `.venv/` (uv로 만들어짐, py3.14)
- **저장소 종류**: git, 47+ commits, Phase A 졸업 태그 박힘
- **사용자**: namgee (Korean speaker, 한국어로 응답해도 OK; 단 코드/docstring/spec은 그동안 *한·영 혼용* 패턴 유지)

## 1. 무엇이 만들어졌나 (1-paragraph)

Mimiron은 Claude Code용 *멀티 에이전트 하네스 플러그인*이다. 6-페이즈 파이프라인(clarify → spec → plan → execute → evaluate → finalize)을 *정량 게이트*로 운영하고, DAG 기반 병렬 실행 + persistent loop + 6겹 안전핀을 갖는다. *Phase A* (CLI 기반 결정적 인프라 + 외부 평가)는 *완료*. *Phase B* (멀티 에이전트 실행/평가 skill, hooks, agents, 그리고 self-eval로 더 많은 benchmark)는 *너(ralph-loop)가 채울 차례*.

## 2. 핵심 문서 (필요할 때 읽어라, 한 번에 다 읽지 말 것)

| 우선순위 | 경로 | 무엇 |
|---|---|---|
| ★★★ | `docs/superpowers/specs/2026-05-22-mimiron-design.md` | 696줄 spec. § 12 schemas + § 7.5 self-eval이 가장 자주 참조됨 |
| ★★★ | `docs/superpowers/plans/2026-05-22-mimiron.md` | 4629줄 plan. Phase A는 끝. Phase B는 *ralph-driven* (정적 plan 없음 — 너가 매 iteration 결정) |
| ★★★ | `docs/ralph-loop-entry.md` | Phase B loop body 명세 (5-fold halt signal 등) |
| ★★ | `benchmarks/B01-welcome-message-fix/` | 첫 benchmark. PR ts-cxdm/workspace#1299 기반 |
| ★★ | `dogfood/001-b01-manual-run/notes.md` | B01 종주 결과 |
| ★ | `README.md` / `README.ko.md` | 개요 |

## 3. 디렉토리 지도

```
.
├── .claude-plugin/{plugin.json, marketplace.json}
├── .bench-clones/workspace/              # 외부 PR 클론 (gitignored), B01 평가용
├── .mimiron/_outer/status/B01-*.json     # bench 산출 (gitignored except _global/)
├── .venv/                                # uv 생성 (gitignored)
├── benchmarks/_cutoff.yaml               # cutoff + weights
├── benchmarks/B01-welcome-message-fix/{benchmark.yaml, issue.md, expected.diff, curation.md}
├── docs/
│   ├── HANDOVER.md                       # 이 문서
│   ├── ralph-loop-entry.md
│   └── superpowers/{specs,plans}/...
├── dogfood/001-b01-manual-run/{_outer/, notes.md}
├── pyproject.toml                        # py3.11+ stdlib + PyYAML
├── scripts/{mimiron, mimiron-bench}      # bash entry
├── skills/{clarify,spec}/SKILL.md        # 2개 완성
├── src/mimiron/
│   ├── __init__.py                       # SCHEMA_VERSION = 1
│   ├── cli.py                            # 6 subcommands: init/ls/status/scan/gate/commit-task
│   ├── state.py                          # State + GateRecord (§ 12.1)
│   ├── spec.py                           # Spec + Verify-kind contract (§ 12.2)
│   ├── plan.py                           # Plan + DAG validation (§ 12.3)
│   ├── verdict.py                        # Verdict.make (§ 12.4)
│   ├── artifacts.py                      # Artifacts + hash 검증 (§ 12.5)
│   ├── scanner.py                        # DAG scanner
│   ├── gates.py                          # mechanical gate runner
│   ├── thresholds.py                     # _global/thresholds.yaml 로더
│   ├── hash_util.py                      # sha256 helpers
│   ├── llm.py                            # MIMIRON_STUB + median_of_3
│   └── bench/
│       ├── cli.py                        # 4 subcommands: list/run/compare/suite
│       ├── runner.py                     # run_benchmark + Benchmark dataclass
│       ├── scorer.py                     # bench_score 공식 + pytest 파서
│       ├── worktree_iso.py               # git worktree 격리
│       └── suite.py                      # 5-fold halt signal
└── tests/                                # 81 passing (unit 73 + integration 8)
```

## 4. 명령어 빠른 참조

```bash
# 결정적 CLI (LLM 호출 0개)
.venv/bin/mimiron init <slug>
.venv/bin/mimiron ls
.venv/bin/mimiron status <slug>
.venv/bin/mimiron scan <slug>
.venv/bin/mimiron gate <slug> {mechanical|ambiguity|quality}
.venv/bin/mimiron commit-task <slug> <task_id>

# Self-eval
.venv/bin/mimiron-bench list
.venv/bin/mimiron-bench run <id>
.venv/bin/mimiron-bench suite
.venv/bin/mimiron-bench compare <dir1> <dir2>

# 회귀
.venv/bin/pytest -q

# Lint/type
.venv/bin/ruff check src/ tests/
.venv/bin/mypy src/mimiron/
```

## 5. Phase B 목표 (너의 일)

해결 순서 (우선순위):

1. **similarity_provider 통합** — `bench/runner.py`의 `run_benchmark`가 받는 콜백. 두 diff(actual vs expected)를 받아 0~1 점수 반환. v0 구현은 *Claude 자가 호출* (reviewer agent로 dispatch + 점수 받기) 정도. 이게 있으면 B01이 `deferred` → `passed`/`failed`가 됨.
2. **B02~B05 benchmark 큐레이션** — `ts-cxdm/workspace`의 `naver-smartstore` 라벨 머지 PR에서 small/medium/hard 다양하게 4개 추가. PR 후보는 `gh pr list --repo ts-cxdm/workspace --state merged --label naver-smartstore` 로 찾기. *tide-namgee* 작성 PR 선호 (사용자 본인).
3. **execute / evaluate / finalize skill 작성** — `skills/execute/SKILL.md`, `skills/evaluate/SKILL.md`, `skills/finalize/SKILL.md`. spec § 4.3, § 5.3, § 7.5 참고.
4. **agents/ 정의** — `mimiron-worker`, `mimiron-tester`, `mimiron-reviewer` (3종 워커 tier). spec § 4.4.
5. **hooks/ 작성** — `hooks/session-start.py`, `hooks/stop-hook.py` (persistent loop), `hooks/post-toolwrite.py` (drift warn). spec § 5.4.
6. **commit-task에 spec_hash 검증 추가** — 현재 scan만 검증함 (spec § 5.3 reviewer가 짚어준 gap).
7. **Plan.load의 KeyError → PlanError 래핑** — final review에서 짚어준 minor.

각 변경 후 *반드시* `pytest -q && ruff check src/ tests/ && mypy src/mimiron/` 통과. 회귀 만들지 말 것.

## 6. 절대 지킬 계약 (Honor at all cost)

### 6.1 3-Lane 분리
- **Creative lane (skill)**: SKILL.md에서 Claude가 결정 내림. *직접 state.json 쓰기 금지*.
- **Deterministic lane (CLI)**: `src/mimiron/cli.py` + `bench/cli.py` 어디서도 *LLM 호출 금지* (`llm.call_llm`은 MIMIRON_STUB=1에서만 동작).
- **Persistence lane (hook)**: 가볍게. 그 외 일체 금지.

### 6.2 6-fold infinite loop defense
spec § 5.4. 1=gate 차단, 2=task retry ≤3, 3=gate fail ≥3 → stuck, 4=unstuck 발동, 5=wall_clock 4h, 6=token_budget 500K. 새 skill 추가 시 이 정책 어기지 말 것.

### 6.3 4-fold judge defense
spec § 6.4. median-of-3, certainty band, acceptance contract, mutation(opt-in). 새 게이트 추가 시 이 정책 따를 것.

### 6.4 5-fold outer-loop safety pin
spec § 7.5.5. `compute_halt_signal()`이 본인의 *멈춤 신호*다. 무시하지 말 것.

### 6.5 spec_hash freeze
plan 진입 후 spec.yaml mutate 금지. mutate해야 한다면 `state.spec_unlocked=true` 명시 (unstuck flow only).

### 6.6 bench는 원본 repo 절대 안 건드림
`bench/worktree_iso.py.isolate_at_ref`만 사용. 원본 working tree 읽기조차 안 함 (worktree만 사용).

## 7. 미해결 결정 / 알려진 한계 (의도된 deferral)

spec § 8 참고. 짧게:

1. 🟡 Gate가 phase 전이의 *유일한* 게이트키퍼? — v0 yes
2. 🟡 Persistence cap 임계 — `wall_clock_max_s=14400`, `token_budget=500K`
3. 🟡 PostToolUse drift hard reject 승급 — v0는 warn+log
4. 🟡 Benchmark cutoff·가중치 — `cutoff=0.75`, `w_test=0.6/w_sim=0.4`
5. 🟡 Benchmark suite — 현재 B01만. 너가 B02~B05 추가
6. 🟡 Mutation 룰 default — v0 opt-in
7. 🟡 Component 트리밍 — 22 → 13~14 옵션

`compute_halt_signal`이 `ASYMPTOTE`/`ALL_DEFERRED`로 멈출 때 *너가 이 결정들을 사용자에게 보고*해야 함. 특히 #5는 너의 행동으로 해결 가능.

## 8. 첫 iteration 가이드

권장 첫 iteration의 *구체 단계*:

```
1. .venv/bin/mimiron-bench list  → 현재 상태 확인 (B01 deferred)
2. similarity_provider 인터페이스 설계:
   - bench/runner.py에 SimilarityProvider type alias 이미 있음
   - Claude-as-judge 함수를 src/mimiron/bench/judge.py에 신설 권장
   - 기존 llm.call_llm은 stub 모드만 — 실제 LLM 호출은 *skill 안에서* 또는
     anthropic SDK 직접 호출 (별도 dep 추가). v0는 skill 위주 권장.
3. TDD: tests/unit/test_bench_judge.py 먼저
4. 통과 후 commit, mimiron-bench run B01-welcome-message-fix 재실행
5. status가 deferred 아닌 verdict 나오면 B01 첫 점수 획득
6. .mimiron/_outer/halt-report.md 갱신 + 다음 액션 3가지 제안
```

이 iteration이 *너무 크면* 더 작게 쪼개도 됨. 한 iteration = 한 PR-sized 변경이 원칙.

## 9. 사용자가 너에게 기대하는 톤

- **결정에 직진**: 합리적인 default를 잡고 진행. 매번 사용자에게 묻지 말 것. 단, *주요 architectural pivot*은 보고.
- **회귀 zero**: `pytest -q`는 항상 통과. 깨지면 즉시 fix.
- **Korean OK**: docstring/comment에 한국어 OK (기존 패턴 유지). 사용자와 대화는 한국어.
- **Bg session 친화**: progress 마다 narration. "result:" 헤더는 *진짜 끝*에서만.

## 10. 안 할 것 (anti-pattern)

- ❌ spec/plan/HANDOVER.md를 *수정*하지 말 것 (Phase B에서 plan은 동적). spec은 spec_unlocked flow 전엔 frozen 취급.
- ❌ `.mimiron/_global/thresholds.yaml`을 임의 변경 (사용자 결정 영역).
- ❌ `.bench-clones/workspace/` 안을 직접 편집 (외부 PR repo, 읽기 전용).
- ❌ `main` branch로 머지 (사용자가 명시 요청 전엔 worktree에서 작업).
- ❌ Phase A 코드를 *대규모 refactor*. 짚인 issue만 minimal change.
- ❌ 외부 의존성 추가 (anthropic SDK 같은 거 *명시 승인 없이* dep 추가 금지).

## 11. 결과물 인보이스 (현재 상태 hash)

```
git log --oneline | head -1
→ 0c2a94e dogfood: B01 manual end-to-end run (A6 graduation)

git tag --list "mimiron-*"
→ mimiron-a1 … mimiron-a6, mimiron-phase-a-done, mimiron-b-entry-ready

.venv/bin/pytest -q
→ 81 passed

.venv/bin/ruff check src/ tests/
→ All checks passed!

.venv/bin/mypy src/mimiron/
→ Success: no issues found in 18 source files
```

이 상태가 너의 starting line이다. 깨지면 fix 먼저.

---

**행운을 빈다. spec의 정신은 *measured forward motion*이다 — 빠르게가 아니라 *되돌릴 수 있게*. ralph가 자율이라 해도, 매 변경은 `git log`에 흔적이 남고 회귀가 잡혀야 한다.**
