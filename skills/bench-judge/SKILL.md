---
name: mimiron-bench-judge
description: Mimiron self-eval 루프의 *판정자(judge)*. Mimiron이 만든 diff와 원본 PR의 expected diff를 비교해 0~1 의미 유사도 점수를 산출, .mimiron/_outer/judge/<bench_id>.json으로 기록한다. `mimiron-bench run <id> --similarity-from <judge.json>`이 그 파일을 읽어 verdict를 확정. deterministic CLI에서 LLM 직접 호출이 금지되므로 (3-Lane 분리) 이 skill이 *유일한* judge 생산 경로.
---

# bench-judge — Mimiron Self-Eval Judge

## 사용자 응답 언어

이 skill의 산출물은 JSON 점수 파일이라 언어 영향이 적지만, 사용자에게 보내는 진행 알림은 호출 컨텍스트에 `user_language` 단서가 있으면 그걸 따른다. 없으면 사용자 메시지 언어를 자동 감지. JSON 키와 score는 영어/숫자 그대로.

## 언제 발동

- `mimiron-bench run <id>` 이 `status: deferred, reason: similarity_provider not set`을 반환했을 때
- 사용자가 `bench-judge <id>` 또는 동등 요청을 했을 때
- Outer ralph-loop이 deferred 케이스를 unstuck하려 할 때

## 진입 조건

- `benchmarks/<bench_id>/expected.diff` 가 존재
- Mimiron이 만든 *후보 diff* 가 다음 중 하나에 존재:
  - `.mimiron/_bench/<bench_id>/mimiron_output.diff` (자동 모드)
  - `.mimiron/<task_slug>/mimiron_output.diff` (수동 모드)
  - 사용자가 `--actual <path>`로 명시
- `state.phase`는 무관 (이 skill은 outer-loop 도구)

## 산출물

- `.mimiron/_outer/judge/<bench_id>.json`
  ```json
  {
    "score": 0.0~1.0,
    "rationale": "<200자 미만 정리>",
    "samples": [s1, s2, s3],
    "apply_check": 0.0 | 1.0,
    "ts": "<ISO8601>"
  }
  ```
  (현 schema는 `score`만 필수. `samples`/`rationale`/`apply_check`/`ts`는 optional — 없으면 4-차원 fallback 으로 해석.)

## 점수 룰브릭 (5 차원, 각 0~1, *동일 가중치 평균*)

1. **J1 — 변경 위치 일치도**: actual diff의 파일/함수가 expected와 같은가
2. **J2 — 변경 의미 일치도**: 추가/삭제/수정의 *기능적 효과*가 같은가 (이름/주석은 무관)
3. **J3 — 회귀 위험**: actual이 expected가 *건드리지 않은* 영역을 손댔는가 (많을수록 점수 ↓)
4. **J4 — 완결성**: acceptance criteria의 *모든* 항목이 actual에서 만족되는가
5. **J5 — Applicability** *(v0.3.0 신설)*: actual diff 가 base_ref 워크트리에 *적용 가능* 한가. 0/1 binary.

`score = (J1 + J2 + J3 + J4 + J5) / 5`

> **Backward-compat fallback**: judge JSON 에 `apply_check` 필드가 *없으면* (v0.2.0 이전 산출물) 4-차원 평균 `(J1+J2+J3+J4)/4` 로 해석. 이 fallback 은 *읽기 호환성* 만 — 신규 채점은 반드시 J5 포함.

### J5 산출 — 가벼운 형태 (기본)

```bash
git -C <repo> checkout <base_ref>
git -C <repo> apply --check <candidate.diff>
```

- exit 0 → **J5 = 1.0** (`apply_check: 1.0`)
- non-zero (corrupt patch / context mismatch / 미존재 파일 등) → **J5 = 0.0** (`apply_check: 0.0`)

이 형태는 *catastrophic 수준의 부적용 candidate* (hand-edited 또는 LLM-generated diff 에서 흔한 hunk 카운트 깨짐, 잘못된 base 가정 등) 를 잡는다. 가장 가볍고 결정론적.

### J5 산출 — 강한 형태 (opt-in, `--strong-applicability` 플래그)

apply --check 통과 + 추가로 변경된 *.py 파일들의 syntactic validity 검사:

```bash
git -C <repo> apply <candidate.diff>
python -m py_compile <changed.py files>
```

