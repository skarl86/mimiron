# B02 큐레이션 노트

- **후보 PR**: [ts-cxdm/workspace#1336](https://github.com/ts-cxdm/workspace/pull/1336) — fix(naver-smartstore): 상담사 개입 시 봇 이중 응답 방지 핸드오버 처리
- **선택 일자**: 2026-05-23
- **난이도**: medium
- **base_ref**: `f5ffd87fcf7ef0a9bda100fc12230760f2d1fadd`
- **target_ref**: `7e4b0c71c14fee45da88b8706a6fd2f50eb935d1` (merge commit)
- **변경 파일 수**: 4 (prod 3 + test 1)
- **변경 라인 수**: +143 / -2

## 선택 이유

1. B01(easy, 4 lines)과 *난이도 다양성* 확보 — multi-file, behavior-changing fix
2. **PR description에 *근본 원인*과 *변경 내용*이 분리 기술**되어 acceptance criteria가 명확
3. 핵심 가드 3개(`standby`, `event=handover`, `echo` 분기)가 모두 *문장으로* 표현 가능 — implementation vocabulary 누설 없이 issue.md 작성 가능
4. 상담사 핸드오버는 *실 운영 영향이 큰* 도메인 — Mimiron이 잘 처리하면 의미 있는 시그널
5. PR 본문에 *naver-talktalk의 동등 패턴* 차용이 명시돼 있어 `Out-of-scope`가 자연스럽게 정의됨

## 검증 항목

- [x] **issue.md에 *구현 어휘 누설* 없음**: `passThread`/`standby`/`event=handover` 같은 구현 토큰 제거. *행동* 단위로 기술 (예: "상담사가 주도권을 보유한 세션").
- [x] **expected.diff 크기**: 193 lines (헤더 포함). 실 변경 153 lines (prod +143/-2 + test).
- [x] **test_command가 base에서는 fail, target에서는 pass 인지**: 수동 검증 완료. base_ref (`f5ffd87f`)에서 exit=1, target_ref (`7e4b0c71`)에서 exit=0.

## test_command 전략

전체 의존성 설치 없이 핵심 가드 3개의 *존재 여부*만 확인:

```bash
python3 -c "import sys; s=open('agents/naver-smartstore/app/__main__.py').read(); ok = ('talk.standby is True' in s) and ('talk.event == \"handover\"' in s) and ('initiate_counselor_passthread' in s); sys.exit(0 if ok else 1)"
```

- base_ref에서 실행: 세 토큰 모두 부재 → exit 1 (fail)
- target_ref에서 실행: 세 토큰 모두 존재 → exit 0 (pass)

*infra smoke 모드* — 실제 mimiron pipeline 평가 시점에는 더 두꺼운 test_command
(`pytest tests/test_welcome_message.py -k handover`)로 교체 권장.

## B01과의 차이

| 측면 | B01 | B02 |
|---|---|---|
| Diff 크기 | 33줄 (실 4줄) | 193줄 (실 153줄) |
| 파일 수 | 2 (prod 1 + test 1) | 4 (prod 3 + test 1) |
| 변경 종류 | 키 제거 (subtractive) | 가드 3종 + 헬퍼 추가 (additive) |
| 도메인 | 웰컴 메시지 | 상담사 핸드오버 |
| 난이도 | easy | medium |
