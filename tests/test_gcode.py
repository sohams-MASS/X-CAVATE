"""Tests for xcavate.io.gcode writers."""

import numpy as np
import pytest

from xcavate.config import XcavateConfig, PrinterType, PathfindingAlgorithm
from xcavate.io.gcode import PressureGcodeWriter, PositiveInkGcodeWriter, AerotechGcodeWriter


@pytest.fixture
def gcode_config(tmp_path):
    """Config suitable for G-code writer tests."""
    return XcavateConfig(
        network_file=tmp_path / "dummy_network.txt",
        inletoutlet_file=tmp_path / "dummy_inletoutlet.txt",
        nozzle_diameter=0.25,
        container_height=50.0,
        num_decimals=2,
        amount_up=10.0,
        print_speed=1.0,
        jog_speed=5.0,
        printer_type=PrinterType.PRESSURE,
        algorithm=PathfindingAlgorithm.DFS,
        output_dir=tmp_path / "outputs",
    )


@pytest.fixture
def minimal_passes():
    """A minimal set of print passes with two passes."""
    return {
        0: [0, 1, 2],
        1: [3, 4, 5],
    }


@pytest.fixture
def minimal_points():
    """A minimal set of 6 points for the two-pass fixture."""
    return np.array([
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.0, 2.0],
        [1.0, 0.0, 3.0],
        [1.0, 0.0, 4.0],
        [1.0, 0.0, 5.0],
    ])


class TestPressureGcodeWriter:
    """Tests for PressureGcodeWriter."""

    def test_pressure_writer_creates_file(
        self, tmp_path, gcode_config, minimal_passes, minimal_points
    ):
        """PressureGcodeWriter.write() should create a non-empty file."""
        output_path = tmp_path / "test_pressure.gcode"
        writer = PressureGcodeWriter(gcode_config)
        writer.write(output_path, minimal_passes, minimal_points)

        assert output_path.exists()
        content = output_path.read_text()
        assert len(content) > 0

    def test_gcode_contains_header(
        self, tmp_path, gcode_config, minimal_passes, minimal_points
    ):
        """Output should start with the standard header comment."""
        output_path = tmp_path / "test_header.gcode"
        writer = PressureGcodeWriter(gcode_config)
        writer.write(output_path, minimal_passes, minimal_points)

        content = output_path.read_text()
        assert content.startswith(";===========")


class TestPositiveInkGcodeWriter:
    """Tests for PositiveInkGcodeWriter."""

    def test_positive_ink_writer_creates_file(
        self, tmp_path, gcode_config, minimal_passes, minimal_points
    ):
        """PositiveInkGcodeWriter.write() should create a non-empty file."""
        output_path = tmp_path / "test_positive_ink.gcode"
        writer = PositiveInkGcodeWriter(gcode_config)
        writer.write(output_path, minimal_passes, minimal_points)

        assert output_path.exists()
        content = output_path.read_text()
        assert len(content) > 0


class TestAerotechGcodeWriter:
    """Tests for AerotechGcodeWriter."""

    def test_aerotech_writer_creates_file(
        self, tmp_path, gcode_config, minimal_passes, minimal_points
    ):
        """AerotechGcodeWriter.write() should create a non-empty file."""
        output_path = tmp_path / "test_aerotech.gcode"
        writer = AerotechGcodeWriter(gcode_config)
        writer.write(output_path, minimal_passes, minimal_points)

        assert output_path.exists()
        content = output_path.read_text()
        assert len(content) > 0
