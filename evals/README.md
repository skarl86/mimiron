# evals/ — Mechanical Gate Fixtures

`_global/mechanical.toml` 의 *예시 템플릿* 모음. 프로젝트 type 별로 build/test/lint
명령이 다르므로, 사용자는 `mimiron init` 후 자신의 프로젝트에 맞는 fixture를
`<project>/.mimiron/_global/mechanical.toml` 로 복사 + 조정한다.

## 사용법

```bash
# 1. 프로젝트 type에 맞는 fixture 고르기
cp /path/to/mimiron/evals/python-uv.toml \
   <project>/.mimiron/_global/mechanical.toml

# 2. (필요하면) 명령 조정
$EDITOR <project>/.mimiron/_global/mechanical.toml

# 3. mechanical gate 실행
mimiron gate <slug> mechanical
```

## 형식

```toml
[[checks]]
name = "human-readable name"        # 보고서에 표시
command = "shell command string"    # shlex.split 됨
timeout_s = 60                       # 기본 60
```

`checks[]` 순서대로 실행. 하나라도 exit code != 0이면 verdict=fail. 모두
exit 0이면 verdict=pass.

## 가용 fixture

| 파일 | 대상 |
|---|---|
| `python-uv.toml` | uv-managed Python (pytest + ruff + mypy) — Mimiron *자체* 가 이걸 씀 |
| `python-pip.toml` | pip-managed Python |
| `node-npm.toml` | Node.js + npm test/lint |
| `go.toml` | Go (go test + go vet) |

(필요시 fixture를 늘리세요. PR 환영.)
