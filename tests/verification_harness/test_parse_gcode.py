"""Tests for the G-code parser."""
from pathlib import Path
import textwrap

from tests.verification_harness.parse_gcode import Move, parse, parse_text


SAMPLE = textwrap.dedent("""\
    G90
    G92 X0 Y0 A0
    G1 X1.5 Y2.0 A0.1 F60
    G1 X2.0 Y2.0 A0.2 F60
    G4 P0.08
    G91
    G1 A0.5 F0.25
    G90
""")


def test_parse_text_handles_all_command_types():
    moves = parse_text(SAMPLE)
    cmds = [m.cmd for m in moves]
    assert cmds == ["G90", "G92", "G1", "G1", "G4", "G91", "G1", "G90"]


def test_g1_extracts_xyz_and_feedrate():
    moves = parse_text(SAMPLE)
    g1_first = moves[2]
    assert g1_first.x == 1.5
    assert g1_first.y == 2.0
    assert g1_first.a == 0.1
    assert g1_first.f == 60.0


def test_g4_extracts_dwell():
    moves = parse_text(SAMPLE)
    dwell = next(m for m in moves if m.cmd == "G4")
    assert dwell.p == 0.08


def test_blank_lines_and_comments_are_skipped():
    text = "G90\n\n; a comment\nG1 X1 Y2 F60\n"
    moves = parse_text(text)
    assert [m.cmd for m in moves] == ["G90", "G1"]
    assert moves[1].x == 1.0


def test_parse_reads_from_path(tmp_path):
    p = tmp_path / "t.gcode"
    p.write_text("G90\nG1 X1 Y2 F60\n")
    moves = parse(p)
    assert len(moves) == 2
    assert moves[1].x == 1.0


def test_unknown_token_keeps_cmd_drops_coords():
    moves = parse_text("M104 S200\n")
    assert len(moves) == 1
    assert moves[0].cmd == "M104"
    assert moves[0].x is None
