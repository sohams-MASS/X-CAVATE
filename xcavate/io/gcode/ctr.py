"""G-code writer for Concentric Tube Robot (CTR) printers.

Outputs actuator commands in SNT coordinates (SS extension, Nitinol extension,
Theta rotation) instead of Cartesian XYZ. Each Cartesian target from the
network is converted to SNT via the CTR inverse kinematics before writing.

Theta values are unwrapped to minimize rotation between consecutive moves.

When ``gimbal_solutions`` is provided, SNT values are taken from the
pre-solved gimbal configuration for each node, and A/B axis commands are
emitted for gimbal tilt/azimuth. Mid-pass gimbal transitions include a
retract → reorient → extend sequence.
"""

from __future__ import annotations

from typing import TextIO

import numpy as np

from xcavate.core.ctr_kinematics import CTRConfig, global_to_snt
from xcavate.io.gcode.base import GcodeWriter


class CTRGcodeWriter(GcodeWriter):
    """G-code writer outputting SNT coordinates for a Concentric Tube Robot."""

    def __init__(self, config, custom_codes=None):
        super().__init__(config, custom_codes)
        self._ctr_config: CTRConfig | None = None
        self._prev_theta: float = 0.0
        self._gimbal_solutions = None
        self._prev_config_idx: int = -1
        self._print_passes_ref = None

    def write(self, output_path, print_passes, points, **kwargs):
        """Override to initialize CTR config before writing."""
        self._ctr_config = CTRConfig.from_xcavate_config(self.config)
        self._prev_theta = 0.0
        self._gimbal_solutions = kwargs.pop('gimbal_solutions', None)
        self._prev_config_idx = -1
        self._print_passes_ref = print_passes
        super().write(output_path, print_passes, points, **kwargs)

    # ------------------------------------------------------------------ #
    # Header / Footer
    # ------------------------------------------------------------------ #

    def _write_header(self, f: TextIO):
        cfg = self.config
        f.write(";=========== Begin CTR GCODE ============= \n")
        f.write(f"; Axis mapping: SS={cfg.ctr_ss_axis_name}, "
                f"NTNL={cfg.ctr_ntnl_axis_name}, "
                f"ROT={cfg.ctr_rot_axis_name}\n")
        if self._gimbal_solutions:
            f.write("; Gimbal axes: A=tilt, B=azimuth\n")
        if self.config.custom_gcode and self.codes:
            f.write(self.codes.header + "\n")

    def _write_footer(self, f: TextIO, network_top: float):
        cfg = self.config
        f.write("G90 \n")
        # Retract: pull SS back to zero, nitinol back to zero
        f.write(f"G1 {cfg.ctr_ss_axis_name}0 {cfg.ctr_ntnl_axis_name}0 "
                f"F{cfg.ctr_jogging_feedrate}\n")
        # Home gimbal if active
        if self._gimbal_solutions:
            f.write(f"G1 A0.000 B0.000 F{cfg.ctr_jogging_feedrate}\n")

    # ------------------------------------------------------------------ #
    # Abstract method implementations
    # ------------------------------------------------------------------ #

    def _write_first_pass_start(self, f: TextIO, x, y, z, speed, artven):
        cfg = self.config
        node_idx = self._print_passes_ref[0][0] if self._print_passes_ref else None
        snt = self._xyz_to_snt(x, y, z, node_idx=node_idx)
        if snt is None:
            f.write("; WARNING: first node unreachable by CTR\n")
            return

        z_ss, z_ntnl, theta = snt
        self._prev_theta = theta

        f.write("; Print Pass 0 \n")
        f.write("G90 \n")
        # Home to known state
        f.write(f"G92 {cfg.ctr_ss_axis_name}0 {cfg.ctr_ntnl_axis_name}0 "
                f"{cfg.ctr_rot_axis_name}0\n")

        # Gimbal positioning at start
        if self._gimbal_solutions and node_idx is not None and node_idx in self._gimbal_solutions:
            sol = self._gimbal_solutions[node_idx]
            alpha_deg = np.degrees(sol.alpha)
            phi_deg = np.degrees(sol.phi)
            f.write(f"G1 A{alpha_deg:.3f} B{phi_deg:.3f} F{cfg.ctr_jogging_feedrate}\n")
            self._prev_config_idx = sol.config_idx

        # Move to first position
        f.write(f"G1 {cfg.ctr_ss_axis_name}{z_ss:.{cfg.num_decimals}f} "
                f"{cfg.ctr_ntnl_axis_name}{z_ntnl:.{cfg.num_decimals}f} "
                f"{cfg.ctr_rot_axis_name}{np.degrees(theta):.{cfg.num_decimals}f} "
                f"F{cfg.ctr_jogging_feedrate}\n")
        # Start extrusion
        if cfg.custom_gcode and self.codes:
            self._write_custom(f, self.codes.start_extrusion)
        f.write(f"; Extruding at F{cfg.ctr_extrusion_feedrate}\n")

    def _write_pass_start(self, f: TextIO, pass_idx, x, y, z, speed, artven, prev_x, prev_y):
        cfg = self.config
        node_idx = self._print_passes_ref[pass_idx][0] if self._print_passes_ref else None
        snt = self._xyz_to_snt(x, y, z, node_idx=node_idx)
        if snt is None:
            f.write(f"; WARNING: pass {pass_idx} start node unreachable by CTR\n")
            return

        z_ss, z_ntnl, theta = snt

        f.write(f"; Print pass {pass_idx} \n")
        f.write("G90 \n")
        # Retract needle before jogging
        f.write(f"G1 {cfg.ctr_ss_axis_name}0 {cfg.ctr_ntnl_axis_name}0 "
                f"F{cfg.ctr_jogging_feedrate}\n")

        # Gimbal positioning at pass start
        if self._gimbal_solutions and node_idx is not None and node_idx in self._gimbal_solutions:
            sol = self._gimbal_solutions[node_idx]
            alpha_deg = np.degrees(sol.alpha)
            phi_deg = np.degrees(sol.phi)
            f.write(f"G1 A{alpha_deg:.3f} B{phi_deg:.3f} F{cfg.ctr_jogging_feedrate}\n")
            self._prev_config_idx = sol.config_idx

        # Rotate to new theta
        f.write(f"G1 {cfg.ctr_rot_axis_name}{np.degrees(theta):.{cfg.num_decimals}f} "
                f"F{cfg.ctr_jogging_feedrate}\n")
        # Extend to new position
        f.write(f"G1 {cfg.ctr_ss_axis_name}{z_ss:.{cfg.num_decimals}f} "
                f"{cfg.ctr_ntnl_axis_name}{z_ntnl:.{cfg.num_decimals}f} "
                f"F{cfg.ctr_jogging_feedrate}\n")
        # Start extrusion
        if cfg.custom_gcode and self.codes:
            self._write_custom(f, self.codes.start_extrusion)

        self._prev_theta = theta

    def _write_move(self, f: TextIO, node, j_counter, x, y, z, speed, points, nd, pass_nodes):
        cfg = self.config

        # Check for gimbal transition
        if self._gimbal_solutions and node in self._gimbal_solutions:
            sol = self._gimbal_solutions[node]
            if sol.config_idx != self._prev_config_idx:
                self._write_gimbal_transition(f, sol, nd)
                self._prev_config_idx = sol.config_idx
                self._prev_theta = self._unwrap_theta(sol.theta)
                return  # transition already positioned at the node

        snt = self._xyz_to_snt(x, y, z, node_idx=node)
        if snt is None:
            f.write(f"; WARNING: node {node} unreachable, skipping\n")
            return

        z_ss, z_ntnl, theta = snt

        # Compute extrusion amount (distance-based)
        if j_counter > 0:
            prev_node = pass_nodes[j_counter - 1]
            dist = float(np.linalg.norm(
                points[node, :3] - points[prev_node, :3]
            ))
            extrusion = dist * cfg.ctr_extruder_mm_per_mm
        else:
            extrusion = 0.0

        # Compute target feedrate from linear speed
        feedrate = cfg.ctr_extrusion_feedrate

        f.write(f"G90 G1 "
                f"{cfg.ctr_ss_axis_name}{z_ss:.{nd}f} "
                f"{cfg.ctr_ntnl_axis_name}{z_ntnl:.{nd}f} "
                f"{cfg.ctr_rot_axis_name}{np.degrees(theta):.{nd}f} "
                f"{cfg.ctr_extruder_axis_name}{extrusion:.{nd}f} "
                f"F{feedrate}\n")

        self._prev_theta = theta

    def _write_pass_end(self, f: TextIO, network_top: float):
        cfg = self.config
        # Stop extrusion
        if cfg.custom_gcode and self.codes:
            self._write_custom(f, self.codes.stop_extrusion)
        # Retract needle
        f.write(f"G90 G1 {cfg.ctr_ss_axis_name}0 {cfg.ctr_ntnl_axis_name}0 "
                f"F{cfg.ctr_jogging_feedrate}\n")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _xyz_to_snt(self, x, y, z, node_idx=None):
        """Convert Cartesian target to unwrapped SNT values.

        If ``gimbal_solutions`` is active and contains a solution for
        ``node_idx``, the pre-solved SNT values are returned directly
        (already computed under the correct tilted config during pathfinding).
        """
        if self._gimbal_solutions and node_idx is not None and node_idx in self._gimbal_solutions:
            sol = self._gimbal_solutions[node_idx]
            theta = self._unwrap_theta(sol.theta)
            return sol.z_ss, sol.z_ntnl, theta

        point_G = np.array([float(x), float(y), float(z)])
        snt = global_to_snt(point_G, self._ctr_config)
        if snt is None:
            return None
        z_ss, z_ntnl, theta = snt
        # Unwrap theta: choose closest 2*pi*n offset to previous theta
        theta = self._unwrap_theta(theta)
        return z_ss, z_ntnl, theta

    def _unwrap_theta(self, theta: float) -> float:
        """Unwrap theta to minimize rotation from previous position."""
        diff = theta - self._prev_theta
        # Normalize to [-pi, pi]
        diff = (diff + np.pi) % (2 * np.pi) - np.pi
        return self._prev_theta + diff

    def _write_gimbal_transition(self, f: TextIO, sol, nd: int):
        """Write a mid-pass gimbal reorientation sequence.

        Sequence: stop extrusion → retract → reorient gimbal → extend → resume.
        """
        cfg = self.config
        jog = cfg.ctr_jogging_feedrate
        f.write(f"M5\n")                                          # stop extrusion
        f.write(f"G1 {cfg.ctr_ss_axis_name}0 "
                f"{cfg.ctr_ntnl_axis_name}0 F{jog}\n")            # retract needle
        alpha_deg = np.degrees(sol.alpha)
        phi_deg = np.degrees(sol.phi)
        f.write(f"G1 A{alpha_deg:.3f} B{phi_deg:.3f} F{jog}\n")   # reorient gimbal
        theta_unwrapped = self._unwrap_theta(sol.theta)
        f.write(f"G1 {cfg.ctr_ss_axis_name}{sol.z_ss:.{nd}f} "
                f"{cfg.ctr_ntnl_axis_name}{sol.z_ntnl:.{nd}f} "
                f"{cfg.ctr_rot_axis_name}{np.degrees(theta_unwrapped):.{nd}f} "
                f"F{jog}\n")                                       # extend to node
        f.write(f"M3\n")                                           # resume extrusion

    def _write_custom(self, f: TextIO, code: str):
        """Write custom G-code snippet if available."""
        if self.config.custom_gcode and code:
            f.write(code)
            if not code.endswith("\n"):
                f.write("\n")
