"""Regression test: inlet/outlet node indices must reference the
post-interpolation coordinate array, not the pre-interpolation one.

Until this fix, `match_inlet_outlet_nodes` was called against the raw
400-row coordinate array of the 4-vessel network, returning index 99 for
the outlet. After `interpolate_network` densified to 1780 rows, the
original outlet endpoint moved to index 489 — but `outlet_nodes` was
never remapped, so `_find_branchpoints` skipped the wrong node and added
spurious branchpoint edges through the actual outlet (489).

This test reaches into the pipeline and verifies that the indices
returned in the result dict point at coordinates equal to the original
outlet target after interpolation.
"""
import numpy as np
import tempfile
import os
from pathlib import Path

from xcavate.config import (
    OverlapAlgorithm, PathfindingAlgorithm, PrinterType, SpeedUnit, XcavateConfig,
)
from xcavate.pipeline import run_xcavate


NETWORK = Path("/Users/sohams/X-CAVATE/Vascular Trees Verification/Figure 4 (F)/network_0_b_splines_4_vessels.txt")
IOC = Path("/Users/sohams/X-CAVATE/Vascular Trees Verification/Figure 4 (F)/network_inlet_outlet_4_vessels.txt")


def test_outlet_node_resolves_to_post_interp_endpoint():
    """The outlet node index must point at coord (20, 10, -10) in the
    interpolated array — i.e. the matching happens AFTER interpolation,
    not before."""
    if not NETWORK.exists() or not IOC.exists():
        import pytest
        pytest.skip("4-vessel verification network not available")

    wd = tempfile.mkdtemp()
    os.chdir(wd)
    cfg = XcavateConfig(
        network_file=NETWORK,
        inletoutlet_file=IOC,
        nozzle_diameter=0.41, container_height=50.0, num_decimals=6, amount_up=10.0,
        multimaterial=False, speed_calc=True, downsample=False, custom_gcode=False,
        printer_type=PrinterType.PRESSURE, speed_unit=SpeedUnit.MM_PER_S,
        algorithm=PathfindingAlgorithm.DFS, overlap_algorithm=OverlapAlgorithm.RETRACE,
        convert_factor=10.0, flow=0.1609429886081009,
        output_dir=Path(wd) / "outputs",
    )
    result = run_xcavate(cfg)

    # The result dict exposes 'points' (interp) and 'print_passes_sm'.
    # We need the inlet/outlet node indices — look them up from the dump file.
    special = (Path(wd) / "outputs" / "graph" / "special_nodes.txt").read_text()

    # Outlet line: e.g. "Outlet nodes:[489]" (post-fix) or "Outlet nodes:[99]" (pre-fix)
    import re
    outlet_match = re.search(r"Outlet nodes:\[(\d+)\]", special)
    assert outlet_match is not None, "couldn't parse Outlet nodes from special_nodes.txt"
    outlet_idx = int(outlet_match.group(1))

    # Outlet target coord after convert_factor=10: (20, 10, -10)
    points_interp = result["points"]
    coord = points_interp[outlet_idx, :3]
    expected = np.array([20.0, 10.0, -10.0])
    assert np.allclose(coord, expected, atol=1e-6), (
        f"outlet node {outlet_idx} has coord {coord}, expected {expected}. "
        f"This means inlet/outlet matching ran on pre-interpolation points "
        f"and the indices were never remapped."
    )


def test_pass_count_matches_x1130_reference_on_4_vessel():
    """With the inlet/outlet fix, main's print_passes_sm count should match
    x1130's reference of 23 passes for the 4-vessel network (down from 24
    pre-fix). The "extra" pass was a 2-node branchpoint bridge caused by
    spurious adjacency edges through the misidentified outlet."""
    if not NETWORK.exists() or not IOC.exists():
        import pytest
        pytest.skip("4-vessel verification network not available")

    wd = tempfile.mkdtemp()
    os.chdir(wd)
    cfg = XcavateConfig(
        network_file=NETWORK,
        inletoutlet_file=IOC,
        nozzle_diameter=0.41, container_height=50.0, num_decimals=6, amount_up=10.0,
        multimaterial=False, speed_calc=True, downsample=False, custom_gcode=False,
        printer_type=PrinterType.PRESSURE, speed_unit=SpeedUnit.MM_PER_S,
        algorithm=PathfindingAlgorithm.DFS, overlap_algorithm=OverlapAlgorithm.RETRACE,
        convert_factor=10.0, flow=0.1609429886081009,
        output_dir=Path(wd) / "outputs",
    )
    result = run_xcavate(cfg)
    assert len(result["print_passes_sm"]) == 23, (
        f"expected 23 passes (matching x1130 on 4-vessel after the inlet/outlet "
        f"remap fix), got {len(result['print_passes_sm'])}"
    )
