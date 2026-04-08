"""Configuration dataclass replacing 30+ global variables from the original xcavate.py."""

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from enum import Enum
from typing import Optional


class SpeedUnit(Enum):
    """Speed units for G-code F parameter."""
    MM_PER_MIN = "mm/min"   # Most G-code printers
    MM_PER_S = "mm/s"       # Aerotech and some controllers


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
    speed_unit: SpeedUnit = SpeedUnit.MM_PER_MIN
    automation1: bool = False            # Automation1 Aerotech program wrapper
    algorithm: PathfindingAlgorithm = PathfindingAlgorithm.DFS
    reorder_passes: bool = False

    # --- Geometry ---
    tolerance: float = 0.0
    scale_factor: float = 1.0
    top_padding: float = 0.0       # mm above network top
    container_x: float = 50.0      # mm
    container_y: float = 50.0      # mm
    convert_factor: float = 1.0    # unit conversion (1.0 = input in mm; 10.0 = input in cm)

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
    gap_extension_size: float = 0.0  # mm; auto-extend passes at endpoints (0 = disabled)
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

    def to_dict(self) -> dict:
        """Serialize config to a JSON-safe dictionary."""
        d = {}
        for f in fields(self):
            val = getattr(self, f.name)
            if isinstance(val, Path):
                d[f.name] = str(val)
            elif isinstance(val, Enum):
                d[f.name] = val.value
            else:
                d[f.name] = val
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, d: dict) -> "XcavateConfig":
        """Deserialize config from a dictionary."""
        d = dict(d)  # copy
        if "printer_type" in d:
            d["printer_type"] = PrinterType(d["printer_type"])
        if "speed_unit" in d:
            d["speed_unit"] = SpeedUnit(d["speed_unit"])
        if "algorithm" in d:
            d["algorithm"] = PathfindingAlgorithm(d["algorithm"])
        if "overlap_algorithm" in d:
            d["overlap_algorithm"] = OverlapAlgorithm(d["overlap_algorithm"])
        for path_field in ("network_file", "inletoutlet_file", "custom_gcode_dir",
                           "extension_dir", "output_dir"):
            if path_field in d and isinstance(d[path_field], str):
                d[path_field] = Path(d[path_field])
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json(cls, json_str: str) -> "XcavateConfig":
        return cls.from_dict(json.loads(json_str))
