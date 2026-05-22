# Ralph-Loop Entry — Phase B Driver

> Phase A가 끝난 시점에 ralph-loop을 어떻게 진입시키는지에 대한 지침.

## 전제

다음이 모두 충족되어야 함:
- `git tag mimiron-phase-a-done` 존재
- `benchmarks/B01-<slug>/`이 큐레이션 완료
- `mimiron-bench run B01-<slug>`가 *deferred 아닌* JSON 반환

## 진입 명령

```
/loop "Continue building Mimiron until mimiron-bench suite aggregate >= 0.75 OR halt signal raised. Each iteration: pick next pending/failed benchmark, run mimiron-bench, analyze failure, apply minimal change to Mimiron, retry. Honor safety pins from src/mimiron/bench/suite.py."
```

## 매 iteration body (ralph가 따라야 하는 단계)

1. `mimiron-bench list` 실행. status=pending 또는 failed인 다음 케이스 선택.
2. `mimiron-bench run <id>` 실행.
3. verdict 분석:
   - `passed` → 다음 케이스
   - `failed` → 실패 원인 식별 (어느 phase, 어느 gate, worker drift 등)
   - `deferred` → similarity_provider 미설치 → reviewer agent 호출 통합 작업
4. Mimiron 코드/skill/agent에 *최소 변경* 적용 (집중된 PR-sized).
5. `pytest`로 회귀 없음 확인.
6. 같은 케이스 재실행. 3회 실패 시 deferred 마킹 후 다음 케이스로.
7. 매 5 iteration마다 `mimiron-bench suite` aggregate 기록.
8. `compute_halt_signal` 호출 — None 아니면 halt-report 작성 후 종료.

## halt 종류

- `iteration_cap` (30) — 더 많은 시도는 분리된 세션에서.
- `asymptote` — 본질적 진척 없음. 벤치 큐레이션 재검토.
- `all_deferred` — similarity_provider 미설치 등 인프라 부족.
- `wall_clock` (24h) — 다음 날 재개.
- `user_abort` — `mimiron-bench --abort` 사용자 호출.

## halt 보고서 자동 생성

`.mimiron/_outer/halt-report.md`에 다음 3가지 다음 액션 제안 자동 작성:
1. 코드 변경 후보 (어떤 모듈 / skill에 손대야 하나)
2. 벤치마크 큐레이션 변경 (난이도 조정, 케이스 추가/제거)
3. 사용자 결정 필요 사항 (Deferred Decisions § 8 중 어느 것)

## 종료 조건 (성공)

- `mimiron-bench suite`의 `suite_aggregate >= 0.75`
- 또는 최소 3개 케이스 `status=passed`
- 또는 모든 케이스가 `solved` 또는 `deferred`

## 종료 후 (v0 → v1 졸업)

DoD checklist (spec § 7.4) 확인 후 PR.
