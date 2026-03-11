"""Tests for xcavate.io.gcode writers."""

import numpy as np
import pytest

from xcavate.config import XcavateConfig, PrinterType, PathfindingAlgorithm
from xcavate.io.gcode import PressureGcodeWriter, PositiveInkGcodeWriter, AerotechGcodeWriter
from xcavate.io.gcode.base import CustomCodes


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


class TestCustomCodesLoad:
    """Tests for CustomCodes.load_from_dir() dwell file loading."""

    def test_load_dwell_start_and_end(self, tmp_path):
        """load_from_dir should read dwell_start.txt and dwell_end.txt."""
        (tmp_path / "dwell_start.txt").write_text("G4 P100 ; start dwell\n")
        (tmp_path / "dwell_end.txt").write_text("G4 P200 ; end dwell\n")
        codes = CustomCodes.load_from_dir(tmp_path)
        assert codes.dwell_start == "G4 P100 ; start dwell\n"
        assert codes.dwell_end == "G4 P200 ; end dwell\n"

    def test_load_dwell_missing_files(self, tmp_path):
        """load_from_dir should return empty strings when dwell files are absent."""
        codes = CustomCodes.load_from_dir(tmp_path)
        assert codes.dwell_start == ""
        assert codes.dwell_end == ""


class TestAerotechDwell:
    """Tests for Aerotech dwell injection."""

    def _make_custom_config(self, tmp_path, custom_gcode=True):
        return XcavateConfig(
            network_file=tmp_path / "dummy_network.txt",
            inletoutlet_file=tmp_path / "dummy_inletoutlet.txt",
            nozzle_diameter=0.25,
            container_height=50.0,
            num_decimals=2,
            amount_up=10.0,
            print_speed=1.0,
            jog_speed=5.0,
            printer_type=PrinterType.AEROTECH,
            algorithm=PathfindingAlgorithm.DFS,
            output_dir=tmp_path / "outputs",
            custom_gcode=custom_gcode,
        )

    def test_aerotech_custom_dwell(self, tmp_path, minimal_passes, minimal_points):
        """When custom_gcode=True, custom dwell text should appear instead of numeric DWELL."""
        cfg = self._make_custom_config(tmp_path, custom_gcode=True)
        codes = CustomCodes(dwell_start="G4 P100 ; custom start\n", dwell_end="G4 P200 ; custom end\n")
        writer = AerotechGcodeWriter(cfg, custom_codes=codes)
        output_path = tmp_path / "test.gcode"
        writer.write(output_path, minimal_passes, minimal_points)
        content = output_path.read_text()
        assert "G4 P100 ; custom start" in content
        assert "G4 P200 ; custom end" in content

    def test_aerotech_numeric_dwell_fallback(self, tmp_path, minimal_passes, minimal_points):
        """When custom_gcode=False, numeric DWELL lines should be preserved."""
        cfg = self._make_custom_config(tmp_path, custom_gcode=False)
        writer = AerotechGcodeWriter(cfg)
        output_path = tmp_path / "test.gcode"
        writer.write(output_path, minimal_passes, minimal_points)
        content = output_path.read_text()
        assert f"DWELL {cfg.dwell_start}" in content
        assert f"DWELL {cfg.dwell_end}" in content


class TestPressureDwell:
    """Tests for Pressure writer dwell injection."""

    def test_pressure_dwell_injection(self, tmp_path, minimal_passes, minimal_points):
        """Pressure writer should inject dwell_start and dwell_end when custom_gcode=True."""
        cfg = XcavateConfig(
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
            custom_gcode=True,
        )
        codes = CustomCodes(
            start_extrusion="M3 S255\n",
            stop_extrusion="M5\n",
            dwell_start="G4 P80 ; dwell start\n",
            dwell_end="G4 P80 ; dwell end\n",
        )
        writer = PressureGcodeWriter(cfg, custom_codes=codes)
        output_path = tmp_path / "test.gcode"
        writer.write(output_path, minimal_passes, minimal_points)
        content = output_path.read_text()
        assert "G4 P80 ; dwell start" in content
        assert "G4 P80 ; dwell end" in content


class TestPositiveInkDwell:
    """Tests for Positive Ink writer dwell injection."""

    def test_positive_ink_dwell_injection(self, tmp_path, minimal_passes, minimal_points):
        """Positive Ink writer should inject dwell_start and dwell_end when custom_gcode=True."""
        cfg = XcavateConfig(
            network_file=tmp_path / "dummy_network.txt",
            inletoutlet_file=tmp_path / "dummy_inletoutlet.txt",
            nozzle_diameter=0.25,
            container_height=50.0,
            num_decimals=2,
            amount_up=10.0,
            print_speed=1.0,
            jog_speed=5.0,
            printer_type=PrinterType.POSITIVE_INK,
            algorithm=PathfindingAlgorithm.DFS,
            output_dir=tmp_path / "outputs",
            custom_gcode=True,
        )
        codes = CustomCodes(
            start_extrusion_ph1="G1 E1\n",
            start_extrusion_ph2="G1 E2\n",
            stop_extrusion_ph1="G1 E-1\n",
            stop_extrusion_ph2="G1 E-2\n",
            dwell_start="G4 P50 ; pi dwell start\n",
            dwell_end="G4 P50 ; pi dwell end\n",
        )
        writer = PositiveInkGcodeWriter(cfg, custom_codes=codes)
        output_path = tmp_path / "test.gcode"
        writer.write(output_path, minimal_passes, minimal_points)
        content = output_path.read_text()
        assert "G4 P50 ; pi dwell start" in content
        assert "G4 P50 ; pi dwell end" in content
