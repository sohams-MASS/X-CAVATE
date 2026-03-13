"""Run 6-robot multi-CTR pipeline and save HTML visualizations to ~/Downloads."""

import logging
import sys
import time
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xcavate.config import PrinterType, PathfindingAlgorithm, XcavateConfig
from xcavate.pipeline import run_xcavate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-30s %(levelname)-7s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("generate_6robot_viz")

DOWNLOADS = Path.home() / "Downloads"


def main():
    network_file = Path("/Users/sohams/Downloads/network_0_b_splines_500_vessels (3).txt")
    assert network_file.exists(), f"Network file not found: {network_file}"

    # Parse network to find inlet/outlet endpoints
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

    v0 = vessels[0]
    inlet_pt = v0[0]
    outlet_pt = v0[-1]

    io_file = Path(tempfile.mktemp(suffix="_inlet_outlet.txt"))
    with open(io_file, "w") as f:
        f.write("inlet\n")
        f.write(f"{inlet_pt[0]}, {inlet_pt[1]}, {inlet_pt[2]}\n")
        f.write("outlet\n")
        f.write(f"{outlet_pt[0]}, {outlet_pt[1]}, {outlet_pt[2]}\n")

    output_dir = Path(tempfile.mkdtemp(prefix="xcavate_multi_ctr_6_"))

    config = XcavateConfig(
        network_file=network_file,
        inletoutlet_file=io_file,
        nozzle_diameter=0.4,
        container_height=60.0,
        num_decimals=4,
        scale_factor=1.0,
        printer_type=PrinterType.CTR,
        algorithm=PathfindingAlgorithm.ANGULAR_SECTOR,
        generate_plots=False,
        ctr_auto_place=True,
        ctr_radius=55.0,
        ctr_ss_max=65.0,
        ctr_ntnl_max=140.0,
        ctr_ss_od=4.0,
        ctr_ntnl_od=1.6,
        ctr_needle_body_samples=20,
        ctr_num_sectors=8,
        n_robots=6,
        multi_ctr_execution="parallel",
        inter_robot_clearance=2.0,
        ctr_oracle_orient=True,
        gimbal_enabled=True,
        gimbal_cone_angle=15.0,
        gimbal_n_tilt=3,
        gimbal_n_azimuth=8,
        output_dir=output_dir,
    )

    # --- Run pipeline ---
    logger.info("=" * 70)
    logger.info("Running 6-robot multi-CTR pipeline on 500-vessel network")
    logger.info("=" * 70)
    t0 = time.time()
    result = run_xcavate(config)
    elapsed = time.time() - t0
    logger.info("Pipeline completed in %.1f seconds", elapsed)

    # --- Print summary ---
    per_robot_passes = result.get("per_robot_passes", {})
    per_robot_solutions = result.get("per_robot_solutions", {})
    ctr_configs_multi = result.get("ctr_configs_multi", [])
    node_assignments = result.get("node_assignments", {})
    pts = result["points"]

    print(f"\n{'='*70}")
    print(f"6-ROBOT RESULTS: {sum(len(v) for v in node_assignments.values())} nodes assigned")
    for r in sorted(node_assignments.keys()):
        n_nodes = sum(len(v) for v in per_robot_passes.get(r, {}).values())
        print(f"  Robot {r}: {len(node_assignments[r])} assigned, "
              f"{len(per_robot_passes.get(r, {}))} passes, {n_nodes} printed")
    print(f"{'='*70}\n")

    # --- Generate visualizations ---
    from xcavate.viz.ctr_simulation import (
        create_multi_ctr_parallel_simulation,
        create_multi_ctr_static_view,
    )

    # 1. Multi-robot PARALLEL animation (all robots move at once)
    logger.info("Generating parallel multi-robot animation (every step, 1.5K trail)...")
    t1 = time.time()
    fig_anim = create_multi_ctr_parallel_simulation(
        per_robot_passes=per_robot_passes,
        per_robot_solutions=per_robot_solutions,
        ctr_configs_multi=ctr_configs_multi,
        points=pts,
        max_frames=20000,          # effectively unlimited — shows every single step
        trail_max_points=1500,     # reduced to control file size
        ghost_max=10000,
        trail_marker_size=2.5,
        needle_width=5,
    )
    fig_anim.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 33

    anim_path = DOWNLOADS / "ctr_6robot_animation.html"
    fig_anim.write_html(str(anim_path), include_plotlyjs="cdn")
    anim_size = anim_path.stat().st_size / (1024 * 1024)
    logger.info("Animation saved: %s (%.1f MB, %.1fs)", anim_path, anim_size, time.time() - t1)

    # 2. Static overview
    logger.info("Generating static overview...")
    t2 = time.time()
    fig_static = create_multi_ctr_static_view(
        per_robot_passes=per_robot_passes,
        per_robot_solutions=per_robot_solutions,
        ctr_configs_multi=ctr_configs_multi,
        points=pts,
    )

    static_path = DOWNLOADS / "ctr_6robot_static_overview.html"
    fig_static.write_html(str(static_path), include_plotlyjs="cdn")
    static_size = static_path.stat().st_size / (1024 * 1024)
    logger.info("Static overview saved: %s (%.1f MB, %.1fs)", static_path, static_size, time.time() - t2)

    # 3. Per-robot animations (lighter: 100 frames, 3K trail)
    for ridx in sorted(per_robot_passes.keys()):
        robot_passes = per_robot_passes[ridx]
        robot_solutions = per_robot_solutions.get(ridx, {})
        robot_cfg = ctr_configs_multi[ridx]

        if not robot_passes:
            continue

        logger.info("Generating Robot %d animation...", ridx)
        t3 = time.time()

        from xcavate.viz.ctr_simulation import create_ctr_simulation_all_passes
        fig_r = create_ctr_simulation_all_passes(
            print_passes=robot_passes,
            points=pts,
            gimbal_solutions=robot_solutions,
            ctr_base=np.array(robot_cfg["X"]),
            R_hat_base=np.array(robot_cfg["R_hat"]),
            radius=robot_cfg["radius"],
            n_hat_base=np.array(robot_cfg["n_hat"]),
            theta_match=robot_cfg["theta_match"],
            max_frames=100,
            trail_max_points=3000,
        )
        fig_r.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 50

        r_path = DOWNLOADS / f"ctr_6robot_robot{ridx}.html"
        fig_r.write_html(str(r_path), include_plotlyjs="cdn")
        r_size = r_path.stat().st_size / (1024 * 1024)
        logger.info("  Robot %d saved: %s (%.1f MB, %.1fs)", ridx, r_path, r_size, time.time() - t3)

    # Cleanup
    io_file.unlink(missing_ok=True)

    print(f"\n{'='*70}")
    print(f"ALL VISUALIZATIONS SAVED TO {DOWNLOADS}")
    print(f"  - ctr_6robot_animation.html      ({anim_size:.1f} MB)")
    print(f"  - ctr_6robot_static_overview.html ({static_size:.1f} MB)")
    for ridx in sorted(per_robot_passes.keys()):
        r_path = DOWNLOADS / f"ctr_6robot_robot{ridx}.html"
        if r_path.exists():
            print(f"  - ctr_6robot_robot{ridx}.html")
    print(f"\nTotal pipeline time: {elapsed:.1f}s")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
