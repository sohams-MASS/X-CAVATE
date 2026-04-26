"""Build the FINAL_REPORT.md from the harness's reports/ tree.

Run AFTER `collect_artifacts.py` so the per-case files and summary are in
place. Reads:
  reports/summary.md
  reports/<case>/report.md  (for metrics + diff stats)

Writes:
  final_report/FINAL_REPORT.md
"""
from __future__ import annotations

from pathlib import Path

REPORTS = Path("/Users/sohams/X-CAVATE/tests/verification_harness/reports")
OUT_DIR = Path("/Users/sohams/X-CAVATE/tests/verification_harness/final_report")


_NARRATIVE_HEADER = """# X-CAVATE Verification Harness — Final Report

This report compares three X-CAVATE pipelines on the seven networks under
`Vascular Trees Verification/` and documents the bugs found, fixes applied,
and residual differences that remain.

## Pipelines

| ID | Source | Notes |
|---|---|---|
| **science** | `xcavate_Science.py` (June 2023, Herrmann) | 5,568-line monolithic script. Three logging/typo bugs patched in `tests/verification_harness/science_runner.py` so it can run end-to-end. |
| **x1130** | `xcavate_11_30_25.py` (Nov 30 2025) | 5,568-line fork of Science.py. Two patches in `tests/verification_harness/x1130_runner.py`: the `custom_gcode == 1` gate on multimaterial-pressure emission, and an unguarded `graph[i].remove()` on the 500-vessel network. |
| **main** | `sohams-MASS/X-CAVATE` `xcavate/` package, branch `verification-harness` | Modular refactor with iterative DFS, KD-tree spatial queries, and dataclass-based config. Three correctness fixes applied during this work — see "Bugs fixed in main" below. |

The harness invokes each pipeline as a subprocess in an isolated working
directory, parses the emitted G-code, computes aggregate metrics, and
diffs each pair pairwise. `numerical_diff` uses `align_on_first_g1=True`
so a missing leading `G90` doesn't shift the entire stream.

## Inputs

Seven networks under `Vascular Trees Verification/`:

| Network | Vessels | Type |
|---|---:|---|
| `CNET Network/cnet_network_0_b_splines_100_points.txt` | 100 | single |
| `Figure 4 (F)/network_0_b_splines_4_vessels.txt` | 4 | single |
| `Figure 4 (F)/network_0_b_splines_9_vessels.txt` | 9 | single |
| `Figure 4 (F)/network_0_b_splines_14_vessels.txt` | 14 | single |
| `Figure 2 (A-C), Figure 4 (G)/multimaterial_test_network_61_vessels.txt` | 61 | **multi** |
| `Figure 2 (D-E)/5-1-23_multimaterial_network_0_b_splines.txt` | ~30 | **multi** |
| `network_0_b_splines_500_vessels (1).txt` | 500 | single (orphan — synthesized inlet/outlet) |

Canonical run parameters: `nozzle_diameter=0.41`, `container_height=50`,
`flow=0.1609429886081009` (matched to x1130's hardcoded value), `print_speed=1`,
`jog_speed=5`, `dwell_start=dwell_end=0.08`, `printer_type=0` (pressure),
`convert_factor=10.0` (cm→mm — main only; the legacy scripts hardcode
this).

"""

_RESULTS_INTRO = """
## Results

### Summary table

`max_xyz_dev` is the largest XYZ deviation (mm) between any pair of
G1 moves after preamble alignment. **0** = bit-identical G1 trajectories.
**5×10⁻⁷** = float-precision noise only (different decimal printing
between pipelines, no actual coordinate divergence).

"""


_BUGS_FIXED_BLOCK = """
## Bugs fixed in main (`sohams-MASS/X-CAVATE`)

1. **Inlet/outlet matching ran on the pre-interpolation 400-row coordinate
   array but the indices were used post-interpolation.** Fixed by moving
   the `match_inlet_outlet_nodes` call to AFTER `interpolate_network`
   (`xcavate/pipeline.py:104` → after `points_interp`). Eliminated the
   spurious branchpoint edges through misidentified outlets and the
   resulting +1 raw-DFS pass per network on every SM case.

2. **`classify_passes_by_material` indexed the LAST node of each pass
   (`nodes[-1]`) but the docstring said "second node".** The second-node
   choice in xcavate_11_30_25.py is more robust against material outliers
   at the tail of long passes. Implementation now matches the docstring
   and x1130's behavior (`xcavate/core/multimaterial.py`).

3. **`_subdivide_by_material` wrote swapped artven values back to the
   shared `points[n, 4]` column.** Branchpoint nodes appear in multiple
   passes; a swap performed for pass A leaked the mutated value into
   pass B's break detection, producing extra material-transition splits.
   x1130 keeps swap state in a per-pass-local `print_passes_processed_artven`
   dict. Fix: main now uses an `artven_local` dict per pass and never
   touches `points`. Result: dropped main's MM transition count from 205
   to 183 on the 61-vessel network, exactly matching x1130
   (`xcavate/pipeline.py:_subdivide_by_material`).

Each fix has a regression test under `tests/`:
- `tests/test_inlet_outlet_remap.py`
- `tests/test_multimaterial.py::test_multinode_uses_second_node`
- `tests/test_subdivide_by_material_swap_order.py`

A separate fix to `xcavate/core/multimaterial.py::classify_passes_by_material`
made it tolerate empty sub-passes that survive `_subdivide_by_material`'s
slicing — this allowed the multimaterial path to run at all on the
61-vessel network (previously crashed with `IndexError: list index out
of range`).

"""


