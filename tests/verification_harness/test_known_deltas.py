"""Tests for the known-deltas catalog and report formatter."""
from dataclasses import dataclass
from pathlib import Path

from .compare import Metrics
from .known_deltas import KNOWN_DELTAS, format_for_case
from .report import PipelineResult


@dataclass
class _Case:
    multimaterial: bool


def _ok(name: str) -> PipelineResult:
    return PipelineResult(
        name=name, status="OK", gcode_paths=[Path("/tmp/x.txt")],
        metrics=Metrics(0, 0, 0, 0, 0.0, 0, 0.0),
        stderr_excerpt="", exit_code=0,
    )


def _fail(name: str) -> PipelineResult:
    return PipelineResult(
        name=name, status="FAIL", gcode_paths=[], metrics=None,
        stderr_excerpt="boom", exit_code=1,
    )


def test_catalog_has_expected_ids():
    ids = {d.id for d in KNOWN_DELTAS}
    expected = {
        "x1130-flow-override",
        "preamble-line-shift",
        "x1130-mm-pressure-gate",
        "dfs-extra-pass",
        "gap-closure-branchpoint-distribution",
        "mm-nozzle-axis-ordering",
        "science-keyerror",
    }
    assert expected.issubset(ids)


def test_mm_only_deltas_suppress_on_sm_case():
    case = _Case(multimaterial=False)
    results = {"science": _ok("s"), "x1130": _ok("x"), "main": _ok("m")}
    section = format_for_case(case, results, {})
    # MM-only deltas must NOT appear
    assert "x1130-mm-pressure-gate" not in section
    assert "mm-nozzle-axis-ordering" not in section
    # universally-relevant deltas SHOULD appear
    assert "x1130-flow-override" in section


def test_mm_deltas_appear_on_mm_case():
    case = _Case(multimaterial=True)
    results = {"science": _fail("s"), "x1130": _ok("x"), "main": _ok("m")}
    section = format_for_case(case, results, {})
    assert "x1130-mm-pressure-gate" in section
    assert "mm-nozzle-axis-ordering" in section


def test_science_keyerror_only_when_science_failed():
    case = _Case(multimaterial=False)
    section_ok = format_for_case(case, {"science": _ok("s"), "main": _ok("m")}, {})
    assert "science-keyerror" not in section_ok
    section_fail = format_for_case(case, {"science": _fail("s"), "main": _ok("m")}, {})
    assert "science-keyerror" in section_fail


def test_dfs_and_gap_closure_deltas_only_when_both_modern_pipelines_ok():
    case = _Case(multimaterial=False)
    section_only_main = format_for_case(case, {"main": _ok("m"), "x1130": _fail("x")}, {})
    assert "dfs-extra-pass" not in section_only_main
    section_both = format_for_case(case, {"main": _ok("m"), "x1130": _ok("x")}, {})
    assert "dfs-extra-pass" in section_both


def test_section_starts_with_documented_header():
    case = _Case(multimaterial=True)
    section = format_for_case(case, {"x1130": _ok("x"), "main": _ok("m")}, {})
    assert section.startswith("## Known residual deltas\n")
