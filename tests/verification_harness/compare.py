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


@dataclass(frozen=True)
class DiffReport:
    pair: tuple[str, str]
    move_count_a: int
    move_count_b: int
    aligned: bool
    max_xyz_dev: float
    max_f_dev: float
    max_e_dev: float
    out_of_tol_count: int
    first_divergences: tuple[tuple[int, str, str], ...]
    byte_equal: bool


def _xyz_dev(a: Move, b: Move) -> float:
    dev = 0.0
    for av, bv in ((a.x, b.x), (a.y, b.y), (a.z, b.z), (a.a, b.a), (a.b, b.b)):
        if av is None and bv is None:
            continue
        if av is None or bv is None:
            return math.inf
        dev = max(dev, abs(av - bv))
    return dev


def _f_dev(a: Move, b: Move) -> float:
    if a.f is None and b.f is None:
        return 0.0
    if a.f is None or b.f is None:
        return math.inf
    return abs(a.f - b.f)


def _e_dev(a: Move, b: Move) -> float:
    if a.e is None and b.e is None:
        return 0.0
    if a.e is None or b.e is None:
        return math.inf
    return abs(a.e - b.e)


def numerical_diff(
    moves_a: list[Move],
    moves_b: list[Move],
    *,
    pair: tuple[str, str],
    eps_xyz: float = 1e-3,
    eps_f: float = 1e-2,
    eps_e: float = 1e-3,
    max_listed: int = 20,
) -> DiffReport:
    n = min(len(moves_a), len(moves_b))
    aligned = len(moves_a) == len(moves_b)
    max_xyz = 0.0
    max_f = 0.0
    max_e = 0.0
    out = 0
    first: list[tuple[int, str, str]] = []
    for i in range(n):
        a, b = moves_a[i], moves_b[i]
        xyz = _xyz_dev(a, b)
        f = _f_dev(a, b)
        e = _e_dev(a, b)
        max_xyz = max(max_xyz, xyz if xyz != math.inf else max_xyz)
        max_f = max(max_f, f if f != math.inf else max_f)
        max_e = max(max_e, e if e != math.inf else max_e)
        if xyz > eps_xyz or f > eps_f or e > eps_e or a.cmd != b.cmd:
            out += 1
            if len(first) < max_listed:
                first.append((i, a.raw, b.raw))
    byte_equal = (
        len(moves_a) == len(moves_b)
        and all(a.raw == b.raw for a, b in zip(moves_a, moves_b))
    )
    return DiffReport(
        pair=pair,
        move_count_a=len(moves_a),
        move_count_b=len(moves_b),
        aligned=aligned,
        max_xyz_dev=max_xyz,
        max_f_dev=max_f,
        max_e_dev=max_e,
        out_of_tol_count=out,
        first_divergences=tuple(first),
        byte_equal=byte_equal,
    )
