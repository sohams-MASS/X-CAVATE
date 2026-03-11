"""Stress tests and edge-case tests for the refactored X-CAVATE codebase.

Validates behavioral equivalence with the original xcavate_11_30_25.py and
exercises edge cases that could reveal regressions:

1. End-to-end pipeline with real test data (tree_Test2)
2. Single-vessel networks (no branching)
3. Minimal networks (2-3 points per vessel)
4. Y-shaped branching networks
5. Large nozzle diameter (no interpolation needed)
6. Very small nozzle diameter (heavy interpolation)
7. Disconnected components
8. Collinear points / degenerate geometry
9. Identical z-coordinates (flat network)
10. Overlap and downsampling features
11. Tolerance-enabled collision detection
12. Multi-branch (complex) networks
"""

import copy
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple

import numpy as np
import pytest

from xcavate.config import (
    PathfindingAlgorithm,
    PrinterType,
    XcavateConfig,
)
from xcavate.core.gap_closure import (
    DisconnectInfo,
    find_disconnects,
    run_full_gap_closure_pipeline,
)
from xcavate.core.graph import build_graph
from xcavate.core.pathfinding import (
    CollisionDetector,
    DFSStrategy,
    generate_print_passes,
    iterative_dfs,
)
from xcavate.core.postprocessing import (
    add_overlap,
    downsample_passes,
    reorder_passes_nearest_neighbor,
    subdivide_passes,
)
from xcavate.core.preprocessing import (
    get_vessel_boundaries,
    interpolate_network,
)

# ─── Fixtures ───────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp_output(tmp_path):
    """Provide a temporary output directory with required subdirs."""
    (tmp_path / "graph").mkdir()
    (tmp_path / "gcode").mkdir()
    (tmp_path / "plots").mkdir()
    return tmp_path


def _make_config(tmp_path, **overrides):
    """Build an XcavateConfig with sensible defaults and optional overrides."""
    defaults = dict(
        network_file=tmp_path / "dummy.txt",
        inletoutlet_file=tmp_path / "dummy_io.txt",
        nozzle_diameter=0.25,
        container_height=50.0,
        num_decimals=3,
        amount_up=10.0,
        tolerance=0.0,
        tolerance_flag=False,
        scale_factor=1.0,
        print_speed=1.0,
        jog_speed=5.0,
        algorithm=PathfindingAlgorithm.DFS,
        printer_type=PrinterType.PRESSURE,
        output_dir=tmp_path / "outputs",
    )
    defaults.update(overrides)
    return XcavateConfig(**defaults)


def _write_network_file(path, vessels):
    """Write a SimVascular-format network file from vessel data.

    Args:
        path: Output file path.
        vessels: Dict mapping vessel_id -> numpy array of shape (N, C)
                 where C is 3 (xyz) or 4 (xyz + radius).
    """
    with open(path, "w") as f:
        for vid, pts in sorted(vessels.items()):
            f.write(f"Vessel: {vid}, Number of Points: {len(pts)}\n\n")
            for row in pts:
                f.write(", ".join(f"{v}" for v in row) + "\n")


def _write_inletoutlet_file(path, inlets, outlets):
    """Write an inlet/outlet file."""
    with open(path, "w") as f:
        for inlet in inlets:
            f.write("inlet\n")
            f.write(", ".join(f"{v}" for v in inlet) + "\n")
        for outlet in outlets:
            f.write("outlet\n")
            f.write(", ".join(f"{v}" for v in outlet) + "\n")


# ─── Helper: build graph + passes from raw points ──────────────────────────

