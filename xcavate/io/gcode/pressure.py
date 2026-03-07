"""Pressure-based printer G-code writer.

Replaces the pressure-based G-code blocks from xcavate.py:
- Single material: lines 4409-4506
- Multimaterial: lines 4713-4974
"""

from typing import TextIO
from xcavate.io.gcode.base import GcodeWriter


class PressureGcodeWriter(GcodeWriter):
    """G-code writer for pressure-based extrusion printers."""

    def _write_first_pass_start(self, f: TextIO, x, y, z, speed, artven):
        cfg = self.config
        if cfg.multimaterial:
            self._curr = 0  # venous
            self._curr_axis = cfg.axis_2
            self._curr_ph = cfg.printhead_2
            if artven != 0:
                self._curr = 1
                self._curr_axis = cfg.axis_1
                self._curr_ph = cfg.printhead_1
                f.write("; Print Pass 0 \n")
                f.write(f"G92 X{x} Y{y} {cfg.axis_1}{z} {cfg.axis_2}{z} \n")
                f.write("; moving to ARTERIAL \n")
                self._write_custom(f, self.codes.rest_pressure_ph2 if self.codes else "")
                self._write_custom(f, self.codes.active_pressure_ph1 if self.codes else "")
                f.write(f"G91 G1 {cfg.axis_1}{cfg.container_height + cfg.amount_up} "
                        f"{cfg.axis_2}{cfg.container_height + cfg.amount_up} F{cfg.jog_speed} \n")
                f.write(f"G91 G1 X{cfg.offset_x} F{cfg.jog_translation} \n")
                y_off = cfg.offset_y if cfg.front_nozzle == 1 else -cfg.offset_y
                f.write(f"G91 G1 Y{y_off} F{cfg.jog_speed} \n")
                f.write(f"G91 G1 {cfg.axis_1}-{cfg.container_height + cfg.amount_up} "
                        f"{cfg.axis_2}-{cfg.container_height + cfg.amount_up} \n")
                f.write("G90 \n")
                f.write(f"G92 X{x} Y{y} \n")
                self._write_custom(f, self.codes.start_extrusion_ph2 if self.codes else "")
                self._write_custom(f, self.codes.start_extrusion_ph1 if self.codes else "")
                f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} F{speed} \n")
                self._curr = 0
            else:
                f.write("; Print Pass 0 \n")
                f.write(f"G92 X{x} Y{y} {cfg.axis_1}{z} {cfg.axis_2}{z} \n")
                f.write("G90 F0.5 \n")
                self._write_custom(f, self.codes.start_extrusion_ph1 if self.codes else "")
                f.write(f"G1 X{x} Y{y} {cfg.axis_1}{z} F{speed} \n")
        else:
            f.write("; Print Pass 0 \n")
            f.write(f"G92 X{x} Y{y} Z{z} \n")
            f.write("G90 F0.5 \n")
            self._write_custom(f, self.codes.start_extrusion if self.codes else "")
            f.write(f"G1 X{x} Y{y} Z{z} F{speed} \n")

    def _write_pass_start(self, f: TextIO, pass_idx, x, y, z, speed, artven, prev_x, prev_y):
        cfg = self.config
        f.write(f"; Print pass {pass_idx} \n")

        if cfg.multimaterial:
            self._write_mm_pass_start(f, x, y, z, speed, artven, prev_x, prev_y)
        else:
            f.write(f"G1 X{x} Y{y} \n")
            f.write(f"G1 X{x} Y{y} Z{z} \n")
            self._write_custom(f, self.codes.start_extrusion if self.codes else "")
            f.write(f"G1 X{x} Y{y} Z{z} F{speed} \n")

    def _write_mm_pass_start(self, f, x, y, z, speed, artven, prev_x, prev_y):
        """Handle multimaterial printhead switching at pass boundaries."""
        cfg = self.config
        y_to_ven = -cfg.offset_y if cfg.front_nozzle == 1 else cfg.offset_y
        y_to_art = cfg.offset_y if cfg.front_nozzle == 1 else -cfg.offset_y

        need_switch_to_art = artven != 0 and self._curr == 0
        need_switch_to_ven = artven == 0 and self._curr == 1

        if need_switch_to_art:
            self._curr_axis = cfg.axis_1
            self._curr_ph = cfg.printhead_1
            f.write("; moving to ARTERIAL \n")
            self._write_custom(f, self.codes.rest_pressure_ph2 if self.codes else "")
            self._write_custom(f, self.codes.active_pressure_ph1 if self.codes else "")
            f.write(f"G91 G1 {cfg.axis_1}{cfg.container_height + cfg.amount_up} "
                    f"{cfg.axis_2}{cfg.container_height + cfg.amount_up} F{cfg.jog_speed} \n")
            f.write(f"G91 G1 X{cfg.offset_x} F{cfg.jog_translation} \n")
            f.write(f"G91 G1 Y{y_to_art} F{cfg.jog_speed} \n")
            f.write(f"G91 G1 {cfg.axis_1}-{cfg.container_height + cfg.amount_up} "
                    f"{cfg.axis_2}-{cfg.container_height + cfg.amount_up} \n")
            f.write("G90 \n")
            f.write(f"G92 X{prev_x} Y{prev_y} \n")
            f.write(f"G90 G1 X{x} Y{y} \n")
            f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} \n")
            self._write_custom(f, self.codes.start_extrusion_ph1 if self.codes else "")
            self._write_custom(f, self.codes.start_extrusion_ph2 if self.codes else "")
            self._curr = 1
        elif need_switch_to_ven:
            self._curr_axis = cfg.axis_2
            self._curr_ph = cfg.printhead_2
            f.write("; moving to VENOUS \n")
            self._write_custom(f, self.codes.rest_pressure_ph1 if self.codes else "")
            self._write_custom(f, self.codes.active_pressure_ph2 if self.codes else "")
            f.write(f"G91 G1 {cfg.axis_1}{cfg.container_height + cfg.amount_up} "
                    f"{cfg.axis_2}{cfg.container_height + cfg.amount_up} F{cfg.jog_speed} \n")
            f.write(f"G91 G1 X-{cfg.offset_x} F{cfg.jog_translation} \n")
            f.write(f"G91 G1 Y{y_to_ven} F{cfg.jog_speed} \n")
            f.write(f"G91 G1 {cfg.axis_1}-{cfg.container_height + cfg.amount_up} "
                    f"{cfg.axis_2}-{cfg.container_height + cfg.amount_up} \n")
            f.write("G90 \n")
            f.write(f"G92 X{prev_x} Y{prev_y} \n")
            f.write(f"G90 G1 X{x} Y{y} \n")
            f.write(f"G90 G1 X{x} Y{y} {self._curr_axis}{z} \n")
            self._write_custom(f, self.codes.start_extrusion_ph2 if self.codes else "")
            self._write_custom(f, self.codes.start_extrusion_ph1 if self.codes else "")
            self._curr = 0
        else:
            f.write(f"G1 X{x} Y{y} \n")
            f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} \n")
            self._write_custom(f, self.codes.start_extrusion_ph1 if self.codes else "")
            self._write_custom(f, self.codes.start_extrusion_ph2 if self.codes else "")
            f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} F{speed} \n")

    def _write_move(self, f: TextIO, node, j_counter, x, y, z, speed, points, nd, pass_nodes):
        if self.config.multimaterial:
            f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} F{speed} \n")
        else:
            f.write(f"G1 X{x} Y{y} Z{z} F{speed} \n")

    def _write_pass_end(self, f: TextIO, network_top: float):
        cfg = self.config
        if cfg.multimaterial:
            self._write_custom(f, self.codes.stop_extrusion_ph1 if self.codes else "")
            self._write_custom(f, self.codes.stop_extrusion_ph2 if self.codes else "")
            f.write(f"G91 G1 {self._curr_axis}{cfg.initial_lift} F{cfg.jog_speed_lift} \n")
            f.write(f"G90 G1 {cfg.axis_1}{network_top} {cfg.axis_2}{network_top} F{cfg.jog_speed} \n")
            f.write(f"; ending on {'ARTERIAL' if self._curr == 1 else 'VENOUS'} \n")
        else:
            self._write_custom(f, self.codes.stop_extrusion if self.codes else "")
            f.write(f"G91 G1 Z{cfg.initial_lift} F{cfg.jog_speed_lift} \n")
            f.write(f"G90 G1 Z{network_top} F{cfg.jog_speed} \n")

    def _write_custom(self, f: TextIO, code: str):
        """Write custom G-code snippet if available."""
        if self.config.custom_gcode and code:
            f.write(code)
            if not code.endswith("\n"):
                f.write("\n")
