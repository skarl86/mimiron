# B04 큐레이션 노트

- **후보 PR**: [ts-cxdm/workspace#2046](https://github.com/ts-cxdm/workspace/pull/2046) — fix(smartstore): 가격 견적 환각 근본 차단 (벳푸 사파리 사건)
- **선택 일자**: 2026-05-24
- **난이도**: hard
- **base_ref**: `7585e0a3a629468aeb5b9525a609453bf7c750fc`
- **target_ref**: `4267e138c28976ef22fdbc557b1220d7bef97850` (merge commit)
- **변경 파일 수**: 9 (prod 4 + test fixtures/tests 5)  *plan doc 1건 제외*
- **변경 라인 수**: +2286 / -95 (plan doc 제외 시점 기준)

## 선택 이유

1. **난이도 다양성** — B01(easy, 4줄) / B02(medium, 153줄) 위로 *hard tier* 가 비어 있었음. B04 는 *9 파일, 신규 서비스 1개, 도구 등록, 프롬프트 개정* 까지 *수직 슬라이스* 변경.
2. **PR 본문이 *근본 원인 3분할*(컨텍스트 오염 / LLM 산수 환각 / 내부 필드 유출) 로 정리되어 있어** acceptance criteria 를 *행동 단위* 로 깔끔하게 옮길 수 있음.
3. **구조적 fix** — workaround 가 아니라 신규 결정론 계산 모듈 분리 + 단일 진실 소스 헬퍼 도입. Mimiron 이 *플랜 단계에서 옳은 분해를 했는지* 가 직접 시그널이 됨.
4. **실 운영 사고 기반** — 실제 결제 금액과 LLM 답변이 어긋난 incident. 의도와 도메인이 *명확* 해 구현 어휘 누설 없이 issue.md 가 작성 가능.
5. **expected.diff 가 *durable signal* 을 풍부하게 제공** — 신규 파일 1, 신규 함수 2, 도구 등록 1, 프롬프트 갱신 1. test_command 의 AND 매칭이 우연 일치 거의 불가.

## 검증 항목

- [x] **issue.md 에 *구현 어휘 누설* 없음**: `apolloInfo`/`net_price_currency`/`compute_quote`/`resolve_option_unit_prices` 같은 *내부 식별자* 는 issue.md 에서 제거. 파일 경로·함수 시그니처는 acceptance criteria 에 일부 유지 (B01/B02 양식). 라이브러리·프레임워크 명칭(pydantic, langchain 등) 노출 없음.
- [x] **expected.diff 정합성**: `git diff <base>..<target> -- 'agents/'` 로 생성. `docs/superpowers/plans/2026-05-19-smartstore-price-quote-hardening.md` (1290 줄 planning artifact) 는 *judge 공정성 위해 의도적으로 제외* — Mimiron 이 재현할 산출물이 아님. 변경 라인 수는 prod+test 만 반영.
- [x] **test_command 가 base 에서는 fail, target 에서는 pass**: 수동 검증 완료. base_ref (`7585e0a3`) 에서 exit=1 (price_quote.py 미존재), target_ref (`4267e138`) 에서 exit=0 (4개 signal 모두 통과).

## test_command 전략

4 개 *durable fix signal* 을 AND 매칭. 풀 pytest 회피, file-content assertion:

```python
python3 -c "
import os, sys
root='agents/naver-smartstore'
ok = (
    os.path.exists(f'{root}/app/services/price_quote.py')
    and 'def compute_quote' in open(f'{root}/app/services/price_quote.py').read()
    and 'def resolve_option_unit_prices' in open(f'{root}/app/services/product_context.py').read()
    and 'quote_price' in open(f'{root}/app/routers/product.py').read()
)
sys.exit(0 if ok else 1)
"
```

| ref | price_quote.py | compute_quote | resolve_option_unit_prices | quote_price tool | exit |
|---|---|---|---|---|---|
| base (`7585e0a3`) | 미존재 | – | – | – | 1 (fail) |
| target (`4267e138`) | 존재 | ✓ | ✓ | ✓ | 0 (pass) |

*infra smoke 모드* — 실 mimiron pipeline 평가 시점에는 더 두꺼운 test_command (예: `pytest tests/test_product_intent_regression_beppu.py`) 로 교체 권장.

## B02 와의 차이

| 측면 | B02 | B04 |
|---|---|---|
| Diff 크기 | 193줄 (실 153줄) | 1359줄 (실 2286줄, plan doc 제외 후) |
| 파일 수 | 4 (prod 3 + test 1) | 9 (prod 4 + test 5) |
| 변경 종류 | 가드 3종 + 헬퍼 추가 | 신규 서비스 모듈 + 도구 등록 + 단일 진실 소스 |
| 도메인 | 상담사 핸드오버 | 상품 가격 견적 환각 |
| 난이도 | medium | hard |
| 신규 파일 | 0 | 4 (서비스 1, 테스트 3, fixture 1) |
| Mimiron 도전 포인트 | 가드 3종 모두 검출 | *구조적 분해* (계산 → 모듈 / 단가 → 단일 소스 / 견적 → 도구) |