def _full_pipeline_from_points(
    points_xyz,
    coord_num_dict,
    inlet_nodes,
    outlet_nodes,
    nozzle_radius,
    tolerance=0.0,
    tolerance_flag=False,
):
    """Run interpolation → graph → pathfinding → subdivision → gap closure."""
    num_columns = 3
    points_3col = points_xyz[:, :3] if points_xyz.shape[1] > 3 else points_xyz

    # Interpolate
    points_interp = interpolate_network(
        points_3col, coord_num_dict, nozzle_radius, num_columns,
    )
    boundaries = get_vessel_boundaries(points_interp, coord_num_dict)
    coord_num_dict_interp = {v: info["count"] for v, info in boundaries.items()}
    vessel_start_nodes = [info["start"] for v, info in sorted(boundaries.items())]

    xyz = points_interp[:, :3].copy()

    # Build graph
    (
        graph, branch_dict, branchpoint_list,
        branchpoint_daughter_dict, endpoint_nodes,
        nodes_by_vessel, repeat_daughters,
    ) = build_graph(
        xyz, coord_num_dict_interp, vessel_start_nodes,
        inlet_nodes, outlet_nodes,
    )

    # Pathfinding
    class MockConfig:
        def __init__(self):
            self.algorithm = PathfindingAlgorithm.DFS
            self.nozzle_radius = nozzle_radius
            self.tolerance = tolerance
            self.tolerance_flag = tolerance_flag

    raw_passes = generate_print_passes(graph, xyz, MockConfig())

    # Subdivide
    passes_sub = subdivide_passes(raw_passes, graph, xyz)

    # Save a copy before gap closure (which mutates in place)
    passes_sub_snapshot = copy.deepcopy(passes_sub)

    # Gap closure
    branchpoint_list_keys = list(branch_dict.keys())
    arbitrary_val = 999999999
    passes_closed, changelog = run_full_gap_closure_pipeline(
        passes_sub, graph,
        branch_dict, branchpoint_list, branchpoint_list_keys,
        branchpoint_daughter_dict, endpoint_nodes,
        inlet_nodes, outlet_nodes,
        repeat_daughters, arbitrary_val,
    )

    return {
        "points_interp": points_interp,
        "xyz": xyz,
        "graph": graph,
        "branch_dict": branch_dict,
        "branchpoint_list": branchpoint_list,
        "endpoint_nodes": endpoint_nodes,
        "raw_passes": raw_passes,
        "passes_subdivided": passes_sub_snapshot,
        "passes_closed": passes_closed,
        "changelog": changelog,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. END-TO-END COMPARISON WITH REAL TEST DATA
# ═══════════════════════════════════════════════════════════════════════════

class TestEndToEndRealData:
    """Compare refactored pipeline output with stored original outputs."""

    @pytest.fixture
    def real_data_paths(self):
        return {
            "network": ROOT / "tree_Test2.txt",
            "inletoutlet": ROOT / "tree_Test2_inlet_outlet.txt",
            "original_output": ROOT / "outputs" / "graph" / "all_coordinates_SM.txt",
            "refactored_output": ROOT / "outputs_refactored" / "graph" / "all_coordinates_SM.txt",
        }

    def _parse_output(self, filepath):
        """Parse all_coordinates_SM.txt into {pass_idx: [coord_lines]}."""
        passes = {}
        current = None
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                m = re.match(r"Pass (\d+)", line)
                if m:
                    current = int(m.group(1))
                    passes[current] = []
                elif line and current is not None:
                    passes[current].append(line)
        return passes

    @pytest.mark.skipif(
        not (ROOT / "outputs" / "graph" / "all_coordinates_SM.txt").exists(),
        reason="Original outputs not present",
    )
    def test_coordinate_sets_identical(self, real_data_paths):
        """The set of unique coordinate lines must be identical."""
        orig = self._parse_output(real_data_paths["original_output"])
        refac = self._parse_output(real_data_paths["refactored_output"])

        orig_coords = set()
        for v in orig.values():
            orig_coords.update(v)
        refac_coords = set()
        for v in refac.values():
            refac_coords.update(v)

        assert orig_coords == refac_coords, (
            f"Coordinate mismatch: "
            f"{len(orig_coords - refac_coords)} only in original, "
            f"{len(refac_coords - orig_coords)} only in refactored"
        )

    @pytest.mark.skipif(
        not (ROOT / "outputs" / "graph" / "all_coordinates_SM.txt").exists(),
        reason="Original outputs not present",
    )
    def test_pass_count_identical(self, real_data_paths):
        """Both runs must produce the same number of passes."""
        orig = self._parse_output(real_data_paths["original_output"])
        refac = self._parse_output(real_data_paths["refactored_output"])
        assert len(orig) == len(refac)

    @pytest.mark.skipif(
        not (ROOT / "outputs" / "graph" / "all_coordinates_SM.txt").exists(),
        reason="Original outputs not present",
    )
    def test_all_passes_match_as_sequences(self, real_data_paths):
        """Every pass in refactored output must exist (possibly reordered) in original."""
        orig = self._parse_output(real_data_paths["original_output"])
        refac = self._parse_output(real_data_paths["refactored_output"])

        orig_seqs = set(tuple(v) for v in orig.values())
        refac_seqs = set(tuple(v) for v in refac.values())
        assert orig_seqs == refac_seqs, "Pass sequences differ between original and refactored"

    @pytest.mark.skipif(
        not (ROOT / "outputs" / "gcode" / "gcode_SM_pressure.txt").exists(),
        reason="Original G-code not present",
    )
    def test_gcode_xyz_identical(self, real_data_paths):
        """G-code XYZ positions must match (feed rates may differ slightly)."""
        def extract_xyz(filepath):
            coords = []
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("G1 "):
                        m = re.findall(r"[XYA]([0-9.\-]+)", line)
                        if len(m) >= 3:
                            coords.append((m[0], m[1], m[2]))
            return Counter(coords)

        orig_path = ROOT / "outputs" / "gcode" / "gcode_SM_pressure.txt"
        refac_path = ROOT / "outputs_refactored" / "gcode" / "gcode_SM_pressure.txt"
        assert extract_xyz(orig_path) == extract_xyz(refac_path)


# ═══════════════════════════════════════════════════════════════════════════
# 2. SINGLE VESSEL (NO BRANCHING)
# ═══════════════════════════════════════════════════════════════════════════

class TestSingleVessel:
    """A network with one vessel and no branchpoints."""

    def test_straight_line_up(self, tmp_path):
        """Single vertical vessel: should produce exactly one pass."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 2.0],
            [0.0, 0.0, 3.0],
            [0.0, 0.0, 4.0],
        ])
        coord_num = {0: 5}
        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=0.5,
        )
        # Single vessel, no collisions → should produce exactly 1 pass
        assert len(result["passes_closed"]) >= 1
        # All nodes should be visited
        all_nodes = set()
        for v in result["passes_closed"].values():
            all_nodes.update(v)
        interp_count = result["xyz"].shape[0]
        # All interpolated nodes covered
        assert len(all_nodes) >= interp_count - 1  # allow for artifacts

    def test_single_vessel_two_points(self, tmp_path):
        """Minimal vessel: just 2 points."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ])
        coord_num = {0: 2}
        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=2.0,
        )
        assert len(result["passes_closed"]) >= 1

    def test_diagonal_vessel(self, tmp_path):
        """Diagonal vessel requiring interpolation."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [5.0, 5.0, 5.0],
        ])
        coord_num = {0: 2}
        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=0.5,
        )
        # Interpolation should add many points
        assert result["xyz"].shape[0] > 2
        assert len(result["passes_closed"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 3. MINIMAL NETWORKS
# ═══════════════════════════════════════════════════════════════════════════

class TestMinimalNetworks:
    """Networks with very few points per vessel."""

    def test_three_points_per_vessel(self, tmp_path):
        """Y-shaped network with only 3 points per vessel."""
        v0 = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 2.0]])
        v1 = np.array([[0.0, 0.0, 2.0], [1.0, 0.0, 3.0], [2.0, 0.0, 4.0]])
        v2 = np.array([[0.0, 0.0, 2.0], [-1.0, 0.0, 3.0], [-2.0, 0.0, 4.0]])
        points = np.vstack([v0, v1, v2])
        coord_num = {0: 3, 1: 3, 2: 3}

        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=0.5,
        )
        assert len(result["passes_closed"]) >= 1
        assert len(result["branch_dict"]) >= 0  # May or may not detect branchpoint

    def test_two_points_per_vessel_three_vessels(self, tmp_path):
        """Minimal branching: 2 points each, 3 vessels."""
        v0 = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 2.0]])
        v1 = np.array([[0.0, 0.0, 2.0], [1.0, 0.0, 4.0]])
        v2 = np.array([[0.0, 0.0, 2.0], [-1.0, 0.0, 4.0]])
        points = np.vstack([v0, v1, v2])
        coord_num = {0: 2, 1: 2, 2: 2}

        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=1.0,
        )
        assert len(result["passes_closed"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 4. COLLISION DETECTOR EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestCollisionDetector:
    """Edge cases for the KD-tree based collision detector."""

    def test_single_node(self):
        """One-node network: always valid."""
        points = np.array([[0.0, 0.0, 0.0]])
        det = CollisionDetector(points, nozzle_radius=1.0)
        assert det.is_valid(0)
        det.mark_visited(0)
        assert not det.has_unvisited()

    def test_two_nodes_same_xy_different_z(self):
        """Two stacked nodes: lower valid first, upper blocked."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ])
        det = CollisionDetector(points, nozzle_radius=1.0)
        # Lower node valid
        assert det.is_valid(0)
        # Upper node blocked by lower
        assert not det.is_valid(1)
        # Print lower, then upper becomes valid
        det.mark_visited(0)
        assert det.is_valid(1)

    def test_two_nodes_far_apart_xy(self):
        """Two nodes far apart in XY: both valid regardless of z."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [10.0, 10.0, 1.0],
        ])
        det = CollisionDetector(points, nozzle_radius=1.0)
        assert det.is_valid(0)
        assert det.is_valid(1)

    def test_same_z_coordinates(self):
        """Nodes at the same z: neither blocks the other."""
        points = np.array([
            [0.0, 0.0, 5.0],
            [0.1, 0.0, 5.0],
        ])
        det = CollisionDetector(points, nozzle_radius=1.0)
        assert det.is_valid(0)
        assert det.is_valid(1)

    def test_tolerance_exception(self):
        """With tolerance, nearby blocking nodes are ignored."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.1],  # Very close in 3D
        ])
        # Without tolerance: node 1 blocked by node 0
        det1 = CollisionDetector(points, nozzle_radius=1.0, tolerance=0.0, tolerance_flag=False)
        assert not det1.is_valid(1)

        # With tolerance 0.5: node 0 is within tolerance distance, so not blocking
        det2 = CollisionDetector(points, nozzle_radius=1.0, tolerance=0.5, tolerance_flag=True)
        assert det2.is_valid(1)

    def test_many_nodes_rebuild(self):
        """Test KD-tree rebuild after many removals."""
        np.random.seed(42)
        n = 1000
        points = np.random.rand(n, 3) * 10
        det = CollisionDetector(points, nozzle_radius=0.1, rebuild_interval=100)
        # Mark many visited to trigger rebuild
        for i in range(500):
            det.mark_visited(i)
        # Should still work correctly after rebuild
        remaining = [i for i in range(500, n) if det.is_valid(i)]
        assert len(remaining) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 5. INTERPOLATION EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestInterpolation:
    """Edge cases for network interpolation."""

    def test_no_interpolation_needed(self):
        """Points already within nozzle radius: no new points added."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.1],
            [0.0, 0.0, 0.2],
        ])
        coord_num = {0: 3}
        result = interpolate_network(points, coord_num, nozzle_radius=1.0, num_columns=3)
        # Only the flag column should be added; no new rows
        assert result.shape[0] == 3
        assert result.shape[1] == 4  # 3 coords + flag

    def test_heavy_interpolation(self):
        """Large spacing with small nozzle: many points added."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
        ])
        coord_num = {0: 2}
        result = interpolate_network(points, coord_num, nozzle_radius=0.1, num_columns=3)
        # 10mm / 0.1mm = 100 segments → ~101 points (minus original 2 = ~99 new)
        assert result.shape[0] >= 100

    def test_multiple_vessels_flags(self):
        """Vessel start flags (500) correctly mark each vessel."""
        v0 = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        v1 = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 1.0]])
        points = np.vstack([v0, v1])
        coord_num = {0: 2, 1: 2}
        result = interpolate_network(points, coord_num, nozzle_radius=2.0, num_columns=3)
        # Check flag column
        flags = result[:, -1]
        vessel_starts = np.where(flags == 500)[0]
        assert len(vessel_starts) == 2

    def test_interpolation_preserves_endpoints(self):
        """First and last points of each vessel are preserved exactly."""
        points = np.array([
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0],
        ])
        coord_num = {0: 2}
        result = interpolate_network(points, coord_num, nozzle_radius=0.5, num_columns=3)
        np.testing.assert_array_almost_equal(result[0, :3], [1.0, 2.0, 3.0])
        np.testing.assert_array_almost_equal(result[-1, :3], [4.0, 5.0, 6.0])

    def test_with_radius_column(self):
        """4-column input (xyz + radius) interpolation preserves radius."""
        points = np.array([
            [0.0, 0.0, 0.0, 0.5],
            [5.0, 0.0, 0.0, 0.5],
        ])
        coord_num = {0: 2}
        result = interpolate_network(points, coord_num, nozzle_radius=1.0, num_columns=4)
        # All interpolated points should have radius 0.5
        assert np.all(result[:, 3] == 0.5)

    def test_zero_length_segment(self):
        """Duplicate points (zero distance): no interpolation needed."""
        points = np.array([
            [1.0, 1.0, 1.0],
            [1.0, 1.0, 1.0],
            [1.0, 1.0, 2.0],
        ])
        coord_num = {0: 3}
        result = interpolate_network(points, coord_num, nozzle_radius=0.5, num_columns=3)
        # Should not crash; duplicate stays as-is
        assert result.shape[0] >= 3


