"""mimiron CLI — argparse 기반 결정적 진입점."""
from __future__ import annotations

import argparse
import json as _json
import re
import sys
from pathlib import Path

import yaml

from mimiron.artifacts import Artifacts, ArtifactError
from mimiron.gates import run_mechanical_gate
from mimiron.plan import Plan, PlanError
from mimiron.scanner import scan as run_scan
from mimiron.spec import Spec, SpecError
from mimiron.state import GateRecord, State
from mimiron.thresholds import Thresholds
from mimiron.verdict import Verdict

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2


def _sidecar_dir(cwd: Path, slug: str) -> Path:
    return cwd / ".mimiron" / slug


def _check_slug_or_die(slug: str) -> None:
    if not SLUG_RE.match(slug):
        raise SystemExit(
            f"invalid slug {slug!r}: must match {SLUG_RE.pattern} "
            "(lowercase alnum + dashes, max 63 chars, no '..' or path separators)"
        )


VALID_TOOLCHAINS = frozenset({"python-uv", "python-pip", "node-npm", "go"})


def _plugin_root() -> Path:
    """Mimiron plugin source root — evals/ fixture 위치 발견."""
    return Path(__file__).resolve().parent.parent.parent


_DEFAULT_THRESHOLDS = """\
ambiguity_max: 0.20
spec_quality_min: 0.85
certainty_band: 0.05
max_parallel_workers: 4
wall_clock_max_s: 14400
token_budget: 500000
"""


def _bootstrap_global(cwd: Path, toolchain: str) -> None:
    """`.mimiron/_global/`에 mechanical.toml + thresholds.yaml 작성.

    이미 존재하는 파일은 *덮어쓰지 않음* (사용자 결정 보존).
    """
    global_dir = cwd / ".mimiron" / "_global"
    global_dir.mkdir(parents=True, exist_ok=True)
    mech_target = global_dir / "mechanical.toml"
    if not mech_target.exists():
        fixture = _plugin_root() / "evals" / f"{toolchain}.toml"
        if not fixture.exists():
            raise SystemExit(
                f"bootstrap fixture not found: {fixture}. "
                f"Known toolchains: {sorted(VALID_TOOLCHAINS)}"
            )
        mech_target.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    th_target = global_dir / "thresholds.yaml"
    if not th_target.exists():
        th_target.write_text(_DEFAULT_THRESHOLDS, encoding="utf-8")


