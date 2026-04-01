"""Aerotech 6-axis controller G-code writer.

Replaces xcavate.py Aerotech blocks:
- Single material: lines 4632-4712
- Multimaterial: lines 5279-5487
"""

from typing import TextIO, Optional
from xcavate.io.gcode.base import GcodeWriter, CustomCodes
from xcavate.config import XcavateConfig
import numpy as np


class AerotechGcodeWriter(GcodeWriter):
    """G-code writer for Aerotech motion controllers.

    Uses Enable/Brake commands for extrusion control and
    setPress calls for pressure switching in multimaterial mode.
    """

    def __init__(self, config: XcavateConfig, custom_codes: Optional[CustomCodes] = None):
        super().__init__(config, custom_codes)
        self._curr = 1  # Aerotech defaults to arterial
        self._curr_axis = config.axis_1
        self._curr_ph = config.printhead_1
        self._other_ph = config.printhead_2
        self._arterial_com = 2
        self._venous_com = 1

    def _write_header(self, f: TextIO):
        f.write("DVAR $AP, $COM,$hFile,$press,$length,$lame,$cCheck \n")
        super()._write_header(f)

    def _write_first_pass_start(self, f: TextIO, x, y, z, speed, artven):
        cfg = self.config
        f.write("VELOCITY ON \n")
        f.write("ROUNDING ON \n")
        f.write("G90 \n")

        if not cfg.multimaterial:
            # Single-material Aerotech: single axis, single printhead
            f.write("; Print Pass 0 \n")
            f.write(f"G92 X{x} Y{y} {cfg.axis_1}{z} \n")
            f.write(f"Enable {cfg.printhead_1} \n")
            f.write(f"G90 F{speed} \n")
            f.write(f"BRAKE {cfg.printhead_1} 0 \n")
            if self.config.custom_gcode and self.codes and self.codes.dwell_start:
                self._write_custom(f, self.codes.dwell_start)
            else:
                f.write(f"DWELL {cfg.dwell_start} \n")
            f.write(f"G1 X{x} Y{y} {cfg.axis_1}{z} F{speed}\n")
            return

        y_to_ven = cfg.offset_y if cfg.front_nozzle == 1 else -cfg.offset_y

        if artven == 0 and self._curr == 1:
            # Need to switch to venous
            self._curr = 0
            self._curr_axis = cfg.axis_2
            self._curr_ph = cfg.printhead_2
            self._other_ph = cfg.printhead_1
            f.write("; Print Pass 0 \n")
            f.write("; moving to VENOUS \n")
            f.write(f"$COM={self._arterial_com} \n")
            f.write(f"$AP={cfg.resting_pressure} \n")
            f.write("Call setPress P$COM Q$AP \n")
            f.write(f"$COM={self._venous_com} \n")
            f.write(f"$AP={cfg.active_pressure} \n")
            f.write("Call setPress P$COM Q$AP \n")
            f.write(f"G91 G1 {cfg.axis_1}{cfg.container_height + cfg.amount_up} "
                    f"{cfg.axis_2}{cfg.container_height + cfg.amount_up} F{self._f_speed(cfg.jog_speed)} \n")
            f.write(f"G91 G1 X-{cfg.offset_x} F{self._f_speed(cfg.jog_translation)} \n")
            f.write(f"G91 G1 Y{y_to_ven} F{self._f_speed(cfg.jog_speed)} \n")
            f.write(f"G91 G1 {cfg.axis_1}-{cfg.container_height + cfg.amount_up} "
                    f"{cfg.axis_2}-{cfg.container_height + cfg.amount_up} F{self._f_speed(cfg.jog_speed)} \n")
            f.write("G90 \n")
            f.write(f"G92 X{x} Y{y} {cfg.axis_1}{z} {cfg.axis_2}{z} \n")
            self._write_enable(f)
            f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} F{speed} \n")
        else:
            f.write("; Print Pass 0 \n")
            f.write(f"G92 X{x} Y{y} {cfg.axis_1}{z} {cfg.axis_2}{z} \n")
            self._write_enable(f)
            f.write(f"G1 X{x} Y{y} {cfg.axis_1}{z} F{speed} \n")

    def _write_pass_start(self, f: TextIO, pass_idx, x, y, z, speed, artven, prev_x, prev_y):
        cfg = self.config
        f.write(f"; Print pass {pass_idx} \n")

        if not cfg.multimaterial:
            # Single-material Aerotech: single axis, single printhead
            f.write("G90 \n")
            f.write(f"BRAKE {cfg.printhead_1} 1 \n")
            f.write(f"G1 X{x} Y{y} \n")
            f.write("G90 \n")
            f.write(f"G1 X{x} Y{y} {cfg.axis_1}{z}\n")
            f.write(f"Enable {cfg.printhead_1} \n")
            f.write("G91 \n")
            f.write(f"BRAKE {cfg.printhead_1} 0 \n")
            if self.config.custom_gcode and self.codes and self.codes.dwell_start:
                self._write_custom(f, self.codes.dwell_start)
            else:
                f.write(f"DWELL {cfg.dwell_start} \n")
            f.write("G90 \n")
            f.write(f"G1 X{x} Y{y} {cfg.axis_1}{z} F{speed}\n")
            return

        y_to_ven = cfg.offset_y if cfg.front_nozzle == 1 else -cfg.offset_y
        y_to_art = -cfg.offset_y if cfg.front_nozzle == 1 else cfg.offset_y

        if artven != 0 and self._curr == 0:
            # Switch to arterial
            self._curr_axis = cfg.axis_1
            self._curr_ph = cfg.printhead_1
            self._other_ph = cfg.printhead_2
            f.write("; moving to ARTERIAL \n")
            f.write(f"$COM={self._venous_com} \n")
            f.write(f"$AP={cfg.resting_pressure} \n")
            f.write("Call setPress P$COM Q$AP \n")
            f.write(f"$COM={self._arterial_com} \n")
            f.write(f"$AP={cfg.active_pressure} \n")
            f.write("Call setPress P$COM Q$AP \n")
            f.write(f"G91 G1 {cfg.axis_1}{cfg.container_height + cfg.amount_up} "
                    f"{cfg.axis_2}{cfg.container_height + cfg.amount_up} F{self._f_speed(cfg.jog_speed)} \n")
            f.write(f"G91 G1 X{cfg.offset_x} F{self._f_speed(cfg.jog_translation)} \n")
            f.write(f"G91 G1 Y{y_to_art} F{self._f_speed(cfg.jog_speed)} \n")
            f.write(f"G91 G1 {cfg.axis_1}-{cfg.container_height + cfg.amount_up} "
                    f"{cfg.axis_2}-{cfg.container_height + cfg.amount_up} F{self._f_speed(cfg.jog_speed)} \n")
            f.write("G90 \n")
            f.write(f"G92 X{prev_x} Y{prev_y} \n")
            f.write(f"G90 G1 X{x} Y{y} \n")
            f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} \n")
            self._write_enable(f)
            self._curr = 1
        elif artven == 0 and self._curr == 1:
            # Switch to venous
            self._curr_axis = cfg.axis_2
            self._curr_ph = cfg.printhead_2
            self._other_ph = cfg.printhead_1
            f.write("; moving to VENOUS \n")
            f.write(f"$COM={self._arterial_com} \n")
            f.write(f"$AP={cfg.resting_pressure} \n")
            f.write("Call setPress P$COM Q$AP \n")
            f.write(f"$COM={self._venous_com} \n")
            f.write(f"$AP={cfg.active_pressure} \n")
            f.write("Call setPress P$COM Q$AP \n")
            f.write(f"G91 G1 {cfg.axis_1}{cfg.container_height + cfg.amount_up} "
                    f"{cfg.axis_2}{cfg.container_height + cfg.amount_up} F{self._f_speed(cfg.jog_speed)} \n")
            f.write(f"G91 G1 X-{cfg.offset_x} F{self._f_speed(cfg.jog_translation)} \n")
            f.write(f"G91 G1 Y{y_to_ven} F{self._f_speed(cfg.jog_speed)} \n")
            f.write(f"G91 G1 {cfg.axis_1}-{cfg.container_height + cfg.amount_up} "
                    f"{cfg.axis_2}-{cfg.container_height + cfg.amount_up} F{self._f_speed(cfg.jog_speed)} \n")
            f.write("G90 \n")
            f.write(f"G92 X{prev_x} Y{prev_y} \n")
            f.write(f"G90 G1 X{x} Y{y} \n")
            f.write(f"G90 G1 X{x} Y{y} {self._curr_axis}{z} \n")
            self._write_enable(f)
            self._curr = 0
        else:
            f.write(f"G1 X{x} Y{y} \n")
            f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} \n")
            self._write_enable(f)
            f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} F{speed} \n")

    def _write_move(self, f: TextIO, node, j_counter, x, y, z, speed, points, nd, pass_nodes):
        if self.config.multimaterial:
            f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} F{speed} \n")
        else:
            f.write(f"G1 X{x} Y{y} {self.config.axis_1}{z} F{speed}\n")

    def _write_pass_end(self, f: TextIO, network_top: float):
        cfg = self.config
        if not cfg.multimaterial:
            # Single-material Aerotech: single printhead, single axis
            f.write(f"Enable {cfg.printhead_1} \n")
            f.write("G91 \n")
            if self.config.custom_gcode and self.codes and self.codes.dwell_end:
                self._write_custom(f, self.codes.dwell_end)
            else:
                f.write(f"DWELL {cfg.dwell_end} \n")
            f.write(f"BRAKE {cfg.printhead_1} 1 \n")
            f.write(f"G1 {cfg.axis_1}{cfg.initial_lift} F{self._f_speed(cfg.jog_speed_lift)} \n")
            f.write("G90 \n")
            f.write(f"G1 {cfg.axis_1}{network_top} F{self._f_speed(cfg.jog_speed)} \n")
        else:
            if self.config.custom_gcode and self.codes and self.codes.dwell_end:
                self._write_custom(f, self.codes.dwell_end)
            else:
                f.write(f"DWELL {cfg.dwell_end} \n")
            f.write(f"BRAKE {self._curr_ph} 1 \n")
            f.write(f"BRAKE {self._other_ph} 1 \n")
            f.write(f"G91 G1 {self._curr_axis}{cfg.initial_lift} F{self._f_speed(cfg.jog_speed_lift)} \n")
            f.write(f"G90 G1 {cfg.axis_1}{network_top} {cfg.axis_2}{network_top} F{self._f_speed(cfg.jog_speed)} \n")
            f.write(f"; ending on {'ARTERIAL' if self._curr == 1 else 'VENOUS'} \n")

    def _write_footer(self, f: TextIO, network_top: float):
        cfg = self.config
        f.write("G90 \n")
        f.write(f"G1 {cfg.axis_1}{cfg.container_height + cfg.amount_up} \n")
        f.write("M2 \n")

    def _write_custom(self, f: TextIO, code: str):
        """Write custom G-code snippet if available."""
        if self.config.custom_gcode and code:
            f.write(code)
            if not code.endswith("\n"):
                f.write("\n")

    def _write_enable(self, f: TextIO):
        """Write Enable/Brake/Dwell sequence for starting extrusion."""
        f.write(f"Enable {self._curr_ph} \n")
        f.write(f"Enable {self._other_ph} \n")
        f.write(f"BRAKE {self._other_ph} 0 \n")
        f.write(f"BRAKE {self._curr_ph} 0 \n")
        if self.config.custom_gcode and self.codes and self.codes.dwell_start:
            self._write_custom(f, self.codes.dwell_start)
        else:
            f.write(f"DWELL {self.config.dwell_start} \n")
