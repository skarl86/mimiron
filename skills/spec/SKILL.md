---
name: mimiron-spec
description: Mimiron 파이프라인의 spec phase. clarification.md를 입력으로 spec.yaml(goal, constraints, acceptance_criteria with verify-kind contract, ontology)을 결정화하고 quality_score ≥ 0.85 게이트 통과 시 phase=plan으로 전이. /mimiron으로 시작된 슬러그가 phase=spec일 때 자동 발동.
---

# spec — Mimiron Phase 2

## 사용자 응답 언어

`.mimiron/<slug>/state.json`의 `user_language` 필드를 *시작 시 한 번* 읽어, 사용자에게 보내는 자연어 산문(질문, 진행 알림, spec.yaml의 `desc`·`goal` 등 사람이 읽는 텍스트)을 그 언어로 작성한다. `null` 이면 가장 최근 사용자 메시지 언어를 자동 감지해 매칭. *YAML 키, `kind` enum, 파일 경로, 식별자는 영어 유지* — 자연어 산문에만 적용.

## 진입 조건

- `state.phase == "spec"` (ambiguity gate 통과 직후)
- `clarification.md` 존재

## 산출물

- `.mimiron/<slug>/spec.yaml` — schema § 12.2 준수
- spec.yaml의 `quality_score` 필드를 채움
- state.gate_history에 `{kind: quality}` 한 줄

## 흐름

1. clarification.md를 읽고, 다음 구조로 spec.yaml을 *결정화*:
   ```yaml
   schema_version: 1
   slug: <slug>
   goal: "<한 문장>"
   constraints:
     - id: C01
       desc: "<what-level statement only — *implementation 어휘 금지*>"
       kind: what               # 또는 prescribed_implementation
   acceptance_criteria:
     - id: AC01
       desc: "<검증 가능한 진술>"
       verify:
         # 아래 verify-kind 표 참고. 정확한 *kind 이름*은 test / grep / reviewer 셋 뿐.
         kind: test
         command: "<bash 명령>"
   ontology:
     <term>: "<definition>"
   hypothesis:
     - id: H01
       claim: "<왜 이렇게 만든다고 생각하나 — outcome가 H를 부정할 수도 있음>"
       confidence: 0.75         # 0~1
   quality_score: <0~1, median-of-3>
   ambiguity_score: <0~1, clarification.md에서 복사>
   ```

   **verify-kind 표** (`acceptance_criteria[].verify` 필드 — 결정적 검증을
   위해 *kind 별로 다른 필드*를 요구한다):

   | `kind` | 필요한 추가 필드 | 의미 |
   |---|---|---|
   | `test` | `command: "<bash>"` | shell 명령 exit 0이면 pass. 자동 검증 *최선의 선택*. |
   | `grep` | `pattern: "<regex>"` + `in: "<file path>"` | `in` 파일에 `pattern` regex가 매치되면 pass. *키 이름이 `in` 임 주의* (yaml 예약어 회피로 Python attr는 `in_` 이지만 yaml에서는 `in:`). |
   | `reviewer` | (없음) | LLM judge가 채점 — 다른 옵션이 *진짜* 없을 때만. spec quality_score에 페널티 (reviewer-kind 비율 > 50% → -0.1). |

   ⚠️ **`kind` 값으로 `pattern` 이나 `in` 같은 *필드명*을 쓰지 말 것** — 그건 grep의 *하위 필드*다. dogfood 결과 자주 헷갈리는 함정.
2. 각 acceptance_criterion의 `verify.kind`를 *반드시* 선언. `kind=reviewer` 비율이 50% 초과면 quality_score에 페널티 0.1 차감 (구조적 단속).
3. quality_score를 *median-of-3*로 자가 평가. 룰브릭:
   - Q1: criteria testability (각 AC가 자동 검증 가능한가)
   - Q2: ontology completeness (도메인 단어 정의 충분)
   - Q3: constraint specificity (모호한 문장 없음)
   - Q4: scope clarity (out-of-scope가 명시)
   - 평균을 quality_score로
4. 게이트 임계 (`thresholds.yaml.spec_quality_min`, 기본 0.85). certainty band `[0.80, 0.90]` 안이면 `needs_review`.
5. 통과하면 `mimiron gate <slug> quality`로 verdict 저장 후, 다음 phase=plan 자동 전이는 spec gate에서 *CLI가 처리*.

## 가드

- spec.yaml에 *구현 어휘* 노출 금지 (v1+ pollution-free spec 시그니처). v0는 self-check 권고만.
- LLM 호출 temperature=0, median-of-3.

## 다음

- spec.yaml 작성 완료 → quality gate 통과 → phase=plan, plan skill 자동 발동.
