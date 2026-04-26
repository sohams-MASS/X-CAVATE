"""Aggregate metrics and pairwise numerical diff for parsed G-code."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .parse_gcode import Move


@dataclass(frozen=True)
class Metrics:
    move_count: int
    g0_count: int
    g1_count: int
    g4_count: int
    total_path_length_mm: float
    multimat_transitions: int
    est_print_time_s: float


def _last_xyz(state: dict, m: Move) -> None:
    for axis, val in (("x", m.x), ("y", m.y), ("z", m.z)):
        if val is not None:
            state[axis] = val


def aggregate(moves: list[Move]) -> Metrics:
    g0 = g1 = g4 = 0
    total_len = 0.0
    print_time = 0.0
    pos = {"x": 0.0, "y": 0.0, "z": 0.0}
    last_feed: float | None = None
    transitions = 0
    last_active: str | None = None  # "A" or "B"

    for m in moves:
        if m.cmd == "G0":
            g0 += 1
            _last_xyz(pos, m)
        elif m.cmd == "G1":
            g1 += 1
            x_new = m.x if m.x is not None else pos["x"]
            y_new = m.y if m.y is not None else pos["y"]
            z_new = m.z if m.z is not None else pos["z"]
            dx, dy, dz = x_new - pos["x"], y_new - pos["y"], z_new - pos["z"]
            seg = math.sqrt(dx * dx + dy * dy + dz * dz)
            total_len += seg
            if m.f is not None:
                last_feed = m.f
            if last_feed and last_feed > 0:
                print_time += seg / last_feed
            pos.update(x=x_new, y=y_new, z=z_new)
            # transition tracking — based on which axis the line touches
            if m.a is not None and m.b is None:
                active = "A"
            elif m.b is not None and m.a is None:
                active = "B"
            else:
                active = last_active
            if active is not None and last_active is not None and active != last_active:
                transitions += 1
            if active is not None:
                last_active = active
        elif m.cmd == "G4":
            g4 += 1

    return Metrics(
        move_count=len(moves),
        g0_count=g0,
        g1_count=g1,
        g4_count=g4,
        total_path_length_mm=total_len,
        multimat_transitions=transitions,
        est_print_time_s=print_time,
    )
