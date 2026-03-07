"""Pipeline orchestrator: wires all modules into the full X-CAVATE workflow.

``run_xcavate(config)`` is the single entry point that replaces the monolithic
5568-line script.  It performs the following stages:

1. Read and preprocess network geometry
2. Interpolate to nozzle-radius resolution
3. Build the vascular adjacency graph
4. Generate collision-free print passes
5. Subdivide, gap-close, downsample, overlap, and reorder passes
6. (Optional) Multimaterial splitting
7. Write coordinate outputs, plots, and G-code
"""

from __future__ import annotations

import copy
import logging
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

from xcavate.config import PrinterType, XcavateConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Callback type for progress reporting (used by GUI)
# ---------------------------------------------------------------------------
ProgressCallback = Optional[Callable[[int, str], None]]


def run_xcavate(
    config: XcavateConfig,
    progress_cb: ProgressCallback = None,
) -> dict:
    """Execute the full X-CAVATE pipeline.

    Args:
        config: Fully populated configuration.
        progress_cb: Optional callback ``(step_number, description)`` for GUI
            progress bars.  Steps are numbered 1-7.

    Returns:
        Dict with keys:
            - ``print_passes_sm``: Single-material passes.
            - ``print_passes_mm``: Multimaterial passes (or None).
            - ``points``: Interpolated coordinate array.
            - ``changelog``: List of changelog lines.
            - ``speed_map_sm``: Speed map for SM (or None).
            - ``speed_map_mm``: Speed map for MM (or None).
            - ``material_map``: Material classification (or None).
    """
    from xcavate.io.reader import (
        read_network_file,
        read_inlet_outlet_file,
        preprocess_coordinates,
        match_inlet_outlet_nodes,
    )
    from xcavate.core.preprocessing import interpolate_network, get_vessel_boundaries
    from xcavate.core.graph import build_graph, write_special_nodes, write_graph
    from xcavate.core.pathfinding import generate_print_passes
    from xcavate.core.postprocessing import (
        subdivide_passes,
        downsample_passes,
        add_overlap,
        reorder_passes_nearest_neighbor,
    )
    from xcavate.core.gap_closure import run_full_gap_closure_pipeline
    from xcavate.core.multimaterial import (
        classify_passes_by_material,
        compute_radius_speeds,
    )
    from xcavate.io.writer import write_pass_coordinates, write_changelog
    from xcavate.io.gcode.base import CustomCodes
    from xcavate.io.gcode.pressure import PressureGcodeWriter
    from xcavate.io.gcode.positive_ink import PositiveInkGcodeWriter
    from xcavate.io.gcode.aerotech import AerotechGcodeWriter
    from xcavate.viz.plotting import create_network_plot

    def _progress(step: int, msg: str) -> None:
        logger.info("Step %d/7: %s", step, msg)
        if progress_cb:
            progress_cb(step, msg)

    config.ensure_output_dirs()
    t0 = time.time()

    # ── Step 1: Read and preprocess ──────────────────────────────────────
    _progress(1, "Reading network and inlet/outlet files")

    points_raw, coord_num_dict = read_network_file(config.network_file)
    inlets_raw, outlets_raw = read_inlet_outlet_file(config.inletoutlet_file)
    num_columns = points_raw.shape[1]

    points, inlets, outlets, _num_decimals_raw = preprocess_coordinates(
        points_raw, inlets_raw, outlets_raw, config,
    )

    inlet_nodes, outlet_nodes = match_inlet_outlet_nodes(
        points, inlets, outlets,
    )

    logger.info(
        "Loaded network: %d points, %d vessels, %d inlets, %d outlets",
        points.shape[0], len(coord_num_dict), len(inlet_nodes), len(outlet_nodes),
    )

    # ── Step 2: Interpolate ──────────────────────────────────────────────
    _progress(2, "Interpolating network to nozzle resolution")

    points_interp = interpolate_network(
        points, coord_num_dict, config.nozzle_radius, num_columns,
    )

    boundaries = get_vessel_boundaries(points_interp, coord_num_dict)
    coord_num_dict_interp = {v: info["count"] for v, info in boundaries.items()}
    vessel_start_nodes = [info["start"] for v, info in sorted(boundaries.items())]

    # Extract xyz for graph building (strip flag column)
    points_xyz = points_interp[:, :3].copy()

    logger.info("Interpolated: %d -> %d points", points.shape[0], points_xyz.shape[0])

    # ── Step 3: Build graph ──────────────────────────────────────────────
    _progress(3, "Building adjacency graph and detecting branchpoints")

    (
        graph,
        branch_dict,
        branchpoint_list,
        branchpoint_daughter_dict,
        endpoint_nodes,
        nodes_by_vessel,
        repeat_daughters,
    ) = build_graph(
        points_xyz, coord_num_dict_interp, vessel_start_nodes,
        inlet_nodes, outlet_nodes,
    )

    # Write diagnostic files
    write_special_nodes(
        str(config.graph_dir / "special_nodes.txt"),
        inlet_nodes, outlet_nodes, endpoint_nodes,
        list(branch_dict.keys()), branchpoint_list,
    )
    write_graph(str(config.graph_dir / "graph.txt"), graph)

    # ── Step 4: Generate print passes ────────────────────────────────────
    _progress(4, "Generating collision-free print passes")

    raw_passes = generate_print_passes(graph, points_xyz, config)

    logger.info("Generated %d raw print passes", len(raw_passes))

    # ── Step 5: Post-process passes ──────────────────────────────────────
    _progress(5, "Post-processing: subdivision, gap closure, overlap")

    # Subdivide at DFS backtrack points
    passes_subdivided = subdivide_passes(raw_passes, graph, points_xyz)

    # Gap closure
    branchpoint_list_keys = list(branch_dict.keys())
    arbitrary_val = 999999999

    passes_closed, changelog = run_full_gap_closure_pipeline(
        passes_subdivided, graph,
        branch_dict, branchpoint_list, branchpoint_list_keys,
        branchpoint_daughter_dict, endpoint_nodes,
        inlet_nodes, outlet_nodes,
        repeat_daughters, arbitrary_val,
    )

    # Write changelog
    write_changelog(config.output_dir, changelog)

    # Single-material passes (copy before multimaterial processing)
    print_passes_sm = copy.deepcopy(passes_closed)

    # Optional downsampling
    if config.downsample and config.downsample_factor > 1:
        print_passes_sm = downsample_passes(
            print_passes_sm, points_interp, config.downsample_factor,
            branchpoint_list, branchpoint_list_keys, endpoint_nodes,
        )

    # Optional overlap
    if config.num_overlap > 0:
        print_passes_sm = add_overlap(print_passes_sm, config.num_overlap, graph)

    # Reorder for minimal travel
    print_passes_sm = reorder_passes_nearest_neighbor(print_passes_sm, points_interp)

    # Speed computation
    speed_map_sm = None
    if config.speed_calc:
        speed_map_sm = compute_radius_speeds(
            print_passes_sm, points_interp, config.flow, num_columns,
        )

    # ── Step 6: Multimaterial ────────────────────────────────────────────
    print_passes_mm = None
    speed_map_mm = None
    material_map = None

    if config.multimaterial and num_columns >= 5:
        _progress(6, "Processing multimaterial passes")

        print_passes_mm = copy.deepcopy(passes_closed)

        # Classify by material
        material_map = classify_passes_by_material(
            print_passes_mm, points_interp, num_columns,
        )

        # Subdivide at material boundaries
        _subdivide_by_material(print_passes_mm, material_map, points_interp, num_columns)

        # Downsample
        if config.downsample and config.downsample_factor > 1:
            print_passes_mm = downsample_passes(
                print_passes_mm, points_interp, config.downsample_factor,
                branchpoint_list, branchpoint_list_keys, endpoint_nodes,
            )

        # Overlap
        if config.num_overlap > 0:
            print_passes_mm = add_overlap(print_passes_mm, config.num_overlap, graph)

        # Re-classify after subdivision
        material_map = classify_passes_by_material(
            print_passes_mm, points_interp, num_columns,
        )

        # Speed
        if config.speed_calc:
            speed_map_mm = compute_radius_speeds(
                print_passes_mm, points_interp, config.flow, num_columns,
            )
    else:
        _progress(6, "Skipping multimaterial (not enabled)")

    # ── Step 7: Output ───────────────────────────────────────────────────
    _progress(7, "Writing output files and G-code")

    # Coordinate output files
    write_pass_coordinates(
        config.graph_dir, "SM",
        print_passes_sm, points_interp, config.num_decimals, num_columns,
        speed_map_sm, arbitrary_val,
    )

    if print_passes_mm is not None:
        write_pass_coordinates(
            config.graph_dir, "MM",
            print_passes_mm, points_interp, config.num_decimals, num_columns,
            speed_map_mm, arbitrary_val,
        )

    # Plots
    if config.generate_plots:
        _write_plots(
            config, print_passes_sm, print_passes_mm,
            points_interp, material_map,
        )

    # Compute network top for G-code
    network_top = float(np.max(points_xyz[:, 2])) + config.top_padding

    # Load custom G-code templates if needed
    custom_codes = None
    if config.custom_gcode:
        custom_codes = CustomCodes.load_from_dir(config.custom_gcode_dir)

    # Load gap extension data if needed
    gap_ext_sm = _load_gap_extensions(config, "SM") if config.close_sm else None
    gap_ext_mm = _load_gap_extensions(config, "MM") if config.close_mm else None

    # G-code: single material
    writer = _create_gcode_writer(config, custom_codes)
    writer.write(
        config.gcode_dir / f"gcode_SM_{config.printer_type.name.lower()}.txt",
        print_passes_sm, points_interp,
        speed_map=speed_map_sm,
        gap_extensions=gap_ext_sm,
        network_top=network_top,
    )

    # G-code: multimaterial
    if print_passes_mm is not None:
        writer_mm = _create_gcode_writer(config, custom_codes)
        writer_mm.write(
            config.gcode_dir / f"gcode_MM_{config.printer_type.name.lower()}.txt",
            print_passes_mm, points_interp,
            speed_map=speed_map_mm,
            material_map=material_map,
            gap_extensions=gap_ext_mm,
            network_top=network_top,
        )

    elapsed = time.time() - t0
    logger.info("X-CAVATE completed in %.1f seconds", elapsed)
    print(f"\nX-CAVATE completed in {elapsed:.1f}s. Output in {config.output_dir}/")

    return {
        "print_passes_sm": print_passes_sm,
        "print_passes_mm": print_passes_mm,
        "points": points_interp,
        "changelog": changelog,
        "speed_map_sm": speed_map_sm,
        "speed_map_mm": speed_map_mm,
        "material_map": material_map,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _create_gcode_writer(config: XcavateConfig, custom_codes):
    """Instantiate the appropriate G-code writer for the configured printer."""
    if config.printer_type == PrinterType.PRESSURE:
        return PressureGcodeWriter(config, custom_codes)
    elif config.printer_type == PrinterType.POSITIVE_INK:
        return PositiveInkGcodeWriter(config, custom_codes)
    elif config.printer_type == PrinterType.AEROTECH:
        return AerotechGcodeWriter(config, custom_codes)
    else:
        raise ValueError(f"Unknown printer type: {config.printer_type}")


def _subdivide_by_material(
    print_passes: Dict[int, List[int]],
    material_map: Dict[int, int],
    points: np.ndarray,
    num_columns: int,
) -> None:
    """Subdivide passes at arterial/venous boundaries (in-place).

    Replaces xcavate.py lines 3358-3589.  When a pass contains nodes of
    different material types, it is split at the transition points.
    """
    if num_columns < 5:
        return

    # Swap outlier artven values at pass boundaries
    for i in list(print_passes.keys()):
        nodes = print_passes[i]
        if len(nodes) < 3:
            continue
        artven = [int(points[n, 4]) for n in nodes]
        # Swap first node if it disagrees with the next two
        if artven[1] == artven[2] and artven[0] != artven[1]:
            artven[0] = artven[1]
        # Swap last node if it disagrees with the previous two
        if artven[-2] == artven[-3] and artven[-1] != artven[-2]:
            artven[-1] = artven[-2]
        # Swap interior nodes surrounded by same type
        for j in range(1, len(artven) - 1):
            if artven[j - 1] == artven[j + 1] and artven[j] != artven[j - 1]:
                artven[j] = artven[j - 1]

    # Find material transition break points
    break_points = {}
    for i in list(print_passes.keys()):
        nodes = print_passes[i]
        if len(nodes) < 3:
            continue
        artven = [int(points[n, 4]) for n in nodes]
        breaks = []
        for j in range(1, len(artven)):
            if artven[j] != artven[j - 1]:
                breaks.append(nodes[j])
        if breaks:
            break_points[i] = breaks

    if not break_points:
        return

    # Split passes at break points
    new_matrix = {}
    for i in break_points:
        new_passes = {}
        start = 0
        for counter, bp in enumerate(break_points[i]):
            bp_idx = print_passes[i].index(bp)
            new_passes[counter] = print_passes[i][start:bp_idx]
            start = bp_idx
        new_passes[len(break_points[i])] = print_passes[i][start:]
        new_matrix[i] = new_passes

    # Reassemble with new indices
    num_new = sum(len(v) for v in new_matrix.values()) - len(new_matrix)
    num_total = len(print_passes) + num_new
    result = {}
    counter = 0
    counter_old = 0
    while counter < num_total:
        if counter_old in new_matrix:
            for sub_idx in range(len(new_matrix[counter_old])):
                result[counter] = new_matrix[counter_old][sub_idx]
                counter += 1
            counter_old += 1
        else:
            result[counter] = print_passes[counter_old]
            counter += 1
            counter_old += 1

    # Update in place
    print_passes.clear()
    print_passes.update(result)


def _load_gap_extensions(config: XcavateConfig, suffix: str):
    """Load gap extension data from input files if they exist."""
    from xcavate.io.gcode.base import GapExtension

    pass_file = config.extension_dir / f"pass_to_extend_{suffix}.txt"
    delta_file = config.extension_dir / f"deltas_to_extend_{suffix}.txt"

    if not pass_file.exists() or not delta_file.exists():
        return None

    extensions = {}
    with open(pass_file) as pf:
        pass_indices = [int(line.strip()) for line in pf if line.strip()]
    with open(delta_file) as df:
        deltas = []
        for line in df:
            parts = line.strip().split()
            if len(parts) >= 3:
                deltas.append((float(parts[0]), float(parts[1]), float(parts[2])))

    for idx, pass_num in enumerate(pass_indices):
        if idx < len(deltas):
            dx, dy, dz = deltas[idx]
            extensions[pass_num] = GapExtension(delta_x=dx, delta_y=dy, delta_z=dz)

    return extensions


def _write_plots(
    config: XcavateConfig,
    print_passes_sm: Dict[int, List[int]],
    print_passes_mm: Optional[Dict[int, List[int]]],
    points: np.ndarray,
    material_map: Optional[Dict[int, int]],
) -> None:
    """Generate and save interactive 3D plots."""
    from xcavate.viz.plotting import create_network_plot
    from xcavate.core.multimaterial import generate_multimaterial_colors

    # Single material plot
    fig_sm = create_network_plot(
        print_passes_sm, points, title="Single Material",
    )
    fig_sm.write_html(str(config.plots_dir / "network_SM.html"))

    # Multimaterial plot
    if print_passes_mm is not None and material_map is not None:
        colors = generate_multimaterial_colors(print_passes_mm, material_map)
        fig_mm = create_network_plot(
            print_passes_mm, points, title="Multimaterial", colors=colors,
        )
        fig_mm.write_html(str(config.plots_dir / "network_MM.html"))
