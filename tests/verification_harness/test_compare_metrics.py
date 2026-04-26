"""Tests for aggregate metrics on parsed G-code."""
from .parse_gcode import parse_text
from .compare import aggregate


def test_metrics_count_g0_g1_g4():
    moves = parse_text(
        "G90\nG0 X0 Y0\nG1 X1 Y0 F60\nG1 X1 Y1 F60\nG4 P0.08\n"
    )
    m = aggregate(moves)
    assert m.move_count == 5
    assert m.g0_count == 1
    assert m.g1_count == 2
    assert m.g4_count == 1


def test_metrics_total_path_length_sums_g1_steps():
    moves = parse_text(
        "G90\nG92 X0 Y0 Z0\nG1 X3 Y0 Z0 F60\nG1 X3 Y4 Z0 F60\n"
    )
    m = aggregate(moves)
    # First G1: 3 mm. Second G1: 4 mm. Total: 7 mm.
    assert m.total_path_length_mm == 7.0


def test_metrics_estimated_print_time_uses_feedrate():
    # feedrate is in mm/s for legacy scripts and main with --speed_unit mm/s
    moves = parse_text(
        "G92 X0 Y0 Z0\nG1 X10 Y0 Z0 F2\n"  # 10 mm at 2 mm/s = 5 s
    )
    m = aggregate(moves)
    assert m.est_print_time_s == 5.0


def test_metrics_multimat_transitions_counts_axis_switches():
    # Aerotech-style multimaterial uses A then B; transitions = number of switches
    moves = parse_text(
        "G92 X0 Y0 A0 B0\n"
        "G1 X1 Y0 A0.1 F60\n"   # arterial
        "G1 X2 Y0 A0.2 F60\n"   # arterial
        "G1 X3 Y0 B0.1 F60\n"   # switch to venous (1)
        "G1 X4 Y0 B0.2 F60\n"   # venous
        "G1 X5 Y0 A0.3 F60\n"   # switch to arterial (2)
    )
    m = aggregate(moves)
    assert m.multimat_transitions == 2
