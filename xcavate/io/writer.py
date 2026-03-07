"""Coordinate output writer for processed print passes.

Replaces the duplicated output blocks in xcavate.py (lines 4086-4405) that
write per-axis coordinates, radii, vessel types, print speeds, and
combined coordinate files for both single-material and multimaterial modes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from numpy.typing import NDArray


def write_pass_coordinates(
    output_dir: Path,
    suffix: str,
    print_passes: Dict[int, List[int]],
    points: NDArray[np.floating],
    num_decimals: int,
    num_columns: int,
    speed_map: Optional[Dict[int, float]] = None,
    arbitrary_val: int = 999999999,
) -> None:
    """Write all coordinate output files for a set of print passes.

    Generates per-axis coordinate files, radii, vessel type, print speed,
    and combined coordinate files.  The ``suffix`` distinguishes single-
    material ("SM") from multimaterial ("MM") output.

    Args:
        output_dir: Directory to write output files into.
        suffix: File name suffix, e.g. "SM" or "MM".
        print_passes: Ordered passes {idx: [node_indices]}.
        points: Full coordinate array (N, C).
        num_decimals: Decimal places for rounding output values.
        num_columns: Number of data columns (3, 4, or 5).
        speed_map: Optional per-node print speed dict.
        arbitrary_val: Sentinel value for artifact nodes to skip.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Per-axis coordinate files
    for col, name in [(0, "x"), (1, "y"), (2, "z")]:
        _write_column_file(
            output_dir / f"{name}_coordinates_{suffix}.txt",
            print_passes, points, col, num_decimals, arbitrary_val,
        )

    # Radii file
    if num_columns > 3:
        _write_column_file(
            output_dir / f"radii_list_{suffix}.txt",
            print_passes, points, 3, num_decimals, arbitrary_val,
        )

    # Vessel type file
    if num_columns == 5:
        _write_column_file(
            output_dir / f"vesseltype_list_{suffix}.txt",
            print_passes, points, 4, num_decimals, arbitrary_val,
        )

    # Print speed file
    if speed_map is not None:
        _write_speed_file(
            output_dir / f"printspeed_list_{suffix}.txt",
            print_passes, speed_map, num_decimals,
        )

    # Combined coordinate file
    _write_combined_file(
        output_dir / f"all_coordinates_{suffix}.txt",
        print_passes, points, num_decimals, num_columns, arbitrary_val,
    )


def write_changelog(output_dir: Path, changelog_lines: List[str]) -> None:
    """Write the gap closure changelog to a text file.

    Args:
        output_dir: Directory to write into.
        changelog_lines: Lines produced by the gap closure pipeline.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "changelog.txt", "w") as f:
        f.write("\n".join(changelog_lines))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_column_file(
    path: Path,
    print_passes: Dict[int, List[int]],
    points: NDArray[np.floating],
    col: int,
    nd: int,
    arbitrary_val: int,
) -> None:
    """Write a single-column output file for one coordinate axis or property."""
    with open(path, "w") as f:
        for i in sorted(print_passes.keys()):
            f.write(f"Pass {i}\n")
            for node in print_passes[i]:
                if int(node) != arbitrary_val:
                    val = round(float(points[node, col]), nd)
                    f.write(f"{val:.{nd}f}\n")
            f.write("\n")


def _write_speed_file(
    path: Path,
    print_passes: Dict[int, List[int]],
    speed_map: Dict[int, float],
    nd: int,
) -> None:
    """Write per-node print speed output file."""
    with open(path, "w") as f:
        for i in sorted(print_passes.keys()):
            f.write(f"Pass {i}\n")
            for node in print_passes[i]:
                val = round(speed_map.get(node, 1.0), nd)
                f.write(f"{val:.{nd}f}\n")
            f.write("\n")


def _write_combined_file(
    path: Path,
    print_passes: Dict[int, List[int]],
    points: NDArray[np.floating],
    nd: int,
    num_columns: int,
    arbitrary_val: int,
) -> None:
    """Write combined coordinate file with all available columns."""
    with open(path, "w") as f:
        for i in sorted(print_passes.keys()):
            f.write(f"Pass {i}\n")
            for node in print_passes[i]:
                if int(node) != arbitrary_val:
                    parts = [f"{round(float(points[node, c]), nd)}" for c in range(min(num_columns, points.shape[1]))]
                    f.write(" ".join(parts) + "\n")
            f.write("\n")
