"""Tests for the inlet/outlet synthesizer."""
import textwrap
from pathlib import Path

from .synth_io import (
    synthesize_inletoutlet,
    _parse_vessels,
)


SAMPLE_NETWORK = textwrap.dedent("""\
    Vessel: 0, Number of Points: 3

    1.0, 2.0, 3.0, 0.05
    1.5, 2.5, 3.5, 0.05
    2.0, 3.0, 4.0, 0.05
    Vessel: 1, Number of Points: 2

    9.0, 8.0, 7.0, 0.05
    9.5, 8.5, 7.5, 0.05
""")


def test_parse_vessels_returns_per_vessel_point_lists():
    vessels = _parse_vessels(SAMPLE_NETWORK)
    assert len(vessels) == 2
    assert vessels[0][0] == (1.0, 2.0, 3.0)
    assert vessels[0][-1] == (2.0, 3.0, 4.0)
    assert vessels[1][-1] == (9.5, 8.5, 7.5)


def test_synthesize_writes_companion_file(tmp_path):
    network_path = tmp_path / "net.txt"
    network_path.write_text(SAMPLE_NETWORK)
    out = synthesize_inletoutlet(network_path)
    assert out.exists()
    assert out.name == "net_synth_inletoutlet.txt"
    content = out.read_text()
    assert content.startswith("inlet\n")
    assert "outlet\n" in content


def test_inlet_is_first_point_of_vessel_zero(tmp_path):
    network_path = tmp_path / "net.txt"
    network_path.write_text(SAMPLE_NETWORK)
    out = synthesize_inletoutlet(network_path)
    lines = out.read_text().splitlines()
    inlet_idx = lines.index("inlet")
    inlet_coord = lines[inlet_idx + 1]
    assert inlet_coord.startswith("1.0, 2.0, 3.0")


def test_outlet_is_endpoint_of_longest_leaf(tmp_path):
    network_path = tmp_path / "net.txt"
    network_path.write_text(SAMPLE_NETWORK)
    out = synthesize_inletoutlet(network_path)
    lines = out.read_text().splitlines()
    outlet_idx = lines.index("outlet")
    outlet_coord = lines[outlet_idx + 1]
    # Vessel 0 has length sqrt(0.5^2*3) * 2 ≈ 1.732; vessel 1 has length sqrt(0.5^2*3) ≈ 0.866.
    # Longest vessel (vessel 0) endpoint is (2.0, 3.0, 4.0).
    assert outlet_coord.startswith("2.0, 3.0, 4.0")
