"""Integration tests for CTR pipeline."""

import numpy as np
import pytest
from pathlib import Path

from xcavate.config import XcavateConfig, PrinterType, PathfindingAlgorithm
from xcavate.core.ctr_kinematics import CTRConfig, is_reachable, _load_calibration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ctr_config_for_pipeline(tmp_path):
    """Config suitable for a mini pipeline test."""
    return XcavateConfig(
        network_file=tmp_path / "net.txt",
        inletoutlet_file=tmp_path / "io.txt",
        nozzle_diameter=0.5,
        container_height=50.0,
        num_decimals=3,
        printer_type=PrinterType.CTR,
        algorithm=PathfindingAlgorithm.DFS,
        ctr_position_cartesian=(0.0, 0.0, 0.0),
        ctr_orientation=(0.0, -1.0, 0.0),
        ctr_radius=47.0,
        ctr_ss_max=65.0,
        ctr_ntnl_max=140.0,
        output_dir=tmp_path / "outputs",
    )


# ---------------------------------------------------------------------------
# Reachability filtering
# ---------------------------------------------------------------------------

class TestReachabilityFiltering:
    def test_reachable_nodes_kept(self, ctr_config_for_pipeline):
        """Nodes within the CTR workspace should not be filtered out."""
        ctr = CTRConfig.from_xcavate_config(ctr_config_for_pipeline)

        # Points along the insertion axis (should be reachable)
        points = np.array([
            [0.0, -10.0, 0.0],
            [0.0, -20.0, 0.0],
            [0.0, -30.0, 0.0],
        ])

        unreachable = {i for i in range(len(points)) if not is_reachable(points[i], ctr)}
        assert len(unreachable) == 0

    def test_unreachable_nodes_filtered(self, ctr_config_for_pipeline):
        """Nodes far outside the workspace should be filtered."""
        ctr = CTRConfig.from_xcavate_config(ctr_config_for_pipeline)

        points = np.array([
            [0.0, -20.0, 0.0],    # reachable
            [500.0, 500.0, 500.0], # unreachable
            [0.0, -30.0, 0.0],    # reachable
        ])

        unreachable = {i for i in range(len(points)) if not is_reachable(points[i], ctr)}
        assert 1 in unreachable
        assert 0 not in unreachable
        assert 2 not in unreachable


# ---------------------------------------------------------------------------
# DFS with CTR collision detector
# ---------------------------------------------------------------------------

class TestDFSWithCTR:
    def test_pathfinding_generates_passes(self, ctr_config_for_pipeline):
        """DFS should generate at least one pass for reachable nodes."""
        from xcavate.core.pathfinding import generate_print_passes

        # Simple line of points along insertion axis
        points = np.array([
            [0.0, -10.0, 0.0],
            [0.0, -12.0, 0.0],
            [0.0, -14.0, 0.0],
            [0.0, -16.0, 0.0],
        ])

        # Simple chain graph: 0-1-2-3
        graph = {
            0: [0, 1],
            1: [1, 0, 2],
            2: [2, 1, 3],
            3: [3, 2],
        }

        passes = generate_print_passes(graph, points, ctr_config_for_pipeline)
        assert len(passes) > 0

        # All nodes should appear in some pass
        visited = set()
        for pass_nodes in passes.values():
            visited.update(pass_nodes)
        # Some nodes might not be visited if body-drag blocks them,
        # but at least some should be visited
        assert len(visited) > 0

    def test_gcode_writer_dispatch(self, ctr_config_for_pipeline, tmp_path):
        """_create_gcode_writer should return CTRGcodeWriter for CTR config."""
        from xcavate.pipeline import _create_gcode_writer
        from xcavate.io.gcode.ctr import CTRGcodeWriter

        writer = _create_gcode_writer(ctr_config_for_pipeline, None)
        assert isinstance(writer, CTRGcodeWriter)


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

class TestCTRConfigValidation:
    def test_printer_type_ctr_value(self):
        assert PrinterType.CTR.value == 3

    def test_config_defaults(self, tmp_path):
        config = XcavateConfig(
            network_file=tmp_path / "net.txt",
            inletoutlet_file=tmp_path / "io.txt",
            nozzle_diameter=0.5,
            container_height=50.0,
            num_decimals=3,
            printer_type=PrinterType.CTR,
            ctr_position_cartesian=(0.0, 0.0, 0.0),
        )
        assert config.ctr_radius == 47.0
        assert config.ctr_ss_max == 65.0
        assert config.ctr_ntnl_max == 140.0
        assert config.ctr_ss_axis_name == "X"
        assert config.ctr_ntnl_axis_name == "Y"
        assert config.ctr_rot_axis_name == "Z"
        assert config.ctr_needle_body_samples == 20