_LEGACY_PATCHES_BLOCK = """
## Legacy-script patches (in `tests/verification_harness/`)

The two legacy scripts are not modified on disk. Each is invoked through
a wrapper that applies in-memory patches before `exec`:

### `science_runner.py` (3 patches)

1. **`KeyError` in Branchpoint Condition #1 logging** (script line ~1781):
   the f-string referenced `append_first_branch[i]` inside a loop iterating
   `append_last_branch`. Fixed by mirroring the correct dict reference.
2. **`FileNotFoundError` in Branchpoint Condition #2** (script line ~2127):
   `open('changelog.txt,' 'a')` — comma INSIDE the filename literal
   produced the path `'changelog.txt,a'`. Fixed by moving the comma.
3. **`ValueError: list.remove(x): x not in list`** in daughter-pair
   dedup (script line ~766): unguarded `graph[i].remove(daughter_to_remove)`.
   Fixed with an `if x in graph[i]:` guard.

### `x1130_runner.py` (2 patches)

1. **`gcode_MM_pressure.txt` never emitted** (script line 4717): the
   multimaterial-pressure writer was gated on `custom_gcode == 1`.
   Without `--custom 1`, x1130 silently skipped MM emission and only
   wrote `gcode_SM_pressure.txt`, reporting 0 nozzle transitions on
   multimaterial inputs. Fixed by dropping the `custom_gcode == 1`
   condition.
2. **Same `graph[i].remove()` bug** as Science (script line ~878).
   Fixed with the same `if x in graph[i]:` guard.

x1130 also hardcodes `flow = 0.1609429886081009` at script line 3705,
overriding its own `--flow` argparse value. This is not patched; the
harness's `CANONICAL_PARAMS["flow"]` is set to the same value so all
three pipelines compute feedrates on identical flow.

"""


def parse_summary(path: Path) -> list[dict]:
    """Parse the markdown summary into a list of row dicts."""
    text = path.read_text()
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if "case" in line and "science" in line.lower():
            continue
        if set(line.replace("|", "").strip()) <= set("-"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 7:
            continue
        rows.append({
            "case": cols[0],
            "science": cols[1],
            "x1130": cols[2],
            "main": cols[3],
            "sci_x1130_xyz": cols[4],
            "sci_main_xyz": cols[5],
            "x1130_main_xyz": cols[6],
        })
    return rows


def _read_metric_lines_from_report(report_path: Path) -> list[str]:
    """Pull the bullet-list lines starting with '- metrics:' from a report."""
    if not report_path.exists():
        return []
    return [
        line for line in report_path.read_text().splitlines()
        if line.strip().startswith("- metrics:")
    ]


def render_results_table(rows: list[dict]) -> str:
    out = ["| Case | science | x1130 | main | sci↔x1130 max_xyz | sci↔main max_xyz | x1130↔main max_xyz |",
           "|---|---|---|---|---:|---:|---:|"]
    for r in rows:
        out.append(
            f"| `{r['case']}` | {r['science']} | {r['x1130']} | {r['main']} | "
            f"{r['sci_x1130_xyz']} | {r['sci_main_xyz']} | {r['x1130_main_xyz']} |"
        )
    return "\n".join(out)


def render_per_case_metrics(rows: list[dict]) -> str:
    """For each case, pull metrics lines and present them."""
    out = ["", "### Per-case G-code metrics", ""]
    for r in rows:
        case = r["case"]
        report_path = REPORTS / case / "report.md"
        metrics = _read_metric_lines_from_report(report_path)
        if not metrics:
            continue
        out.append(f"#### `{case}`")
        out.append("")
        out.append("```")
        out.extend(m.strip()[2:] for m in metrics)  # strip leading "- "
        out.append("```")
        out.append("")
    return "\n".join(out)


def main() -> None:
    summary_path = REPORTS / "summary.md"
    if not summary_path.exists():
        print(f"ERROR: {summary_path} not found. Run the sweep first.")
        return

    rows = parse_summary(summary_path)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    body = []
    body.append(_NARRATIVE_HEADER)
    body.append(_RESULTS_INTRO)
    body.append(render_results_table(rows))
    body.append(render_per_case_metrics(rows))
    body.append(_BUGS_FIXED_BLOCK)
    body.append(_LEGACY_PATCHES_BLOCK)

    body.append(
        "## Reproduction\n\n"
        "```bash\n"
        "git checkout verification-harness\n"
        "pytest tests/  # 157 passed, 4 skipped\n"
        "python -m tests.verification_harness.run_verification --timeout 1800\n"
        "python -m tests.verification_harness.collect_artifacts\n"
        "python -m tests.verification_harness.generate_final_report\n"
        "```\n\n"
        "Outputs land at `tests/verification_harness/reports/` (per-case "
        "scratch directories, gitignored) and "
        "`tests/verification_harness/final_report/` (publishable copy "
        "with collected gcode files).\n"
    )

    out_path = OUT_DIR / "FINAL_REPORT.md"
    out_path.write_text("\n".join(body))
    print(f"Wrote {out_path}  ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
