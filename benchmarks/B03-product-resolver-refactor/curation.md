# B03 큐레이션 노트

- **후보 PR**: [ts-cxdm/workspace#2072](https://github.com/ts-cxdm/workspace/pull/2072) — refactor(smartstore): product 라우터 식별자 해상도 헬퍼 추출
- **선택 일자**: 2026-05-23
- **난이도**: medium
- **base_ref**: `459f093cbe90984404a8bb5ce5f550e78267e707`
- **target_ref**: `5dc89af353d0c5ca61cffa962d4c1034bc875daf`
- **변경 파일 수**: 1
- **변경 라인 수**: +22 / -34 (net -12 LOC)

## 선택 이유

1. **B01/B02와 다른 변경 유형 (refactor)** — fix가 아닌 *pure refactor*. 동작 변경 없음, 코드 위치만 이동. Mimiron이 *non-behavior* 변경을 어떻게 다루나 측정.
2. **TODO 주석이 *직접* 헬퍼 시그니처를 명시** — `async def _resolve_product(client, identifier) -> dict | None`. 호출자가 명확한 *계약*을 박아둠 → Mimiron이 그 시그니처를 그대로 구현하면 됨.
3. **회귀 위험 낮음** — 단일 파일, 동작 동일성만 유지.
4. **acceptance criteria가 *명확한 4 조건*** — 헬퍼 존재, PRD 분기, channelProductNo 분기, None fallback. 점수화 쉬움.

## 검증 항목

- [x] **issue.md에 *구현 어휘 누설* 없음**: `_resolve_product`, `search_products_by_prd` 같은 *함수명*은 issue.md에 등장하지 않음. 행동 단위로 기술 (예: "검색 → 채널상품번호 추출 → 상품 조회").
- [x] **expected.diff 크기**: 81 lines (헤더 포함). 실 변경 56 lines (prod +22 / -34).
- [x] **test_command가 base에서는 fail, target에서는 pass 인지**: 수동 검증 — base에 TODO 주석 + 헬퍼 없음 (exit 1), target에 헬퍼 + TODO 제거 (exit 0).

## test_command 전략

3가지 결정적 조건 grep:

```bash
python3 -c "import sys; s=open('agents/naver-smartstore/app/routers/product.py').read(); ok = ('_resolve_product' in s) and (s.count('_resolve_product(commerce_client') >= 2) and ('PRD/channel 식별자 해상도 로직이 quote_price 와 중복' not in s); sys.exit(0 if ok else 1)"
```

- `_resolve_product` 정의 또는 호출이 존재
- `_resolve_product(commerce_client` 호출이 *2회 이상* (두 도구가 모두 호출)
- 원본 TODO 주석 제거됨

*infra smoke 모드* — 실 mimiron pipeline은 `pytest tests/test_product_router_tool_payload.py`로 5 cases 통과 검증.

## B01/B02/B03 비교

| 측면 | B01 | B02 | B03 |
|---|---|---|---|
| 변경 유형 | bug fix (subtractive) | bug fix (additive guards) | **refactor (move-only)** |
| Diff 크기 | 33 line | 193 line | 81 line |
| 파일 수 | 2 | 4 | 1 |
| 도메인 | 웰컴 메시지 | 상담사 핸드오버 | 상품 식별자 해상도 |
| 난이도 | easy | medium | medium |
| Mimiron 측정 포인트 | 단순 키 제거 | 다단 가드 + 헬퍼 추가 | 중복 추출 + 동작 유지 |
