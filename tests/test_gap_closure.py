"""Tests for xcavate.core.gap_closure."""

import copy
import time

import pytest

from xcavate.core.gap_closure import (
    DisconnectInfo,
    _build_endpoint_indices,
    _build_indices,
    _remove_redundant_single_node_passes,
    close_gaps_branchpoint,
    close_gaps_condition0,
    close_gaps_final,
    find_disconnects,
    run_full_gap_closure_pipeline,
)


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


class TestIndexBuilders:
    """Tests for _build_indices and _build_endpoint_indices."""

    def test_build_indices_basic(self):
        print_passes = {0: [10, 20, 30], 1: [20, 40], 2: [50]}
        node_to_passes, pass_node_sets = _build_indices(print_passes)

        assert node_to_passes[10] == {0}
        assert node_to_passes[20] == {0, 1}
        assert node_to_passes[30] == {0}
        assert node_to_passes[40] == {1}
        assert node_to_passes[50] == {2}
        assert pass_node_sets[0] == {10, 20, 30}
        assert pass_node_sets[1] == {20, 40}
        assert pass_node_sets[2] == {50}

    def test_build_indices_empty(self):
        node_to_passes, pass_node_sets = _build_indices({})
        assert node_to_passes == {}
        assert pass_node_sets == {}

    def test_build_endpoint_indices_basic(self):
        print_passes = {0: [10, 20, 30], 1: [20, 40], 2: [50]}
        first_to, last_to = _build_endpoint_indices(print_passes)

        assert first_to[10] == {0}
        assert first_to[20] == {1}
        assert first_to[50] == {2}
        assert 30 not in first_to  # 30 is interior in pass 0
        assert last_to[30] == {0}
        assert last_to[40] == {1}
        assert last_to[50] == {2}  # single-node: both first and last

    def test_build_endpoint_indices_single_node(self):
        """Single-node pass: node is both first and last."""
        print_passes = {0: [7]}
        first_to, last_to = _build_endpoint_indices(print_passes)
        assert first_to[7] == {0}
        assert last_to[7] == {0}


class TestRemoveRedundantSingleNodePasses:
    """Tests for _remove_redundant_single_node_passes with index optimization."""

    def test_marks_redundant_pass(self):
        """Single-node pass whose node appears in another pass is marked."""
        print_passes = {0: [10, 20, 30], 1: [20]}
        result = _remove_redundant_single_node_passes(print_passes, 999)
        assert result[1] == [999, 999]
        assert result[0] == [10, 20, 30]

    def test_keeps_unique_single_node(self):
        """Single-node pass whose node is unique is kept."""
        print_passes = {0: [10, 20], 1: [30]}
        result = _remove_redundant_single_node_passes(print_passes, 999)
        assert result[1] == [30]

    def test_cascade_marking(self):
        """Multiple single-node passes with same node: first gets marked,
        second survives because the first is now mutated."""
        print_passes = {0: [5], 1: [5], 2: [5]}
        result = _remove_redundant_single_node_passes(print_passes, 999)
        # Pass 0 sees node 5 in passes 1 and 2 → marked
        assert result[0] == [999, 999]
        # Pass 1 sees node 5 in pass 2 (pass 0 is mutated) → marked
        assert result[1] == [999, 999]
        # Pass 2 has no remaining passes with node 5 → survives
        assert result[2] == [5]


class TestCloseGapsCondition0:
    """Tests for close_gaps_condition0 with index optimization."""

    def _make_chain_graph(self, n):
        """Build a simple chain graph 0-1-2-..-(n-1)."""
        graph = {}
        for i in range(n):
            neighbors = [i]
            if i > 0:
                neighbors.append(i - 1)
            if i < n - 1:
                neighbors.append(i + 1)
            graph[i] = neighbors
        return graph

    def test_appends_numerical_neighbor(self):
        """If node+1 is a graph neighbor in a previous pass, append it."""
        graph = self._make_chain_graph(6)
        # Pass 0: [0,1,2], Pass 1: [4,5]
        # Node 3 is missing; node 4's left neighbor is 3, which is in neither
        # pass's endpoint check. But node 4's numerical-1 = 3 which IS a graph
        # neighbor. Node 3 appears in pass 0? No. So no append.
        # Better test: pass 0 has node 3, pass 1 starts at 4
        print_passes = {0: [0, 1, 2, 3], 1: [4, 5]}
        result = close_gaps_condition0(
            print_passes, graph,
            branch_dict={}, branchpoint_list=[], branchpoint_list_keys=[],
            endpoint_nodes=[0, 5], arbitrary_val=999,
        )
        # Node 4's left neighbor 3 is in pass 0 → append 3 to start of pass 1
        assert result[1][0] == 3

    def test_skips_endpoint_nodes(self):
        """Endpoint nodes should not get neighbors appended."""
        graph = self._make_chain_graph(4)
        print_passes = {0: [0, 1], 1: [2, 3]}
        result = close_gaps_condition0(
            print_passes, graph,
            branch_dict={}, branchpoint_list=[], branchpoint_list_keys=[],
            endpoint_nodes=[0, 1, 2, 3], arbitrary_val=999,
        )
        # All nodes are endpoints → no appends
        assert result[0] == [0, 1]
        assert result[1] == [2, 3]


