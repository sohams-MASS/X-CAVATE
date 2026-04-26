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


def test_alternating_VAVA_propagates_to_last():
    """Pass [V, A, V, A]: cascading middle swaps must reach the last node.

    Step-by-step expected:
      0. Original artven    : [V, A, V, A]
      1. j=0 swap            : artven[1] != artven[2] (A != V) -> no swap
      2. j=1 (middle) swap   : artven[0]==artven[2]==V, artven[1]=A != V
                               -> artven[1] = V       => [V, V, V, A]
      3. j=2 (middle) swap   : artven[1]==artven[3]? V==A no
                               -> no swap              => [V, V, V, A]
      4. j=last swap         : artven[-2]==artven[-3]==V (after step 2!),
                               artven[-1]=A != V
                               -> artven[-1] = V       => [V, V, V, V]

    main's pre-fix order ran step 4 before step 2, so artven[-3] was still A
    at the time of the last-node check, the condition (artven[-2] == artven[-3])
    failed, and the last swap was skipped. Result was [V, V, V, A] with a
    spurious A→V transition at the tail.
    """
    points = _points_from_artven([1, 0, 1, 0])  # V=0, A=1
    passes = {0: [0, 1, 2, 3]}
    _subdivide_by_material(passes, {0: 1}, points, num_columns=5)
    final_artven = [int(points[n, 4]) for n in range(4)]
    assert final_artven == [1, 1, 1, 1], (
        f"swap order regression: expected [1,1,1,1] after cascading middle + "
        f"last swaps, got {final_artven}. Last-node swap must run after the "
        f"middle-node swap loop."
    )


def test_clean_pass_no_swap_no_split():
    """Already-uniform pass produces no break points and stays as one pass."""
    points = _points_from_artven([1, 1, 1, 1, 1])
    passes = {0: [0, 1, 2, 3, 4]}
    _subdivide_by_material(passes, {0: 1}, points, num_columns=5)
    assert list(passes.keys()) == [0]
    assert passes[0] == [0, 1, 2, 3, 4]


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
