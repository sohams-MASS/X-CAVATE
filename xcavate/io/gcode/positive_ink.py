"""Positive ink displacement printer G-code writer.

Replaces xcavate.py positive ink displacement blocks:
- Single material: lines 4508-4630
- Multimaterial: lines 4976-5277
"""

from typing import TextIO, Dict, List, Optional
import numpy as np
from xcavate.io.gcode.base import GcodeWriter, CustomCodes
from xcavate.config import XcavateConfig


class PositiveInkGcodeWriter(GcodeWriter):
    """G-code writer for positive ink displacement printers.

    Tracks cumulative plunger position for arterial and venous syringes
    and computes extrusion amounts based on line geometry and syringe diameter.
    """

    def __init__(self, config: XcavateConfig, custom_codes: Optional[CustomCodes] = None):
        super().__init__(config, custom_codes)
        self._plunger_a = 0.0  # arterial plunger position
        self._plunger_v = 0.0  # venous plunger position
        self._curr = 0  # 0=venous, 1=arterial
        self._curr_axis = config.axis_2
        self._curr_ph = config.printhead_2

    def _compute_extrusion(self, norm: float, line_radius: float) -> float:
        """Compute extrusion amount from segment length and geometry.

        E = f * N * ((L_r + s) / S_r)^2
        """
        cfg = self.config
        syringe_radius = cfg.positive_ink_syringe_diam / 2
        return cfg.positive_ink_factor * norm * ((line_radius + cfg.positive_ink_shift) / syringe_radius) ** 2

    def _get_line_radius(self, node: int, points: np.ndarray, nd: int) -> float:
        cfg = self.config
        if cfg.positive_ink_radii and points.shape[1] > 3:
            return round(points[node, 3], nd)
        return cfg.positive_ink_diam / 2

    def _write_first_pass_start(self, f: TextIO, x, y, z, speed, artven):
        cfg = self.config
        self._curr = 0
        self._curr_axis = cfg.axis_2
        self._curr_ph = cfg.printhead_2

        if artven != 0 and self._curr == 0:
            self._curr = 1
            self._curr_axis = cfg.axis_1
            self._curr_ph = cfg.printhead_1
            f.write("; Print Pass 0 \n")
            f.write(f"G92 {cfg.axis_1}{z} {cfg.axis_2}{z} {cfg.printhead_1}{0} {cfg.printhead_2}{0} \n")
            f.write("; moving to ARTERIAL \n")
            f.write("G90 \n")
            f.write(f"G1 {cfg.axis_1}{cfg.amount_up} "
                    f"{cfg.axis_2}{cfg.amount_up} F{self._f_speed(cfg.jog_speed)} \n")
            f.write("G91 \n")
            f.write(f"G1 X-{cfg.offset_x} F{self._f_speed(cfg.jog_translation)} \n")
            y_off = cfg.offset_y if cfg.front_nozzle == 1 else -cfg.offset_y
            f.write(f"G1 Y{y_off} F{self._f_speed(cfg.jog_translation)} \n")
            if cfg.offset_z:
                f.write(f"G1 {cfg.axis_1}{cfg.offset_z} F{self._f_speed(cfg.jog_speed)} \n")
            f.write("G90 \n")
            f.write(f"G92 X{x} Y{y} \n")
            f.write(f"G1 {cfg.axis_1}{z} F{self._f_speed(cfg.jog_speed)} \n")
            if cfg.custom_gcode and self.codes:
                f.write("G91 \n")
                self._write_custom(f, self.codes.start_extrusion_ph1)
                self._write_custom(f, self.codes.dwell_start)
                f.write("G90 \n")
                self._plunger_v += cfg.positive_ink_start_venous
            self._curr = 0
        else:
            f.write("; Print Pass 0 \n")
            f.write(f"G92 X{x} Y{y} {cfg.axis_1}{z} {cfg.axis_2}{z} \n")
            f.write("G90 \n")
            f.write(f"G1 {cfg.axis_1}{cfg.amount_up} F{self._f_speed(cfg.jog_speed)} \n")
            if cfg.custom_gcode and self.codes:
                f.write("G91 \n")
                self._write_custom(f, self.codes.start_extrusion_ph2)
                self._write_custom(f, self.codes.dwell_start)
                f.write("G90 \n")
                self._plunger_a += cfg.positive_ink_start_arterial

    def _write_pass_start(self, f: TextIO, pass_idx, x, y, z, speed, artven, prev_x, prev_y):
        cfg = self.config
        f.write(f"; Print pass {pass_idx} \n")

        y_to_ven = -cfg.offset_y if cfg.front_nozzle == 1 else cfg.offset_y
        y_to_art = cfg.offset_y if cfg.front_nozzle == 1 else -cfg.offset_y

        if artven != 0 and self._curr == 0:
            self._curr_axis = cfg.axis_1
            self._curr_ph = cfg.printhead_1
            f.write("; moving to ARTERIAL \n")
            f.write(f"G1 {cfg.axis_1}{cfg.amount_up} "
                    f"{cfg.axis_2}{cfg.amount_up} F{self._f_speed(cfg.jog_speed)} \n")
            f.write("G91 \n")
            f.write(f"G1 X-{cfg.offset_x} F{self._f_speed(cfg.jog_translation)} \n")
            f.write(f"G1 Y{y_to_art} F{self._f_speed(cfg.jog_speed)} \n")
            if cfg.offset_z:
                f.write(f"G1 {cfg.axis_1}-{cfg.offset_z} F{self._f_speed(cfg.jog_speed)} \n")
            f.write("G90 \n")
            f.write(f"G92 X{prev_x} Y{prev_y} \n")
            f.write(f"G1 X{x} Y{y} \n")
            f.write(f"G1 {self._curr_axis}{z} \n")
            if cfg.custom_gcode and self.codes:
                f.write("G91 \n")
                self._write_custom(f, self.codes.start_extrusion_ph1)
                self._write_custom(f, self.codes.dwell_start)
                f.write("G90 \n")
                self._plunger_a += cfg.positive_ink_start_arterial
            self._curr = 1
        elif artven == 0 and self._curr == 1:
            self._curr_axis = cfg.axis_2
            self._curr_ph = cfg.printhead_2
            f.write("; moving to VENOUS \n")
            f.write(f"G1 {cfg.axis_1}{cfg.amount_up} "
                    f"{cfg.axis_2}{cfg.amount_up} F{self._f_speed(cfg.jog_speed)} \n")
            f.write("G91 \n")
            f.write(f"G1 X{cfg.offset_x} F{self._f_speed(cfg.jog_translation)} \n")
            f.write(f"G1 Y{y_to_ven} F{self._f_speed(cfg.jog_translation)} \n")
            if cfg.offset_z:
                f.write(f"G1 {cfg.axis_2}{cfg.offset_z} F{self._f_speed(cfg.jog_speed)} \n")
            f.write("G90 \n")
            f.write(f"G92 X{prev_x} Y{prev_y} \n")
            f.write(f"G1 X{x} Y{y} \n")
            f.write(f"G1 {self._curr_axis}{z} \n")
            if cfg.custom_gcode and self.codes:
                f.write("G91 \n")
                self._write_custom(f, self.codes.start_extrusion_ph2)
                self._write_custom(f, self.codes.dwell_start)
                f.write("G90 \n")
                self._plunger_v += cfg.positive_ink_start_venous
            self._curr = 0
        else:
            f.write(f"G1 X{x} Y{y} \n")
            f.write(f"G1 {self._curr_axis}{z} \n")
            if cfg.custom_gcode and self.codes:
                if self._curr_axis == cfg.axis_1:
                    f.write("G91 \n")
                    self._write_custom(f, self.codes.start_extrusion_ph1)
                    self._write_custom(f, self.codes.dwell_start)
                    f.write("G90 \n")
                    self._plunger_a += cfg.positive_ink_start_arterial
                else:
                    f.write("G91 \n")
                    self._write_custom(f, self.codes.start_extrusion_ph2)
                    self._write_custom(f, self.codes.dwell_start)
                    f.write("G90 \n")
                    self._plunger_v += cfg.positive_ink_start_venous

    def _write_move(self, f: TextIO, node, j_counter, x, y, z, speed, points, nd, pass_nodes):
        """Write a move command with extrusion amount based on segment geometry."""
        cfg = self.config
        prev_node = pass_nodes[j_counter - 1]
        xp = points[prev_node, 0]
        yp = points[prev_node, 1]
        zp = points[prev_node, 2]

        diff = np.array([x - xp, y - yp, z - zp])
        norm = np.linalg.norm(diff)

        line_radius = self._get_line_radius(node, points, nd)
        extrusion = self._compute_extrusion(norm, line_radius)

        if self._curr_axis == cfg.axis_1:
            self._plunger_a += extrusion
            plunger_val = round(self._plunger_a, nd)
            f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} {self._curr_ph}{plunger_val} F{speed} \n")
        else:
            self._plunger_v += extrusion
            plunger_val = round(self._plunger_v, nd)
            f.write(f"G1 X{x} Y{y} {self._curr_axis}{z} {self._curr_ph}{plunger_val} F{speed} \n")

    def _write_pass_end(self, f: TextIO, network_top: float):
        cfg = self.config
        f.write("G91 \n")
        if cfg.custom_gcode and self.codes:
            self._write_custom(f, self.codes.dwell_end)
            if self._curr_axis == cfg.axis_1:
                self._write_custom(f, self.codes.stop_extrusion_ph1)
                self._plunger_a += cfg.positive_ink_end_arterial
            else:
                self._write_custom(f, self.codes.stop_extrusion_ph2)
                self._plunger_v += cfg.positive_ink_end_venous
        f.write(f"G1 {self._curr_axis}{cfg.initial_lift} F{self._f_speed(cfg.jog_speed_lift)} \n")
        f.write("G90 \n")
        f.write(f"G1 {self._curr_axis}{round(network_top, cfg.num_decimals)} F{self._f_speed(cfg.jog_speed)} \n")
        f.write(f"; ending on {'ARTERIAL' if self._curr == 1 else 'VENOUS'} \n")

    def _write_custom(self, f: TextIO, code: str):
        if self.config.custom_gcode and code:
            f.write(code)
            if not code.endswith("\n"):
                f.write("\n")
