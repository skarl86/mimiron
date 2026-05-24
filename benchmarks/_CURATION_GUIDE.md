# Benchmark Curation Guide

이 문서는 새 benchmark 를 `benchmarks/<id>/` 아래에 큐레이션할 때, 특히 `issue.md` 의 *root-cause hint 수준* 을 어디까지 노출할지 결정하기 위한 가이드라인입니다.

## 배경 — 왜 이 가이드가 필요한가

dogfood/005-real-judge-bench.md 의 B01 케이스에서 관찰된 갭:

- B01 의 `issue.md` 는 "정상 동작" 정도로만 기술되어 있어 candidate (agent) 가 `if insert_result.data:` 게이트를 *wild guess* 로 의심해 제거 (오히려 silent failure 회귀 추가).
- 실제 expected 는 `source` 칼럼이 DB 스키마에 없어서 PostgREST 42703 에러를 내는 *외부 시그널 기반 진단*.
- `issue.md` 가 그 시그널을 *증상 형태로* 라도 제공했다면 candidate 가 wild guess 를 안 했을 가능성 큼.

대조군: B02 / B04 / B05 는 원본 PR description 에 *근본 원인* 이 명시되어 있어 `issue.md` 도 그걸 행동 단위로 옮길 수 있었음.

이 갭을 닫기 위한 5 룰.

## 5 룰

### 1. 외부 시그널 기반 진단은 *증상 형태로* 노출 OK

PostgREST 에러 코드, HTTP 5XX, 무한 루프, 특정 로그 패턴 같은 *시스템 경계에서 관찰되는 시그널* 은 `issue.md` 에 적어도 된다 — 단, *원인 단정* 이 아니라 *증상 형태* 로.

OK 예:
> 재접속 시 에러 로그에 `42703` (외부 시스템 코드) 가 보이고 메시지 미발송.

NG 예 (원인 단정):
> Supabase 의 `source` 칼럼이 누락되어서 발생함.

### 2. 구현 vocabulary 누설 금지

라이브러리·프레임워크 이름은 `issue.md` 에 드러내지 않는다. agent 가 *큐레이션이 의도한 fix 경로* 를 즉시 알아내서 benchmark 가 자명해지는 것을 막기 위함.

NG 예: "pydantic 의 validator 가 `None` 을 통과시킴"
OK 예: "입력이 비어 있어도 검증을 통과해 잘못된 값이 저장됨"

파일 경로 / 함수 시그니처 / 도메인 객체 이름은 *허용* — 큐레이션 의도를 노출하지 않는 한.

### 3. Acceptance criteria 는 *행동 단위*

AC 는 "코드가 무엇을 하는가" 가 아니라 "어떤 *외부 관찰 가능한 동작* 이 성립해야 하는가" 로 작성한다. 파일/함수 시그니처는 *최소한* 으로 — agent 가 큐레이터의 구현 형태를 모방하도록 강제하면 benchmark 가 *모양 베끼기 시험* 으로 전락한다.

OK 예: "재접속 시 웰컴 메시지가 *재발송되지 않는다* (당일 기준)"
NG 예: "`daily_access_tracker.is_first_access_today()` 가 `False` 를 리턴한다"

(예외: B04 같은 *복합 fix* 는 신설 파일/함수가 *AC 의 핵심* 일 수 있음 — 그땐 명시. 다만 *최소한* 으로.)

### 4. Out-of-scope 명시

agent 의 *wild guess 가능 영역* 을 사전 차단한다. 다른 에이전트, 인접 모듈, 후속 follow-up 으로 분리된 작업은 모두 "이번 변경 범위 아님" 으로 박는다.

이게 빠지면 agent 가 *주변 정리* 까지 시도해 candidate diff 가 비대해지고, judge 의 J1 (위치) / J3 (회귀) 채점이 흐려진다.

### 5. 선택 PR description 이 *원인-결과* 로 분리된 PR 만 큐레이션

후보 PR 의 description 이 "증상 → 원인 → 해결" 구조로 *명확히* 적혀 있는 PR 만 큐레이션. 그렇지 않은 PR 은 `issue.md` 작성이 어렵고, 큐레이터의 *재구성* 단계에서 원본 의도가 왜곡될 위험이 크다.

가능하면 *PR 본문 자체* 가 description 으로 거의 그대로 `issue.md` 5 섹션 (증상 / 의도된 동작 / AC / Out-of-scope / 참고) 으로 매핑되는 PR 을 선호.

## 예시 — Positive / Negative

### Positive: B02 `benchmarks/B02-counselor-handover/issue.md`

- 증상: "상담사가 *개입한 이후에도* 봇이 사용자 메시지에 계속 응답하여 *이중 답변* 발생."
- 의도된 동작: 상담사 주도권 상태 / 핸드오버 시그널 / 비공식 답변 정황 — 3 시나리오 모두 *행동 단위* 로 분리.
- AC: HTTP 200 반환 / passThread 발송 / 회귀 없음 — *외부 관찰 가능* 한 행동.
- Out-of-scope: 다른 에이전트, 상담사 화면 변경 — 명시적 차단.

### Positive: B04 `benchmarks/B04-hallucination-guard/issue.md`

- 증상: 컨텍스트 오염 / 산수 환각 / 내부 필드 유출 — 3 결함을 *시그널 형태* (수치 불일치 사례, 노출되면 안 되는 필드명) 로.
- 라이브러리 명 (langchain, pydantic 등) 일체 없음 — 구현 vocabulary 누설 0.
- AC 에 파일/함수 명이 비교적 많이 노출되지만 *복합 fix* 라 신설 모듈이 AC 의 핵심 — 룰 #3 의 예외 케이스에 해당.

### Negative: B01 `benchmarks/B01-welcome-message-fix/issue.md` (원본 형태)

- "정상 동작" 정도로만 acceptance criteria 가 적혀 있었음.
- 외부 시그널 (PostgREST 42703 에러) 이 *전혀 노출되지 않음* → agent 가 다른 root cause 로 wild guess → catastrophic fail.
- 본 가이드 도입 후 *시그널 1줄* 보강됨 (dogfood/005 회고 기반).

## 큐레이션 시 체크리스트

새 benchmark 의 `curation.md` 에 다음을 인용 / 체크해주세요:

- [ ] 룰 1: 외부 시그널을 *증상 형태로* 노출했는가 (또는 시그널이 없는 케이스라면 명시)
- [ ] 룰 2: 라이브러리·프레임워크 명을 누설하지 않았는가
- [ ] 룰 3: AC 가 행동 단위인가 (파일/함수는 최소한인가)
- [ ] 룰 4: Out-of-scope 가 *agent 의 wild guess 영역* 까지 차단하는가
- [ ] 룰 5: 후보 PR description 이 *원인-결과* 로 분리되어 있었는가

체크가 어렵거나 룰을 *의도적으로* 어기는 경우 (예: B04 의 AC 가 파일/함수 다수 노출) 그 이유를 `curation.md` 에 명시.

## 참고

- dogfood/005-real-judge-bench.md §"흥미로운 점" 2번 (root-cause hint 균형 문제)
- 이 가이드는 v0.3.0 의 issue #25 회고로 도입.
