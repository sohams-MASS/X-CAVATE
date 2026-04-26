"""Tests for the pipeline registry, case discovery, and arg builders."""
from pathlib import Path

from .pipelines import (
    Case,
    CANONICAL_PARAMS,
    PIPELINES,
    discover_cases,
    build_args_science,
    build_args_x1130,
    build_args_main,
)


VERIF_ROOT = Path("/Users/sohams/X-CAVATE/Vascular Trees Verification")


def test_pipeline_registry_has_three_entries():
    names = [p.name for p in PIPELINES]
    assert names == ["science", "x1130", "main"]


def test_discover_cases_finds_six_paired_networks_plus_orphan():
    cases = discover_cases(VERIF_ROOT)
    network_names = {c.network.name for c in cases}
    assert "cnet_network_0_b_splines_100_points.txt" in network_names
    assert "multimaterial_test_network_61_vessels.txt" in network_names
    assert "5-1-23_multimaterial_network_0_b_splines.txt" in network_names
    assert "network_0_b_splines_4_vessels.txt" in network_names
    assert "network_0_b_splines_9_vessels.txt" in network_names
    assert "network_0_b_splines_14_vessels.txt" in network_names
    assert "network_0_b_splines_500_vessels (1).txt" in network_names
    assert len(cases) == 7


def test_multimaterial_inferred_from_filename():
    cases = {c.network.name: c for c in discover_cases(VERIF_ROOT)}
    assert cases["multimaterial_test_network_61_vessels.txt"].multimaterial is True
    assert cases["5-1-23_multimaterial_network_0_b_splines.txt"].multimaterial is True
    assert cases["network_0_b_splines_4_vessels.txt"].multimaterial is False
    assert cases["cnet_network_0_b_splines_100_points.txt"].multimaterial is False


def test_orphan_500_vessel_has_synthesized_io():
    cases = {c.network.name: c for c in discover_cases(VERIF_ROOT)}
    orphan = cases["network_0_b_splines_500_vessels (1).txt"]
    assert orphan.inletoutlet.exists()
    assert "synth_inletoutlet" in orphan.inletoutlet.name


def test_companion_io_matches_by_shared_tokens():
    """Figure 4 (F) has three networks with three sibling I/O files; each network
    must pair with the matching vessel-count companion."""
    cases = {c.network.name: c for c in discover_cases(VERIF_ROOT)}
    assert cases["network_0_b_splines_4_vessels.txt"].inletoutlet.name == "network_inlet_outlet_4_vessels.txt"
    assert cases["network_0_b_splines_9_vessels.txt"].inletoutlet.name == "network_inlet_outlet_9_vessels.txt"
    assert cases["network_0_b_splines_14_vessels.txt"].inletoutlet.name == "network_inlet_outlet_14_vessels.txt"


def _make_case(tmp_path):
    net = tmp_path / "net.txt"
    net.write_text("Vessel: 0, Number of Points: 1\n\n1.0, 2.0, 3.0, 0.05\n")
    ioc = tmp_path / "ioc.txt"
    ioc.write_text("inlet\n1.0, 2.0, 3.0\noutlet\n1.0, 2.0, 3.0\n")
    return Case(network=net, inletoutlet=ioc, multimaterial=False, slug="test")


def test_science_args_omit_modern_flags(tmp_path):
    case = _make_case(tmp_path)
    args = build_args_science(case, CANONICAL_PARAMS)
    assert "--custom" not in args
    assert "--printer_type" not in args
    assert "--amount_up" not in args
    assert "--container_height" not in args
    assert "--nozzle_diameter" not in args
    for required in (
        "--network_file", "--inletoutlet_file", "--multimaterial",
        "--tolerance_flag", "--nozzleOD", "--numDecimalsOutput",
        "--speed_calc", "--plots", "--downsample", "--container_z",
    ):
        assert required in args, f"Missing required Science.py flag: {required}"


def test_x1130_args_include_modern_required_flags(tmp_path):
    case = _make_case(tmp_path)
    args = build_args_x1130(case, CANONICAL_PARAMS)
    for required in (
        "--network_file", "--inletoutlet_file", "--multimaterial",
        "--tolerance_flag", "--nozzle_diameter", "--num_decimals",
        "--speed_calc", "--plots", "--downsample", "--container_height",
        "--amount_up", "--custom", "--printer_type",
    ):
        assert required in args, f"Missing required 11_30 flag: {required}"


def test_main_args_pin_convert_factor_to_ten(tmp_path):
    case = _make_case(tmp_path)
    args = build_args_main(case, CANONICAL_PARAMS)
    assert "--convert_factor" in args
    cf_idx = args.index("--convert_factor")
    assert args[cf_idx + 1] == "10.0"


def test_multimaterial_flag_propagates(tmp_path):
    case = _make_case(tmp_path)
    object.__setattr__(case, "multimaterial", True)
    args = build_args_science(case, CANONICAL_PARAMS)
    mm_idx = args.index("--multimaterial")
    assert args[mm_idx + 1] == "1"
