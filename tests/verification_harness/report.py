"""Markdown report writers for case-level and summary outputs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .compare import DiffReport, Metrics
from .known_deltas import format_for_case as _format_known_deltas


@dataclass
class PipelineResult:
    name: str
    status: str        # "OK" | "FAIL" | "TIMEOUT" | "SKIP"
    gcode_paths: list[Path]
    metrics: Metrics | None
    stderr_excerpt: str
    exit_code: int


def _fmt_metrics(m: Metrics | None) -> str:
    if m is None:
        return "(no metrics)"
    return (
        f"moves={m.move_count} g0={m.g0_count} g1={m.g1_count} g4={m.g4_count} "
        f"path={m.total_path_length_mm:.3f} mm "
        f"mm_trans={m.multimat_transitions} "
        f"t_est={m.est_print_time_s:.2f} s"
    )


def _fmt_diff(d: DiffReport) -> str:
    return (
        f"counts=({d.move_count_a},{d.move_count_b}) aligned={d.aligned} "
        f"max_xyz_dev={d.max_xyz_dev:.4g} max_f_dev={d.max_f_dev:.4g} "
        f"max_e_dev={d.max_e_dev:.4g} out_of_tol={d.out_of_tol_count} "
        f"byte_equal={d.byte_equal}"
    )


def write_case_report(
    case_dir: Path,
    case_slug: str,
    results: dict,
    diffs: dict,
    case=None,
) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    out = case_dir / "report.md"
    lines = [f"# Case `{case_slug}`", ""]

    lines.append("## Pipelines")
    for name, r in results.items():
        lines.append(f"### {name} — {r.status}")
        lines.append(f"- exit_code: `{r.exit_code}`")
        if r.gcode_paths:
            lines.append("- emitted: " + ", ".join(f"`{p.name}`" for p in r.gcode_paths))
        lines.append(f"- metrics: `{_fmt_metrics(r.metrics)}`")
        if r.status != "OK" and r.stderr_excerpt:
            lines.append("- stderr (excerpt):")
            lines.append("")
            lines.append("```")
            lines.append(r.stderr_excerpt[-2000:])
            lines.append("```")
        lines.append("")

    if diffs:
        lines.append("## Pairwise diffs")
        for (a, b), d in diffs.items():
            lines.append(f"### {a} vs {b}")
            lines.append(f"- {_fmt_diff(d)}")
            if d.first_divergences:
                lines.append("- first divergences:")
                lines.append("")
                lines.append("```")
                for idx, ra, rb in d.first_divergences:
                    lines.append(f"  [{idx:>5}] A: {ra}")
                    lines.append(f"        B: {rb}")
                lines.append("```")
            lines.append("")

    if case is not None:
        deltas_section = _format_known_deltas(case, results, diffs)
        if deltas_section:
            lines.append(deltas_section)

    out.write_text("\n".join(lines))


_SUMMARY_HEADER = (
    "| case | science | x1130 | main | sci↔x1130 max_xyz | sci↔main max_xyz | x1130↔main max_xyz |\n"
    "|---|---|---|---|---|---|---|\n"
)


def append_summary_row(
    summary_path: Path,
    case_slug: str,
    results: dict,
    diffs: dict,
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    if not summary_path.exists():
        summary_path.write_text(_SUMMARY_HEADER)

    def _status(name: str) -> str:
        r = results.get(name)
        return r.status if r else "—"

    def _xyz(pair_a: str, pair_b: str) -> str:
        d = diffs.get((pair_a, pair_b)) or diffs.get((pair_b, pair_a))
        return f"{d.max_xyz_dev:.4g}" if d else "—"

    row = (
        f"| {case_slug} | {_status('science')} | {_status('x1130')} | {_status('main')} | "
        f"{_xyz('science', 'x1130')} | {_xyz('science', 'main')} | {_xyz('x1130', 'main')} |\n"
    )
    with summary_path.open("a") as f:
        f.write(row)
