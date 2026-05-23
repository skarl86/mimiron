---
name: mimiron-unstuck
description: |
  Mimiron의 *안전핀의 인격화*. `state.phase == "stuck"` (재시도 ≥3 또는 게이트 3연속 실패) 슬러그를 분석해 어디서·왜 막혔는지 사람용 보고서(`unstuck.md`)를 작성하고, 다음 행동 *세 가지*를 제안한다. **자동 복구 금지** — 모든 결정은 사용자가 한다. 다른 모든 skill과 달리, 이건 *재진입을 막는* 책임이 있다 (state.paused=true 마킹).
---

# unstuck — Mimiron Safety Pin

## 사용자 응답 언어

`.mimiron/<slug>/state.json`의 `user_language` 필드를 *시작 시 한 번* 읽어, `unstuck.md` 보고서와 사용자 대화 모두를 그 언어로 작성한다. `null` 이면 가장 최근 사용자 메시지 언어를 자동 감지. *phase 이름, gate 종류, task id는 영어 유지.*

## 진입 조건

- `state.phase == "stuck"` *또는*
- `state.consecutive_gate_fails >= 3` *또는*
- 사용자가 `/mimiron-unstuck <slug>` 명시 호출

(stuck이 아닌데 사용자가 호출했다면 *경고*만 띄우고 일반 progress 보고. 임의 mutate 금지.)

## 산출물

- `.mimiron/<slug>/unstuck.md` — 사람이 읽을 진단 + 3가지 다음 액션
- `state.paused = true` (CLI `mimiron pause <slug>`로) — stop-hook 재진입 차단
- **사용자 결정 대기** — 이 skill은 *제안만 한다*.

## 흐름

### 1) 진단 (read-only)

1. `mimiron status <slug>` → 현재 phase, gate_history 수, retry 카운터.
2. `state.json` 읽기:
   - `consecutive_gate_fails`
   - `retries[task_id]` — 어느 task가 retry 임계 도달?
   - `gate_history[-3:]` — 마지막 3 gate의 verdict/score
3. `.mimiron/<slug>/evaluation/` 의 마지막 verdict.json/semantic.md 요약.
4. `.mimiron/<slug>/drift.log` (있다면) tail 5줄 — owned 위반 패턴이 보이나?
5. `tasks/<task_id>/result.md` 마지막 실패 task의 요약.

### 2) 막힌 원인 분류

다음 카테고리 중 하나 또는 다중:

| 원인 | 시그널 | 권장 액션 패턴 |
|---|---|---|
| **임계 너무 엄격** | gate 점수가 cutoff에 *가까이* 떨어짐 (band 안에서 fail 누적) | thresholds.yaml 조정 |
| **plan 결함** | 같은 task가 3 retry — task가 *너무 큼* 또는 *AC가 모호* | plan.yaml 분할 또는 spec 보강 |
| **spec 모호** | reviewer 의견이 *서로 충돌* | spec_unlocked=true로 spec 재진입 |
| **인프라 문제** | mechanical gate가 build/test 환경 누락으로 fail | `_global/mechanical.toml` 수정 |
| **drift 누적** | drift.log에 owned 밖 쓰기 반복 | worker prompt에 더 강한 가드 |
| **외부 봉쇄** | 외부 API/리소스 의존성 — Mimiron 안에서 못 풀음 | archive + 사람 처리 |

### 3) `unstuck.md` 작성

```markdown
# Unstuck Report — <slug>

- **Stuck at**: <ISO timestamp>
- **Phase at stuck**: <state.phase>
- **Trigger**: consecutive_gate_fails=N OR retries=N OR manual

## 진단

- Last 3 gates:
  - <ts> phase=X kind=Y verdict=fail score=0.XX
  - ...
- Retry 카운터:
  - T03: 3/3 — *임계 도달*
- Drift log (최근 5):
  - <ts> file=...
- 가장 마지막 verdict 요약:
  > <semantic.md의 마지막 단락 인용>

## 추정 원인

<위 카테고리 중 1~2개 식별 + 근거 짧게>

## 다음 행동 (사용자 결정용 — 3가지)

### A. <행동 1, 가장 가능성 높은 것>
- 무엇: <한 줄>
- 어떻게: <구체적 명령 또는 편집>
- 위험: <부작용>

### B. <행동 2>
- 무엇:
- 어떻게:
- 위험:

### C. archive (마지막 수단)
- 무엇: 현재 상태로 종착 — 미완 산출물은 그대로 git에 살아 있음
- 어떻게: `mimiron archive <slug>`
- 위험: 다음 슬러그로 미완 task가 이어지지 않음. 사람 핸드오프 필요.
```

### 4) 차단

`mimiron pause <slug>` 호출 — `state.paused=true`. stop-hook 재진입 끊김. 사용자가 명시적으로 `/mimiron-resume <slug>` 또는 행동 A/B/C를 골라 진행하지 않는 한 *대기*.

### 5) 사용자에게 보고

```
unstuck <slug>: paused. Report: .mimiron/<slug>/unstuck.md
3 options proposed (A: <짧은 라벨>, B: <짧은 라벨>, C: archive).
```

이후 *추가 행동 없이 종료*. AskUserQuestion 으로 ABC 중 골라달라 요청 *가능* — 사용자 응답 후 해당 액션을 시작.

## 가드

- ❌ **자동으로 thresholds.yaml mutate 금지**. 제안만, 변경은 사용자.
- ❌ **자동으로 plan.yaml/spec.yaml mutate 금지**. spec_unlocked로 가는 결정은 *사용자가* 해야 함.
- ❌ **자동으로 archive 호출 금지**. 종착은 *사용자가* `mimiron archive` 또는 `/mimiron-unstuck`의 C 선택.
- ❌ **`state.phase`를 임의 변경 금지**. CLI(`mimiron pause`) 경유.
- ❌ **3개 이상 옵션 제안 금지**. 선택 과부하 — *세 개*가 한계.
- ❌ **"잘 모르겠으면 다시 retry" 같은 제안 금지**. 이미 retry 다 썼는데 그게 답인 적은 없음.
- ✅ **"외부 봉쇄"가 판단되면 *솔직하게 archive 권장*** — Mimiron이 못 푸는 문제도 있다.

## 다음

- 사용자가 A/B를 골라 진행 → 해당 행동 실행 + `mimiron resume <slug>`로 paused 해제 + 적절한 skill 재진입.
- 사용자가 C를 골라 진행 → `mimiron archive <slug>` → done.
- 사용자가 응답 없이 세션 끝 → 슬러그는 paused 유지, 다음 세션에서 사용자 결정.
