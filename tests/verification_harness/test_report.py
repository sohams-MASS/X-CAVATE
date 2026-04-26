"""Tests for the markdown report writers."""
from pathlib import Path

from .compare import Metrics, DiffReport
from .report import (
    PipelineResult,
    write_case_report,
    append_summary_row,
)


def _ok(name):
    return PipelineResult(
        name=name,
        status="OK",
        gcode_paths=[Path(f"/tmp/{name}.txt")],
        metrics=Metrics(
            move_count=10,
            g0_count=2,
            g1_count=7,
            g4_count=1,
            total_path_length_mm=12.34,
            multimat_transitions=0,
            est_print_time_s=5.5,
        ),
        stderr_excerpt="",
        exit_code=0,
    )


def _diff(p1, p2):
    return DiffReport(
        pair=(p1, p2),
        move_count_a=10,
        move_count_b=10,
        aligned=True,
        max_xyz_dev=0.0001,
        max_f_dev=0.0,
        max_e_dev=0.0,
        out_of_tol_count=0,
        first_divergences=(),
        byte_equal=False,
    )


def test_write_case_report_creates_markdown(tmp_path):
    case_dir = tmp_path / "case_a"
    case_dir.mkdir()
    results = {"science": _ok("science"), "x1130": _ok("x1130"), "main": _ok("main")}
    diffs = {("science", "x1130"): _diff("science", "x1130")}
    write_case_report(case_dir, "case_a", results, diffs)
    md = (case_dir / "report.md").read_text()
    assert "# Case `case_a`" in md
    assert "science" in md
    assert "max_xyz_dev" in md


def test_append_summary_row_writes_header_once(tmp_path):
    summary = tmp_path / "summary.md"
    results = {"science": _ok("science"), "x1130": _ok("x1130"), "main": _ok("main")}
    diffs = {("science", "x1130"): _diff("science", "x1130")}
    append_summary_row(summary, "case_a", results, diffs)
    append_summary_row(summary, "case_b", results, diffs)
    text = summary.read_text()
    # Header appears exactly once
    assert text.count("| case ") == 1
    # Two rows
    assert text.count("| case_a") == 1
    assert text.count("| case_b") == 1


def test_failed_pipeline_renders_FAIL(tmp_path):
    case_dir = tmp_path / "case_b"
    case_dir.mkdir()
    failed = PipelineResult(
        name="x1130", status="FAIL",
        gcode_paths=[], metrics=None,
        stderr_excerpt="boom\n", exit_code=1,
    )
    results = {"science": _ok("science"), "x1130": failed, "main": _ok("main")}
    write_case_report(case_dir, "case_b", results, {})
    md = (case_dir / "report.md").read_text()
    assert "FAIL" in md
    assert "boom" in md


def test_known_deltas_section_appears_when_case_provided(tmp_path):
    """write_case_report should inject the known-deltas section when a Case is
    passed in. With no case (legacy callers), no deltas section is added."""
    from dataclasses import dataclass

    @dataclass
    class _Case:
        multimaterial: bool

    case_dir = tmp_path / "case_with_deltas"
    case_dir.mkdir()
    results = {"science": _ok("science"), "x1130": _ok("x1130"), "main": _ok("main")}
    diffs = {("x1130", "main"): _diff("x1130", "main")}
    write_case_report(
        case_dir, "case_with_deltas", results, diffs, case=_Case(multimaterial=True),
    )
    md = (case_dir / "report.md").read_text()
    assert "## Known residual deltas" in md
    # multimaterial-specific deltas should appear for an MM case
    assert "x1130-mm-pressure-gate" in md
    assert "mm-transition-count-divergence" in md


def test_known_deltas_section_omitted_when_no_case(tmp_path):
    case_dir = tmp_path / "case_legacy"
    case_dir.mkdir()
    results = {"main": _ok("main")}
    write_case_report(case_dir, "case_legacy", results, {})
    md = (case_dir / "report.md").read_text()
    assert "## Known residual deltas" not in md
