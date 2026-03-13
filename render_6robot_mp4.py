"""Render every-step 6-robot parallel simulation to MP4 video."""

import logging
import sys
import time
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter
from mpl_toolkits.mplot3d import Axes3D
from scipy.spatial.distance import cdist

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xcavate.config import PrinterType, PathfindingAlgorithm, XcavateConfig
from xcavate.pipeline import run_xcavate
from xcavate.viz.ctr_simulation import (
    compute_needle_geometry,
    _compute_frame_data,
    _unpack_robot_config,
    _ROBOT_COLORS,
)
from xcavate.core.gimbal_solver import GimbalNodeSolution

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-30s %(levelname)-7s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("render_mp4")

DOWNLOADS = Path.home() / "Downloads"

# Matplotlib-friendly colors (convert hex to RGB tuples)
MPL_COLORS = [
    (0.122, 0.467, 0.706),   # #1f77b4 blue
    (1.000, 0.498, 0.055),   # #ff7f0e orange
    (0.173, 0.627, 0.173),   # #2ca02c green
    (0.839, 0.153, 0.157),   # #d62728 red
    (0.580, 0.404, 0.741),   # #9467bd purple
    (0.549, 0.337, 0.294),   # #8c564b brown
]


def run_pipeline():
    """Run the 6-robot pipeline and return results."""
    network_file = Path("/Users/sohams/Downloads/network_0_b_splines_500_vessels (3).txt")
    assert network_file.exists(), f"Network file not found: {network_file}"

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
    inlet_pt, outlet_pt = v0[0], v0[-1]

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

    logger.info("Running 6-robot pipeline...")
    t0 = time.time()
    result = run_xcavate(config)
    logger.info("Pipeline completed in %.1fs", time.time() - t0)

    io_file.unlink(missing_ok=True)
    return result