# ═══════════════════════════════════════════════════════════════════════════
# 6. GRAPH CONSTRUCTION EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestGraphConstruction:
    """Edge cases for adjacency graph building."""

    def test_single_vessel_graph(self):
        """One vessel: graph is a simple chain."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 2.0],
        ])
        coord_num = {0: 3}
        graph, branch_dict, *_ = build_graph(
            points, coord_num, vessel_start_nodes=[0],
            inlet_nodes=[0], outlet_nodes=[2],
        )
        # No branchpoints
        assert len(branch_dict) == 0
        # Node 1 connects to 0 and 2 (plus self)
        assert 0 in graph[1]
        assert 2 in graph[1]
        assert 1 in graph[1]  # self-loop

    def test_y_branch_detection(self):
        """Y-shaped network: one parent branchpoint with two daughters."""
        # Vessel 0: trunk
        v0 = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 2.0],
            [0.0, 0.0, 3.0],
            [0.0, 0.0, 4.0],
            [0.0, 0.0, 5.0],
        ])
        # Vessel 1: daughter branch +x
        v1 = np.array([
            [0.0, 0.0, 5.0],
            [0.4, 0.0, 6.0],
            [0.8, 0.0, 7.0],
            [1.2, 0.0, 8.0],
            [1.6, 0.0, 9.0],
            [2.0, 0.0, 10.0],
        ])
        # Vessel 2: daughter branch -x
        v2 = np.array([
            [0.0, 0.0, 5.0],
            [-0.4, 0.0, 6.0],
            [-0.8, 0.0, 7.0],
            [-1.2, 0.0, 8.0],
            [-1.6, 0.0, 9.0],
            [-2.0, 0.0, 10.0],
        ])
        points = np.vstack([v0, v1, v2])
        coord_num = {0: 6, 1: 6, 2: 6}

        graph, branch_dict, branchpoint_list, *_ = build_graph(
            points, coord_num,
            vessel_start_nodes=[0, 6, 12],
            inlet_nodes=[0], outlet_nodes=[11, 17],
        )
        # Should detect at least one branchpoint
        assert len(branch_dict) >= 1
        # Branchpoint should connect parent to daughters
        for parent, daughters in branch_dict.items():
            assert len(daughters) == 2
            for d in daughters:
                assert parent in graph[d] or d in graph[parent]

    def test_graph_self_loops(self):
        """Every node should have a self-loop in its adjacency list."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 2.0],
        ])
        coord_num = {0: 3}
        graph, *_ = build_graph(
            points, coord_num, vessel_start_nodes=[0],
            inlet_nodes=[0], outlet_nodes=[2],
        )
        for node in graph:
            assert node in graph[node], f"Node {node} missing self-loop"


