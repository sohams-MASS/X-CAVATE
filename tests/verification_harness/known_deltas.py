"""Catalog of documented residual differences between the three X-CAVATE pipelines.

These are NOT bugs in the harness or in any single pipeline — they are stable,
characterized divergences that result from real algorithmic / implementation
differences between the three codebases. The harness exposes them rather than
hiding them so the comparison report stays honest.

Each delta has:
  * ``id``           — short stable identifier
  * ``title``        — one-line summary
  * ``description``  — multi-line explanation, including any harness-side
                       mitigation that's already in place
  * ``applies``      — predicate ``(case, results, diffs) -> bool`` telling the
                       report writer whether this delta is relevant to a given
                       case (e.g., MM-only deltas suppress on SM-only inputs)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class KnownDelta:
    id: str
    title: str
    description: str
    applies: Callable[[object, dict, dict], bool]


def _both_ok(name_a: str, name_b: str):
    def f(_case, results: dict, _diffs: dict) -> bool:
        a = results.get(name_a)
        b = results.get(name_b)
        return bool(a and b and a.status == "OK" and b.status == "OK")
    return f


def _mm(case, _results, _diffs) -> bool:
    return bool(getattr(case, "multimaterial", False))


def _science_failed(_case, results, _diffs) -> bool:
    s = results.get("science")
    return bool(s and s.status == "FAIL")


def _always(_case, _results, _diffs) -> bool:
    return True


KNOWN_DELTAS: list[KnownDelta] = [
    KnownDelta(
        id="x1130-flow-override",
        title="x1130 ignores its own `--flow` argument (mitigated)",
        description=(
            "`xcavate_11_30_25.py` line 3705 hardcodes "
            "`flow = 0.1609429886081009`, overriding the `--flow` argparse "
            "value. The harness sets `CANONICAL_PARAMS['flow'] = 0.1609429...` "
            "so all pipelines compute feedrates on the same flow constant; "
            "without this match the F values would diverge by the 0.1609/0.1272 "
            "= 1.265× ratio across every G1 move."
        ),
        applies=_always,
    ),
    KnownDelta(
        id="preamble-line-shift",
        title="x1130 emits an extra leading `G90` before its first `G92`",
        description=(
            "x1130's preamble is `G90 / G92 .. / G90 F<feed> / ...`; main's is "
            "`G92 .. / G90 F<feed> / ...`. This shifts every subsequent line "
            "index by 1 between the two streams. The harness compensates via "
            "`align_on_first_g1=True` in `numerical_diff`, so reported "
            "deviations are post-alignment and reflect actual trajectory drift "
            "rather than the index shift."
        ),
        applies=_both_ok("x1130", "main"),
    ),
    KnownDelta(
        id="x1130-mm-pressure-gate",
        title="x1130's multimaterial-pressure writer is gated on `custom_gcode == 1` (patched)",
        description=(
            "Script line 4717 reads "
            "`if multimaterial == 1 and custom_gcode == 1 and printer_type == 0:`. "
            "Without `--custom 1` (and the auxiliary `inputs/custom/*.txt` "
            "template files it would then read), x1130 silently skipped MM "
            "emission and only wrote `gcode_SM_pressure.txt` even for MM "
            "inputs — leading to `mm_trans=0` in our metrics. "
            "`x1130_runner.py` rewrites that gate in memory so the MM writer "
            "runs without requiring custom template files. After the patch, "
            "x1130 emits 184 nozzle transitions on the 61-vessel network "
            "(vs main's 206)."
        ),
        applies=_mm,
    ),
    KnownDelta(
        id="dfs-extra-pass",
        title="main's iterative DFS produces one more raw pass than x1130's recursive DFS",
        description=(
            "main uses an explicit-stack iterative DFS in "
            "`xcavate/core/pathfinding.py` with reversed neighbour push order; "
            "x1130 uses a recursive DFS that iterates `graph[node]` in native "
            "order. On the 4-vessel network, main produces **14 raw passes** "
            "(lengths sorted: 5, 11, 12, 13, 20, 33, 68, 97, 113, 163, 203, "
            "227, 397, 418) while x1130 produces **13**. The extra pass is "
            "typically a 2-node bridge through a branchpoint that x1130 "
            "absorbs into an adjacent pass. Same vessels are printed; the "
            "split boundary differs."
        ),
        applies=_both_ok("x1130", "main"),
    ),
    KnownDelta(
        id="gap-closure-branchpoint-distribution",
        title="`run_full_gap_closure_pipeline` distributes branchpoint nodes differently",
        description=(
            "After subdivision (which is algorithmically equivalent in both "
            "pipelines), main's gap-closure prepends/appends shared "
            "branchpoint nodes to stitch passes — e.g. main pass 1 starts "
            "with `[1571, 1572, ...]` even though `subdivide_passes` returned "
            "`[1572, ...]`. Pass 2 ends with the same node it started with "
            "(`[985, 489, ..., 393, 985]`). x1130's gap closure makes the "
            "same kind of additions but distributes them across different "
            "passes, leaving one fewer net pass. Net effect: same printed "
            "segments and same vessel coverage, slightly different pass "
            "boundaries and therefore slightly different jog choreography "
            "between passes."
        ),
        applies=_both_ok("x1130", "main"),
    ),
    KnownDelta(
        id="mm-transition-count-divergence",
        title="main emits more multimaterial transitions than x1130",
        description=(
            "On the 61-vessel multimaterial network main emits **205** "
            "nozzle switches while x1130 emits **183** — an ~12% surplus. "
            "The per-switch choreography is byte-identical between the two "
            "pipelines (`G91 G1 A60 B60 F5 / G91 G1 X-103 F10 / "
            "G91 G1 Y0.5 F5 / G91 G1 A-60 B-60`); only the **count** and "
            "**positions** of switches differ. Cause: main's "
            "`_subdivide_by_material` in `xcavate/pipeline.py` splits passes "
            "at material transitions more aggressively than x1130's "
            "Branchpoint-Condition analogue, producing extra "
            "arterial↔venous flips. When the harness aligns the two streams "
            "by index, at some row main is mid-shuttle (`G91 G1 X-103`) "
            "while x1130 is on a normal print move at X ≈ +103 — giving "
            "the characteristic ~206 mm `max_xyz_dev`. Functionally the "
            "same vessels are printed in both materials; main just switches "
            "between printheads more often."
        ),
        applies=_mm,
    ),
    KnownDelta(
        id="science-keyerror",
        title="Science.py crashes internally on every verification network",
        description=(
            "`xcavate_Science.py` (June 2023) raises `KeyError` at script "
            "line 1781 (`f.write(f'Appending node {append_first_branch[i]} "
            "to end of pass {i}.')`) during 'Branchpoint Condition #1'. "
            "The error is internal — argparse already passed — and the key "
            "missing in `append_first_branch` is the loop variable `i` "
            "before the dict has been populated for that pass. Modern "
            "pipelines (x1130, main) fixed this. The harness reports "
            "Science.py as FAIL on every case and does not produce diff "
            "rows for it."
        ),
        applies=_science_failed,
    ),
]


def format_for_case(case, results: dict, diffs: dict) -> str:
    """Build the 'Known residual deltas' markdown section for a single case.

    Returns an empty string if no deltas apply (which would happen if every
    pipeline succeeded with byte-equal output and no flagged categories).
    """
    applicable = [d for d in KNOWN_DELTAS if d.applies(case, results, diffs)]
    if not applicable:
        return ""

    lines = [
        "## Known residual deltas",
        "",
        "These are documented, characterized differences between the pipelines — "
        "not bugs in the harness. Each is either intrinsic to the pipeline "
        "implementation or already mitigated by the harness.",
        "",
    ]
    for d in applicable:
        lines.append(f"### {d.title}")
        lines.append(f"`id: {d.id}`")
        lines.append("")
        lines.append(d.description)
        lines.append("")
    return "\n".join(lines)
