# Ralph Loop — v0.2.0 milestone wrap

`skarl86/mimiron` 의 v0.2.0 milestone open 이슈 3개 (#1, #2, #3) 를 한 ralph 세션으로 모두 close 하기 위한 prompt.

- **자동화 범위**: 작업 → commit → push → `closes #N` 으로 이슈 자동 close
- **완료 promise**: `MIMIRON_V020_CLOSED`
- **max-iterations**: 60
- **선행 조건**: `gh auth status` 가 `ts-cxdm/workspace` 접근 권한 있음, working dir = `/home/namgee/Development/private/mimiron`, branch = main, clean tree

## 실행

새 Claude Code 세션에서:

```text
/ralph-loop --max-iterations 60 --completion-promise "MIMIRON_V020_CLOSED" "<아래 Prompt 본문 그대로 붙여넣기>"
```

> Ralph prompt 는 한 문자열이라 shell escape 가 까다롭다. 가장 안전한 방법: Claude Code 의 `/ralph-loop` 슬래시 입력창에 옵션 먼저 치고, prompt 본문은 따옴표 안에 그대로 복붙.

## 검토 체크리스트 (실행 전)

- [ ] `git status` clean & branch == main
- [ ] `.bench-clones/workspace` 없거나, 있다면 ts-cxdm/workspace 최신 main 과 sync 됨
- [ ] `gh auth status` 에 ts-cxdm 조직 접근 OK
- [ ] 다른 Mimiron 슬러그가 stop-hook persistent 상태로 살아있지 않음 (`mimiron status` 비어 있거나 paused)
- [ ] dogfood/004 까지만 존재 (다음 노트가 005)

## Prompt 본문

````text
mimiron 저장소(`skarl86/mimiron`)의 v0.2.0 milestone open 이슈 3개를 모두 close 한다.

# 대상 이슈
- #1 — Curate B04 benchmark — hard fix (ts-cxdm/workspace#2046)
- #2 — Curate B05 benchmark — feat (ts-cxdm/workspace#2061)
- #3 — Run interactive dogfood with real LLM judge on B01/B02/B03

작업 디렉토리: /home/namgee/Development/private/mimiron

# 매 iteration 시작 시 반드시
1. `git status` + `gh issue list --milestone v0.2.0 --state open` 으로 현재 상태 확인.
2. open 이슈가 0개면 곧장 '완료 검증'(맨 아래) 으로 점프.
3. 그렇지 않으면 아래 우선순위로 한 이슈씩 진행 — *한 iteration 안에 두 이슈를 동시에 건드리지 말 것*.

# 우선순위 & 작업 정의

## A. 환경 준비 (한 번만)
- `.bench-clones/workspace/` 가 없으면 `gh repo clone ts-cxdm/workspace .bench-clones/workspace` 로 clone.
- clone 실패(권한/네트워크) 시 dogfood/005-v020-wrap.md 에 'blocked: <원인>' 기록 후 다음 iteration 에서 재시도.

## B. 이슈 #1 — B04 큐레이션 (hard fix)
완료 조건 (전부 파일 시스템으로 관찰 가능):
- `benchmarks/B04-hallucination-guard/benchmark.yaml` 존재 (B02 형식 따름, repo=../../.bench-clones/workspace)
- `benchmarks/B04-hallucination-guard/issue.md` 존재 (구현 어휘 누설 없음 — 파일/함수 이름은 OK, 라이브러리/프레임워크 명칭 X)
- `benchmarks/B04-hallucination-guard/expected.diff` 존재 (ts-cxdm/workspace#2046 의 base→target git diff)
- `benchmarks/B04-hallucination-guard/curation.md` 존재 (B01 curation.md 양식)
- test_command 가 base_ref 에서 fail, target_ref 에서 pass (수동 검증 결과를 curation.md 에 기록)
- `mimiron-bench list` 출력에 B04 가 포함됨

수행:
1. `cd .bench-clones/workspace && gh pr view 2046 --json baseRefOid,headRefOid,mergeCommit` 로 SHA 추출.
2. `git diff <base>..<target> > /tmp/B04.diff` 로 expected.diff 생성, mimiron repo 의 `benchmarks/B04-*/expected.diff` 로 복사.
3. issue.md 는 PR description 에서 *증상/의도된 동작/acceptance criteria/out-of-scope* 4섹션으로 재구성. 구현 vocabulary(예: pydantic, langchain 등) 는 제거.
4. test_command 는 — fix 결과를 검증할 *경량 grep 또는 file-content assertion* 전략 채택 (B02 패턴 참고). 풀 pytest 회피.
5. base/target 양쪽에서 test_command 직접 실행해서 fail→pass 확인. 결과를 curation.md 에 표 형태로.

## C. 이슈 #2 — B05 큐레이션 (feat)
완료 조건: `benchmarks/B05-businessday-deadline/` 아래 동일 4 파일 + suite 5개로 확장.
수행: B04 와 동일 절차, PR 만 ts-cxdm/workspace#2061.
주의: feat 라 base 에는 *해당 함수 자체가 없을 수* 있음 — test_command 는 'target 에서 함수가 callable + 정상 delta 반환' 으로 짜야 base→fail / target→pass 가 성립.

## D. 이슈 #3 — Real-judge dogfood (B01/B02/B03)
완료 조건:
- `.mimiron/_bench/B01-welcome-message-fix/mimiron_output.diff` 존재 (Mimiron pipeline 실 실행 산물)
- 동일하게 B02, B03 도 존재
- `.mimiron/_outer/judge/B01-welcome-message-fix.json`, B02, B03 존재 (samples 3개 + spread 기록)
- `.mimiron/_outer/status/B01-*.json`, B02, B03 의 verdict 가 'passed' 또는 'failed' (절대 'deferred' 아님)
- `mimiron-bench suite` 출력의 suite_aggregate 가 *실수* 값 (stub 아님)
- `dogfood/004-real-judge-bench.md` 가 run 과 관찰 사항 기록

수행:
1. 각 B0X 에 대해: `mimiron-bench run <id>` 로 Mimiron pipeline 종주 → `.mimiron/_bench/<id>/mimiron_output.diff` 산출.
2. Skill 도구로 `mimiron:bench-judge` 호출 (스킬 이름 정확히 — `/mimiron-bench-judge <id>` 형식), 3 회 median + spread 기록.
3. `mimiron-bench run <id> --similarity-from .mimiron/_outer/judge/<id>.json` 로 verdict 확정.
4. 3개 끝나면 `mimiron-bench suite` 실행 → suite_aggregate 캡쳐.
5. dogfood/004-real-judge-bench.md 작성: 각 B0X 의 score/spread, judge skill 의 *관찰된 약점*, suite aggregate, 의외였던 점.

# 자동 커밋/푸시/이슈 close 정책

각 이슈 작업이 끝나고 *위 완료 조건이 git 으로 관찰 가능한 시점*에:
- `git add` (관련 파일만 명시적으로, never -A)
- `git commit -m "feat(bench): curate B04 hallucination-guard (closes #1)"` 형식 (이슈 번호 항상 'closes #N' 으로)
- `git push origin main` 시도
- push 가 branch protection 등으로 거부되면 *바로 무한 재시도하지 말고*: 새 branch `v020-wrap/<이슈번호>` 로 옮기고 `gh pr create` 로 PR 생성 + 자동 머지 가능하면 `gh pr merge --squash --auto`.
- push 또는 PR merge 가 성공해야 GitHub 의 'closes #N' 이 발화 → 이슈 자동 close.

수동 close 가 필요하면 (예: dogfood 노트만 추가된 #3): `gh issue close <N> --comment "<커밋 SHA + 1줄 결과>"`.

# Self-correction 규칙

- 이전 iteration 의 흔적 (불완전 파일, 어중간한 커밋) 발견 시 *덮어쓰지 말고* 먼저 진단: `git log --oneline -10`, `git status`, 해당 파일 read.
- test_command 가 fail→pass 가정 깨지면 (base 에서도 pass, 또는 target 에서도 fail) test_command 전략부터 재검토. expected.diff 가 잘못 떠진 경우도 있으니 SHA 부터 재확인.
- bench-judge 가 score=1.0 또는 0.0 을 내면 *의심*. samples 와 rationale 재확인, 필요 시 한 번 더 돌림.
- 같은 작업을 3 iteration 연속 시도하는데 진전이 없으면: dogfood 노트에 'stuck: <원인>' 박고 *다른 이슈* 로 우회. 마지막 iteration 까지도 못 풀면 해당 이슈에 `gh issue comment` 로 막힌 지점 코멘트 + reopen 상태 유지.

# 완료 검증 (모든 작업이 끝났다고 생각될 때)

다음을 모두 만족해야 완료:
- `gh issue list --milestone v0.2.0 --state open` 결과가 0줄
- `git status` 가 clean
- `git log --oneline -10` 에 closes #1, #2, #3 가 모두 보임 (또는 머지된 PR)
- `dogfood/004-real-judge-bench.md` 와 (있다면) `dogfood/005-v020-wrap.md` 가 커밋되어 있음

모두 만족하면 *마지막* 메시지로 정확히 다음 한 줄만 출력:

MIMIRON_V020_CLOSED

부족한 게 있으면 절대 위 토큰 출력하지 말고, 부족한 항목 1개를 잡아 다음 iteration 으로 계속.
````

## 사후 검토 포인트 (실행 후)

ralph 가 `MIMIRON_V020_CLOSED` 를 출력한 뒤, 사람이 직접 확인:

- `gh issue list --milestone v0.2.0 --state closed` — 3 이슈 모두 closed 상태인지
- `.mimiron/_outer/status/` 의 verdict 파일 3개 가 stub/deferred 아닌 실제 값인지
- B04/B05 의 `issue.md` 가 *구현 어휘 누설* 없는지 (라이브러리/프레임워크 명 노출 X)
- B04/B05 의 expected.diff 가 PR merge commit 이 아니라 *base→target* 사이 진짜 diff 인지 (merge commit 의 conflict 해결분이 섞이면 안 됨)
- dogfood/004 의 4-fold judge defense 관찰 메모 — judge 가 어디서 *흔들렸는지* 가 핵심 시그널
