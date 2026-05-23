# dogfood/004 — plugin-self-contained 검증

- **이슈**: skarl86/mimiron#15
- **슬러그**: plugin-self-contained
- **상태**: 다음 세션 (post-plugin-reload) 에서 사용자 수기 검증 필요

## 배경

v0.1.0 의 `/mimiron` 슬래시 스킬은 외부 `mimiron` CLI 가 `$PATH` 에 있어야 동작했다.
특히 `/home/namgee/.local/bin/mimiron` 같은 bash wrapper 가 `PYTHONPATH=$CLAUDE_PLUGIN_ROOT/src`
를 export 하면서, mimiron 이 spawn 하는 subprocess (pytest/ruff/mypy) 가 동일 PYTHONPATH 를
상속받아 *cached* mimiron 소스를 import 하는 부작용이 있었다 — 그래서 dogfood/003 의
일부 후속 검증에서 21개 false-fail 같은 신호 누수가 관찰됐다.

이 사이클 (`plugin-self-contained`) 은:

1. `scripts/_launcher.py` 도입 — Python 진입 즉시 `os.environ.pop("PYTHONPATH")`
   로 부모 셸이 export 한 PYTHONPATH 끊고, `CLAUDE_PLUGIN_ROOT` (없으면
   `Path(__file__).resolve().parent.parent` 로 fallback) 를 기준으로
   `sys.path` 에 plugin 내 `src/` 를 직접 추가.
2. `scripts/mimiron`, `scripts/mimiron-bench` 셸 스크립트가 런처에 위임
   (`exec python3 "$CLAUDE_PLUGIN_ROOT/scripts/_launcher.py" ...`).
3. `src/mimiron/yaml_compat.py` 로 PyYAML 의존 제거 — stdlib-only YAML 부분 집합
   (mapping / sequence / scalar / `|` literal block) 처리. mimiron 이 쓰는
   `spec.yaml`, `plan.yaml`, `thresholds.yaml`, `benchmark.yaml` 4종은
   이 부분집합 안에서 작성된다.
4. `hooks/{post-toolwrite,stop-hook}.py` 가 yaml_compat 로 lazy import 갱신.
5. README 와 dogfood 정리 (이 문서가 그 dogfood).

## 검증 절차 (다음 세션에서)

현재 세션은 *cached* plugin 으로 돌고 있으므로 wrapper 변경은 **다음 세션** 에서만 발효된다.

1. fresh tmp 디렉토리에서 `git clone https://github.com/skarl86/mimiron`
   (또는 동등 plugin 설치).
2. Claude Code 새 세션 시작 — `/plugin marketplace add skarl86/mimiron`
   + `/plugin install mimiron@mimiron`.
3. `which mimiron` 확인 — `<plugin install dir>/scripts/mimiron` 가 잡혀야 함.
   외부 wrapper (`~/.local/bin/mimiron`) 가 `$PATH` 에 우선하지 않도록
   PATH 순서 점검.
4. `/mimiron "테스트 feature"` 호출 — clarify → spec → plan → execute →
   evaluate → finalize → done 까지 완주 가능?
5. 마치는 시점에 `cat .mimiron/<slug>/evaluation/mechanical.json` 의
   pytest 결과 확인 — PYTHONPATH 누수 흔적 (21 false-fail 같은 케이스) 없어야 함.

## 예상 이슈

- **외부 wrapper 충돌** — 시스템에 `~/.local/bin/mimiron` 이 이미 있고
  `$PATH` 우선순위가 높으면 plugin 의 `scripts/mimiron` 이 못 잡힘.
  검증 시 PATH 순서 확인 필요.
- **CLAUDE_PLUGIN_ROOT 미주입** — Claude Code 가 skill subprocess 에
  이 env 를 안 주면 launcher 가 fallback (script 부모 디렉토리) 으로
  정확한 plugin root 를 찾아야 함. `Path(__file__).resolve().parent.parent`
  가 그 역할.
- **yaml_compat 한계** — 우리가 처리하는 YAML 부분집합 밖 (anchor, alias,
  flow style, `>`-folded scalar 등) 을 쓰는 외부 benchmark.yaml 이 있으면
  mimiron-bench 가 실패. T02a 가 `|` literal block 지원을 추가했는지 확인.

## 발견 사항 (사용자가 검증 후 채워주세요)

- [ ] `which mimiron` 결과: ...
- [ ] `/mimiron` 완주 여부: ...
- [ ] mechanical gate 결과: ...
- [ ] PYTHONPATH 누수 흔적 부재 확인: ...
- [ ] 발견된 추가 이슈: ...
