"""Tests for xcavate.core.pathfinding."""

import numpy as np
import pytest

from xcavate.core.pathfinding import CollisionDetector, DFSStrategy
from xcavate.core.graph import build_graph
from xcavate.core.preprocessing import interpolate_network, get_vessel_boundaries


def _build_test_graph(simple_network_points, coord_num_dict, nozzle_radius=0.125):
    """Helper to build a graph from the simple network fixture."""
    num_columns = 3
    points_interp = interpolate_network(
        simple_network_points, coord_num_dict, nozzle_radius, num_columns
    )

    boundaries = get_vessel_boundaries(points_interp, coord_num_dict)
    coord_num_dict_interp = {v: info["count"] for v, info in boundaries.items()}
    vessel_start_nodes = [info["start"] for v, info in boundaries.items()]

    points_xyz = points_interp[:, :3]

    inlet_nodes = [boundaries[0]["start"]]
    outlet_nodes = [boundaries[1]["end"], boundaries[2]["end"]]

    graph, *_ = build_graph(
        points_xyz, coord_num_dict_interp, vessel_start_nodes,
        inlet_nodes, outlet_nodes,
    )
    return graph, points_xyz


class TestCollisionDetector:
    """Tests for the CollisionDetector class."""

    def test_collision_detector_marks_visited(self):
        """After marking a node visited, is_visited should return True."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 1.0],
            [2.0, 0.0, 2.0],
        ])
        detector = CollisionDetector(points, nozzle_radius=0.5)

        assert not detector.is_visited(0)
        detector.mark_visited(0)
        assert detector.is_visited(0)

        # Other nodes should still be unvisited
        assert not detector.is_visited(1)
        assert not detector.is_visited(2)


class TestDFSStrategy:
    """Tests for the DFS pathfinding strategy."""

    def test_dfs_visits_all_nodes(self, simple_network_points, coord_num_dict):
        """All nodes in the graph should appear in some print pass."""
        graph, points_xyz = _build_test_graph(
            simple_network_points, coord_num_dict
        )

        strategy = DFSStrategy()
        passes = strategy.generate_print_passes(
            graph, points_xyz, nozzle_radius=0.125
        )

        visited_nodes = set()
        for pass_nodes in passes.values():
            visited_nodes.update(pass_nodes)

        all_nodes = set(graph.keys())
        assert visited_nodes == all_nodes, (
            f"Missing nodes: {all_nodes - visited_nodes}"
        )

    def test_passes_are_non_empty(self, simple_network_points, coord_num_dict):
        """No pass should be an empty list."""
        graph, points_xyz = _build_test_graph(
            simple_network_points, coord_num_dict
        )

        strategy = DFSStrategy()
        passes = strategy.generate_print_passes(
            graph, points_xyz, nozzle_radius=0.125
        )

        for idx, pass_nodes in passes.items():
            assert len(pass_nodes) > 0, f"Pass {idx} is empty"
