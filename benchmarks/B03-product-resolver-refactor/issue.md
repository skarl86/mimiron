# 상품 식별자 해상도 로직 중복 — 추출 필요

## 현황

`agents/naver-smartstore/app/routers/product.py`의 두 LangChain 도구
`get_product_info` 와 `quote_price` 는 사용자 입력의 *상품 식별자*
(`PRD...` 코드 또는 채널상품번호)를 받아 상품 dict로 변환하는 *동일한
분기 로직 13줄을* 각자 갖고 있다. 두 함수 머리에 TODO 주석이 박혀
있다: "다음 정리 PR에서 헬퍼로 추출".

## 의도된 동작

- 식별자 해상도 로직을 *한 곳*에 모아 두 도구가 호출하게 한다.
- *동작은 변경하지 않는다* — pure refactor.
- 두 도구의 외부 시그니처는 그대로.

## Acceptance criteria

- `product.py`에 식별자 해상도를 담당하는 *모듈 private 헬퍼 함수*가
  정확히 *한 개* 존재한다. 이름은 호출자 측 TODO 주석에 *명시된 그대로*
  쓴다 (signature 약속).
- 헬퍼는 PRD 코드 입력 시 *검색 → 채널상품번호 추출 → 상품 조회*
  체이닝을 수행한다.
- 헬퍼는 채널상품번호 입력 시 *바로* 상품 조회한다.
- 어느 경로든 실패하면 `None`을 반환한다.
- `get_product_info` 와 `quote_price` 가 *둘 다* 위 헬퍼를 호출한다.
- 기존 두 함수의 외부 동작이 변경되지 않음 (`tests/test_product_router_tool_payload.py` 5개 통과).
- 두 함수 머리의 TODO 주석은 제거된다.

## Out-of-scope

- 다른 도구 (OCR, 취소 마감일 등)는 손대지 않는다.
- 헬퍼의 *공개화* (외부 모듈에서 사용)는 하지 않는다 — 모듈 private 유지.
