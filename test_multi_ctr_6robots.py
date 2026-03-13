"""Test multi-CTR pipeline with n=6 robots on a 500-vessel network.

Generates inlet/outlet from the network's vessel 0 endpoints, runs the full
pipeline with auto-placement and the gimbal solver, and prints diagnostic
statistics.
"""

import logging
import sys
import time
import tempfile
from pathlib import Path

import numpy as np

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from xcavate.config import PrinterType, PathfindingAlgorithm, XcavateConfig
from xcavate.pipeline import run_xcavate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-30s %(levelname)-7s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("test_multi_ctr_6robots")


def main():
    network_file = Path("/Users/sohams/Downloads/network_0_b_splines_500_vessels (3).txt")
    assert network_file.exists(), f"Network file not found: {network_file}"

    # --- Parse network to find inlet/outlet endpoints ---
    with open(network_file) as f:
        lines = f.readlines()

    vessels = {}
    current_vessel = None
    for line in lines:
        line = line.strip()
        if line.startswith("Vessel:"):
            parts = line.split(",")
            vessel_id = int(parts[0].split(":")[1].strip())
            vessels[vessel_id] = []
            current_vessel = vessel_id
        elif line and current_vessel is not None:
            try:
                coords = [float(x) for x in line.split(",")]
                vessels[current_vessel].append(coords[:3])
            except ValueError:
                pass

    # Use vessel 0 first point as inlet, last point as outlet
    v0 = vessels[0]
    inlet_pt = v0[0]
    outlet_pt = v0[-1]

    logger.info("Inlet:  (%.4f, %.4f, %.4f)", *inlet_pt)
    logger.info("Outlet: (%.4f, %.4f, %.4f)", *outlet_pt)

    # Write temporary inlet/outlet file
    io_file = Path(tempfile.mktemp(suffix="_inlet_outlet.txt"))
    with open(io_file, "w") as f:
        f.write("inlet\n")
        f.write(f"{inlet_pt[0]}, {inlet_pt[1]}, {inlet_pt[2]}\n")
        f.write("outlet\n")
        f.write(f"{outlet_pt[0]}, {outlet_pt[1]}, {outlet_pt[2]}\n")

    # --- Build config ---
    output_dir = Path(tempfile.mkdtemp(prefix="xcavate_multi_ctr_6_"))
    logger.info("Output directory: %s", output_dir)

    config = XcavateConfig(
        network_file=network_file,
        inletoutlet_file=io_file,
        nozzle_diameter=0.4,
        container_height=60.0,
        num_decimals=4,
        scale_factor=10.0,            # cm -> mm (network is in cm)
        printer_type=PrinterType.CTR,
        algorithm=PathfindingAlgorithm.ANGULAR_SECTOR,
        generate_plots=False,         # skip HTML plots for speed
        # CTR parameters
        ctr_auto_place=True,
        ctr_radius=55.0,
        ctr_ss_max=65.0,
        ctr_ntnl_max=140.0,
        ctr_ss_od=4.0,
        ctr_ntnl_od=1.6,
        ctr_needle_body_samples=20,
        ctr_num_sectors=8,
        # Multi-CTR: 6 robots
        n_robots=6,
        multi_ctr_execution="sequential",
        inter_robot_clearance=2.0,
        ctr_oracle_orient=True,
        # Gimbal
        gimbal_enabled=True,
        gimbal_cone_angle=15.0,
        gimbal_n_tilt=3,
        gimbal_n_azimuth=8,
        # Output
        output_dir=output_dir,
    )

    # --- Run pipeline ---
    logger.info("=" * 70)
    logger.info("Running 6-robot multi-CTR pipeline on 500-vessel network")
    logger.info("=" * 70)
    t0 = time.time()

    result = run_xcavate(config)

    elapsed = time.time() - t0
    logger.info("=" * 70)
    logger.info("COMPLETED in %.1f seconds", elapsed)
    logger.info("=" * 70)

    # --- Print diagnostics ---
    print("\n" + "=" * 70)
    print("MULTI-CTR 6-ROBOT TEST RESULTS")
    print("=" * 70)

    n_robots = result.get("n_robots", 1)
    print(f"\nNumber of robots: {n_robots}")

    # Node assignments
    node_assignments = result.get("node_assignments", {})
    total_assigned = sum(len(nodes) for nodes in node_assignments.values())
    print(f"\nNode assignments:")
    for r in sorted(node_assignments.keys()):
        nodes = node_assignments[r]
        print(f"  Robot {r}: {len(nodes)} nodes ({100*len(nodes)/max(total_assigned,1):.1f}%)")
    print(f"  Total assigned: {total_assigned}")

    # Per-robot passes
    per_robot_passes = result.get("per_robot_passes", {})
    print(f"\nPer-robot passes:")
    total_passes = 0
    total_nodes_printed = 0
    for r in sorted(per_robot_passes.keys()):
        rp = per_robot_passes[r]
        n_passes = len(rp)
        n_nodes = sum(len(nodes) for nodes in rp.values())
        total_passes += n_passes
        total_nodes_printed += n_nodes
        print(f"  Robot {r}: {n_passes} passes, {n_nodes} nodes printed")
    print(f"  Total: {total_passes} passes, {total_nodes_printed} nodes printed")

    # Per-robot solutions
    per_robot_solutions = result.get("per_robot_solutions", {})
    print(f"\nPer-robot gimbal solutions:")
    for r in sorted(per_robot_solutions.keys()):
        rs = per_robot_solutions[r]
        print(f"  Robot {r}: {len(rs)} solutions")

    # Merged passes
    sm_passes = result.get("print_passes_sm", {})
    print(f"\nMerged single-material passes: {len(sm_passes)}")
    sm_nodes = sum(len(v) for v in sm_passes.values())
    print(f"Merged total nodes in passes: {sm_nodes}")

    # Coverage analysis
    gimbal_solutions = result.get("gimbal_solutions", {})
    print(f"\nTotal gimbal solutions (merged): {len(gimbal_solutions)}")

    # Robot configs
    ctr_configs_multi = result.get("ctr_configs_multi", [])
    print(f"\nRobot configurations:")
    for i, cfg in enumerate(ctr_configs_multi):
        X = cfg["X"]
        R = cfg["R_hat"]
        print(f"  Robot {i}: pos=({X[0]:.1f}, {X[1]:.1f}, {X[2]:.1f}), "
              f"dir=({R[0]:.3f}, {R[1]:.3f}, {R[2]:.3f})")

    # Pass-robot map
    pass_robot_map = result.get("pass_robot_map", {})
    if pass_robot_map:
        from collections import Counter
        robot_pass_counts = Counter(pass_robot_map.values())
        print(f"\nPass-to-robot distribution:")
        for r in sorted(robot_pass_counts.keys()):
            print(f"  Robot {r}: {robot_pass_counts[r]} unified passes")

    # Check for disjointness
    all_assigned_nodes = set()
    overlap_count = 0
    for r, nodes in node_assignments.items():
        overlap = set(nodes) & all_assigned_nodes
        if overlap:
            overlap_count += len(overlap)
            print(f"\n  WARNING: Robot {r} has {len(overlap)} overlapping nodes!")
        all_assigned_nodes.update(nodes)

    if overlap_count == 0:
        print(f"\nNode assignment disjointness: PASS (no overlaps)")
    else:
        print(f"\nNode assignment disjointness: FAIL ({overlap_count} overlapping nodes)")

    # G-code files
    gcode_dir = config.gcode_dir
    gcode_files = sorted(gcode_dir.glob("*.txt"))
    print(f"\nG-code files generated:")
    for gf in gcode_files:
        size_kb = gf.stat().st_size / 1024
        print(f"  {gf.name} ({size_kb:.1f} KB)")

    print(f"\nOutput directory: {output_dir}")
    print(f"Total runtime: {elapsed:.1f}s")
    print("=" * 70)

    # Cleanup temp inlet/outlet
    io_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