def cmd_init(args: argparse.Namespace) -> int:
    _check_slug_or_die(args.slug)
    cwd = Path.cwd()
    sidecar = _sidecar_dir(cwd, args.slug)
    if sidecar.exists():
        print(f"error: slug {args.slug!r} already exists at {sidecar}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    if args.bootstrap_toolchain:
        if args.bootstrap_toolchain not in VALID_TOOLCHAINS:
            print(
                f"error: unknown toolchain {args.bootstrap_toolchain!r}. "
                f"Choose one of {sorted(VALID_TOOLCHAINS)}",
                file=sys.stderr,
            )
            return EXIT_USAGE_ERROR
        _bootstrap_global(cwd, args.bootstrap_toolchain)
    sidecar.mkdir(parents=True)
    state = State.create(slug=args.slug, persistent=not args.no_persist)
    state.save(sidecar / "state.json")
    print(f"initialized {args.slug} at {sidecar}")
    return EXIT_OK


def cmd_ls(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    root = cwd / ".mimiron"
    if not root.exists():
        print("no slugs (no .mimiron directory)")
        return EXIT_OK
    slugs = sorted(p.name for p in root.iterdir() if p.is_dir() and p.name != "_global")
    if not slugs:
        print("no slugs")
        return EXIT_OK
    print(f"{'SLUG':30}  {'PHASE':10}  {'PERSIST':8}")
    for slug in slugs:
        try:
            state = State.load(root / slug / "state.json")
        except (FileNotFoundError, ValueError) as e:
            print(f"{slug:30}  {'corrupted':10}  {'-':8}  ({e})")
            continue
        persist = "yes" if state.persistent else "no"
        print(f"{slug:30}  {state.phase:10}  {persist:8}")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    state_path = _sidecar_dir(cwd, args.slug) / "state.json"
    if not state_path.exists():
        print(f"error: slug {args.slug!r} not found at {state_path}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    state = State.load(state_path)
    persist_tag = "persistent ✓" if state.persistent else "persistent ✗"
    paused_tag = "  [paused]" if state.paused else ""
    print(f"{state.slug}  [{persist_tag}]{paused_tag}")
    print(f"├─ phase:     {state.phase}")
    print(f"├─ retries:   {dict(state.retries) if state.retries else '(none)'}")
    print(
        f"├─ gates:     {len(state.gate_history)} recorded "
        f"(consecutive_fail={state.consecutive_gate_fails})"
    )
    print(f"├─ tokens:    {state.token_usage}")
    print(f"└─ updated:   {state.updated_at}")
    return EXIT_OK


def cmd_scan(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    sidecar = _sidecar_dir(cwd, args.slug)
    state_path = sidecar / "state.json"
    plan_path = sidecar / "plan.yaml"
    if not state_path.exists():
        print(f"error: slug {args.slug!r} not initialized", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    if not plan_path.exists():
        print(f"error: plan.yaml not found at {plan_path}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    state = State.load(state_path)
    try:
        plan = Plan.load(plan_path)
        plan.validate()
    except PlanError as e:
        print(f"plan invalid: {e}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    if state.spec_hash is not None and not state.spec_unlocked:
        if plan.spec_hash != state.spec_hash:
            state.phase = "stuck"
            state.save(state_path)
            print(
                f"spec_hash mismatch: plan.spec_hash={plan.spec_hash[:8]}, "
                f"state.spec_hash={state.spec_hash[:8]}. Run unstuck to recover.",
                file=sys.stderr,
            )
            return EXIT_RUNTIME_ERROR
    result = run_scan(plan, state.completed_task_ids, state.in_flight_task_ids)
    print(
        _json.dumps(
            {
                "slug": args.slug,
                "phase": state.phase,
                "ready": result.ready,
                "in_flight": result.in_flight,
                "pending": result.pending,
                "phase_done": result.phase_done,
            },
            indent=2,
        )
    )
    return EXIT_OK


def _quality_with_penalty(spec: Spec) -> tuple[float, float, dict[str, float]]:
    """spec.quality_score에 reviewer-ratio 페널티 적용."""
    raw = spec.quality_score or 0.0
    total = len(spec.acceptance_criteria)
    if total == 0:
        return raw, 0.0, {"reviewer_ratio": 0.0, "penalty": 0.0}
    reviewer_count = sum(
        1 for a in spec.acceptance_criteria if a.verify.kind == "reviewer"
    )
    ratio = reviewer_count / total
    penalty = 0.1 if ratio > 0.5 else 0.0
    return raw - penalty, penalty, {"reviewer_ratio": ratio, "penalty": penalty}


def _load_quality_samples(sidecar: Path) -> list[float]:
    p = sidecar / "quality.samples.json"
    if not p.exists():
        return []
    return [float(x) for x in _json.loads(p.read_text(encoding="utf-8"))]


def _read_clarification_score(sidecar: Path) -> tuple[float, list[float]]:
    cm = sidecar / "clarification.md"
    if not cm.exists():
        raise SystemExit(f"clarification.md missing at {cm}")
    text = cm.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit("clarification.md missing YAML frontmatter")
    end = text.index("\n---\n", 4)
    fm = yaml.safe_load(text[4:end])
    score = float(fm["ambiguity_score"])
    samples = [float(x) for x in fm.get("samples", [])]
    return score, samples


def _maybe_transition(state: State, v: Verdict, sidecar: Path) -> None:
    """게이트 pass 시 다음 phase로 전이. quality pass 시 spec_hash 박기."""
    if v.verdict != "pass":
        return
    transitions = {
        ("clarify", "ambiguity"): "spec",
        ("spec", "quality"): "plan",
        ("plan", "plan_integrity"): "execute",
        ("execute", "artifacts"): "evaluate",
        ("evaluate", "semantic"): "finalize",
    }
    next_phase = transitions.get((state.phase, v.kind))
    if next_phase is None:
        return
    if next_phase == "plan":
        spec_path = sidecar / "spec.yaml"
        if spec_path.exists():
            state.spec_hash = Spec.compute_hash(spec_path)
    state.phase = next_phase


def cmd_gate(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    sidecar = _sidecar_dir(cwd, args.slug)
    state_path = sidecar / "state.json"
    if not state_path.exists():
        print(f"error: slug {args.slug!r} not initialized", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    state = State.load(state_path)
    if args.kind == "mechanical":
        toml_path = cwd / ".mimiron" / "_global" / "mechanical.toml"
        v = run_mechanical_gate(
            toml_path=toml_path, slug=args.slug, cwd=cwd, phase=state.phase
        )
    elif args.kind == "ambiguity":
        thresholds = Thresholds.load_or_default(
            cwd / ".mimiron" / "_global" / "thresholds.yaml"
        )
        score, samples = _read_clarification_score(sidecar)
        band_lo = thresholds.ambiguity_max - thresholds.certainty_band
        band_hi = thresholds.ambiguity_max + thresholds.certainty_band
        if band_lo <= score <= band_hi:
            verdict = "needs_review"
        elif score <= thresholds.ambiguity_max:
            verdict = "pass"
        else:
            verdict = "fail"
        v = Verdict.make(
            slug=args.slug, phase=state.phase, kind="ambiguity",
            verdict=verdict, score=score, samples=samples,
            details={
                "threshold": thresholds.ambiguity_max,
                "band": thresholds.certainty_band,
            },
        )
    elif args.kind == "artifacts":
        plan_path = sidecar / "plan.yaml"
        if not plan_path.exists():
            print(
                f"error: plan.yaml missing at {plan_path}. "
                "Run plan skill first.",
                file=sys.stderr,
            )
            return EXIT_RUNTIME_ERROR
        try:
            plan = Plan.load(plan_path)
            plan.validate()
        except PlanError as e:
            print(f"plan invalid: {e}", file=sys.stderr)
            return EXIT_RUNTIME_ERROR
        result = run_scan(plan, state.completed_task_ids, state.in_flight_task_ids)
        if result.phase_done:
            v = Verdict.make(
                slug=args.slug, phase=state.phase, kind="artifacts",
                verdict="pass",
                details={"completed_count": len(state.completed_task_ids)},
            )
        else:
            v = Verdict.make(
                slug=args.slug, phase=state.phase, kind="artifacts",
                verdict="fail",
                details={
                    "ready": result.ready,
                    "in_flight": result.in_flight,
                    "pending": result.pending,
                },
            )
    elif args.kind == "plan_integrity":
        plan_path = sidecar / "plan.yaml"
        if not plan_path.exists():
            print(
                f"error: plan.yaml missing at {plan_path}. "
                "Run plan skill first.",
                file=sys.stderr,
            )
            return EXIT_RUNTIME_ERROR
        try:
            plan = Plan.load(plan_path)
            plan.validate()
        except PlanError as e:
            v = Verdict.make(
                slug=args.slug, phase=state.phase, kind="plan_integrity",
                verdict="fail", details={"error": str(e)},
            )
        else:
            if state.spec_hash is not None and plan.spec_hash != state.spec_hash:
                v = Verdict.make(
                    slug=args.slug, phase=state.phase, kind="plan_integrity",
                    verdict="fail",
                    details={
                        "error": (
                            f"spec_hash mismatch: plan={plan.spec_hash[:8]}, "
                            f"state={state.spec_hash[:8]}"
                        )
                    },
                )
            else:
                v = Verdict.make(
                    slug=args.slug, phase=state.phase, kind="plan_integrity",
                    verdict="pass",
                    details={"task_count": len(plan.tasks)},
                )
    elif args.kind == "semantic":
        semantic_path = sidecar / "evaluation" / "semantic.json"
        if not semantic_path.exists():
            print(
                f"error: semantic.json missing at {semantic_path}. "
                "Run evaluate skill first.",
                file=sys.stderr,
            )
            return EXIT_RUNTIME_ERROR
        try:
            raw = _json.loads(semantic_path.read_text(encoding="utf-8"))
        except _json.JSONDecodeError as e:
            print(f"error: semantic.json invalid JSON: {e}", file=sys.stderr)
            return EXIT_USAGE_ERROR
        try:
            v = Verdict.make(
                slug=args.slug,
                phase=state.phase,
                kind="semantic",
                verdict=raw["verdict"],
                score=raw.get("score"),
                samples=list(raw.get("samples", [])),
                details=raw.get("details", {}),
            )
        except (ValueError, KeyError) as e:
            print(f"error: semantic.json schema invalid: {e}", file=sys.stderr)
            return EXIT_USAGE_ERROR
    elif args.kind == "quality":
        thresholds = Thresholds.load_or_default(
            cwd / ".mimiron" / "_global" / "thresholds.yaml"
        )
        spec_path = sidecar / "spec.yaml"
        if not spec_path.exists():
            print("spec.yaml missing", file=sys.stderr)
            return EXIT_RUNTIME_ERROR
        try:
            spec = Spec.load(spec_path)
            spec.validate()
        except SpecError as e:
            print(f"spec invalid: {e}", file=sys.stderr)
            return EXIT_USAGE_ERROR
        adj_score, penalty, meta = _quality_with_penalty(spec)
        samples = _load_quality_samples(sidecar)
        band_lo = thresholds.spec_quality_min - thresholds.certainty_band
        band_hi = thresholds.spec_quality_min + thresholds.certainty_band
        if band_lo <= adj_score <= band_hi:
            verdict = "needs_review"
        elif adj_score >= thresholds.spec_quality_min:
            verdict = "pass"
        else:
            verdict = "fail"
        v = Verdict.make(
            slug=args.slug, phase=state.phase, kind="quality",
            verdict=verdict, score=adj_score, samples=samples,
            details={
                **meta,
                "raw": spec.quality_score,
                "threshold": thresholds.spec_quality_min,
            },
        )
    else:
        print(f"gate kind {args.kind!r} not yet implemented", file=sys.stderr)
        return EXIT_USAGE_ERROR
    verdict_path = sidecar / "evaluation" / f"{args.kind}.json"
    v.save(verdict_path)
    state.gate_history.append(
        GateRecord(
            phase=v.phase, kind=v.kind, verdict=v.verdict,
            score=v.score, samples=v.samples, ts=v.ts,
        )
    )
    if v.verdict == "fail":
        state.consecutive_gate_fails += 1
    elif v.verdict == "pass":
        state.consecutive_gate_fails = 0
    elif v.verdict == "needs_review" and args.kind == "semantic":
        state.paused = True
    _maybe_transition(state, v, sidecar)
    if args.kind == "semantic" and state.consecutive_gate_fails >= 3:
        state.phase = "stuck"
    state.save(state_path)
    print(_json.dumps({"verdict": v.verdict, "score": v.score, "path": str(verdict_path)}))
    return EXIT_OK if v.verdict != "fail" else EXIT_RUNTIME_ERROR


def cmd_commit_task(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    sidecar = _sidecar_dir(cwd, args.slug)
    state_path = sidecar / "state.json"
    if not state_path.exists():
        print(f"error: slug {args.slug!r} not initialized", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    state = State.load(state_path)
    if state.spec_hash is not None and not state.spec_unlocked:
        spec_path = sidecar / "spec.yaml"
        if spec_path.exists():
            current_hash = Spec.compute_hash(spec_path)
            if current_hash != state.spec_hash:
                state.phase = "stuck"
                state.save(state_path)
                print(
                    f"spec_hash mismatch: spec.yaml={current_hash[:8]}, "
                    f"state.spec_hash={state.spec_hash[:8]}. "
                    "Run unstuck to recover.",
                    file=sys.stderr,
                )
                return EXIT_RUNTIME_ERROR
    art_path = sidecar / "tasks" / args.task_id / "artifacts.json"
    if not art_path.exists():
        print(f"error: artifacts.json missing at {art_path}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    try:
        art = Artifacts.load(art_path)
        art.verify(root=cwd)
    except ArtifactError as e:
        state.retries[args.task_id] = state.retries.get(args.task_id, 0) + 1
        state.save(state_path)
        print(
            f"reject: {e} (retries={state.retries[args.task_id]})",
            file=sys.stderr,
        )
        return EXIT_RUNTIME_ERROR
    if args.task_id in state.in_flight_task_ids:
        state.in_flight_task_ids.remove(args.task_id)
    if args.task_id not in state.completed_task_ids:
        state.completed_task_ids.append(args.task_id)
    state.save(state_path)
    print(f"commit ok: {args.task_id}")
    return EXIT_OK


def cmd_pause(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    state_path = _sidecar_dir(cwd, args.slug) / "state.json"
    if not state_path.exists():
        print(f"error: slug {args.slug!r} not initialized", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    state = State.load(state_path)
    state.paused = True
    state.save(state_path)
    print(f"paused: {args.slug}")
    return EXIT_OK


def cmd_resume(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    state_path = _sidecar_dir(cwd, args.slug) / "state.json"
    if not state_path.exists():
        print(f"error: slug {args.slug!r} not initialized", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    state = State.load(state_path)
    if state.phase == "stuck":
        print(
            f"error: slug {args.slug!r} is stuck. Use `mimiron unstuck {args.slug}` "
            "instead of resume.",
            file=sys.stderr,
        )
        return EXIT_RUNTIME_ERROR
    if state.phase == "done":
        print(
            f"error: slug {args.slug!r} is done. Start a new slug with `/mimiron`.",
            file=sys.stderr,
        )
        return EXIT_RUNTIME_ERROR
    state.paused = False
    state.save(state_path)
    print(f"resumed: {args.slug} (phase={state.phase})")
    return EXIT_OK


def cmd_archive(args: argparse.Namespace) -> int:
    """finalize → done 종착. stop-hook re-entry 방지를 위해 persistent=false."""
    cwd = Path.cwd()
    sidecar = _sidecar_dir(cwd, args.slug)
    state_path = sidecar / "state.json"
    if not state_path.exists():
        print(f"error: slug {args.slug!r} not initialized", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    state = State.load(state_path)
    if state.phase == "done":
        # idempotent: archive marker 갱신만, 상태 변화 없음
        _write_archive_marker(sidecar, state)
        print(f"already archived: {args.slug}")
        return EXIT_OK
    if state.phase != "finalize":
        print(
            f"error: slug {args.slug!r} is in phase {state.phase!r}; "
            "archive requires phase=finalize",
            file=sys.stderr,
        )
        return EXIT_RUNTIME_ERROR
    _write_archive_marker(sidecar, state)
    state.phase = "done"
    state.persistent = False
    state.save(state_path)
    print(f"archived: {args.slug} (phase=done, persistent=false)")
    return EXIT_OK


def _write_archive_marker(sidecar: Path, state: State) -> None:
    """archive/COMPLETED.json 작성 — 사람·외부 도구가 읽을 종착 신호."""
    archive_dir = sidecar / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    marker = archive_dir / "COMPLETED.json"
    marker.write_text(
        _json.dumps(
            {
                "schema_version": 1,
                "slug": state.slug,
                "final_phase_before_archive": state.phase,
                "gate_history_count": len(state.gate_history),
                "completed_task_ids": list(state.completed_task_ids),
                "completed_at": _now_iso_for_archive(),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _now_iso_for_archive() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mimiron")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="initialize a new slug")
    p_init.add_argument("slug")
    p_init.add_argument("--no-persist", action="store_true", help="disable persistent loop")
    p_init.add_argument(
        "--bootstrap-toolchain",
        dest="bootstrap_toolchain",
        default=None,
        help=(
            "Also write .mimiron/_global/{mechanical.toml,thresholds.yaml} if absent. "
            "Choose one of python-uv|python-pip|node-npm|go."
        ),
    )
    p_init.set_defaults(func=cmd_init)

    p_ls = sub.add_parser("ls", help="list all slugs with phase")
    p_ls.set_defaults(func=cmd_ls)

    p_status = sub.add_parser("status", help="show status of a slug")
    p_status.add_argument("slug")
    p_status.set_defaults(func=cmd_status)

    p_scan = sub.add_parser("scan", help="compute next ready tasks")
    p_scan.add_argument("slug")
    p_scan.set_defaults(func=cmd_scan)

    p_gate = sub.add_parser("gate", help="run a gate")
    p_gate.add_argument("slug")
    p_gate.add_argument(
        "kind",
        choices=["mechanical", "semantic", "ambiguity", "quality", "plan_integrity", "artifacts"],
    )
    p_gate.set_defaults(func=cmd_gate)

    p_commit = sub.add_parser("commit-task", help="verify artifacts and mark task done")
    p_commit.add_argument("slug")
    p_commit.add_argument("task_id")
    p_commit.set_defaults(func=cmd_commit_task)

    p_archive = sub.add_parser(
        "archive", help="finalize → done 종착 (persistent loop off)"
    )
    p_archive.add_argument("slug")
    p_archive.set_defaults(func=cmd_archive)

    p_pause = sub.add_parser("pause", help="paused=true 마킹 (persistent loop 차단)")
    p_pause.add_argument("slug")
    p_pause.set_defaults(func=cmd_pause)

    p_resume = sub.add_parser("resume", help="paused 해제 (stuck/done은 거부)")
    p_resume.add_argument("slug")
    p_resume.set_defaults(func=cmd_resume)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        rc = args.func(args)
    except SystemExit as exc:
        msg = str(exc)
        if msg:
            print(msg, file=sys.stderr)
        return EXIT_USAGE_ERROR
    # M3: guard against subcommands that forget to `return`
    return int(rc) if rc is not None else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
