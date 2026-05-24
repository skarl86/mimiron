# Ralph Loop — v0.3.0 milestone wrap

`skarl86/mimiron` 의 v0.3.0 milestone open 이슈 6개 (#20, #21, #22, #23, #24, #25) 를 한 ralph 세션으로 모두 close 하기 위한 prompt.

- **자동화 범위**: 작업 → commit → push → `closes #N` 으로 이슈 자동 close
- **완료 promise**: `MIMIRON_V030_CLOSED`
- **max-iterations**: 80
- **선행 조건**: `gh auth status` 가 `skarl86/mimiron` 접근 권한 있음, working dir = `/home/namgee/Development/private/mimiron`, branch = main, clean tree, 그리고 `.bench-clones/workspace/` 가 v0.2.0 wrap 에서 이미 준비되어 있어야 함 (없다면 v0.2.0 wrap 의 §A 환경 준비 먼저).

## 실행

새 Claude Code 세션에서:

```text
/ralph-loop --max-iterations 80 --completion-promise "MIMIRON_V030_CLOSED" "<아래 Prompt 본문 그대로 붙여넣기>"
```

> Ralph prompt 는 한 문자열이라 shell escape 가 까다롭다. Claude Code 의 `/ralph-loop` 슬래시 입력창에 옵션 먼저 치고, prompt 본문은 따옴표 안에 그대로 복붙.

## 검토 체크리스트 (실행 전)

- [ ] `git status` clean & branch == main
- [ ] `gh auth status` 가 skarl86 권한 OK
- [ ] `.bench-clones/workspace/` 존재 + main sync — `mimiron-bench run B01` 이 deferred 든 뭐든 *워크트리 단계* 까지 통과해야 함
- [ ] `dogfood/005-real-judge-bench.md` 까지만 존재 (다음 노트가 006)
- [ ] 다른 Mimiron 슬러그가 stop-hook persistent 상태로 살아있지 않음
- [ ] 이전 ralph 잔류 흔적 없음: `gh issue list --milestone v0.3.0 --state open` 이 6개, `git log --oneline -10` 에 closes #20~#25 가 *하나도* 없음

## 사전 정책 결정 (prompt 안에 박혀 있음 — 바꾸려면 본문 수정)

- **작업 순서**: #25 → #21 → #23 → #22 → #20 → #24. 가벼운 docs 부터 → judge skill 변경 3종 직렬 (같은 파일 conflict 회피) → scorer → cli/docs 갭.
- **PR 단위**: 이슈별 1 PR (v0.2.0 wrap 컨벤션 유지). main 직접 push 우선, 거부되면 `v030-wrap/<번호>` branch 로 fallback.
- **dogfood 노트**: 통합 1개 (`dogfood/006-v030-wrap.md`). 각 이슈별 *재채점* (B01/B02/B03 verdict 변화) 결과를 표로.
- **bench_score 산식 (#20)**: 옵션 1+3 조합 — (1) test_pass_rate 측정을 *candidate-applied* 워크트리로 옮김 + (3) `sim < 0.5` 이면 무조건 failed gate. dogfood/005 의 B02 NameError 회귀 케이스를 해결하는 가장 작은 변경.
- **bench-judge schema 확장 (#21/#23)**: backward-compat *optional* 필드만 (`apply_check`, `certainty_label`, `variation_seed`). 기존 `.mimiron/_outer/judge/*.json`, `_outer/status/*.json` 깨지면 안 됨.
- **#24 (cli/pipeline 갭)**: doc-only (옵션1) 를 *반드시* 수행, runner path 재설계 (옵션3) 는 *시간 남으면* 수행. integration (옵션2) 는 v0.3.0 범위 아님 — 별도 이슈로 split.

## Prompt 본문

````text
mimiron 저장소(`skarl86/mimiron`)의 v0.3.0 milestone open 이슈 6개를 모두 close 한다.

# 대상 이슈 (작업 순서대로)

1. #25 — docs: benchmark issue.md root-cause hint 가이드라인 (`benchmarks/_CURATION_GUIDE.md` 신설 + B01 issue.md 회고 보강)
2. #21 — judge: J5 (apply-check) 차원 추가
3. #23 — judge: certainty band — high score 케이스 'trivial' 별도 라벨링
4. #22 — judge: median-of-3 prompt-variation 부여
5. #20 — bench: bench_score 공식 — test_pass_rate dominance 해소 (옵션 1+3 조합)
6. #24 — cli: mimiron-bench run pipeline trigger 갭 (doc-only 우선, runner path 재설계는 시간 남으면)

작업 디렉토리: /home/namgee/Development/private/mimiron

# 매 iteration 시작 시 반드시

1. `git status` + `gh issue list --milestone v0.3.0 --state open` 으로 현재 상태 확인.
2. open 이슈가 0개면 곧장 '완료 검증' (맨 아래) 으로 점프.
3. 그렇지 않으면 위 순서대로 *가장 앞 미해결 이슈 1개* 만 골라 작업. 한 iteration 안에 두 이슈 동시에 건드리지 말 것.
4. 이전 iteration 의 미완성 커밋/파일 발견 시 *덮어쓰지 말고* 먼저 진단: `git log --oneline -10`, `git status`, 해당 파일 read.

# 공통 산출 정책

- **dogfood 노트는 통합 1개**: `dogfood/006-v030-wrap.md`. 각 이슈 작업이 끝날 때마다 *해당 섹션* 만 append. 절대 이슈별로 별도 dogfood 파일 만들지 말 것.
- **재채점 의무**: #20, #21, #22, #23 작업 후 B01/B02/B03 셋 모두에 대해 `mimiron-bench run <id>` 재실행 + judge 재호출. verdict 변화를 dogfood/006 의 해당 섹션 표로.
- **schema backward-compat**: judge JSON 신규 필드는 *모두 optional*. 기존 `.mimiron/_outer/judge/*.json` 와 `.mimiron/_outer/status/*.json` 파일이 *그대로* 파싱되어야 함. 검증: `python -c "import json; [json.load(open(p)) for p in __import__('pathlib').Path('.mimiron/_outer/judge').glob('*.json')]"` 가 통과.
- **CHANGELOG**: 모든 이슈 작업 후 `CHANGELOG.md` 의 v0.3.0 섹션에 한 줄 추가. (없으면 신설)

# 이슈별 완료 조건

## A. 이슈 #25 — Curation guide (가장 가벼움, warmup)

완료 조건:
- `benchmarks/_CURATION_GUIDE.md` 신설 — 5 룰 (외부 시그널 OK / 구현 어휘 금지 / 행동 단위 AC / out-of-scope 명시 / 원인-결과 PR 만 큐레이션) 명시.
- `benchmarks/B01-welcome-message-fix/issue.md` 회고 보강 — "재접속 시 에러 로그에 외부 시스템 코드 (예: PostgREST 42703) 가 보임" 형태의 *시그널형* 단서 1줄 추가.
- 보강 후 `mimiron-bench run B01` 이 base→fail / target→pass 가정을 여전히 통과해야 함 (직접 한 번 돌려 확인).
- `benchmarks/README.md` 가 있으면 _CURATION_GUIDE.md 참조 한 줄 추가. 없으면 패스.
- dogfood/006 의 "§A #25" 섹션 채움.

수행:
1. dogfood/005-real-judge-bench.md §"흥미로운 점" 2번 + 기존 B01/B02/B04/B05 curation.md 형식 일관성 검토.
2. _CURATION_GUIDE.md 작성 (B02/B04 issue.md 를 *positive example* 로, B01 의 원래 형태를 *negative example* 로 인용).
3. B01 issue.md 에 시그널 1줄만 *추가*. 기존 acceptance criteria 는 건드리지 않음.
4. 재실행 검증.
5. commit: `docs(bench): curation guide for issue.md root-cause hints (closes #25)`

## B. 이슈 #21 — J5 (apply-check) 차원 추가

완료 조건:
- `skills/bench-judge/SKILL.md` 에 J5 정의·산출 방법 명시. score 산식 `(J1+J2+J3+J4+J5)/5` 로 갱신.
- 가벼운 형태 (`git apply --check`) 가 *기본*. strong 모드 (`py_compile`) 는 opt-in 으로 SKILL.md 에 별도 섹션.
- judge JSON 에 `apply_check: 0.0 | 1.0` optional 필드 추가.
- B01/B02/B03 재채점 결과를 dogfood/006 의 "§B #21" 섹션 표로 — *특히 B02* 가 NameError 회귀이므로 J5=0.0 가 verdict 끌어내리는지 확인.

수행:
1. `skills/bench-judge/SKILL.md` read → §"흐름" 룰브릭 부분 식별.
2. J5 정의: candidate diff 를 base_ref 워크트리에 `git apply --check` → 통과 1.0 / 실패 0.0. strong 모드는 apply 후 `py_compile` 변경 .py 파일.
3. 산식 갱신. backward-compat: J5 필드 없으면 기존 4 차원 평균 fallback.
4. B01/B02/B03 재채점: `mimiron-bench run <id>` + judge 재호출. 각 케이스의 apply_check 값과 새 score 기록.
5. dogfood/006 의 표: `| bench | 기존 score | J5 | 새 score | verdict 변화 |`.
6. commit: `feat(judge): J5 apply-check dimension for catastrophic candidate detection (closes #21)`

## C. 이슈 #23 — Certainty band 4-label

완료 조건:
- `skills/bench-judge/SKILL.md` §"가드" 또는 §"흐름" 5번에 4 라벨 정의 (`trivial-certain` / `discriminating-certain` / `failure-certain` / `uncertain`).
- judge JSON 에 `certainty_label` optional 필드 추가.
- B01 → failure-certain, B02 → discriminating-certain, B03 → trivial-certain 으로 분류되는지 확인 + dogfood/006 "§C #23" 섹션에 기록.

수행:
1. SKILL.md 의 기존 certainty band (spread<0.15 → certain) 부분 찾기.
2. 4 라벨 룰 추가:
   - `score ≥ 0.90` + spread < 0.15 → `trivial-certain`
   - `0.4 ≤ score < 0.85` + spread < 0.15 → `discriminating-certain`
   - `score < 0.3` + spread < 0.15 → `failure-certain`
   - spread ≥ 0.15 → `uncertain`
3. 기존 3 케이스 (#21 작업 후 새 score 기준) 재라벨링.
4. dogfood/006 의 "§C" 에 라벨링 매핑 + 해석 가이드 ("trivial-certain 은 판별력 시그널 아님").
5. commit: `feat(judge): 4-label certainty band — trivial vs discriminating vs failure (closes #23)`

## D. 이슈 #22 — Median-of-3 prompt-variation

완료 조건:
- `skills/bench-judge/SKILL.md` §"흐름" 4번 (median-of-3) 에 회차별 prompt-variation 룰 *결정론적으로* 명시.
- judge JSON 에 `variation_seed` optional 메타 추가 (회차별 어떤 variation 썼는지).
- 재채점 결과: 같은 candidate 의 spread 가 기존보다 *유의미하게 더 큰* 케이스 1개 이상 발견 — 발견 못 하면 dogfood/006 에 "관찰 결과: 모든 케이스에서 spread 변화 < 0.05, 가설 부분 기각" 으로 솔직히 기록.

수행:
1. SKILL.md 의 median-of-3 부분 찾기.
2. 3 회차 variation 룰 (결정론적):
   - 회차 1: 룰브릭 순서 J1→J2→J3→J4→J5, expected 먼저 제시
   - 회차 2: 순서 J3→J5→J1→J4→J2, actual 먼저 제시
   - 회차 3: 순서 J5→J2→J4→J1→J3, expected 먼저 + "회귀 위험을 평소보다 엄격히 보라" 강조
3. B01/B02/B03 재채점 (이번엔 새 variation 룰로). spread 비교표를 dogfood/006 "§D #22" 에.
4. commit: `feat(judge): deterministic prompt-variation across median-of-3 rounds (closes #22)`

## E. 이슈 #20 — bench_score 공식 (옵션 1+3 조합)

완료 조건:
- `src/mimiron/bench/runner.py` 의 test_pass_rate 측정 위치가 *candidate-applied* 워크트리로 이동 (옵션 1).
- `src/mimiron/bench/scorer.py` (또는 동등 위치) 에 `sim < 0.5` 이면 무조건 verdict='failed' 게이트 (옵션 3).
- 기존 산식 `0.6 × test_pass + 0.4 × sim` 은 유지 — 게이트만 추가, weight 는 안 건드림.
- design note 를 dogfood/006 "§E #20" 섹션에 (왜 옵션 1+3 인지, 왜 (2) weight 재조정 안 했는지).
- 재채점: B01 → failed (기존 유지), B02 → **failed** (NameError 회귀가 candidate apply 단계에서 detected), B03 → passed (기존 유지).
- 기존 테스트 깨지지 않게 — pytest 통과 필수.

수행:
1. `src/mimiron/bench/runner.py:run_benchmark` 와 `scorer.compute_bench_score` read.
2. test_pass_rate 측정 워크트리 변경:
   - 기존: target_ref 워크트리에서 test_command 실행
   - 신규: candidate diff (`.mimiron/_bench/<id>/mimiron_output.diff`) 를 base_ref 워크트리에 apply 후 test_command 실행
   - apply 실패 시 test_pass_rate = 0.0
3. scorer 에 sim gate 추가 — `bench_score` 산출은 그대로, 다만 verdict 결정 시 `sim < 0.5` 면 'failed' 강제.
4. unit test 추가 (`tests/bench/test_scorer.py` 등) — B02 시나리오 fixture 로 NameError candidate 가 failed 되는지.
5. B01/B02/B03 재채점. 새 verdict 가 위 완료 조건과 일치하는지.
6. dogfood/006 "§E" 에 표 + design note.
7. commit: `fix(bench): score gate (sim<0.5 → failed) + measure test_pass on candidate-applied tree (closes #20)`

## F. 이슈 #24 — CLI/pipeline trigger gap (doc-only + 시간 남으면 path 재설계)

완료 조건 (doc-only 부분, *반드시*):
- `skills/mimiron-bench/SKILL.md` (또는 동등), `docs/HANDOVER.md`, `dogfood/` 템플릿 — 세 곳 이상에 "`mimiron-bench run` 은 Mimiron pipeline 을 트리거하지 않는다, candidate diff 는 외부에서 (사용자/skill/ralph) 주입해야 함" 명시.
- dogfood/006 "§F #24" 에 갭 설명 요약.

완료 조건 (path 재설계, *시간 남으면*):
- `src/mimiron/bench/runner.py` 의 `diff_file = work_root.parent / "mimiron_output.diff"` 를 per-bench path 로 (`.mimiron/_bench_output/<id>.diff` 등) 변경.
- 마이그레이션 노트 1줄 dogfood/006 에.
- 기존 테스트 통과.

수행:
1. doc-only 먼저: 위 3+ 파일 grep → `mimiron-bench run` 언급 부분 찾기 → 갭 명시 1~2 줄 추가.
2. dogfood/006 "§F" 작성.
3. commit 1: `docs(cli): clarify mimiron-bench run does not trigger pipeline (closes #24)`
4. 남는 iteration 여유 있으면 path 재설계 시도. 못 하면 #24 코멘트로 "옵션3 은 v0.4.0 으로" follow-up 이슈 생성 후 #24 는 doc-only 로 close.

# 자동 커밋/푸시/이슈 close 정책 (v0.2.0 wrap 과 동일)

각 이슈 작업이 끝나고 *완료 조건이 git 으로 관찰 가능한 시점*에:
- `git add` (관련 파일만 명시적으로, never -A)
- `git commit -m "<type>(<scope>): <summary> (closes #N)"` 형식
- `git push origin main` 시도
- 거부되면 branch `v030-wrap/<이슈번호>` 로 옮기고 `gh pr create` + 가능하면 `gh pr merge --squash --auto`
- push 또는 PR merge 성공해야 GitHub 의 'closes #N' 발화 → 이슈 자동 close

수동 close 필요 시: `gh issue close <N> --comment "<커밋 SHA + 1줄 결과>"`.

# Self-correction 규칙

- 이전 iteration 의 흔적 (불완전 파일, 어중간한 커밋) 발견 시 *덮어쓰지 말고* 먼저 진단.
- test_command 가 fail→pass 가정 깨지면 — 특히 B01/B02/B03 재채점 단계에서 — 가정부터 재검토. expected.diff 가 잘못된 경우도.
- bench-judge 가 score=1.0 또는 0.0 을 내면 *의심*. samples 와 rationale 재확인.
- judge JSON schema 변경 후 backward-compat 검증 명령 실패 → 작업 되돌리고 optional 필드 누락 부분 수정.
- 같은 작업을 3 iteration 연속 시도하는데 진전이 없으면 dogfood/006 에 'stuck: <원인>' 박고 *다음 이슈* 로 우회. 마지막 iteration 까지 못 풀면 해당 이슈에 `gh issue comment` 로 막힌 지점 코멘트 + 그 이슈는 reopen 상태로 두고 나머지 5개부터 close.

# 완료 검증 (모든 작업이 끝났다고 생각될 때)

다음을 모두 만족해야 완료:
- `gh issue list --milestone v0.3.0 --state open` 결과 0줄
- `git status` clean
- `git log --oneline -20` 에 closes #20, #21, #22, #23, #24, #25 모두 보임 (또는 머지된 PR)
- `dogfood/006-v030-wrap.md` 가 커밋되어 있고 §A~§F 6 섹션 모두 채워짐
- `CHANGELOG.md` 의 v0.3.0 섹션이 6 이슈 모두 한 줄씩 언급
- backward-compat 검증 명령 통과: `python -c "import json; [json.load(open(p)) for p in __import__('pathlib').Path('.mimiron/_outer/judge').glob('*.json')]"`
- pytest 통과 (`pytest -q`)

모두 만족하면 *마지막* 메시지로 정확히 다음 한 줄만 출력:

MIMIRON_V030_CLOSED

부족한 게 있으면 절대 위 토큰 출력하지 말고, 부족한 항목 1개를 잡아 다음 iteration 으로 계속.
````

## 사후 검토 포인트 (실행 후)

ralph 가 `MIMIRON_V030_CLOSED` 를 출력한 뒤, 사람이 직접 확인:

- `gh issue list --milestone v0.3.0 --state closed` — 6 이슈 모두 closed
- `.mimiron/_outer/judge/B0X.json` 가 새 schema (apply_check, certainty_label, variation_seed) 를 *포함* 하면서도 기존 키 보존
- `.mimiron/_outer/status/B0X.json` 의 B02 verdict 가 'failed' 로 바뀌었는지 (#20 의 핵심 시그널)
- `skills/bench-judge/SKILL.md` 의 J5/4-label/variation 룰 3종이 모두 한 곳에 자연스럽게 통합됐는지 — 3 PR 직렬 처리 과정에서 conflict 흔적 없는지
- `benchmarks/_CURATION_GUIDE.md` 가 *negative example* (B01 원본) 까지 인용하고 있는지 — positive only 면 가이드 효과 약함
- dogfood/006 의 "§D #22 — variation 부여 효과" 가 *솔직하게* 적혀 있는지 (효과 없으면 없다고 기록되어 있어야 함)
- runner.py 의 test_pass_rate 측정 위치가 candidate-applied 트리로 옮겨졌는지 — 옮겼다면 동시 실행 안전성도 점검

## 수정 권유 포인트 (실행 전 사용자가 손볼 곳)

- **작업 순서**: judge skill 3종 (#21/#23/#22) 직렬 처리 순서는 J5 → certainty → variation 으로 잡았는데, J5 가 가장 *invasive* 라 먼저 끝내고 schema 확장 마무리하는 의도. 가벼움 순으로 가고 싶으면 #22 → #23 → #21 로 뒤집기.
- **bench_score 옵션**: 본 prompt 는 옵션 1+3 (candidate-applied 측정 + sim gate). 옵션 2 (weight 재조정) 가 더 마음에 들면 §E 의 "수행" 부분 교체.
- **#24 path 재설계 우선순위**: 현재 "시간 남으면" 으로 두었음. 반드시 끝내야 하면 §F 를 doc-only 와 분리해서 두 이슈처럼 다루도록.
- **dogfood 노트 통합 vs 분리**: v0.2.0 wrap 컨벤션 따라 통합 (dogfood/006) 1개로 잡음. 이슈별로 따로 만들고 싶으면 §"공통 산출 정책" 첫 항목 수정.
- **완료 promise 토큰**: `MIMIRON_V030_CLOSED`. ralph-loop hook 의 jq 가 컨트롤 캐릭터에 약하므로 (메모리: `ralph-loop-jq-control-char-trap`) ASCII 만으로 충분히 안전. 이모지/한글 토큰은 피하기.