- 모든 .py 통과 → J5 = 1.0
- 임의 1개 syntax error → J5 = 0.0

⚠️ **알려진 한계**: Python NameError / AttributeError 같은 *runtime* 결함은 py_compile 이 잡지 못한다 (bytecode 컴파일은 name resolution 을 하지 않음). 이런 catastrophic-but-syntactically-valid candidate 는 J5 로 detection 불가 — `bench_score` 산식 차원 (#20) 에서 *candidate-applied test_command* 로 보완.

### J5 와 다른 차원의 관계

- J5 = 0.0 이면 J1~J4 채점은 *그래도* 진행 (LLM 은 diff 텍스트만으로 채점 가능). 다만 rationale 에 "apply_check failed — runtime semantics 추정 불가" 명시.
- J5 = 1.0 이 J1~J4 의 *상한선* 을 의미하지 않음. apply 되더라도 의미가 완전히 어긋날 수 있음 (B02 케이스).

## 흐름

1. `benchmarks/<id>/expected.diff` 읽기.
2. actual diff 위치 결정 (위 진입조건 우선순위).
3. **J5 (apply-check) 먼저 산출** (deterministic, LLM 호출 없음):
   - benchmark.yaml 에서 `repo` 와 `base_ref` 추출
   - `git -C <repo> checkout <base_ref> && git -C <repo> apply --check <actual>` 실행
   - 결과를 `apply_check` 0.0/1.0 으로 기록
4. 두 diff를 *나란히* 살피며 5-차원 채점 (J5 는 위에서 산출된 값을 그대로 사용).
5. **median-of-3** 실행 (같은 룰브릭으로 3회 채점, median을 score로):
   - LLM temperature=0
   - 3 샘플 모두 기록 (audit용)
6. **Certainty band** check: 3 샘플의 *최대-최소* 가 0.15를 초과하면 *uncertain*로
   판정 → score는 median을 유지하되 `rationale`에 "uncertain — spread 0.X"를 명시.
7. `.mimiron/_outer/judge/<bench_id>.json` 작성 (atomic — 임시 파일에 write 후 rename).
8. 사용자에게 한 줄 보고:
   ```
   judge <id>: score=0.XX (samples [.X, .X, .X], spread .Y). 
   → mimiron-bench run <id> --similarity-from <path>
   ```

## 가드

- **LLM 호출은 *이 skill 안에서만***. CLI에 점수 산출을 위임하지 말 것.
- **expected.diff와 actual diff를 *그대로* LLM에 전달**. 사전 요약/정규화 금지 (편향).
- **점수 0.0 ~ 1.0 *strict***. 0 미만/1 초과는 무효 — 재채점.
- **score = 1.0이 나오면 의심**. 두 diff가 *문자 단위로* 동일하지 않은 한 1.0은 거의 없음.
  나오면 rationale에 *왜* 그렇게 판단했는지 명시.
- **score = 0.0도 의심**. 어떤 actual diff든 J1 위치 일부는 일치할 수 있음. 0이 나오면
  actual이 *완전히 빈* diff인지 먼저 확인.

## 산출 예시

```json
{
  "score": 0.86,
  "rationale": "J1=1.0(같은 파일), J2=0.8(같은 효과, 이름 다름), J3=0.7(불필요한 import 추가), J4=0.8(criteria 4/5 만족), J5=1.0(apply-check pass). median-of-3 from [0.84, 0.86, 0.88], spread 0.04 (certain).",
  "samples": [0.84, 0.86, 0.88],
  "apply_check": 1.0,
  "ts": "2026-05-23T12:34:56Z"
}
```

## 안 할 것

- ❌ Mimiron CLI를 *수정*하지 말 것 (CLI는 결정적 lane).
- ❌ expected.diff를 *수정*하지 말 것 (외부 PR repo 기반, 읽기 전용).
- ❌ score를 *수동으로* 결정하지 말 것 (median-of-3 룰브릭 강제).
- ❌ `--similarity-from` 인자를 임의 변경하지 말 것 (CLI 계약).

## 다음

- judge 파일 작성 → 사용자가 `mimiron-bench run <id> --similarity-from <path>` 실행.
- verdict가 `passed` (≥cutoff)면 그 케이스는 outer-loop에서 *해결됨*.
- `failed`면 ralph-loop의 다음 iter에서 Mimiron 본체 수정.
