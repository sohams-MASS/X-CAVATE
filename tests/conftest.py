"""Shared fixtures for X-CAVATE test suite."""

from pathlib import Path

import numpy as np
import pytest

from xcavate.config import XcavateConfig, PrinterType, PathfindingAlgorithm


@pytest.fixture
def simple_network_points():
    """A small 3-vessel Y-shaped network (parent trunk + 2 daughter branches).

    Vessel 0 (parent): 6 points from (0,0,0) up to (0,0,5)
    Vessel 1 (daughter A): 6 points from (0,0,5) branching to (2,0,10)
    Vessel 2 (daughter B): 6 points from (0,0,5) branching to (-2,0,10)

    Total: 18 points, 3 columns (x, y, z).
    """
    # Vessel 0: straight trunk along z-axis
    v0 = np.array([
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.0, 2.0],
        [0.0, 0.0, 3.0],
        [0.0, 0.0, 4.0],
        [0.0, 0.0, 5.0],
    ])
    # Vessel 1: daughter branch toward +x
    v1 = np.array([
        [0.0, 0.0, 5.0],
        [0.4, 0.0, 6.0],
        [0.8, 0.0, 7.0],
        [1.2, 0.0, 8.0],
        [1.6, 0.0, 9.0],
        [2.0, 0.0, 10.0],
    ])
    # Vessel 2: daughter branch toward -x
    v2 = np.array([
        [0.0, 0.0, 5.0],
        [-0.4, 0.0, 6.0],
        [-0.8, 0.0, 7.0],
        [-1.2, 0.0, 8.0],
        [-1.6, 0.0, 9.0],
        [-2.0, 0.0, 10.0],
    ])
    return np.vstack([v0, v1, v2])


@pytest.fixture
def coord_num_dict():
    """Vessel-to-point-count dict matching simple_network_points."""
    return {0: 6, 1: 6, 2: 6}


@pytest.fixture
def simple_config(tmp_path):
    """An XcavateConfig with sensible test defaults."""
    return XcavateConfig(
        network_file=tmp_path / "dummy_network.txt",
        inletoutlet_file=tmp_path / "dummy_inletoutlet.txt",
        nozzle_diameter=0.25,
        container_height=50.0,
        num_decimals=2,
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
