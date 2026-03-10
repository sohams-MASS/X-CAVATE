"""Backward-compatible CLI for X-CAVATE.

Mirrors the original argparse interface from xcavate.py (lines 41-99) so that
existing command-line invocations continue to work.  Converts parsed arguments
into an ``XcavateConfig`` dataclass and delegates to the pipeline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from xcavate.config import OverlapAlgorithm, PathfindingAlgorithm, PrinterType, XcavateConfig


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser with all original flags."""
    p = argparse.ArgumentParser(
        prog="xcavate",
        description="X-CAVATE: Convert vascular network geometry into 3D printer G-code.",
    )

    # --- Required ---
    p.add_argument("--network_file", type=str, required=True,
                    help="Path to .txt file containing network coordinates")
    p.add_argument("--inletoutlet_file", type=str, required=True,
                    help="Path to .txt file containing inlet and outlet coordinates")
    p.add_argument("--multimaterial", type=int, required=True,
                    help="Multimaterial? (1=yes, 0=no)")
    p.add_argument("--tolerance_flag", type=float, required=True, default=0,
                    help="Include tolerance? (1=yes, 0=no)")
    p.add_argument("--tolerance", type=float, required=False, default=0,
                    help="Amount of tolerance (0 is none)")
    p.add_argument("--nozzle_diameter", type=float, required=True,
                    help="Outer diameter of nozzle (mm)")
    p.add_argument("--container_height", type=float, required=True,
                    help="Height of print container (mm)")
    p.add_argument("--num_decimals", type=int, required=True,
                    help="Number of decimal places for rounding output values")
    p.add_argument("--speed_calc", type=int, required=True,
                    help="Compute print speeds for changing radii? (1=yes, 0=no)")
    p.add_argument("--plots", type=int, required=True,
                    help="Generate plots? (1=yes, 0=no)")
    p.add_argument("--downsample", type=int, required=True,
                    help="Downsample network at end? (1=yes, 0=no)")
    p.add_argument("--custom", type=int, required=True,
                    help="Providing custom G-code? (1=yes, 0=no)")
    p.add_argument("--printer_type", type=int, required=True, default=0,
                    help="Type of printer: 0=Pressure, 1=Positive Ink, 2=Aerotech")

    # --- Geometry ---
    p.add_argument("--container_x", type=float, default=50, help="Container x-dimension (mm)")
    p.add_argument("--container_y", type=float, default=50, help="Container y-dimension (mm)")
    p.add_argument("--scale_factor", type=float, default=1, help="Network scale factor")
    p.add_argument("--top_padding", type=float, default=0, help="Padding above network (mm)")

    # --- Downsampling ---
    p.add_argument("--downsample_factor", type=int, default=1, help="Downsample factor")

    # --- Print settings ---
    p.add_argument("--flow", type=float, default=0.1609429886081009,
                    help="Volumetric flow rate (mm^3/s)")
    p.add_argument("--print_speed", type=float, default=1, help="Print speed (mm/s)")
    p.add_argument("--jog_speed", type=float, default=5, help="Jog speed (mm/s)")
    p.add_argument("--jog_speed_lift", type=float, default=0.25,
                    help="Z-lift jog speed (mm/s)")
    p.add_argument("--initial_lift", type=float, default=0.5,
                    help="Initial lift distance (mm)")
    p.add_argument("--jog_translation", type=float, default=10,
                    help="Jog speed between nozzles (mm/s)")
    p.add_argument("--dwell_start", type=float, default=0.08, help="Dwell at start (s)")
    p.add_argument("--dwell_end", type=float, default=0.08, help="Dwell at end (s)")
    p.add_argument("--amount_up", type=float, required=True, default=10,
                    help="Z-raise above container for nozzle switches (mm)")

    # --- Multimaterial ---
    p.add_argument("--offset_x", type=float, default=103, help="Printhead x-offset (mm)")
    p.add_argument("--offset_y", type=float, default=0.5, help="Printhead y-offset (mm)")
    p.add_argument("--front_nozzle", type=int, default=1,
                    help="1 if venous nozzle in front, 2 if behind")
    p.add_argument("--printhead_1", type=str, default="Aa", help="Arterial printhead name")
    p.add_argument("--printhead_2", type=str, default="Ab", help="Venous printhead name")
    p.add_argument("--axis_1", type=str, default="A", help="Arterial z-axis name")
    p.add_argument("--axis_2", type=str, default="B", help="Venous z-axis name")
    p.add_argument("--resting_pressure", type=float, default=0,
                    help="Resting pressure (psi)")
    p.add_argument("--active_pressure", type=float, default=5,
                    help="Active pressure (psi)")

    # --- Gap closure ---
    p.add_argument("--num_overlap", type=int, default=0, help="Overlap nodes")
    p.add_argument("--overlap_algorithm", type=str, default="retrace",
                    choices=["retrace", "consecutive"],
                    help="Overlap algorithm: 'retrace' (original) or 'consecutive' (fast)")
    p.add_argument("--close_sm", type=int, default=0,
                    help="Gap closure file for single material? (1=yes, 0=no)")
    p.add_argument("--close_mm", type=int, default=0,
                    help="Gap closure file for multimaterial? (1=yes, 0=no)")

    # --- Positive ink displacement ---
    p.add_argument("--positiveInk_start", type=float, default=0)
    p.add_argument("--positiveInk_end", type=float, default=0)
    p.add_argument("--positiveInk_radii", type=int, default=0)
    p.add_argument("--positiveInk_diam", type=float, default=1)
    p.add_argument("--positiveInk_syringe_diam", type=float, default=1)
    p.add_argument("--positiveInk_factor", type=float, default=1)
    p.add_argument("--positiveInk_start_arterial", type=float, default=0)
    p.add_argument("--positiveInk_start_venous", type=float, default=0)
    p.add_argument("--positiveInk_end_arterial", type=float, default=0)
    p.add_argument("--positiveInk_end_venous", type=float, default=0)

    # --- New flags (not in original) ---
    p.add_argument("--algorithm", type=str, default="dfs",
                    choices=["dfs", "sweep_line"],
                    help="Pathfinding algorithm (default: dfs)")
    p.add_argument("--output_dir", type=str, default="outputs",
                    help="Output directory (default: outputs)")

    return p