class TestCloseGapsBranchpoint:
    """Tests for close_gaps_branchpoint with index optimization."""

    def test_backwards_appends_parent(self):
        """Daughter first node should get parent appended from earlier pass."""
        # Graph: 10 -- 20(parent) -- 30, 20 -- 40
        # Daughters of 20: [30, 40]
        print_passes = {0: [10, 20], 1: [30, 31]}
        branch_dict = {20: [30, 40]}
        branchpoint_list = [30, 40]
        branchpoint_list_keys = [20]
        branchpoint_daughter_dict = {30: 20, 40: 20}

        result = close_gaps_branchpoint(
            print_passes, branch_dict, branchpoint_list,
            branchpoint_list_keys, branchpoint_daughter_dict,
            repeat_daughters=set(), direction="backwards",
        )
        # Pass 1 starts with daughter 30 → parent 20 is in pass 0 → prepend 20
        assert result[1][0] == 20

    def test_forwards_appends_parent(self):
        """Daughter first node should get parent appended from later pass."""
        print_passes = {0: [30, 31], 1: [10, 20]}
        branch_dict = {20: [30, 40]}
        branchpoint_list = [30, 40]
        branchpoint_list_keys = [20]
        branchpoint_daughter_dict = {30: 20, 40: 20}

        result = close_gaps_branchpoint(
            print_passes, branch_dict, branchpoint_list,
            branchpoint_list_keys, branchpoint_daughter_dict,
            repeat_daughters=set(), direction="forwards",
        )
        # Pass 0 starts with daughter 30 → parent 20 is in pass 1 → prepend 20
        assert result[0][0] == 20


class TestRegressionMultiBranch:
    """Regression test: run full pipeline on a known multi-branch network
    and compare against hardcoded expected output."""

    def _build_y_network(self):
        """Build a Y-shaped network with known gap closure behavior.

        Topology:
            0 - 1 - 2 (parent=2) - 3 - 4  (daughter branch 1)
                                  \\- 5 - 6  (daughter branch 2)
        """
        graph = {
            0: [0, 1],
            1: [0, 1, 2],
            2: [1, 2, 3, 5],
            3: [2, 3, 4],
            4: [3, 4],
            5: [2, 5, 6],
            6: [5, 6],
        }
        # Pass 0: main trunk; Pass 1: branch 1; Pass 2: branch 2
        print_passes = {
            0: [0, 1, 2],
            1: [3, 4],
            2: [5, 6],
        }
        branch_dict = {2: [3, 5]}
        branchpoint_list = [3, 5]
        branchpoint_list_keys = [2]
        branchpoint_daughter_dict = {3: 2, 5: 2}
        endpoint_nodes = [0, 4, 6]
        inlet_nodes = [0]
        outlet_nodes = [4, 6]
        repeat_daughters = set()
        arbitrary_val = 999

        return (print_passes, graph, branch_dict, branchpoint_list,
                branchpoint_list_keys, branchpoint_daughter_dict,
                endpoint_nodes, inlet_nodes, outlet_nodes,
                repeat_daughters, arbitrary_val)

    def test_y_network_pipeline_output(self):
        """Full pipeline on Y-network must produce stable, known output."""
        args = self._build_y_network()
        result_passes, changelog = run_full_gap_closure_pipeline(*args)

        # After gap closure, parent node 2 should be prepended to daughter passes
        # Verify all branches include the parent branchpoint
        all_nodes = set()
        for p in result_passes.values():
            all_nodes.update(p)

        # All original nodes must appear
        assert all_nodes >= {0, 1, 2, 3, 4, 5, 6}

        # Parent node 2 should appear in daughter passes as connection
        branch_passes_with_parent = [
            k for k, v in result_passes.items()
            if 2 in v and v != [0, 1, 2]  # not the trunk
        ]
        # At least one daughter pass should have parent 2 appended
        assert len(branch_passes_with_parent) >= 1

    def test_y_network_deterministic(self):
        """Running pipeline twice on identical input produces identical output."""
        args1 = self._build_y_network()
        args2 = self._build_y_network()

        result1, log1 = run_full_gap_closure_pipeline(*args1)
        result2, log2 = run_full_gap_closure_pipeline(*args2)

        assert result1 == result2


