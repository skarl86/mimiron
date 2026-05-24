---
description: Run SWE-bench Lite suite — fixture 순회 + hybrid 채점 + REPORT.md 생성
allowed-tools: Skill, Bash, Read, Write, Edit, Grep, Glob, Task, AskUserQuestion
---

`mimiron-swebench` skill 을 invoke 해서 `benchmarks/SWE-LITE-*/` fixture 들을 순회 실행하고 `.mimiron/_outer/swebench/REPORT.md` 를 생성한다.

전제: importer 가 이미 돌아 fixture 가 준비된 상태. 없으면 먼저 사용자에게 안내:

```
mimiron-bench swebench import --from-jsonl <path> --stratified 20 --seed 42
```