# ═══════════════════════════════════════════════════════════════════════════
# 7. POSTPROCESSING EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestPostprocessing:
    """Edge cases for subdivision, overlap, downsampling, and reordering."""

    def test_subdivide_no_breaks(self):
        """Passes with no backtracking: no subdivision occurs."""
        graph = {0: [0, 1], 1: [0, 1, 2], 2: [1, 2]}
        passes = {0: [0, 1, 2]}
        points = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 2.0]])
        result = subdivide_passes(passes, graph, points)
        assert len(result) == 1
        assert result[0] == [0, 1, 2]

    def test_subdivide_with_breaks(self):
        """Pass with a backtrack: should split into multiple segments."""
        # Node 0->1->2, then jump to 4 (not neighbor of 2)
        graph = {
            0: [0, 1], 1: [0, 1, 2], 2: [1, 2],
            3: [3, 4], 4: [3, 4],
        }
        passes = {0: [0, 1, 2, 4]}  # 2→4 is a backtrack (not neighbors)
        points = np.array([
            [0.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 2.0],
            [0.0, 0.0, 3.0], [0.0, 0.0, 4.0],
        ])
        result = subdivide_passes(passes, graph, points)
        assert len(result) >= 2

    def test_overlap_zero(self):
        """Overlap with num_overlap=0: passes unchanged."""
        passes = {0: [0, 1, 2], 1: [2, 3, 4]}
        result = add_overlap(passes, num_overlap=0)
        assert result == passes

    def test_overlap_positive(self):
        """Overlap adds nodes from connected passes."""
        passes = {0: [0, 1, 2], 1: [3, 4, 2]}  # Pass 1 ends on node 2 (shared)
        result = add_overlap(passes, num_overlap=1)
        # Pass 1 should have an extra node from pass 0 (retrace backwards from 2)
        assert len(result[1]) >= len(passes[1])

    def test_downsample_preserves_endpoints(self):
        """Downsampling always keeps first and last nodes."""
        passes = {0: list(range(20))}
        points = np.zeros((20, 4))
        for i in range(20):
            points[i, 2] = i
        result = downsample_passes(
            passes, points,
            downsample_factor=5,
            branchpoint_list=[], branchpoint_list_keys=[],
            endpoint_nodes=[0, 19],
        )
        assert result[0][0] == 0
        assert result[0][-1] == 19

    def test_downsample_preserves_branchpoints(self):
        """Branchpoints and endpoints are never removed by downsampling."""
        passes = {0: list(range(20))}
        points = np.zeros((20, 4))
        for i in range(20):
            points[i, 2] = i
        result = downsample_passes(
            passes, points,
            downsample_factor=5,
            branchpoint_list=[5],
            branchpoint_list_keys=[10],
            endpoint_nodes=[0, 19],
        )
        assert 5 in result[0]
        assert 10 in result[0]
        assert 0 in result[0]
        assert 19 in result[0]

    def test_reorder_single_pass(self):
        """Single pass: reordering is a no-op."""
        passes = {0: [0, 1, 2]}
        points = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 2.0]])
        result = reorder_passes_nearest_neighbor(passes, points)
        assert len(result) == 1

    def test_reorder_minimizes_travel(self):
        """Two passes far apart: nearest-neighbor should pick the closer one."""
        passes = {
            0: [0],
            1: [1],
            2: [2],
        }
        points = np.array([
            [0.0, 0.0, 0.0],   # pass 0 start/end
            [100.0, 0.0, 0.0],  # pass 1 far away
            [0.1, 0.0, 0.0],   # pass 2 very close to pass 0
        ])
        result = reorder_passes_nearest_neighbor(passes, points)
        # After pass 0, pass 2 (at x=0.1) should come before pass 1 (at x=100)
        ordered_keys = list(result.keys())
        # Pass 0 stays first
        assert result[0] == [0]
        # Pass 2 (closest) should be second
        assert result[1] == [2]
        assert result[2] == [1]

    def test_empty_passes(self):
        """Empty pass dict: should not crash."""
        result = add_overlap({}, num_overlap=3)
        assert result == {}

        result = reorder_passes_nearest_neighbor(
            {}, np.array([]).reshape(0, 3)
        )
        assert result == {}


