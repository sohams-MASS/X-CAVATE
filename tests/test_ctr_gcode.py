"""Unit tests for CTR G-code writer."""

import numpy as np
import pytest
from pathlib import Path

from xcavate.config import XcavateConfig, PrinterType
from xcavate.io.gcode.ctr import CTRGcodeWriter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ctr_config(tmp_path):
    """Config for CTR printer type."""
    return XcavateConfig(
        network_file=tmp_path / "net.txt",
        inletoutlet_file=tmp_path / "io.txt",
        nozzle_diameter=0.5,
        container_height=50.0,
        num_decimals=3,
        printer_type=PrinterType.CTR,
        ctr_position_cartesian=(0.0, 0.0, 0.0),
        ctr_orientation=(0.0, -1.0, 0.0),
        ctr_radius=47.0,
        ctr_ss_max=65.0,
        ctr_ntnl_max=140.0,
        output_dir=tmp_path / "outputs",
    )


@pytest.fixture
def simple_passes():
    """A simple 2-pass network along the -Y axis."""
    return {
        0: [0, 1, 2],
        1: [3, 4],
    }


@pytest.fixture
def simple_points():
    """Points along the -Y axis (insertion direction)."""
    return np.array([
        [0.0, -10.0, 0.0],
        [0.0, -12.0, 0.0],
        [0.0, -14.0, 0.0],
        [0.0, -20.0, 0.0],
        [0.0, -22.0, 0.0],
    ])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCTRGcodeWriter:
    def test_write_creates_file(self, ctr_config, simple_passes, simple_points, tmp_path):
        ctr_config.ensure_output_dirs()
        output_path = tmp_path / "outputs" / "gcode" / "test_ctr.txt"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        writer = CTRGcodeWriter(ctr_config)
        writer.write(output_path, simple_passes, simple_points, network_top=25.0)

        assert output_path.exists()
        content = output_path.read_text()
        assert len(content) > 0

    def test_output_contains_ctr_header(self, ctr_config, simple_passes, simple_points, tmp_path):
        output_path = tmp_path / "test_ctr.txt"
        writer = CTRGcodeWriter(ctr_config)
        writer.write(output_path, simple_passes, simple_points, network_top=25.0)

        content = output_path.read_text()
        assert "CTR GCODE" in content

    def test_output_contains_axis_names(self, ctr_config, simple_passes, simple_points, tmp_path):
        output_path = tmp_path / "test_ctr.txt"
        writer = CTRGcodeWriter(ctr_config)
        writer.write(output_path, simple_passes, simple_points, network_top=25.0)

        content = output_path.read_text()
        # Should contain the configured axis names
        assert ctr_config.ctr_ss_axis_name in content
        assert ctr_config.ctr_ntnl_axis_name in content

    def test_output_contains_pass_comments(self, ctr_config, simple_passes, simple_points, tmp_path):
        output_path = tmp_path / "test_ctr.txt"
        writer = CTRGcodeWriter(ctr_config)
        writer.write(output_path, simple_passes, simple_points, network_top=25.0)

        content = output_path.read_text()
        assert "; Print Pass 0" in content
        assert "; Print pass 1" in content

    def test_output_contains_g90(self, ctr_config, simple_passes, simple_points, tmp_path):
        output_path = tmp_path / "test_ctr.txt"
        writer = CTRGcodeWriter(ctr_config)
        writer.write(output_path, simple_passes, simple_points, network_top=25.0)

        content = output_path.read_text()
        assert "G90" in content

    def test_retract_between_passes(self, ctr_config, simple_passes, simple_points, tmp_path):
        """Between passes, the CTR should retract (SS=0, NTNL=0)."""
        output_path = tmp_path / "test_ctr.txt"
        writer = CTRGcodeWriter(ctr_config)
        writer.write(output_path, simple_passes, simple_points, network_top=25.0)

        content = output_path.read_text()
        # Should contain retract commands
        assert f"{ctr_config.ctr_ss_axis_name}0" in content
        assert f"{ctr_config.ctr_ntnl_axis_name}0" in content

    def test_custom_axis_names(self, tmp_path, simple_passes, simple_points):
        """Verify custom axis names appear in output."""
        config = XcavateConfig(
            network_file=tmp_path / "net.txt",
            inletoutlet_file=tmp_path / "io.txt",
            nozzle_diameter=0.5,
            container_height=50.0,
            num_decimals=3,
            printer_type=PrinterType.CTR,
            ctr_position_cartesian=(0.0, 0.0, 0.0),
            ctr_ss_axis_name="SS",
            ctr_ntnl_axis_name="NI",
            ctr_rot_axis_name="TH",
            output_dir=tmp_path / "outputs",
        )
        output_path = tmp_path / "test_ctr_custom.txt"
        writer = CTRGcodeWriter(config)
        writer.write(output_path, simple_passes, simple_points, network_top=25.0)

        content = output_path.read_text()
        assert "SS=" in content or "SS" in content
        assert "NI=" in content or "NI" in content


class TestThetaUnwrapping:
    def test_unwrap_minimizes_rotation(self, ctr_config):
        writer = CTRGcodeWriter(ctr_config)
        writer._prev_theta = 0.0

        # A theta just past pi should unwrap to negative
        result = writer._unwrap_theta(3.0)
        assert abs(result - 3.0) < abs(result - (3.0 - 2 * np.pi)) or abs(result - 3.0) < np.pi + 0.1

    def test_unwrap_continuity(self, ctr_config):
        writer = CTRGcodeWriter(ctr_config)
        writer._prev_theta = 3.0

        # Theta = 3.1 should stay near 3.1, not jump by 2*pi
        result = writer._unwrap_theta(3.1)
        assert abs(result - 3.1) < 0.2

    def test_unwrap_across_zero(self, ctr_config):
        writer = CTRGcodeWriter(ctr_config)
        writer._prev_theta = 0.1

        # Theta = -0.1 (equivalently 2*pi - 0.1) should unwrap to -0.1
        result = writer._unwrap_theta(2 * np.pi - 0.1)
        assert abs(result - (-0.1)) < 0.3
