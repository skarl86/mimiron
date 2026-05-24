# B05 큐레이션 노트

- **후보 PR**: [ts-cxdm/workspace#2061](https://github.com/ts-cxdm/workspace/pull/2061) — feat(smartstore): 취소 접수 마감일 영업일 보정
- **선택 일자**: 2026-05-24
- **난이도**: medium
- **base_ref**: `a1f9d134bf2452db49ba954ab089e9ec906265b3`
- **target_ref**: `dc77cba548b0c10e63e94d9d9d7300c9b87dff6c` (merge commit)
- **변경 파일 수**: 18 (agents/ pathspec 한정. plan doc 1건 제외)
- **변경 라인 수**: +1630 / -19 (PR 전체 기준)

## 선택 이유 (variation type: feat)

1. **변경 종류 다양성** — B01·B02·B04 가 모두 *fix* (기존 코드의 버그 수정) 인 반면 B05 는 *feat* — *기능 자체가 base 에 없는* 신규 도입. Mimiron 이 *없는 것을 만들어야 함* 이 시그널.
2. **신규 모듈 두 개** — `business_hours.py` (SSOT 상수), `cancellation_deadline.py` (순수 계산 + LLM 도구). *모듈 경계 분리* 가 plan 단계의 핵심 결정.
3. **PR description 이 *근본 원인 + 변경 단위* 로 정리** — 사용 사례·기대 결과·E2E 검증까지 포함. acceptance criteria 가 *결정론 vs LLM 책임 분리* 라는 *행동 단위* 로 깔끔하게 옮겨짐.
4. **실 운영 incident 기반** — 상품 #13369865657 사용자가 받은 잘못된 안내. 의도와 도메인이 *명확*.
5. **horizontal touch** — 라우터 2개(cancel_refund + product) 에 도구 등록 + 프롬프트 갱신. *한 기능을 위해 다중 흐름을 일관되게 갱신* 하는 Mimiron 의 plan dispatch 능력 시험.

## 검증 항목

- [x] **issue.md 에 *구현 어휘 누설* 없음**: 라이브러리 명칭(`holidays` 등) 제거 — "외부 라이브러리·달력 등 결정론 데이터 소스" 로 우회 표현. `langchain`/`pydantic` 같은 프레임워크 명칭 비노출. 파일 경로·함수 시그니처는 acceptance criteria 일부로 유지 (B01/B02/B04 양식).
- [x] **expected.diff 정합성**: `git diff <base>..<target> -- 'agents/'` 로 생성. `docs/superpowers/plans/2026-05-20-smartstore-cancellation-deadline-business-day.md` (1075줄 plan doc) 는 *judge 공정성 위해 제외* — Mimiron 이 재현할 산출물 아님.
- [x] **test_command 가 base 에서는 fail, target 에서는 pass**: 수동 검증 완료. base_ref (`a1f9d134`) 에서 exit=1 (business_hours.py·cancellation_deadline.py 미존재), target_ref (`dc77cba5`) 에서 exit=0 (4 signal 모두 통과).

## test_command 전략

feat 이므로 base 에는 신규 파일·함수가 *없음* — 그 부재를 *fail signal* 로 활용. 4 durable signal AND 매칭:

```python
python3 -c "
import os, sys
root='agents/naver-smartstore'
ok = (
    os.path.exists(f'{root}/app/business_hours.py')
    and os.path.exists(f'{root}/app/services/cancellation_deadline.py')
    and 'def compute_cancellation_deadline' in open(f'{root}/app/services/cancellation_deadline.py').read()
    and 'def is_business_day' in open(f'{root}/app/utils.py').read()
)
sys.exit(0 if ok else 1)
"
```

| ref | business_hours.py | cancellation_deadline.py | compute_cancellation_deadline | is_business_day | exit |
|---|---|---|---|---|---|
| base (`a1f9d134`) | 미존재 | 미존재 | – | 미존재 | 1 (fail) |
| target (`dc77cba5`) | 존재 | 존재 | ✓ | ✓ | 0 (pass) |

*infra smoke 모드* — 실 mimiron pipeline 평가 시점에는 `pytest tests/test_cancellation_deadline.py` 처럼 *함수 동작* 검증 모드로 교체 권장 (docs/ralph-v0.2.0-wrap.md 가이드: "target 에서 함수가 callable + 정상 delta 반환").

## 기존 B0X 와의 차이

| 측면 | B01 | B02 | B04 | B05 |
|---|---|---|---|---|
| 변경 종류 | fix (subtractive) | fix (가드 추가) | fix (구조 재편) | **feat (신규 기능)** |
| Diff 크기 | 33줄 | 193줄 | 1359줄 | 842줄 |
| 파일 수 | 2 | 4 | 9 | 18 |
| 신규 파일 | 0 | 0 | 4 | **7** |
| 도메인 | 웰컴 메시지 | 핸드오버 | 가격 견적 | **취소 마감일** |
| 난이도 | easy | medium | hard | medium |
| Mimiron 도전 포인트 | 키 1개 제거 | 가드 3종 검출 | 구조적 분해 | **모듈 경계 + 결정론·LLM 책임 분리 + horizontal 도구 등록** |
