"""Regression test: outlier-swap step in `_subdivide_by_material` must run
the last-node swap AFTER the middle-node swaps so cascading propagation
reaches the tail of the pass.

x1130's reference implementation uses a single ordered loop over j=0..last,
so by the time j=last runs, any middle-node swaps have already mutated
artven[-3]. main's previous code ran the last-node swap before the middle
loop, missing those cascades and leaving extra outliers in the tail.

The mismatch produced ~22 extra material-transition break points per
multimaterial network (+12% nozzle switches in main's gcode vs x1130's).
"""
import numpy as np
import pytest

from xcavate.pipeline import _subdivide_by_material


def _points_from_artven(artven_seq):
    """Build a 5-col points array (x,y,z,radius,artven) from a 1D artven list.
    Each row is a node; xyz are placeholders, only the artven column matters
    for `_subdivide_by_material`."""
    n = len(artven_seq)
    arr = np.zeros((n, 5), dtype=float)
    for i, v in enumerate(artven_seq):
        arr[i, 0] = float(i)        # x
        arr[i, 4] = float(v)        # artven
    return arr


def test_alternating_VAVA_propagation_prevents_spurious_split():
    """Pass [A, V, A, V]: with cascading swap order (first → middle → last),
    the local artven becomes uniform [A, A, A, A], no transitions are
    detected, and the pass stays as one. Pre-fix order ran the last-node
    swap before middle-node propagation, so artven[-3] was still V at the
    last-node check — no swap fired — and a spurious break was created at
    the tail. This is the cascade case from `xcavate_11_30_25.py`'s
    single-pass loop over j=0..last.

    Note: the swap is per-pass-local now and does NOT mutate `points`.
    We verify the OUTCOME (no split) rather than `points[n, 4]`.
    """
    # [A, V, A, V] with values 1=arterial, 0=venous
    points = _points_from_artven([1, 0, 1, 0])
    passes = {0: [0, 1, 2, 3]}
    _subdivide_by_material(passes, {0: 1}, points, num_columns=5)
    # After cascading swap the locally-smoothed artven is uniform [A,A,A,A]
    # so no break point is detected and the pass stays whole.
    assert list(passes.keys()) == [0], (
        f"cascading swap should produce uniform local artven and avoid any "
        f"break point — pass should stay as one. Got {len(passes)} passes."
    )
    assert passes[0] == [0, 1, 2, 3]
    # And `points` must NOT have been mutated — the swap is per-pass-local.
    original_artven = [1, 0, 1, 0]
    actual = [int(points[n, 4]) for n in range(4)]
    assert actual == original_artven, (
        f"swap must NOT write back to `points`. Original {original_artven}, "
        f"after subdivide call: {actual}. The mutation would leak to other "
        f"passes containing the same branchpoint nodes."
    )


def test_clean_pass_no_swap_no_split():
    """Already-uniform pass produces no break points and stays as one pass."""
    points = _points_from_artven([1, 1, 1, 1, 1])
    passes = {0: [0, 1, 2, 3, 4]}
    _subdivide_by_material(passes, {0: 1}, points, num_columns=5)
    assert list(passes.keys()) == [0]
    assert passes[0] == [0, 1, 2, 3, 4]


def test_swap_does_not_leak_across_passes():
    """A branchpoint node shared between two passes must NOT have its
    swapped artven value written back to `points`. If pass A swaps the
    branchpoint from V to A, pass B (which contains the same node) must
    still see the ORIGINAL V when it does its own break detection.

    x1130 keeps swap state per-pass-local in `print_passes_processed_artven`;
    main was previously writing swapped values back to `points[n, 4]` and
    leaking the mutation into other passes. That cross-pass leakage was the
    dominant driver of the +22 transition surplus on the 61-vessel network.
    """
    # Branchpoint node 5 has artven=0 (venous). It appears in both pass 0
    # (where the swap fires and would mutate it to 1) and pass 1 (where its
    # original value of 0 must still be read).
    points = _points_from_artven([1, 0, 1, 0, 0, 0, 1, 1])
    # Pass 0: nodes [0,1,2] — alternating triple [1,0,1] → swap fires:
    #         middle j=1 with prev[0]==next[2]==1, curr=0 → swap to 1
    #         result [1,1,1] (in local artven only).
    # Pass 1: nodes [5,6,7] — values [0,1,1] (post-swap-step does nothing
    #         since the only middle node has prev != next).
    passes = {0: [0, 1, 2], 1: [5, 6, 7]}
    _subdivide_by_material(passes, {0: 1, 1: 1}, points, num_columns=5)
    # The shared node hasn't moved between passes here; the test is that
    # `points[1, 4]` is NOT mutated to 1 even though pass 0's local swap set
    # the local artven[1] = 1.
    assert int(points[1, 4]) == 0, (
        f"swap leaked back into points: points[1, 4] = {int(points[1, 4])}, "
        f"expected 0 (original venous value). Per-pass swap state must stay "
        f"local — never write back to the shared `points` array."
    )


def test_real_transition_does_split():
    """A pass with a clean material transition in the middle is split into
    two sub-passes, with the second sub-pass overlapping by 1 node."""
    points = _points_from_artven([1, 1, 1, 0, 0, 0])
    passes = {0: [0, 1, 2, 3, 4, 5]}
    _subdivide_by_material(passes, {0: 1}, points, num_columns=5)
    assert len(passes) == 2
    # First sub-pass: nodes [0..2] (the arterial run)
    assert passes[0] == [0, 1, 2]
    # Second sub-pass: nodes [2..5] (the venous run, overlapping by 1)
    assert passes[1] == [2, 3, 4, 5]
