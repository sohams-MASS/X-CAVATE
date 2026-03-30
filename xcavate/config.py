"""Configuration dataclass replacing 30+ global variables from the original xcavate.py."""

from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from typing import Optional


class PrinterType(Enum):
    """Supported printer types for G-code generation."""
    PRESSURE = 0        # Pressure-based extrusion
    POSITIVE_INK = 1    # Positive ink displacement
    AEROTECH = 2        # Aerotech 6-axis controller


class PathfindingAlgorithm(Enum):
    """Available pathfinding strategies."""
    DFS = "dfs"                # Modified depth-first search (original algorithm)


class OverlapAlgorithm(Enum):
    """Available overlap algorithms."""
    RETRACE = "retrace"        # Original: scan all previous passes, retrace backwards


@dataclass
class XcavateConfig:
    """All configuration parameters for an X-CAVATE run.

    Replaces the 30+ global variables scattered across xcavate.py lines 101-171.
    Organized into logical groups: required, geometry, print settings,
    multimaterial, gap closure, positive ink displacement, and paths.
    """

    # --- Required parameters ---
    network_file: Path
    inletoutlet_file: Path
    nozzle_diameter: float          # mm, inner diameter
    container_height: float         # mm
    num_decimals: int               # decimal places for output rounding
    amount_up: float = 10.0         # mm above container to raise nozzle between passes

    # --- Feature flags ---
    multimaterial: bool = False
    tolerance_flag: bool = False
    speed_calc: bool = False
    generate_plots: bool = True
    downsample: bool = False
    custom_gcode: bool = False
    printer_type: PrinterType = PrinterType.PRESSURE
    algorithm: PathfindingAlgorithm = PathfindingAlgorithm.DFS

    # --- Geometry ---
    tolerance: float = 0.0
    scale_factor: float = 1.0
    top_padding: float = 0.0       # mm above network top
    container_x: float = 50.0      # mm
    container_y: float = 50.0      # mm
    convert_factor: float = 10.0   # cm -> mm

    # --- Downsampling ---
    downsample_factor: int = 1

    # --- Print settings ---
    flow: float = 0.1609429886081009  # mm^3/s; experimentally determined
    print_speed: float = 1.0         # mm/s
    jog_speed: float = 5.0           # mm/s
    jog_speed_lift: float = 0.25     # mm/s for initial z-lift
    jog_translation: float = 10.0    # mm/s between nozzles
    initial_lift: float = 0.5        # mm
    dwell_start: float = 0.08        # seconds
    dwell_end: float = 0.08          # seconds

    # --- Multimaterial ---
    offset_x: float = 103.0          # mm between printheads in x
    offset_y: float = 0.5            # mm between printheads in y
    front_nozzle: int = 1            # 1=venous in front, 2=venous behind
    printhead_1: str = "Aa"          # arterial printhead name
    printhead_2: str = "Ab"          # venous printhead name
    axis_1: str = "A"                # arterial z-axis name
    axis_2: str = "B"                # venous z-axis name
    resting_pressure: float = 0.0    # psi
    active_pressure: float = 5.0     # psi

    # --- Graph construction ---
    branchpoint_distance_threshold: float = 0.0  # mm; 0 = disabled (legacy)

    # --- Gap closure ---
    num_overlap: int = 0
    overlap_algorithm: OverlapAlgorithm = OverlapAlgorithm.RETRACE
    close_sm: bool = False           # single-material gap file
    close_mm: bool = False           # multimaterial gap file

    # --- Positive ink displacement ---
    positive_ink_start: float = 0.0
    positive_ink_end: float = 0.0
    positive_ink_radii: bool = False
    positive_ink_diam: float = 1.0
    positive_ink_syringe_diam: float = 1.0
    positive_ink_factor: float = 1.0
    positive_ink_shift: float = 0.0          # mm radius shift (calibration)
    positive_ink_start_arterial: float = 0.0
    positive_ink_start_venous: float = 0.0
    positive_ink_end_arterial: float = 0.0
    positive_ink_end_venous: float = 0.0

    # --- Paths ---
    custom_gcode_dir: Path = field(default_factory=lambda: Path("inputs/custom"))
    extension_dir: Path = field(default_factory=lambda: Path("inputs/extension"))
    output_dir: Path = field(default_factory=lambda: Path("outputs"))

    @property
    def nozzle_radius(self) -> float:
        """Half the nozzle outer diameter, used for collision detection."""
        return self.nozzle_diameter / 2.0

    @property
    def graph_dir(self) -> Path:
        return self.output_dir / "graph"

    @property
    def gcode_dir(self) -> Path:
        return self.output_dir / "gcode"

    @property
    def plots_dir(self) -> Path:
        return self.output_dir / "plots"

    def ensure_output_dirs(self):
        """Create output directories if they don't exist."""
        for d in [self.graph_dir, self.gcode_dir, self.plots_dir]:
            d.mkdir(parents=True, exist_ok=True)
