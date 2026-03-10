"""Tests for xcavate.core.graph."""

import numpy as np
import pytest

from xcavate.core.graph import build_graph
from xcavate.core.preprocessing import interpolate_network, get_vessel_boundaries


def _prepare_graph_inputs(simple_network_points, coord_num_dict, nozzle_radius=0.125):
    """Helper to run interpolation and prepare inputs for build_graph."""
    num_columns = 3
    points_interp = interpolate_network(
        simple_network_points, coord_num_dict, nozzle_radius, num_columns
    )

    boundaries = get_vessel_boundaries(points_interp, coord_num_dict)
    coord_num_dict_interp = {v: info["count"] for v, info in boundaries.items()}
    vessel_start_nodes = [info["start"] for v, info in boundaries.items()]

    # Use only xyz columns for the graph
    points_xyz = points_interp[:, :3]

    # For the Y-shaped network, node 0 is the inlet (bottom of trunk)
    # and the last nodes of vessels 1 and 2 are outlets (tips of daughters).
    inlet_nodes = [boundaries[0]["start"]]
    outlet_nodes = [boundaries[1]["end"], boundaries[2]["end"]]

    return points_xyz, coord_num_dict_interp, vessel_start_nodes, inlet_nodes, outlet_nodes


class TestBuildGraph:
    """Tests for the build_graph function."""

    def test_build_graph_returns_all_components(
        self, simple_network_points, coord_num_dict
    ):
        """build_graph should return a 7-tuple with expected types."""
        args = _prepare_graph_inputs(simple_network_points, coord_num_dict)
        result = build_graph(*args)

        assert isinstance(result, tuple)
        assert len(result) == 7

        graph, branch_dict, branchpoint_list, bp_daughter_dict, endpoint_nodes, nodes_by_vessel, repeat_daughters = result

        assert isinstance(graph, dict)
        assert isinstance(branch_dict, dict)
        assert isinstance(branchpoint_list, list)
        assert isinstance(bp_daughter_dict, dict)
        assert isinstance(endpoint_nodes, list)
        assert isinstance(nodes_by_vessel, dict)
        assert isinstance(repeat_daughters, set)

    def test_graph_has_self_loops(self, simple_network_points, coord_num_dict):
        """Every node should appear in its own adjacency list."""
        args = _prepare_graph_inputs(simple_network_points, coord_num_dict)
        graph = build_graph(*args)[0]

        for node, neighbors in graph.items():
            assert node in neighbors, f"Node {node} missing self-loop"

    def test_adjacency_mostly_symmetric(self, simple_network_points, coord_num_dict):
        """Most edges should be symmetric (branchpoint wiring may remove some)."""
        args = _prepare_graph_inputs(simple_network_points, coord_num_dict)
        graph = build_graph(*args)[0]

        symmetric = 0
        total = 0
        for node_a, neighbors in graph.items():
            for node_b in neighbors:
                if node_b == node_a:
                    continue
                total += 1
                if node_a in graph.get(node_b, []):
                    symmetric += 1

        # Vast majority of edges should be symmetric; branchpoint resolution
        # may intentionally remove a few back-edges.
        assert symmetric / total > 0.9, (
            f"Too many asymmetric edges: {symmetric}/{total} symmetric"
        )

    def test_branchpoint_detection(self, simple_network_points, coord_num_dict):
        """For the Y-shaped network there should be branchpoints with 2-daughter pairs."""
        args = _prepare_graph_inputs(simple_network_points, coord_num_dict)
        _, branch_dict, branchpoint_list, _, _, _, _ = build_graph(*args)

        # Should have at least one branchpoint
        assert len(branch_dict) >= 1

        # Every parent should have exactly 2 daughters
        for parent, daughters in branch_dict.items():
            assert len(daughters) == 2, (
                f"Branchpoint {parent} has {len(daughters)} daughters, expected 2"
            )