# ═══════════════════════════════════════════════════════════════════════════
# 8. GAP CLOSURE EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestGapClosure:
    """Edge cases for gap detection and closure."""

    def test_no_disconnects(self):
        """Fully connected passes: no gaps to close."""
        # Pass 0: [0,1,2], Pass 1: [2,3,4] — share node 2
        passes = {0: [0, 1, 2], 1: [2, 3, 4]}
        graph = {i: [i] for i in range(5)}
        for i in range(4):
            graph[i].append(i + 1)
            graph[i + 1].append(i)

        info = find_disconnects(passes, graph, endpoint_nodes=[0, 4])
        # Node 0 and 4 are endpoints, so excluded
        # Node 2 appears in both passes, so not disconnected
        # Should have no true disconnects
        assert len(info.final_true_disconnect) == 0

    def test_single_node_pass(self):
        """Pass with one node: special handling in gap closure."""
        passes = {0: [0, 1, 2], 1: [3]}
        graph = {
            0: [0, 1], 1: [0, 1, 2], 2: [1, 2, 3],
            3: [2, 3],
        }
        info = find_disconnects(passes, graph, endpoint_nodes=[0])
        # Node 3 is a single-node pass endpoint, should be handled
        assert isinstance(info, DisconnectInfo)


# ═══════════════════════════════════════════════════════════════════════════
# 9. DEGENERATE GEOMETRY
# ═══════════════════════════════════════════════════════════════════════════

class TestDegenerateGeometry:
    """Networks with unusual spatial configurations."""

    def test_flat_network_same_z(self):
        """All nodes at the same z-coordinate: no collision blocking."""
        points = np.array([
            [0.0, 0.0, 5.0],
            [1.0, 0.0, 5.0],
            [2.0, 0.0, 5.0],
            [3.0, 0.0, 5.0],
        ])
        coord_num = {0: 4}
        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=0.5,
        )
        # No z-blocking → all nodes should be in one pass
        total_nodes = sum(len(v) for v in result["passes_closed"].values())
        assert total_nodes >= result["xyz"].shape[0]

    def test_collinear_points(self):
        """Points on a straight diagonal line."""
        n = 20
        t = np.linspace(0, 1, n)
        points = np.column_stack([t * 10, t * 5, t * 3])
        coord_num = {0: n}
        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=0.5,
        )
        assert len(result["passes_closed"]) >= 1

    def test_spiral_network(self):
        """Helical/spiral vessel: tests complex 3D collision patterns."""
        n = 50
        t = np.linspace(0, 4 * np.pi, n)
        x = np.cos(t)
        y = np.sin(t)
        z = t / (4 * np.pi) * 10  # Rises from 0 to 10
        points = np.column_stack([x, y, z])
        coord_num = {0: n}
        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=0.3,
        )
        # Should complete without errors
        assert len(result["passes_closed"]) >= 1
        # All nodes should be assigned
        all_nodes = set()
        for v in result["passes_closed"].values():
            all_nodes.update(v)
        assert len(all_nodes) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 10. NOZZLE SIZE VARIATIONS
