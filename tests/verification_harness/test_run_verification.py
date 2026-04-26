"""Smoke tests for the orchestrator (no real subprocess execution)."""
from pathlib import Path
from unittest.mock import patch, MagicMock

from . import pipelines as pmod
from .run_verification import (
    plan_matrix,
    run_one,
)


def test_plan_matrix_filters_by_only_glob():
    cases = [
        pmod.Case(network=Path("a/4_vessels.txt"), inletoutlet=Path("a/io.txt"),
                  multimaterial=False, slug="case_4"),
        pmod.Case(network=Path("a/9_vessels.txt"), inletoutlet=Path("a/io.txt"),
                  multimaterial=False, slug="case_9"),
    ]
    filtered = plan_matrix(cases, only="*4*")
    assert len(filtered) == 1
    assert filtered[0].slug == "case_4"


def test_run_one_marks_failed_pipeline_when_subprocess_returns_nonzero(tmp_path):
    case = pmod.Case(
        network=tmp_path / "n.txt",
        inletoutlet=tmp_path / "io.txt",
        multimaterial=False,
        slug="x",
    )
    case.network.write_text("Vessel: 0, Number of Points: 1\n\n1.0, 2.0, 3.0, 0.05\n")
    case.inletoutlet.write_text("inlet\n1.0, 2.0, 3.0\noutlet\n1.0, 2.0, 3.0\n")
    pipeline = pmod.PIPELINES[0]  # science

    fake = MagicMock()
    fake.returncode = 1
    fake.stdout = b""
    fake.stderr = b"argparse error\n"
    with patch("subprocess.run", return_value=fake):
        result = run_one(case, pipeline, tmp_path / "wd", timeout=10)

    assert result.status == "FAIL"
    assert result.exit_code == 1
    assert "argparse error" in result.stderr_excerpt
