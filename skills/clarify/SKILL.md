---
name: mimiron-clarify
description: Mimiron 파이프라인의 clarify phase. Socratic 인터뷰로 모호성을 줄이고 ambiguity_score ≤ 0.2 게이트 통과 시 clarification.md 작성. /mimiron으로 시작된 슬러그가 phase=clarify일 때 자동 발동.
---

# clarify — Mimiron Phase 1

## 진입 조건

- `state.phase == "clarify"` 인 슬러그가 있다 (확인: `mimiron status <slug>`)
- 아직 `clarification.md`가 없거나 ambiguity gate를 통과하지 못함

## 산출물

- `.mimiron/<slug>/clarification.md`
- spec.yaml의 `ambiguity_score: <0.0~1.0>` 필드를 채움
- state.gate_history에 `{kind: ambiguity, verdict, score, samples}` 한 줄 추가

## 흐름

1. 사용자가 준 *feature 요청 한 줄*을 읽고, 다음 4가지 차원에서 *빠진 정보*를 찾는다:
   - **Acceptance criteria**: 무엇이 충족되어야 "끝"인가
   - **Undefined terms**: 도메인 단어 중 정의 안 된 것
   - **Conflicting goals**: 서로 충돌할 수 있는 요구
   - **Out-of-scope boundary**: 무엇은 *안* 하는 것

2. *한 번에 하나씩* 사용자에게 질문 (multi-choice 우선).
3. 답변마다 위 4 차원에서 *해결된 항목*을 표시.
4. ambiguity_score를 *self-evaluate*: 1=완전 모호, 0=완전 명확. *median-of-3*으로 산출(같은 룰브릭으로 3회 채점, median).
5. `_global/thresholds.yaml.ambiguity_max`(기본 0.2) 이하면 게이트 통과.
   - **Certainty band**: 점수가 `[0.15, 0.25]` 안이면 자동 `needs_review` → state=paused, 사용자 승인 대기.
6. 통과하면 `clarification.md`를 작성:
   ```markdown
   ---
   slug: <slug>
   ambiguity_score: <median>
   samples: [<s1>, <s2>, <s3>]
   ---

   # Clarification — <slug>

   ## Goal
   <한 문장>

   ## Resolved
   - <차원>: <합의>
   - ...

   ## Open (deliberately out-of-scope)
   - <차원>: <왜 안 하는지>
   ```
7. `mimiron` CLI로 phase=spec 전이는 spec skill이 담당. clarify는 *clarification.md 작성과 phase=clarify 유지*만.

## 룰브릭 (ambiguity 채점)

다음 4 항목 각 0~1, 평균을 ambiguity_score로:
- A1: missing acceptance criteria (1 = 없음, 0 = 충분)
- A2: undefined domain terms (1 = 많음, 0 = 없음)
- A3: conflicting goals (1 = 존재, 0 = 없음)
- A4: unclear boundary (1 = 모호, 0 = 명확)

## 가드

- 사용자가 "더 묻지 마" / "그냥 진행해"로 명시 abort: `state.spec_unlocked=true`로 변경 후 clarification.md를 *현재 합의대로* 작성, ambiguity_score=0.0 강제 기록 (override 표시).
- LLM 호출은 *항상* temperature=0, median-of-3.

## 다음

- `clarification.md` 작성 완료 → spec skill 진입 (사용자에게 알림).