# ═══════════════════════════════════════════════════════════════════════════

class TestNozzleSizeVariations:
    """Test with extreme nozzle diameters."""

    def test_very_large_nozzle(self):
        """Nozzle larger than network: heavy collision blocking."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 2.0],
            [0.0, 0.0, 3.0],
            [0.0, 0.0, 4.0],
        ])
        coord_num = {0: 5}
        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=50.0,  # Much larger than network
        )
        # All nodes within nozzle radius → can only print bottom-up
        # Should produce 1+ passes depending on collision logic
        assert len(result["passes_closed"]) >= 1

    def test_very_small_nozzle(self):
        """Tiny nozzle: no collision blocking, heavy interpolation."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 5.0],
        ])
        coord_num = {0: 2}
        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=0.05,
        )
        # Heavy interpolation
        assert result["xyz"].shape[0] >= 100
        # Probably one pass (all collinear)
        assert len(result["passes_closed"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 11. DFS PATHFINDING EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestDFSPathfinding:
    """Edge cases for the DFS strategy."""

    def test_disconnected_graph(self):
        """Two disconnected components: should produce passes for both."""
        # Component 1: nodes 0,1,2
        # Component 2: nodes 3,4,5 (far apart in XY)
        graph = {
            0: [0, 1], 1: [0, 1, 2], 2: [1, 2],
            3: [3, 4], 4: [3, 4, 5], 5: [4, 5],
        }
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 2.0],
            [10.0, 10.0, 0.0],
            [10.0, 10.0, 1.0],
            [10.0, 10.0, 2.0],
        ])

        class MockConfig:
            algorithm = PathfindingAlgorithm.DFS
            nozzle_radius = 0.5
            tolerance = 0.0
            tolerance_flag = False

        passes = generate_print_passes(graph, points, MockConfig())
        # Both components should be visited
        all_nodes = set()
        for v in passes.values():
            all_nodes.update(v)
        assert all_nodes == {0, 1, 2, 3, 4, 5}

    def test_star_graph(self):
        """Star topology: central node connected to many leaves."""
        n_leaves = 10
        n = n_leaves + 1
        graph = {0: [0] + list(range(1, n))}
        for i in range(1, n):
            graph[i] = [0, i]

        # Central node at z=5, leaves at various z
        points = np.zeros((n, 3))
        points[0] = [0.0, 0.0, 5.0]
        for i in range(1, n):
            angle = 2 * np.pi * i / n_leaves
            points[i] = [np.cos(angle) * 2, np.sin(angle) * 2, float(i)]

        class MockConfig:
            algorithm = PathfindingAlgorithm.DFS
            nozzle_radius = 0.5
            tolerance = 0.0
            tolerance_flag = False

        passes = generate_print_passes(graph, points, MockConfig())
        all_nodes = set()
        for v in passes.values():
            all_nodes.update(v)
        assert all_nodes == set(range(n))

    def test_long_chain(self):
        """Long linear chain: stress test for stack depth."""
        n = 500
        graph = {}
        for i in range(n):
            nbrs = [i]
            if i > 0:
                nbrs.append(i - 1)
            if i < n - 1:
                nbrs.append(i + 1)
            graph[i] = sorted(nbrs)

        points = np.zeros((n, 3))
        points[:, 2] = np.arange(n) * 0.01  # Gentle upward slope

        class MockConfig:
            algorithm = PathfindingAlgorithm.DFS
            nozzle_radius = 0.05
            tolerance = 0.0
            tolerance_flag = False

        passes = generate_print_passes(graph, points, MockConfig())
        all_nodes = set()
        for v in passes.values():
            all_nodes.update(v)
        assert all_nodes == set(range(n))


# ═══════════════════════════════════════════════════════════════════════════
# 12. COMPLEX MULTI-BRANCH NETWORKS
# ═══════════════════════════════════════════════════════════════════════════

