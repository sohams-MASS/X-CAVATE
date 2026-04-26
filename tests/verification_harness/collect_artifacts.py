"""Collect verification gcode artifacts and per-case reports into a single
publishable directory.

Layout produced::

    tests/verification_harness/final_report/
        FINAL_REPORT.md             — top-level summary across all cases
        summary.md                  — copy of the pairwise-diff table
        gcode/
            <case_slug>/
                science.txt          — Science.py output (preferred MM if applicable)
                x1130.txt            — x1130 output (preferred MM if applicable)
                main.txt             — main pipeline output (preferred MM)
        per_case_reports/
            <case_slug>.md           — copy of the per-case report

Run from anywhere:
    python -m tests.verification_harness.collect_artifacts
"""
from __future__ import annotations

import shutil
from pathlib import Path

REPORTS = Path("/Users/sohams/X-CAVATE/tests/verification_harness/reports")
OUT = Path("/Users/sohams/X-CAVATE/tests/verification_harness/final_report")


def _multimaterial_filename_in(dir: Path) -> Path | None:
    """Return the multimaterial gcode file in `dir`, if any.

    Looks for `*_MM_*.txt` (modern pipelines) or `gcode_multimaterial.txt`
    (Science.py).
    """
    if (dir / "gcode_multimaterial.txt").exists():
        return dir / "gcode_multimaterial.txt"
    matches = sorted(dir.glob("*_MM_*.txt"))
    return matches[0] if matches else None


def _singlematerial_filename_in(dir: Path) -> Path | None:
    """Return the single-material gcode file in `dir`, if any."""
    if (dir / "gcode.txt").exists():
        return dir / "gcode.txt"
    matches = sorted(dir.glob("*_SM_*.txt"))
    return matches[0] if matches else None


def _pipeline_gcode_root(case_dir: Path, pipeline: str) -> Path:
    """Return the directory containing the gcode for a pipeline run.

    Science.py writes gcode files directly to cwd (`gcode.txt` /
    `gcode_multimaterial.txt`); modern pipelines write to
    `outputs/gcode/gcode_*_pressure.txt`. The harness pre-creates
    `outputs/gcode/` for every pipeline, so checking for its existence
    isn't sufficient — we branch on pipeline name explicitly.
    """
    base = case_dir / pipeline
    if pipeline == "science":
        return base
    return base / "outputs" / "gcode"


def collect_for_case(case_slug: str, prefer_mm: bool) -> dict:
    """Copy the chosen gcode file for each pipeline into the artifact tree.

    Returns ``{pipeline: Path | None}`` of the copied files.
    """
    case_dir = REPORTS / case_slug
    out_case = OUT / "gcode" / case_slug
    out_case.mkdir(parents=True, exist_ok=True)

    result: dict[str, Path | None] = {}
    for pipeline in ("science", "x1130", "main"):
        src_root = _pipeline_gcode_root(case_dir, pipeline)
        if not src_root.exists():
            result[pipeline] = None
            continue
        # Prefer MM file if requested; otherwise SM
        chosen = None
        if prefer_mm:
            chosen = _multimaterial_filename_in(src_root) or _singlematerial_filename_in(src_root)
        else:
            chosen = _singlematerial_filename_in(src_root) or _multimaterial_filename_in(src_root)
        if chosen is None:
            result[pipeline] = None
            continue
        # Self-describing filename: pipeline__originalname
        dest = out_case / f"{pipeline}__{chosen.name}"
        shutil.copy2(chosen, dest)
        result[pipeline] = dest
    return result


def detect_mm_from_slug(slug: str) -> bool:
    """True if the case slug names a multimaterial network."""
    return "multimaterial" in slug.lower()


def collect_per_case_reports() -> list[Path]:
    """Copy each per-case report.md into the artifact tree."""
    out_reports = OUT / "per_case_reports"
    out_reports.mkdir(parents=True, exist_ok=True)
    copied = []
    for case_dir in sorted(REPORTS.iterdir()):
        if not case_dir.is_dir():
            continue
        report = case_dir / "report.md"
        if not report.exists():
            continue
        dest = out_reports / f"{case_dir.name}.md"
        shutil.copy2(report, dest)
        copied.append(dest)
    return copied


def collect_summary() -> Path | None:
    src = REPORTS / "summary.md"
    if not src.exists():
        return None
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "summary.md"
    shutil.copy2(src, dest)
    return dest


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Collecting artifacts into {OUT}")

    case_slugs = []
    for case_dir in sorted(REPORTS.iterdir()):
        if not case_dir.is_dir():
            continue
        case_slugs.append(case_dir.name)

    for slug in case_slugs:
        prefer_mm = detect_mm_from_slug(slug)
        result = collect_for_case(slug, prefer_mm=prefer_mm)
        copied = {k: v.name if v else "—" for k, v in result.items()}
        print(f"  [{slug}]  prefer_mm={prefer_mm}  {copied}")

    reports = collect_per_case_reports()
    print(f"  Copied {len(reports)} per-case reports")

    summary = collect_summary()
    if summary:
        print(f"  Copied summary to {summary}")


if __name__ == "__main__":
    main()
