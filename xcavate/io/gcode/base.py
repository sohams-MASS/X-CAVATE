"""Abstract base class for G-code generation.

All printer types share: header/footer structure, pass iteration loop,
gap closure extension segments, start/stop extrusion patterns. Subclasses
implement printer-specific commands.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, TextIO
import numpy as np

from xcavate.config import XcavateConfig


@dataclass
class CustomCodes:
    """Custom G-code snippets loaded once from template files.

    Replaces the pattern of opening/reading the same template file dozens
    of times throughout the original code.
    """
    header: str = ""
    start_extrusion: str = ""
    stop_extrusion: str = ""
    start_extrusion_ph1: str = ""
    start_extrusion_ph2: str = ""
    stop_extrusion_ph1: str = ""
    stop_extrusion_ph2: str = ""
    active_pressure_ph1: str = ""
    active_pressure_ph2: str = ""
    rest_pressure_ph1: str = ""
    rest_pressure_ph2: str = ""
    dwell_code: str = ""

    @classmethod
    def load_from_dir(cls, custom_dir: Path) -> "CustomCodes":
        """Load all custom G-code templates from a directory."""
        def _read(filename: str) -> str:
            path = custom_dir / filename
            if path.exists():
                return path.read_text()
            return ""

        return cls(
            header=_read("header_code.txt"),
            start_extrusion=_read("start_extrusion_code.txt"),
            stop_extrusion=_read("stop_extrusion_code.txt"),
            start_extrusion_ph1=_read("start_extrusion_code_printhead1.txt"),
            start_extrusion_ph2=_read("start_extrusion_code_printhead2.txt"),
            stop_extrusion_ph1=_read("stop_extrusion_code_printhead1.txt"),
            stop_extrusion_ph2=_read("stop_extrusion_code_printhead2.txt"),
            active_pressure_ph1=_read("active_pressure_printhead1.txt"),
            active_pressure_ph2=_read("active_pressure_printhead2.txt"),
            rest_pressure_ph1=_read("rest_pressure_printhead1.txt"),
            rest_pressure_ph2=_read("rest_pressure_printhead2.txt"),
            dwell_code=_read("dwell_code.txt"),
        )


@dataclass
class GapExtension:
    """Gap closure extension data for a single pass."""
    delta_x: float
    delta_y: float
    delta_z: float


class GcodeWriter(ABC):
    """Base class for G-code generation.

    Subclasses implement printer-specific commands for pass start, moves,
    pass end, and printhead switching. The shared iteration loop, header/footer,
    and gap extension logic live here.
    """

    def __init__(self, config: XcavateConfig, custom_codes: Optional[CustomCodes] = None):
        self.config = config
        self.codes = custom_codes

    def write(
        self,
        output_path: Path,
        print_passes: Dict[int, List[int]],
        points: np.ndarray,
        speed_map: Optional[Dict[int, float]] = None,
        material_map: Optional[Dict[int, int]] = None,
        gap_extensions: Optional[Dict[int, GapExtension]] = None,
        network_top: float = 0.0,
    ):
        """Write complete G-code file.

        Args:
            output_path: Path to write G-code.
            print_passes: Ordered passes {idx: [node_indices]}.
            points: Coordinate array.
            speed_map: Optional per-node speed overrides.
            material_map: Optional per-pass material (0=venous, 1=arterial).
            gap_extensions: Optional per-pass gap closure extensions.
            network_top: Z-coordinate of network top (for lift height).
        """
        nd = self.config.num_decimals
        with open(output_path, "w") as f:
            self._write_header(f)
            self._write_network(
                f, print_passes, points, nd, speed_map,
                material_map, gap_extensions, network_top,
            )
            self._write_footer(f, network_top)

    def _write_header(self, f: TextIO):
        f.write(";=========== Begin GCODE ============= \n")
        if self.config.custom_gcode and self.codes:
            f.write(self.codes.header + "\n")

    def _write_footer(self, f: TextIO, network_top: float):
        f.write("G90 \n")
        f.write(f"G1 {self.config.axis_1}{self.config.container_height + self.config.amount_up} \n")

    def _write_network(
        self,
        f: TextIO,
        print_passes: Dict[int, List[int]],
        points: np.ndarray,
        nd: int,
        speed_map: Optional[Dict[int, float]],
        material_map: Optional[Dict[int, int]],
        gap_extensions: Optional[Dict[int, GapExtension]],
        network_top: float,
    ):
        """Shared pass iteration loop for all printer types."""
        gap_tracker = 0
        for i in range(len(print_passes)):
            for j_counter, j in enumerate(print_passes[i]):
                x = round(points[j, 0], nd)
                y = round(points[j, 1], nd)
                z = round(points[j, 2], nd)
                speed = speed_map[j] if speed_map else self.config.print_speed

                artven = 0
                if material_map is not None:
                    artven = material_map.get(i, 0)

                if j_counter == 0 and i == 0:
                    self._write_first_pass_start(f, x, y, z, speed, artven)
                elif j_counter == 0:
                    prev_point = print_passes[i - 1][-1]
                    prev_x = round(points[prev_point, 0], nd)
                    prev_y = round(points[prev_point, 1], nd)
                    self._write_pass_start(f, i, x, y, z, speed, artven, prev_x, prev_y)
                else:
                    self._write_move(f, j, j_counter, x, y, z, speed, points, nd, print_passes[i])

            # Gap closure extension
            if gap_extensions and i in gap_extensions:
                ext = gap_extensions[i]
                f.write(";##### Extra segment #####\n")
                f.write("G91\n")
                f.write(f"G1 X{ext.delta_x} Y{ext.delta_y} Z{ext.delta_z} F{speed}\n")
                f.write("G90\n")
                f.write(";########################\n")
                gap_tracker += 1

            self._write_pass_end(f, network_top)

    @abstractmethod
    def _write_first_pass_start(self, f: TextIO, x, y, z, speed, artven): ...

    @abstractmethod
    def _write_pass_start(self, f: TextIO, pass_idx, x, y, z, speed, artven, prev_x, prev_y): ...

    @abstractmethod
    def _write_move(self, f: TextIO, node, j_counter, x, y, z, speed, points, nd, pass_nodes): ...

    @abstractmethod
    def _write_pass_end(self, f: TextIO, network_top: float): ...