def args_to_config(args: argparse.Namespace) -> XcavateConfig:
    """Convert parsed argparse namespace to an XcavateConfig."""
    return XcavateConfig(
        network_file=Path(args.network_file),
        inletoutlet_file=Path(args.inletoutlet_file),
        nozzle_diameter=args.nozzle_diameter,
        container_height=args.container_height,
        num_decimals=args.num_decimals,
        amount_up=args.amount_up,
        multimaterial=bool(args.multimaterial),
        tolerance_flag=bool(args.tolerance_flag),
        tolerance=args.tolerance,
        speed_calc=bool(args.speed_calc),
        generate_plots=bool(args.plots),
        downsample=bool(args.downsample),
        custom_gcode=bool(args.custom),
        printer_type=PrinterType(args.printer_type),
        algorithm=PathfindingAlgorithm(args.algorithm),
        scale_factor=args.scale_factor,
        top_padding=args.top_padding,
        container_x=args.container_x,
        container_y=args.container_y,
        downsample_factor=args.downsample_factor,
        flow=args.flow,
        print_speed=args.print_speed,
        jog_speed=args.jog_speed,
        jog_speed_lift=args.jog_speed_lift,
        jog_translation=args.jog_translation,
        initial_lift=args.initial_lift,
        dwell_start=args.dwell_start,
        dwell_end=args.dwell_end,
        offset_x=args.offset_x,
        offset_y=args.offset_y,
        front_nozzle=args.front_nozzle,
        printhead_1=args.printhead_1,
        printhead_2=args.printhead_2,
        axis_1=args.axis_1,
        axis_2=args.axis_2,
        resting_pressure=args.resting_pressure,
        active_pressure=args.active_pressure,
        num_overlap=args.num_overlap,
        overlap_algorithm=OverlapAlgorithm(args.overlap_algorithm),
        close_sm=bool(args.close_sm),
        close_mm=bool(args.close_mm),
        positive_ink_start=args.positiveInk_start,
        positive_ink_end=args.positiveInk_end,
        positive_ink_radii=bool(args.positiveInk_radii),
        positive_ink_diam=args.positiveInk_diam,
        positive_ink_syringe_diam=args.positiveInk_syringe_diam,
        positive_ink_factor=args.positiveInk_factor,
        positive_ink_start_arterial=args.positiveInk_start_arterial,
        positive_ink_start_venous=args.positiveInk_start_venous,
        positive_ink_end_arterial=args.positiveInk_end_arterial,
        positive_ink_end_venous=args.positiveInk_end_venous,
        output_dir=Path(args.output_dir),
    )


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``python -m xcavate`` and the ``xcavate`` console script."""
    parser = build_parser()
    args = parser.parse_args(argv)
    config = args_to_config(args)

    from xcavate.pipeline import run_xcavate
    run_xcavate(config)


if __name__ == "__main__":
    main()