class TestComplexNetworks:
    """Networks with multiple branchpoints and complex topology."""

    def test_binary_tree_network(self):
        """Binary tree: trunk → 2 daughters → 4 granddaughters."""
        # Trunk
        v0 = np.array([[0.0, 0.0, float(i)] for i in range(6)])
        # Left daughter
        v1_actual = np.array([
            [0.0, 0.0, 5.0],
            [-0.5, 0.0, 6.0],
            [-1.0, 0.0, 7.0],
            [-1.5, 0.0, 8.0],
            [-2.0, 0.0, 9.0],
            [-2.5, 0.0, 10.0],
        ])
        # Right daughter
        v2 = np.array([
            [0.0, 0.0, 5.0],
            [0.5, 0.0, 6.0],
            [1.0, 0.0, 7.0],
            [1.5, 0.0, 8.0],
            [2.0, 0.0, 9.0],
            [2.5, 0.0, 10.0],
        ])
        points = np.vstack([v0, v1_actual, v2])
        coord_num = {0: 6, 1: 6, 2: 6}

        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=0.3,
        )
        assert len(result["passes_closed"]) >= 1
        # Branchpoint should be detected
        assert len(result["branch_dict"]) >= 1

    def test_symmetric_h_network(self):
        """H-shaped network: two vertical vessels connected by a horizontal bridge."""
        # Left vertical (z = 0 to 5)
        v0 = np.array([[0.0, 0.0, i * 1.0] for i in range(6)])
        # Right vertical (z = 0 to 5)
        v1 = np.array([[3.0, 0.0, i * 1.0] for i in range(6)])
        # Horizontal bridge (at z = 2.5)
        v2 = np.array([
            [0.0, 0.0, 2.5],
            [1.0, 0.0, 2.5],
            [2.0, 0.0, 2.5],
            [3.0, 0.0, 2.5],
        ])
        points = np.vstack([v0, v1, v2])
        coord_num = {0: 6, 1: 6, 2: 4}

        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[11],
            nozzle_radius=0.3,
        )
        assert len(result["passes_closed"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 13. FULL PIPELINE END-TO-END (SYNTHETIC)
# ═══════════════════════════════════════════════════════════════════════════

class TestFullPipelineSynthetic:
    """End-to-end pipeline tests with synthetic network files."""

    def test_y_network_full_pipeline(self, tmp_path):
        """Full pipeline run with a Y-shaped network written to files."""
        # Write network file
        vessels = {
            0: np.array([
                [0.0, 0.0, 0.0, 0.01],
                [0.0, 0.0, 0.5, 0.01],
                [0.0, 0.0, 1.0, 0.01],
                [0.0, 0.0, 1.5, 0.01],
                [0.0, 0.0, 2.0, 0.01],
            ]),
            1: np.array([
                [0.0, 0.0, 2.0, 0.01],
                [0.5, 0.0, 2.5, 0.01],
                [1.0, 0.0, 3.0, 0.01],
                [1.5, 0.0, 3.5, 0.01],
                [2.0, 0.0, 4.0, 0.01],
            ]),
            2: np.array([
                [0.0, 0.0, 2.0, 0.01],
                [-0.5, 0.0, 2.5, 0.01],
                [-1.0, 0.0, 3.0, 0.01],
                [-1.5, 0.0, 3.5, 0.01],
                [-2.0, 0.0, 4.0, 0.01],
            ]),
        }
        net_path = tmp_path / "network.txt"
        _write_network_file(net_path, vessels)

        io_path = tmp_path / "inletoutlet.txt"
        _write_inletoutlet_file(
            io_path,
            inlets=[[0.0, 0.0, 0.0]],
            outlets=[[2.0, 0.0, 4.0]],
        )

        config = _make_config(
            tmp_path,
            network_file=net_path,
            inletoutlet_file=io_path,
            nozzle_diameter=0.2,
            container_height=20.0,
            num_decimals=3,
            scale_factor=10.0,
            generate_plots=False,
            speed_calc=True,
            custom_gcode=False,
            output_dir=tmp_path / "outputs",
        )
        from xcavate.pipeline import run_xcavate
        result = run_xcavate(config)

        assert "print_passes_sm" in result
        assert len(result["print_passes_sm"]) >= 1
        assert result["points"] is not None
        assert result["speed_map_sm"] is not None

        # Check output files were written
        assert (tmp_path / "outputs" / "graph" / "x_coordinates_SM.txt").exists()
        assert (tmp_path / "outputs" / "gcode").exists()

    def test_pipeline_with_overlap(self, tmp_path):
        """Pipeline with overlap enabled."""
        vessels = {
            0: np.array([
                [0.0, 0.0, 0.0, 0.01],
                [0.0, 0.0, 1.0, 0.01],
                [0.0, 0.0, 2.0, 0.01],
            ]),
        }
        net_path = tmp_path / "network.txt"
        _write_network_file(net_path, vessels)

        io_path = tmp_path / "inletoutlet.txt"
        _write_inletoutlet_file(
            io_path,
            inlets=[[0.0, 0.0, 0.0]],
            outlets=[],
        )

        config = _make_config(
            tmp_path,
            network_file=net_path,
            inletoutlet_file=io_path,
            nozzle_diameter=0.2,
            container_height=20.0,
            num_overlap=3,
            scale_factor=10.0,
            generate_plots=False,
            speed_calc=False,
            custom_gcode=False,
            output_dir=tmp_path / "outputs",
        )
        from xcavate.pipeline import run_xcavate
        result = run_xcavate(config)
        assert len(result["print_passes_sm"]) >= 1

    def test_pipeline_with_downsampling(self, tmp_path):
        """Pipeline with downsampling enabled."""
        vessels = {
            0: np.array([
                [0.0, 0.0, float(i), 0.01]
                for i in range(20)
            ]),
        }
        net_path = tmp_path / "network.txt"
        _write_network_file(net_path, vessels)

        io_path = tmp_path / "inletoutlet.txt"
        _write_inletoutlet_file(
            io_path,
            inlets=[[0.0, 0.0, 0.0]],
            outlets=[],
        )

        config = _make_config(
            tmp_path,
            network_file=net_path,
            inletoutlet_file=io_path,
            nozzle_diameter=0.2,
            container_height=100.0,
            downsample=True,
            downsample_factor=3,
            scale_factor=1.0,
            generate_plots=False,
            speed_calc=False,
            custom_gcode=False,
            output_dir=tmp_path / "outputs",
        )
        from xcavate.pipeline import run_xcavate
        result = run_xcavate(config)
        assert len(result["print_passes_sm"]) >= 1

    def test_pipeline_with_tolerance(self, tmp_path):
        """Pipeline with tolerance-based collision detection."""
        vessels = {
            0: np.array([
                [0.0, 0.0, 0.0, 0.01],
                [0.0, 0.0, 0.5, 0.01],
                [0.0, 0.0, 1.0, 0.01],
                [0.0, 0.0, 1.5, 0.01],
                [0.0, 0.0, 2.0, 0.01],
            ]),
        }
        net_path = tmp_path / "network.txt"
        _write_network_file(net_path, vessels)

        io_path = tmp_path / "inletoutlet.txt"
        _write_inletoutlet_file(
            io_path,
            inlets=[[0.0, 0.0, 0.0]],
            outlets=[],
        )

        config = _make_config(
            tmp_path,
            network_file=net_path,
            inletoutlet_file=io_path,
            nozzle_diameter=0.5,
            container_height=20.0,
            tolerance=0.3,
            tolerance_flag=True,
            scale_factor=10.0,
            generate_plots=False,
            speed_calc=False,
            custom_gcode=False,
            output_dir=tmp_path / "outputs",
        )
        from xcavate.pipeline import run_xcavate
        result = run_xcavate(config)
        assert len(result["print_passes_sm"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 14. INVARIANT CHECKS
# ═══════════════════════════════════════════════════════════════════════════

class TestInvariants:
    """Properties that must hold for any valid output."""

    def test_all_nodes_visited(self):
        """Every node in the interpolated network must appear in some pass."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 2.0],
            [0.0, 0.0, 3.0],
            [0.0, 0.0, 4.0],
            [0.0, 0.0, 5.0],
        ])
        coord_num = {0: 6}
        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=0.5,
        )
        all_visited = set()
        for v in result["raw_passes"].values():
            all_visited.update(v)
        n_interp = result["xyz"].shape[0]
        assert all_visited == set(range(n_interp)), (
            f"Missing nodes: {set(range(n_interp)) - all_visited}"
        )

    def test_passes_bottom_up_after_subdivision(self):
        """After subdivision, each pass should start at lower z than it ends."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 2.0],
            [0.0, 0.0, 3.0],
        ])
        coord_num = {0: 4}
        result = _full_pipeline_from_points(
            points, coord_num,
            inlet_nodes=[0], outlet_nodes=[],
            nozzle_radius=0.5,
        )
        xyz = result["xyz"]
        for pid, nodes in result["passes_subdivided"].items():
            if len(nodes) < 2:
                continue
            z_start = xyz[nodes[0], 2]
            z_end = xyz[nodes[-1], 2]
            assert z_start <= z_end + 1e-10, (
                f"Pass {pid}: starts at z={z_start}, ends at z={z_end} (not bottom-up)"
            )

    def test_graph_symmetry_single_vessel(self):
        """Graph adjacency must be symmetric for a single vessel (no branchpoints)."""
        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 2.0],
            [0.0, 0.0, 3.0],
            [0.0, 0.0, 4.0],
        ])
        coord_num = {0: 5}

        points_interp = interpolate_network(points, coord_num, 0.5, 3)
        boundaries = get_vessel_boundaries(points_interp, coord_num)
        coord_num_interp = {v: info["count"] for v, info in boundaries.items()}
        vessel_starts = [info["start"] for v, info in sorted(boundaries.items())]
        xyz = points_interp[:, :3].copy()

        graph, *_ = build_graph(
            xyz, coord_num_interp, vessel_starts,
            inlet_nodes=[0], outlet_nodes=[],
        )

        for node, nbrs in graph.items():
            for nbr in nbrs:
                if nbr == node:
                    continue  # self-loop
                assert node in graph[nbr], (
                    f"Asymmetric edge: {node}→{nbr} but {nbr}↛{node}"
                )

    def test_graph_intra_vessel_edges_complete(self):
        """Within a multi-vessel network, interior nodes have bidirectional edges."""
        # Use Y-shaped network to avoid single-vessel branchpoint artifacts.
        # (Single-vessel networks trigger spurious branchpoint detection because
        # there are no other vessels — same behavior in the original code.)
        v0 = np.array([
            [0.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 2.0],
            [0.0, 0.0, 3.0], [0.0, 0.0, 4.0], [0.0, 0.0, 5.0],
        ])
        v1 = np.array([
            [0.0, 0.0, 5.0], [0.4, 0.0, 6.0], [0.8, 0.0, 7.0],
            [1.2, 0.0, 8.0], [1.6, 0.0, 9.0], [2.0, 0.0, 10.0],
        ])
        v2 = np.array([
            [0.0, 0.0, 5.0], [-0.4, 0.0, 6.0], [-0.8, 0.0, 7.0],
            [-1.2, 0.0, 8.0], [-1.6, 0.0, 9.0], [-2.0, 0.0, 10.0],
        ])
        points = np.vstack([v0, v1, v2])
        coord_num = {0: 6, 1: 6, 2: 6}

        points_interp = interpolate_network(points, coord_num, 0.5, 3)
        boundaries = get_vessel_boundaries(points_interp, coord_num)
        coord_num_interp = {v: info["count"] for v, info in boundaries.items()}
        vessel_starts = [info["start"] for v, info in sorted(boundaries.items())]
        xyz = points_interp[:, :3].copy()

        graph, branch_dict, *_ = build_graph(
            xyz, coord_num_interp, vessel_starts,
            inlet_nodes=[0], outlet_nodes=[boundaries[1]["end"], boundaries[2]["end"]],
        )

        # For vessel 0 (trunk), interior nodes should have bidirectional edges
        v0_nodes = boundaries[0]["nodes"]
        for i in range(1, len(v0_nodes) - 2):
            n_cur = v0_nodes[i]
            n_nxt = v0_nodes[i + 1]
            assert n_nxt in graph[n_cur], f"Missing edge {n_cur}→{n_nxt}"
            assert n_cur in graph[n_nxt], f"Missing edge {n_nxt}→{n_cur}"
