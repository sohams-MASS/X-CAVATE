"""Tests for xcavate.core.multimaterial."""

import numpy as np

from xcavate.core.multimaterial import classify_passes_by_material


def _points_5col(rows):
    """Build a 5-col points array (x, y, z, radius, artven)."""
    return np.array(rows, dtype=float)


class TestClassifyPassesByMaterial:
    """Coverage for classify_passes_by_material edge cases."""

    def test_empty_pass_does_not_crash(self):
        """An empty pass (zero nodes) must be classified safely, not raise."""
        points = _points_5col([
            [0.0, 0.0, 0.0, 0.05, 1.0],
            [1.0, 0.0, 0.0, 0.05, 1.0],
        ])
        passes = {0: [0, 1], 1: []}  # one normal, one empty
        result = classify_passes_by_material(passes, points, num_columns=5)
        assert 0 in result
        assert 1 in result  # empty pass still classified
        assert result[0] == 1  # both nodes artven=1 → arterial

    def test_singleton_pass_uses_its_only_node(self):
        points = _points_5col([
            [0.0, 0.0, 0.0, 0.05, 0.0],  # venous
            [1.0, 0.0, 0.0, 0.05, 1.0],  # arterial
        ])
        passes = {0: [0], 1: [1]}
        result = classify_passes_by_material(passes, points, num_columns=5)
        assert result[0] == 0  # venous
        assert result[1] == 1  # arterial

    def test_multinode_uses_last_node(self):
        """Documented behavior: multi-node pass classified by its last node."""
        points = _points_5col([
            [0.0, 0.0, 0.0, 0.05, 0.0],  # venous
            [1.0, 0.0, 0.0, 0.05, 0.0],  # venous
            [2.0, 0.0, 0.0, 0.05, 1.0],  # arterial (last)
        ])
        passes = {0: [0, 1, 2]}
        result = classify_passes_by_material(passes, points, num_columns=5)
        assert result[0] == 1  # arterial (from last node)

    def test_num_columns_below_5_returns_all_zero(self):
        points = _points_5col([
            [0.0, 0.0, 0.0, 0.05, 1.0],
            [1.0, 0.0, 0.0, 0.05, 1.0],
        ])
        passes = {0: [0, 1], 1: []}
        result = classify_passes_by_material(passes, points, num_columns=4)
        assert result == {0: 0, 1: 0}
