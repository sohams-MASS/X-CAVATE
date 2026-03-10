"""Tests for xcavate.core.gap_closure."""

import pytest

from xcavate.core.gap_closure import find_disconnects, DisconnectInfo


class TestFindDisconnects:
    """Tests for the find_disconnects function."""

    def test_find_disconnects_returns_dataclass(self):
        """find_disconnects should return a DisconnectInfo dataclass."""
        # Minimal connected graph: 3 nodes in a chain
        graph = {
            0: [0, 1],
            1: [0, 1, 2],
            2: [1, 2],
        }
        # Single pass containing all nodes in order
        print_passes = {0: [0, 1, 2]}
        endpoint_nodes = [0, 2]

        result = find_disconnects(print_passes, graph, endpoint_nodes)
        assert isinstance(result, DisconnectInfo)

    def test_no_disconnects_in_connected_pass(self):
        """If all passes are internally connected, should find 0 disconnects."""
        # Two passes that share a node at their boundary
        graph = {
            0: [0, 1],
            1: [0, 1, 2],
            2: [1, 2, 3],
            3: [2, 3],
        }
        # Pass 0 ends at node 1, pass 1 starts at node 2.
        # Nodes 1 and 2 are graph neighbors, and both appear as pass
        # endpoints -- each appears once, making them potentially
        # disconnected.  However, because node 1 is an endpoint_node
        # (original vessel endpoint) it is excluded by step 3 of the
        # algorithm.  Similarly node 2 is an endpoint_node.
        print_passes = {0: [0, 1], 1: [2, 3]}
        endpoint_nodes = [0, 1, 2, 3]

        result = find_disconnects(print_passes, graph, endpoint_nodes)
        assert len(result.final_true_disconnect) == 0