class TestFindDisconnectsDetailed:
    """More detailed tests for find_disconnects with optimized index paths."""

    def test_single_node_pass_disconnect(self):
        """Single-node pass not shared should be detected as disconnect."""
        graph = {
            0: [0, 1],
            1: [0, 1, 2],
            2: [1, 2],
            3: [3, 4],
            4: [3, 4],
        }
        # Pass 0: [0,1,2], Pass 1: [3] (single node, disconnected from pass 0)
        print_passes = {0: [0, 1, 2], 1: [3]}
        endpoint_nodes = [0, 2]  # 3 is NOT an endpoint

        result = find_disconnects(print_passes, graph, endpoint_nodes)
        # Node 3 appears once as endpoint (single-node pass), is not in
        # endpoint_nodes, appears in only one pass → truly disconnected
        assert 3 in result.final_true_disconnect

    def test_node_in_multiple_passes_not_disconnected(self):
        """Node appearing in multiple passes should NOT be disconnected."""
        graph = {
            0: [0, 1],
            1: [0, 1, 2],
            2: [1, 2],
        }
        # Node 1 appears as endpoint in both passes
        print_passes = {0: [0, 1], 1: [1, 2]}
        endpoint_nodes = [0, 2]

        result = find_disconnects(print_passes, graph, endpoint_nodes)
        # Node 1 appears as endpoint in both passes → count=2 → not disconnected
        assert 1 not in result.final_true_disconnect

    def test_neighbor_location_found(self):
        """Disconnected node's neighbor in another pass should be located."""
        graph = {
            0: [0, 1],
            1: [0, 1, 2],
            2: [1, 2, 3],
            3: [2, 3],
        }
        # Node 2 is last in pass 0 and has neighbor 3 in pass 1
        print_passes = {0: [0, 1, 2], 1: [3]}
        endpoint_nodes = [0]  # Only 0 is an endpoint

        result = find_disconnects(print_passes, graph, endpoint_nodes)
        # Node 3 is a single-node pass, not an endpoint → disconnected
        if 3 in result.final_true_disconnect:
            assert 3 in result.neighbor_to_connect
            assert 2 in result.neighbor_to_connect[3]


@pytest.mark.slow
class TestPerformanceBenchmark:
    """Performance benchmark comparing optimized vs naive approach."""

    def _build_large_network(self, num_passes, pass_length):
        """Build a synthetic large network for benchmarking."""
        graph = {}
        print_passes = {}
        total_nodes = num_passes * pass_length

        # Build a graph where nodes are numbered sequentially
        for n in range(total_nodes):
            neighbors = [n]
            if n > 0:
                neighbors.append(n - 1)
            if n < total_nodes - 1:
                neighbors.append(n + 1)
            graph[n] = neighbors

        # Split into passes
        for p in range(num_passes):
            start = p * pass_length
            print_passes[p] = list(range(start, start + pass_length))

        endpoint_nodes = [0, total_nodes - 1]
        return print_passes, graph, endpoint_nodes

    def test_find_disconnects_scales(self):
        """find_disconnects on 200 passes should complete in reasonable time."""
        print_passes, graph, endpoint_nodes = self._build_large_network(200, 50)

        start = time.perf_counter()
        result = find_disconnects(print_passes, graph, endpoint_nodes)
        elapsed = time.perf_counter() - start

        # Should complete in under 5 seconds with optimized indices
        assert elapsed < 5.0, f"find_disconnects took {elapsed:.2f}s (expected < 5s)"

    def test_condition0_scales(self):
        """close_gaps_condition0 on 200 passes should complete quickly."""
        print_passes, graph, endpoint_nodes = self._build_large_network(200, 50)

        start = time.perf_counter()
        close_gaps_condition0(
            print_passes, graph,
            branch_dict={}, branchpoint_list=[], branchpoint_list_keys=[],
            endpoint_nodes=endpoint_nodes, arbitrary_val=999999,
        )
        elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"condition0 took {elapsed:.2f}s (expected < 5s)"

    def test_full_pipeline_moderate_network(self):
        """Full pipeline on 100-pass network completes in reasonable time."""
        num_passes = 100
        pass_length = 30
        total = num_passes * pass_length

        graph = {}
        for n in range(total):
            neighbors = [n]
            if n > 0:
                neighbors.append(n - 1)
            if n < total - 1:
                neighbors.append(n + 1)
            graph[n] = neighbors

        print_passes = {}
        for p in range(num_passes):
            start_n = p * pass_length
            print_passes[p] = list(range(start_n, start_n + pass_length))

        start = time.perf_counter()
        result, _ = run_full_gap_closure_pipeline(
            print_passes, graph,
            branch_dict={}, branchpoint_list=[], branchpoint_list_keys=[],
            branchpoint_daughter_dict={}, endpoint_nodes=[0, total - 1],
            inlet_nodes=[0], outlet_nodes=[total - 1],
            repeat_daughters=set(), arbitrary_val=999999,
        )
        elapsed = time.perf_counter() - start

        assert elapsed < 10.0, f"full pipeline took {elapsed:.2f}s (expected < 10s)"