def render_mp4(result, output_path: Path, fps: int = 30, dpi: int = 150):
    """Render every-step parallel animation to MP4."""
    per_robot_passes = result["per_robot_passes"]
    per_robot_solutions = result["per_robot_solutions"]
    ctr_configs_multi = result["ctr_configs_multi"]
    pts = result["points"]

    n_robots = len(ctr_configs_multi)
    robot_indices = sorted(per_robot_passes.keys())
    active_robots = [r for r in robot_indices if per_robot_passes.get(r)]

    # Unpack configs
    robot_cfgs = {}
    for ridx in range(n_robots):
        robot_cfgs[ridx] = _unpack_robot_config(ctr_configs_multi[ridx])

    # Build flat node list per robot
    robot_flat_nodes: Dict[int, List[int]] = {}
    for ridx in active_robots:
        nodes_list: List[int] = []
        for pk in sorted(per_robot_passes[ridx].keys()):
            nodes_list.extend(per_robot_passes[ridx][pk])
        robot_flat_nodes[ridx] = nodes_list

    max_steps = max((len(robot_flat_nodes[r]) for r in active_robots), default=0)
    logger.info("Total steps: %d, active robots: %d", max_steps, len(active_robots))

    # Ghost points for network background
    all_pts = pts[:, :3]
    ghost_max = 15000
    if len(all_pts) > ghost_max:
        ghost_idx = np.linspace(0, len(all_pts) - 1, ghost_max, dtype=int)
        ghost_pts = all_pts[ghost_idx]
    else:
        ghost_pts = all_pts

    # Axis ranges
    pad = 5.0
    x_min, x_max = float(all_pts[:, 0].min()) - pad, float(all_pts[:, 0].max()) + pad
    y_min, y_max = float(all_pts[:, 1].min()) - pad, float(all_pts[:, 1].max()) + pad
    z_min, z_max = float(all_pts[:, 2].min()) - pad, float(all_pts[:, 2].max()) + pad
    for ridx in range(n_robots):
        base = np.asarray(ctr_configs_multi[ridx]["X"], dtype=float)
        x_min, x_max = min(x_min, base[0] - pad), max(x_max, base[0] + pad)
        y_min, y_max = min(y_min, base[1] - pad), max(y_max, base[1] + pad)
        z_min, z_max = min(z_min, base[2] - pad), max(z_max, base[2] + pad)

    # Precompute trail subsampling: store printed node indices per robot at each step
    # (we only subsample for rendering, not for the actual data)
    trail_max_per_robot = 500  # keep trail lightweight for rendering speed

    # ---- Set up matplotlib figure ----
    fig = plt.figure(figsize=(16, 10), facecolor="black")
    ax = fig.add_subplot(111, projection="3d", facecolor="black")

    # Style the axes
    for axis in [ax.xaxis, ax.yaxis, ax.zaxis]:
        axis.pane.fill = False
        axis.pane.set_edgecolor("gray")
        axis.label.set_color("white")
        axis.set_tick_params(colors="white")
    ax.set_xlabel("X (mm)", color="white")
    ax.set_ylabel("Y (mm)", color="white")
    ax.set_zlabel("Z (mm)", color="white")
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_zlim(z_min, z_max)

    # Network ghost (static — drawn once)
    ax.scatter(
        ghost_pts[:, 0], ghost_pts[:, 1], ghost_pts[:, 2],
        s=0.3, c="gray", alpha=0.2, depthshade=False,
    )

    # Base markers (static)
    for ridx in range(n_robots):
        base = np.asarray(ctr_configs_multi[ridx]["X"], dtype=float)
        color = MPL_COLORS[ridx % len(MPL_COLORS)]
        ax.scatter(
            [base[0]], [base[1]], [base[2]],
            s=60, c=[color], marker="D", edgecolors="white", linewidths=0.5,
            zorder=10,
        )

    # Title text
    title_text = ax.set_title("", color="white", fontsize=11, pad=10)

    # Create dynamic artists per robot: SS line, arc line, tip marker, trail scatter
    robot_artists = {}
    for ridx in range(n_robots):
        color = MPL_COLORS[ridx % len(MPL_COLORS)]
        ss_line, = ax.plot([], [], [], color=color, linewidth=2.0, solid_capstyle="round")
        arc_line, = ax.plot([], [], [], color=color, linewidth=1.5, solid_capstyle="round")
        tip_marker = ax.scatter([], [], [], s=30, c="lime", zorder=10, depthshade=False)
        trail_scatter = ax.scatter([], [], [], s=1.0, c=[color], alpha=0.6, depthshade=False)
        robot_artists[ridx] = {
            "ss": ss_line,
            "arc": arc_line,
            "tip": tip_marker,
            "trail": trail_scatter,
        }

    # Set a good initial viewing angle
    ax.view_init(elev=25, azim=45)

    def update(step):
        """Update frame for step number."""
        robot_bodies: Dict[int, np.ndarray] = {}

        for ridx in range(n_robots):
            artists = robot_artists[ridx]

            if ridx in active_robots and robot_flat_nodes[ridx]:
                n_nodes = len(robot_flat_nodes[ridx])
                robot_step = min(step, n_nodes - 1)
                node = robot_flat_nodes[ridx][robot_step]
                sols = per_robot_solutions.get(ridx, {})
                X, R_hat, n_hat, tm, rad = robot_cfgs[ridx]
                geom, _ = _compute_frame_data(node, sols, X, R_hat, n_hat, tm, rad)

                # Collect body for distance calc
                body_parts = [geom["ss_line"]]
                if len(geom["arc_line"]) > 0:
                    body_parts.append(geom["arc_line"])
                robot_bodies[ridx] = np.vstack(body_parts)

                # SS tube
                ss = geom["ss_line"]
                artists["ss"].set_data_3d(ss[:, 0], ss[:, 1], ss[:, 2])

                # Arc
                arc = geom["arc_line"]
                if len(arc) > 0:
                    artists["arc"].set_data_3d(arc[:, 0], arc[:, 1], arc[:, 2])
                else:
                    artists["arc"].set_data_3d([], [], [])

                # Tip
                tip = geom["tip"]
                artists["tip"]._offsets3d = ([float(tip[0])], [float(tip[1])], [float(tip[2])])

                # Trail: subsample printed nodes
                count = robot_step + 1
                trail_nodes = robot_flat_nodes[ridx][:count]
                if len(trail_nodes) > trail_max_per_robot:
                    step_s = max(1, len(trail_nodes) // trail_max_per_robot)
                    trail_nodes = trail_nodes[::step_s]
                if trail_nodes:
                    trail_pts = pts[trail_nodes, :3]
                    artists["trail"]._offsets3d = (
                        trail_pts[:, 0], trail_pts[:, 1], trail_pts[:, 2],
                    )
                else:
                    artists["trail"]._offsets3d = ([], [], [])
            else:
                # Idle — hide
                artists["ss"].set_data_3d([], [], [])
                artists["arc"].set_data_3d([], [], [])
                artists["tip"]._offsets3d = ([], [], [])
                artists["trail"]._offsets3d = ([], [], [])

        # Compute minimum inter-robot distance
        min_dist = float("inf")
        min_pair = (-1, -1)
        body_keys = sorted(robot_bodies.keys())
        for i in range(len(body_keys)):
            for j in range(i + 1, len(body_keys)):
                ri, rj = body_keys[i], body_keys[j]
                d = cdist(robot_bodies[ri], robot_bodies[rj]).min()
                if d < min_dist:
                    min_dist = d
                    min_pair = (ri, rj)

        if min_dist < 4.0:
            dist_str = f"MIN DIST: {min_dist:.1f}mm R{min_pair[0]}-R{min_pair[1]} WARNING"
            title_color = "red"
        elif min_dist < float("inf"):
            dist_str = f"min dist: {min_dist:.1f}mm"
            title_color = "white"
        else:
            dist_str = ""
            title_color = "white"

        title_text.set_text(
            f"6-Robot Parallel | Step {step + 1}/{max_steps} | {dist_str}"
        )
        title_text.set_color(title_color)

        # Slow camera rotation for visual appeal
        ax.view_init(elev=25, azim=45 + step * 0.03)

        return []

    logger.info("Rendering %d frames to MP4 at %d fps, %d dpi...", max_steps, fps, dpi)
    logger.info("Estimated video duration: %.1f seconds", max_steps / fps)
    t0 = time.time()

    anim = FuncAnimation(fig, update, frames=max_steps, blit=False, interval=1000 // fps)

    writer = FFMpegWriter(fps=fps, bitrate=5000, codec="h264",
                          extra_args=["-pix_fmt", "yuv420p"])

    anim.save(str(output_path), writer=writer, dpi=dpi)

    elapsed = time.time() - t0
    file_size = output_path.stat().st_size / (1024 * 1024)
    logger.info("MP4 saved: %s (%.1f MB, rendered in %.1fs)", output_path, file_size, elapsed)

    plt.close(fig)
    return file_size


def main():
    result = run_pipeline()

    per_robot_passes = result.get("per_robot_passes", {})
    node_assignments = result.get("node_assignments", {})

    print(f"\n{'='*70}")
    print(f"6-ROBOT RESULTS: {sum(len(v) for v in node_assignments.values())} nodes assigned")
    for r in sorted(node_assignments.keys()):
        n_nodes = sum(len(v) for v in per_robot_passes.get(r, {}).values())
        print(f"  Robot {r}: {len(node_assignments[r])} assigned, "
              f"{len(per_robot_passes.get(r, {}))} passes, {n_nodes} printed")
    print(f"{'='*70}\n")

    output_path = DOWNLOADS / "ctr_6robot_parallel.mp4"
    render_mp4(result, output_path, fps=30, dpi=150)

    print(f"\nVideo saved to: {output_path}")


if __name__ == "__main__":
    main()
