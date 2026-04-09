"""Automation1 Aerotech G-code writer.

Generates Aerotech G-code wrapped in the Automation1 program structure
with variable-relative coordinates, VelocityBlending/CornerRounding,
and DriveBrakeOn/Off function definitions for pressure dispensing.

Single material: StartExtrusion/StopExtrusion use a fixed axis.
Multimaterial: StartExtrusion/StopExtrusion accept the printhead axis
  (the hidden pressure dispensing axis) as a parameter.
"""

from typing import Dict, List, Optional, TextIO
import numpy as np

from xcavate.io.gcode.base import CustomCodes, GapExtension, GcodeWriter
from xcavate.config import XcavateConfig


class Automation1GcodeWriter(GcodeWriter):
    """G-code writer for Aerotech controllers using Automation1 program syntax."""

    def __init__(self, config: XcavateConfig, custom_codes: Optional[CustomCodes] = None):
        super().__init__(config, custom_codes)
        self._curr = 1  # default arterial
        self._curr_axis = config.axis_1
        self._curr_ph = config.printhead_1
        self._other_ph = config.printhead_2

    # -- Coordinate formatting --------------------------------------------------

    def _fx(self, x) -> str:
        return f"($X_start+{x})"

    def _fy(self, y) -> str:
        return f"($Y_start+{y})"

    def _fz(self, z) -> str:
        return f"($Z_print+{z})"

    # -- Header / Footer -------------------------------------------------------

    def _write_header(self, f: TextIO):
        cfg = self.config
        f.write("; Automation1 Aerotech program\n")
        if cfg.custom_gcode and self.codes:
            f.write(self.codes.header + "\n")
        f.write("\n")

    def _write_footer(self, f: TextIO, network_top: float):
        cfg = self.config
        nd = cfg.num_decimals
        f.write(f"G1 {cfg.axis_1} $Z_safe F $jog_speed \n")
        f.write("\n")

    def write(
        self,
        output_path,
        print_passes: Dict[int, List[int]],
        points: np.ndarray,
        speed_map=None,
        material_map=None,
        gap_extensions=None,
        network_top: float = 0.0,
    ):
        """Write complete Automation1 program file."""
        cfg = self.config
        nd = cfg.num_decimals
        mm = cfg.multimaterial
        with open(output_path, "w") as f:
            # -- Program wrapper --
            f.write("program\n")
            f.write(f"      var $X_start as real = 0\n")
            f.write(f"      var $Y_start as real = 0\n")
            f.write(f"      var $Z_print as real = 0\n")
            f.write(f"      var $Z_safe as real = $Z_print + {cfg.amount_up}\n")
            f.write(f"      var $jog_speed as real = {cfg.jog_speed}\n")
            if mm:
                f.write(f"      var $offset_x as real = {cfg.offset_x}\n")
                f.write(f"      var $offset_y as real = {cfg.offset_y}\n")
                f.write(f"      var $offset_z as real = {cfg.offset_z}\n")
                f.write(f"      var $lift_height as real = {cfg.container_height + cfg.amount_up}\n")
                f.write(f"      var $jog_translation as real = {cfg.jog_translation}\n")
                f.write(f"      var $dwell_start as real = {cfg.dwell_start}\n")
                f.write(f"      var $dwell_end as real = {cfg.dwell_end}\n")
            f.write("\n")
            f.write("      G90\n")
            f.write("      G1 X $X_start Y $Y_start F 20\n")
            f.write(f"      G1 {cfg.axis_1} $Z_safe F 10\n")
            f.write("      ProgramPause()\n")
            if mm:
                f.write("      print_network($jog_speed, $X_start, $Y_start, $Z_print, $Z_safe, "
                        "$offset_x, $offset_y, $offset_z, $lift_height, $jog_translation, $dwell_start, $dwell_end)\n")
            else:
                f.write("      print_network($jog_speed, $X_start, $Y_start, $Z_print, $Z_safe)\n")
            f.write("end\n\n")

            # -- Network function --
            if mm:
                f.write("function print_network($jog_speed as real, $X_start as real, "
                        "$Y_start as real, $Z_print as real, $Z_safe as real, "
                        "$offset_x as real, $offset_y as real, $offset_z as real, $lift_height as real, "
                        "$jog_translation as real, $dwell_start as real, $dwell_end as real)\n")
            else:
                f.write("function print_network($jog_speed as real, $X_start as real, "
                        "$Y_start as real, $Z_print as real, $Z_safe as real)\n")

            self._write_header(f)
            self._write_network(
                f, print_passes, points, nd, speed_map,
                material_map, gap_extensions, network_top,
            )
            self._write_footer(f, network_top)

            f.write("end\n\n")

            # -- StartExtrusion / StopExtrusion functions --
            self._write_extrusion_functions(f)

    def _write_extrusion_functions(self, f: TextIO):
        """Write StartExtrusion/StopExtrusion function definitions."""
        cfg = self.config
        if cfg.multimaterial:
            # Multimaterial: accept printhead axis and dwell as parameters
            f.write("function StartExtrusion($ph as axis, $dwell_start as real)\n")
            f.write("      DriveBrakeOff($ph)\n")
            f.write("      Dwell($dwell_start)\n")
            f.write("end\n\n")

            f.write("function StopExtrusion($Z_safe as real, $ph as axis, $dwell_end as real)\n")
            f.write("      DriveBrakeOn($ph)\n")
            f.write("      Dwell($dwell_end)\n")
            f.write(f"      G1 {cfg.axis_1} $Z_safe F 10\n")
            f.write("end\n\n")
        else:
            # Single material: fixed axis
            f.write("function StartExtrusion()\n")
            f.write(f"      DriveBrakeOff({cfg.printhead_1})\n")
            f.write(f"      Dwell({cfg.dwell_start})\n")
            f.write("end\n\n")

            f.write("function StopExtrusion($Z_safe as real)\n")
            f.write(f"      DriveBrakeOn({cfg.printhead_1})\n")
            f.write(f"      Dwell({cfg.dwell_end})\n")
            f.write(f"      G1 {cfg.axis_1} $Z_safe F 10\n")
            f.write("end\n\n")

    # -- Pass start / end / move ------------------------------------------------

    def _write_first_pass_start(self, f: TextIO, x, y, z, speed, artven):
        cfg = self.config
        f.write("; Print Pass 0 \n")

        if not cfg.multimaterial:
            f.write(f"G1 X {self._fx(x)} Y {self._fy(y)} F $jog_speed\n")
            f.write(f"G1 {cfg.axis_1} {self._fz(z)} F $jog_speed\n")
            f.write("VelocityBlendingOn()\n")
            f.write("CornerRoundingOn()\n")
            f.write("StartExtrusion()\n")
            f.write(f"G1 X {self._fx(x)} Y {self._fy(y)} {cfg.axis_1} {self._fz(z)} F {speed}\n")
            return

        # Multimaterial first pass
        if artven == 0 and self._curr == 1:
            # Switch to venous
            self._curr = 0
            self._curr_axis = cfg.axis_2
            self._curr_ph = cfg.printhead_2
            self._other_ph = cfg.printhead_1
            f.write("; moving to VENOUS \n")
            y_sign = "" if cfg.front_nozzle == 1 else "-"
            f.write(f"G91 G1 {cfg.axis_1} $lift_height "
                    f"{cfg.axis_2} $lift_height F $jog_speed \n")
            f.write(f"G91 G1 X (-$offset_x) F $jog_translation \n")
            f.write(f"G91 G1 Y ({y_sign}$offset_y) F $jog_speed \n")
            f.write(f"G91 G1 {cfg.axis_2} $offset_z F $jog_speed \n")
            f.write(f"G91 G1 {cfg.axis_1} (-$lift_height) "
                    f"{cfg.axis_2} (-$lift_height) F $jog_speed \n")
            f.write("G90 \n")

        f.write(f"G1 X {self._fx(x)} Y {self._fy(y)} F $jog_speed \n")
        f.write(f"G1 {self._curr_axis} {self._fz(z)} F $jog_speed \n")
        f.write("VelocityBlendingOn()\n")
        f.write("CornerRoundingOn()\n")
        f.write(f"StartExtrusion({self._curr_ph}, $dwell_start)\n")
        f.write(f"G1 X {self._fx(x)} Y {self._fy(y)} {self._curr_axis} {self._fz(z)} F {speed} \n")

    def _write_pass_start(self, f: TextIO, pass_idx, x, y, z, speed, artven, prev_x, prev_y):
        cfg = self.config
        f.write(f"; Print pass {pass_idx} \n")

        if not cfg.multimaterial:
            f.write(f"G1 X {self._fx(x)} Y {self._fy(y)} F $jog_speed\n")
            f.write(f"G1 {cfg.axis_1} {self._fz(z)} F $jog_speed\n")
            f.write("VelocityBlendingOn()\n")
            f.write("CornerRoundingOn()\n")
            f.write("StartExtrusion()\n")
            f.write(f"G1 X {self._fx(x)} Y {self._fy(y)} {cfg.axis_1} {self._fz(z)} F {speed}\n")
            return

        # Multimaterial pass transitions
        # Y offset sign depends on front_nozzle config
        y_ven_sign = "" if cfg.front_nozzle == 1 else "-"
        y_art_sign = "-" if cfg.front_nozzle == 1 else ""

        if artven != 0 and self._curr == 0:
            # Switch to arterial
            self._curr_axis = cfg.axis_1
            self._curr_ph = cfg.printhead_1
            self._other_ph = cfg.printhead_2
            f.write("; moving to ARTERIAL \n")
            f.write(f"G91 G1 {cfg.axis_1} $lift_height "
                    f"{cfg.axis_2} $lift_height F $jog_speed \n")
            f.write(f"G91 G1 X $offset_x F $jog_translation \n")
            f.write(f"G91 G1 Y ({y_art_sign}$offset_y) F $jog_speed \n")
            f.write(f"G91 G1 {cfg.axis_1} (-$offset_z) F $jog_speed \n")
            f.write(f"G91 G1 {cfg.axis_1} (-$lift_height) "
                    f"{cfg.axis_2} (-$lift_height) F $jog_speed \n")
            f.write("G90 \n")
            self._curr = 1
        elif artven == 0 and self._curr == 1:
            # Switch to venous
            self._curr_axis = cfg.axis_2
            self._curr_ph = cfg.printhead_2
            self._other_ph = cfg.printhead_1
            f.write("; moving to VENOUS \n")
            f.write(f"G91 G1 {cfg.axis_1} $lift_height "
                    f"{cfg.axis_2} $lift_height F $jog_speed \n")
            f.write(f"G91 G1 X (-$offset_x) F $jog_translation \n")
            f.write(f"G91 G1 Y ({y_ven_sign}$offset_y) F $jog_speed \n")
            f.write(f"G91 G1 {cfg.axis_2} $offset_z F $jog_speed \n")
            f.write(f"G91 G1 {cfg.axis_1} (-$lift_height) "
                    f"{cfg.axis_2} (-$lift_height) F $jog_speed \n")
            f.write("G90 \n")
            self._curr = 0

        # Navigate to pass start and begin extrusion
        f.write(f"G1 X {self._fx(x)} Y {self._fy(y)} F $jog_speed \n")
        f.write(f"G1 {self._curr_axis} {self._fz(z)} F $jog_speed \n")
        f.write("VelocityBlendingOn()\n")
        f.write("CornerRoundingOn()\n")
        f.write(f"StartExtrusion({self._curr_ph}, $dwell_start)\n")
        f.write(f"G1 X {self._fx(x)} Y {self._fy(y)} {self._curr_axis} {self._fz(z)} F {speed} \n")

    def _write_move(self, f: TextIO, node, j_counter, x, y, z, speed, points, nd, pass_nodes):
        cfg = self.config
        if cfg.multimaterial:
            f.write(f"G1 X {self._fx(x)} Y {self._fy(y)} {self._curr_axis} {self._fz(z)} F {speed} \n")
        else:
            f.write(f"G1 X {self._fx(x)} Y {self._fy(y)} {cfg.axis_1} {self._fz(z)} F {speed}\n")

    def _write_pass_end(self, f: TextIO, network_top: float):
        cfg = self.config
        nd = cfg.num_decimals

        if not cfg.multimaterial:
            f.write("StopExtrusion()\n")
            f.write("VelocityBlendingOff()\n")
            f.write("CornerRoundingOff()\n")
            f.write(f"G1 {cfg.axis_1} $Z_safe F $jog_speed\n")
            f.write("Disable(Y)\n")
            f.write("Enable(Y)\n")
        else:
            f.write(f"StopExtrusion($Z_safe, {self._curr_ph}, $dwell_end)\n")
            f.write("VelocityBlendingOff()\n")
            f.write("CornerRoundingOff()\n")
            f.write(f"G1 {cfg.axis_1} ($Z_print+{round(network_top, nd)}) "
                    f"{cfg.axis_2} ($Z_print+{round(network_top, nd)}) F $jog_speed \n")
            f.write(f"; ending on {'ARTERIAL' if self._curr == 1 else 'VENOUS'} \n")
