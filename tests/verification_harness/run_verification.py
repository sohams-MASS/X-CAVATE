"""Orchestrator: discover → run pipelines → parse → diff → report."""
from __future__ import annotations

import argparse
import fnmatch
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .compare import aggregate, numerical_diff
from .parse_gcode import parse
from .pipelines import (
    CANONICAL_PARAMS, PIPELINES, Case, Pipeline, discover_cases,
)
from .report import (
    PipelineResult, append_summary_row, write_case_report,
)


VERIF_ROOT = Path("/Users/sohams/X-CAVATE/Vascular Trees Verification")
REPORTS_ROOT = Path("/Users/sohams/X-CAVATE/tests/verification_harness/reports")


def plan_matrix(cases: list[Case], only: str | None = None) -> list[Case]:
    if only is None:
        return list(cases)
    return [c for c in cases if fnmatch.fnmatch(c.slug, only) or fnmatch.fnmatch(c.network.name, only)]


def _prepare_cwd(case_dir: Path, pipeline: Pipeline) -> Path:
    wd = case_dir / pipeline.name
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True)
    (wd / "outputs").mkdir(exist_ok=True)
    (wd / "outputs" / "gcode").mkdir(exist_ok=True)
    (wd / "outputs" / "graph").mkdir(exist_ok=True)
    (wd / "outputs" / "plots").mkdir(exist_ok=True)
    return wd


def run_one(case: Case, pipeline: Pipeline, case_dir: Path, *, timeout: int) -> PipelineResult:
    wd = _prepare_cwd(case_dir, pipeline)
    argv = pipeline.invocation + pipeline.build_args(case, CANONICAL_PARAMS)
    log_path = wd / "run.log"
    try:
        proc = subprocess.run(
            argv,
            cwd=wd,
            timeout=timeout,
            capture_output=True,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        log_path.write_text(f"TIMEOUT after {timeout}s\nstderr:\n{(e.stderr or b'').decode(errors='replace')}\n")
        return PipelineResult(
            name=pipeline.name, status="TIMEOUT",
            gcode_paths=[], metrics=None,
            stderr_excerpt=(e.stderr or b"").decode(errors="replace")[-4000:],
            exit_code=-1,
        )

    stderr = proc.stderr.decode(errors="replace")
    stdout = proc.stdout.decode(errors="replace")
    log_path.write_text(
        f"argv: {argv}\nexit: {proc.returncode}\n\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n"
    )

    if proc.returncode != 0:
        return PipelineResult(
            name=pipeline.name, status="FAIL",
            gcode_paths=[], metrics=None,
            stderr_excerpt=stderr[-4000:], exit_code=proc.returncode,
        )

    gcode_paths = pipeline.locate_gcode(wd, case)
    if not gcode_paths:
        return PipelineResult(
            name=pipeline.name, status="FAIL",
            gcode_paths=[], metrics=None,
            stderr_excerpt="(no g-code emitted)\n" + stderr[-2000:],
            exit_code=proc.returncode,
        )

    moves = parse(gcode_paths[0])
    metrics = aggregate(moves)
    return PipelineResult(
        name=pipeline.name, status="OK",
        gcode_paths=gcode_paths, metrics=metrics,
        stderr_excerpt="", exit_code=0,
    )


def run_case(case: Case, *, timeout: int) -> tuple[dict, dict]:
    case_dir = REPORTS_ROOT / case.slug
    case_dir.mkdir(parents=True, exist_ok=True)
    results: dict = {}
    parsed_moves: dict = {}
    for pipeline in PIPELINES:
        print(f"  → {pipeline.name} ...", flush=True)
        t0 = time.time()
        res = run_one(case, pipeline, case_dir, timeout=timeout)
        print(f"    {res.status} in {time.time() - t0:.1f}s", flush=True)
        results[pipeline.name] = res
        if res.status == "OK":
            parsed_moves[pipeline.name] = parse(res.gcode_paths[0])

    diffs: dict = {}
    names = list(parsed_moves)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            diffs[(a, b)] = numerical_diff(parsed_moves[a], parsed_moves[b], pair=(a, b))

    write_case_report(case_dir, case.slug, results, diffs)
    return results, diffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Vascular verification harness")
    ap.add_argument("--only", default=None, help="glob filter on case slug or network filename")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--verification-root", default=str(VERIF_ROOT))
    args = ap.parse_args(argv)

    cases = discover_cases(Path(args.verification_root))
    cases = plan_matrix(cases, only=args.only)

    print(f"Planned matrix: {len(cases)} cases × {len(PIPELINES)} pipelines")
    for c in cases:
        kind = "MM" if c.multimaterial else "SM"
        print(f"  - {c.slug}  ({kind})  ioc={c.inletoutlet.name}")

    if args.dry_run:
        return 0

    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    summary = REPORTS_ROOT / "summary.md"
    if summary.exists():
        summary.unlink()

    for c in cases:
        print(f"[{c.slug}]")
        results, diffs = run_case(c, timeout=args.timeout)
        append_summary_row(summary, c.slug, results, diffs)

    print(f"\nDone. Summary at {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
