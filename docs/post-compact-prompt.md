# Post-Compact Kickoff Prompt

> `/compact` 직후에 *이 블록을 복사*해서 채팅에 붙여넣어라. 새 Claude가 핸드오버 문서를 읽고 ralph-loop을 자율 시작한다.

---

## 복사용 프롬프트 (한 줄도 빼지 말 것)

```
Mimiron Phase B 시작. 먼저 `docs/HANDOVER.md`를 끝까지 읽고 컨텍스트를
복원해라. 그 다음 ralph-loop으로 자율 사이클 진입.

CWD 확인: `/home/namgee/Development/private/mimiron/.claude/worktrees/mimiron-spec/`
브랜치 확인: `worktree-mimiron-spec`
sanity 확인: `.venv/bin/pytest -q` → 81 passed

핸드오버 문서 § 8 (첫 iteration 가이드)대로 첫 단계를 시작한다.

ralph-loop 제약 (첫 세션):
- 최대 5 iteration (기본 30 대신)
- wall_clock 한도 1h (기본 4h 대신)
- 각 iteration 끝에 한 줄 progress 보고
- `compute_halt_signal()`의 halt 조건은 즉시 honor
- 5 iteration 도달 OR halt signal → `.mimiron/_outer/halt-report.md`에
  요약(무엇 했음·다음 액션 3가지) 작성 후 사용자 호출

만약 첫 iteration에서 architectural decision이 필요해 보이면 (예: anthropic
SDK 의존성 추가, 새 hook 도입 등), iteration 진행 *전에* 사용자에게 보고하고
승인 받기.

핸드오버 § 10 (절대 안 할 것) 준수: spec/plan 수정 금지, main 머지 금지,
대규모 refactor 금지, 외부 dep 임의 추가 금지.

이제 `/ralph-loop` 발동해서 위 제약대로 첫 사이클 시작.
```

---

## 참고: prompt의 의도

- **문서 우선 읽기**: `/compact` 후 컨텍스트가 압축돼서 spec/plan 디테일이 흐릿할 수 있음. HANDOVER.md가 그걸 복원.
- **첫 세션 제약**: ralph가 첫 자율 행동을 *작게* 잡도록 강제 (5 iter, 1h). 실수 발견 시 빨리 멈출 수 있게.
- **architectural pivot 보고 의무**: 자율이라도 *시스템 모양을 바꾸는* 결정은 사용자가 한 번 봐야 함.
- **halt 후 보고 의무**: 매번 *왜 멈췄나*가 명시되도록.

## 변경하면 좋은 곳 (사용자가 원하면)

- **iteration 수 조정**: 5 → 10 (더 길게 자율) 또는 3 (더 짧게).
- **wall_clock 조정**: 1h → 2h.
- **첫 우선순위 변경**: 핸드오버 § 5의 1번(similarity_provider) 대신 2번(B02~B05 큐레이션) 먼저 — 만약 너가 "더 많은 benchmark가 먼저 있어야 ralph가 의미 있다"고 판단하면.

위 셋 중 하나 바꿀 거면 prompt 안 해당 줄을 직접 수정하고 붙여넣어라.

## 만약 ralph-loop이 멈춘 후

- `.mimiron/_outer/halt-report.md` 읽기
- 거기 제안된 *다음 액션 3가지* 중 하나 골라서 사용자가 다음 ralph 사이클 띄우기 (또는 수동으로 한 PR 만들고 다시 띄우기)
- benchmark suite aggregate가 0.75 이상이면 Phase B 졸업 후보, spec § 7.4 DoD 확인
