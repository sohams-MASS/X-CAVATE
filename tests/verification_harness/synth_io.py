"""Synthesize an inlet/outlet companion file for orphan vascular networks."""
from __future__ import annotations

import math
from pathlib import Path

Point = tuple[float, float, float]


def _parse_vessels(text: str) -> list[list[Point]]:
    """Split the network text into per-vessel lists of (x, y, z) points."""
    vessels: list[list[Point]] = []
    current: list[Point] | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("Vessel"):
            current = []
            vessels.append(current)
            continue
        if current is None:
            continue
        parts = [p.strip() for p in s.split(",")]
        if len(parts) < 3:
            continue
        try:
            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError:
            continue
        current.append((x, y, z))
    return vessels


def _vessel_length(points: list[Point]) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        total += math.sqrt(dx * dx + dy * dy + dz * dz)
    return total


def synthesize_inletoutlet(network_path: str | Path) -> Path:
    """Write <stem>_synth_inletoutlet.txt next to the network file.

    Inlet  = first point of vessel 0.
    Outlet = last point of the vessel with greatest arc length.
    """
    network_path = Path(network_path)
    text = network_path.read_text()
    vessels = _parse_vessels(text)
    if not vessels or not vessels[0]:
        raise ValueError(f"No vessels parsed from {network_path}")

    inlet = vessels[0][0]
    longest_idx = max(range(len(vessels)), key=lambda i: _vessel_length(vessels[i]))
    outlet = vessels[longest_idx][-1]

    out_path = network_path.with_name(f"{network_path.stem}_synth_inletoutlet.txt")

    def _fmt(pt: Point) -> str:
        return f"{pt[0]}, {pt[1]}, {pt[2]}"

    out_path.write_text(
        "inlet\n" + _fmt(inlet) + "\n" + "outlet\n" + _fmt(outlet) + "\n"
    )
    return out_path
