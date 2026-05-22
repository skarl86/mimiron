# B01 큐레이션 노트

- **후보 PR**: [ts-cxdm/workspace#1299](https://github.com/ts-cxdm/workspace/pull/1299) — fix(naver-smartstore): 웰컴 메시지 미발송 버그 수정
- **선택 일자**: 2026-05-22
- **난이도**: easy
- **base_ref**: `df726371a9ed`
- **target_ref**: `0473b1c015b5` (merge commit)
- **변경 파일 수**: 2 (prod 1 + test 1)
- **변경 라인 수**: prod -2, test -1 (총 -3)

## 선택 이유

1. 가장 작은 self-contained PR (실 코드 변경 2 라인)
2. *명확한 bug 시나리오*가 PR description에 박혀 있음 (PostgREST 42703 오류)
3. tests 포함 — 검증 자동화 가능
4. acceptance criteria가 명확 (첫 접속/재접속 4 시나리오)
5. naver-smartstore 도메인이 사용자가 직접 만든 영역

## 검증 항목

- [x] **issue.md에 *구현 어휘 누설* 없음**: PostgREST나 Supabase 같은 *기술* 명시 제거. `daily_access_tracker.py` 같은 *파일 이름*은 acceptance criteria 일부로 유지(허용).
- [x] **expected.diff 크기**: 33 lines (헤더 포함, 실 변경 4 라인)
- [ ] **test_command가 base에서는 fail, target에서는 pass 인지**: 확인 — `bench run` 시 자동 검증

## test_command 전략

전체 의존성 설치 없이 *fix 적용 여부*만 확인:

```bash
python3 -c "import sys; s=open('agents/naver-smartstore/app/services/daily_access_tracker.py').read(); sys.exit(0 if '\"source\"' not in s else 1)"
```

- base_ref에서 실행: `"source"`가 파일에 있음 → exit 1 (fail)
- target_ref에서 실행: `"source"` 제거됨 → exit 0 (pass)

이는 *infra smoke 모드*입니다. 실제 mimiron pipeline 평가 시점에는 더 두꺼운 test_command(예: 실제 pytest)로 교체 권장.
