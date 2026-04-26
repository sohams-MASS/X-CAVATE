"""Tokenize an X-CAVATE G-code file into normalized Move records."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Move:
    line_no: int
    cmd: str
    x: float | None
    y: float | None
    z: float | None
    a: float | None
    b: float | None
    f: float | None
    e: float | None
    p: float | None
    raw: str


def _strip_comment(line: str) -> str:
    for marker in (";", "("):
        idx = line.find(marker)
        if idx >= 0:
            line = line[:idx]
    return line.strip()


def _coerce(token: str) -> tuple[str, float] | None:
    """Split a G-code token like 'X1.5' into ('X', 1.5). Return None if malformed."""
    if not token:
        return None
    head, rest = token[0].upper(), token[1:]
    if not rest:
        return None
    try:
        return head, float(rest)
    except ValueError:
        return None


def _tokenize(line: str) -> list[str]:
    return line.split()


def parse_text(text: str) -> list[Move]:
    moves: list[Move] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        clean = _strip_comment(raw)
        if not clean:
            continue
        tokens = _tokenize(clean)
        if not tokens:
            continue
        cmd = tokens[0].upper()
        coords = {"X": None, "Y": None, "Z": None, "A": None, "B": None, "F": None, "E": None, "P": None}
        for tok in tokens[1:]:
            parsed = _coerce(tok)
            if parsed is None:
                continue
            head, val = parsed
            if head in coords:
                coords[head] = val
        moves.append(Move(
            line_no=line_no,
            cmd=cmd,
            x=coords["X"], y=coords["Y"], z=coords["Z"],
            a=coords["A"], b=coords["B"],
            f=coords["F"], e=coords["E"], p=coords["P"],
            raw=raw.strip(),
        ))
    return moves


def parse(path: Path) -> list[Move]:
    return parse_text(Path(path).read_text())
