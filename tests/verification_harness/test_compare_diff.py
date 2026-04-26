"""Tests for pairwise numerical diff."""
from .parse_gcode import parse_text
from .compare import numerical_diff


def _parse(s):
    return parse_text(s)


def test_identical_gcode_has_zero_deviation():
    text = "G90\nG1 X1 Y2 Z0 F60\n"
    a = _parse(text)
    b = _parse(text)
    d = numerical_diff(a, b, pair=("p1", "p2"))
    assert d.aligned is True
    assert d.max_xyz_dev == 0.0
    assert d.max_f_dev == 0.0
    assert d.byte_equal is True
    assert d.out_of_tol_count == 0


def test_small_xyz_difference_within_tolerance_is_zero_outliers():
    a = _parse("G1 X1.0000 Y2.0 F60\n")
    b = _parse("G1 X1.0005 Y2.0 F60\n")
    d = numerical_diff(a, b, pair=("a", "b"), eps_xyz=1e-3)
    assert d.out_of_tol_count == 0


def test_large_xyz_difference_is_flagged():
    a = _parse("G1 X1.0 Y2.0 F60\n")
    b = _parse("G1 X1.5 Y2.0 F60\n")
    d = numerical_diff(a, b, pair=("a", "b"), eps_xyz=1e-3)
    assert d.out_of_tol_count == 1
    assert d.max_xyz_dev == 0.5


def test_length_mismatch_marks_unaligned():
    a = _parse("G1 X1 Y1 F60\nG1 X2 Y2 F60\n")
    b = _parse("G1 X1 Y1 F60\n")
    d = numerical_diff(a, b, pair=("a", "b"))
    assert d.aligned is False
    assert d.move_count_a == 2
    assert d.move_count_b == 1


def test_first_divergences_caps_at_n():
    a_text = "\n".join(f"G1 X{i} Y0 F60" for i in range(50)) + "\n"
    b_text = "\n".join(f"G1 X{i + 10} Y0 F60" for i in range(50)) + "\n"
    d = numerical_diff(_parse(a_text), _parse(b_text), pair=("a", "b"), max_listed=5)
    assert len(d.first_divergences) == 5


def test_align_on_first_g1_skips_preamble_offset():
    """A's preamble is one line longer (G90 leader); aligned diff should still
    return zero deviation since the actual G1 trajectories agree."""
    a = _parse(
        "G90\n"          # extra leader
        "G92 X0 Y0\n"
        "G90 F60\n"
        "G1 X1 Y2 F60\n"
        "G1 X3 Y4 F60\n"
    )
    b = _parse(
        "G92 X0 Y0\n"   # no extra G90
        "G90 F60\n"
        "G1 X1 Y2 F60\n"
        "G1 X3 Y4 F60\n"
    )
    d = numerical_diff(a, b, pair=("a", "b"), align_on_first_g1=True)
    assert d.max_xyz_dev == 0.0
    assert d.out_of_tol_count == 0


def test_align_on_first_g1_preserves_real_drift():
    a = _parse(
        "G90\nG92 X0 Y0\nG90 F60\n"
        "G1 X1 Y2 F60\nG1 X3 Y4 F60\n"
    )
    b = _parse(
        "G92 X0 Y0\nG90 F60\n"
        "G1 X1 Y2 F60\nG1 X3.5 Y4 F60\n"   # 0.5mm drift on second G1
    )
    d = numerical_diff(a, b, pair=("a", "b"), align_on_first_g1=True)
    assert d.max_xyz_dev == 0.5
    assert d.out_of_tol_count == 1
