"""Oracle diagnostic: CTR collision detector with body-drag check disabled.

This module provides ``OracleDetector``, a subclass of
:class:`~xcavate.core.ctr_collision.CTRCollisionDetector` that skips the
body-drag check (visited-node collisions) while keeping shaft collision
detection intact.  This establishes a theoretical upper bound on visit rate
— if angular sector ordering can approach this ceiling, the strategy is
working well.

This is diagnostic only and should never be used in production G-code
generation.
"""

from __future__ import annotations

import heapq
import logging
from math import radians
from typing import Dict, List, Optional

import numpy as np
from numpy.typing import NDArray

from xcavate.core.ctr_collision import CTRCollisionDetector
from xcavate.core.ctr_kinematics import (
    CTRConfig,
    _perpendicular_unit,
    compute_needle_body,
    global_to_snt,
    rodrigues_rotation,
)

logger = logging.getLogger(__name__)

Graph = Dict[int, List[int]]


class OracleDetector(CTRCollisionDetector):
    """CTR collision detector that skips the body-drag check.

    Inherits all behavior from :class:`CTRCollisionDetector` but overrides
    ``is_valid`` to skip the visited-node body-drag check (the loop at
    lines 182-191 of the parent).  Shaft collision with unvisited nodes
    is still enforced.
    """

    def is_valid(self, node: int) -> bool:
        """Check validity without body-drag (visited-node) collisions."""
        if node not in self._unvisited:
            return False

        # Reachability check
        snt = global_to_snt(self._points[node], self._ctr_config)
        if snt is None:
            return False
        z_ss, z_ntnl, theta = snt
        if z_ss < 0 or z_ss > self._ctr_config.ss_lim:
            return False
        if z_ntnl < 0 or z_ntnl > self._ctr_config.ntnl_lim:
            return False

        # Compute full needle body
        body = compute_needle_body(
            z_ss, z_ntnl, theta, self._ctr_config, self._n_arc_samples,
        )

        target_pt = self._points[node]
        collision_r = self._nozzle_radius
        tip_excl_r_sq = self._tip_exclusion_r ** 2

        # Collect graph neighbors for exemption
        if self._graph is not None and node in self._graph:
            neighbors = set(self._graph[node])
        else:
            neighbors = set()

        # --- Check body vs unvisited nodes (shaft collision) ---
        for bp in body:
            if np.sum((bp - target_pt) ** 2) < tip_excl_r_sq:
                continue

            nearby = self._unvisited_tree.query_ball_point(bp, collision_r)
            for idx in nearby:
                other = int(self._unvisited_indices[idx]) if idx < len(self._unvisited_indices) else idx
                if other == node:
                    continue
                if other not in self._unvisited:
                    continue
                if other in neighbors:
                    continue
                if self._tolerance_flag and self._tolerance > 0:
                    dist_sq = float(np.sum((self._points[other] - target_pt) ** 2))
                    if dist_sq < self._tolerance * self._tolerance:
                        continue
                return False

        # Body-drag check SKIPPED — this is the oracle
        return True


# ---------------------------------------------------------------------------
# Gimbal support
# ---------------------------------------------------------------------------


def make_gimbal_config(
    base_config: CTRConfig,
    alpha: float,
    phi: float,
) -> CTRConfig:
    """Create a new CTRConfig with R_hat tilted by *alpha* at azimuth *phi*.

    Parameters
    ----------
    base_config : CTRConfig
        Original (untilted) configuration.
    alpha : float
        Tilt magnitude (radians) from the original R_hat.
    phi : float
        Azimuth angle (radians) defining the tilt direction in the plane
        perpendicular to R_hat.

    Returns
    -------
    CTRConfig
        New config with tilted R_hat/n_hat/theta_match; same X, radius,
        calibration, and actuator limits.
    """
    if alpha == 0.0:
        return base_config

    R_hat = base_config.R_hat
    n_hat_base = base_config.n_hat

    # Build a second perpendicular vector to define the tilt plane
    b_hat = np.cross(R_hat, n_hat_base)
    b_hat /= np.linalg.norm(b_hat)

    # Tilt axis: lies in the plane perpendicular to R_hat, at azimuth phi
    tilt_axis = np.cos(phi) * n_hat_base + np.sin(phi) * b_hat
    tilt_axis /= np.linalg.norm(tilt_axis)

    # Rotate R_hat by alpha about the tilt axis
    R_tilt = rodrigues_rotation(alpha, tilt_axis)
    R_hat_new = R_tilt @ R_hat
    R_hat_new /= np.linalg.norm(R_hat_new)

    # Compute new n_hat and theta_match
    n_hat_new = _perpendicular_unit(R_hat_new)
    theta_match_new = float(np.arctan2(
        np.dot(np.cross(n_hat_new, np.array([1.0, 0.0, 0.0])), R_hat_new),
        np.dot(n_hat_new, np.array([1.0, 0.0, 0.0])),
    ))

    return CTRConfig(
        X=base_config.X,
        R_hat=R_hat_new,
        n_hat=n_hat_new,
        theta_match=theta_match_new,
        radius=base_config.radius,
        f_xr_yr=base_config.f_xr_yr,
        f_yr_ntnlss=base_config.f_yr_ntnlss,
        x_val=base_config.x_val,
        ss_lim=base_config.ss_lim,
        ntnl_lim=base_config.ntnl_lim,
    )


def _build_gimbal_configs(
    base_config: CTRConfig,
    cone_angle_deg: float,
    n_tilt: int,
    n_azimuth: int,
) -> List[CTRConfig]:
    """Precompute gimbal configs for all (alpha, phi) in the cone."""
    configs: List[CTRConfig] = [base_config]  # alpha=0 first

    if cone_angle_deg <= 0 or n_tilt <= 0:
        return configs

    alpha_values = np.linspace(0, radians(cone_angle_deg), n_tilt + 1)[1:]  # skip 0
    phi_values = np.linspace(0, 2 * np.pi, n_azimuth, endpoint=False)

    for alpha in alpha_values:
        for phi in phi_values:
            configs.append(make_gimbal_config(base_config, float(alpha), float(phi)))

    return configs


class GimbalOracleDetector(CTRCollisionDetector):
    """Gimbal-equipped CTR detector WITHOUT body-drag (theoretical ceiling).

    Tries multiple insertion angles within a cone. A node is valid if ANY
    angle yields a collision-free path (shaft collisions only, no body-drag).
    """

    def __init__(
        self,
        points: NDArray[np.floating],
        ctr_config: CTRConfig,
        nozzle_radius: float,
        graph: Optional[Graph] = None,
        tolerance: float = 0.0,
        tolerance_flag: bool = False,
        n_arc_samples: int = 20,
        rebuild_interval: int = 500,
        cone_angle_deg: float = 15.0,
        n_tilt: int = 3,
        n_azimuth: int = 8,
    ) -> None:
        super().__init__(
            points, ctr_config, nozzle_radius,
            graph=graph, tolerance=tolerance, tolerance_flag=tolerance_flag,
            n_arc_samples=n_arc_samples, rebuild_interval=rebuild_interval,
        )
        self._gimbal_configs = _build_gimbal_configs(
            ctr_config, cone_angle_deg, n_tilt, n_azimuth,
        )

    def is_valid(self, node: int) -> bool:
        """Check validity trying all gimbal angles; no body-drag."""
        if node not in self._unvisited:
            return False

        target_pt = self._points[node]
        collision_r = self._nozzle_radius
        tip_excl_r_sq = self._tip_exclusion_r ** 2

        if self._graph is not None and node in self._graph:
            neighbors = set(self._graph[node])
        else:
            neighbors = set()

        for cfg in self._gimbal_configs:
            snt = global_to_snt(self._points[node], cfg)
            if snt is None:
                continue
            z_ss, z_ntnl, theta = snt
            if z_ss < 0 or z_ss > cfg.ss_lim:
                continue
            if z_ntnl < 0 or z_ntnl > cfg.ntnl_lim:
                continue

            body = compute_needle_body(
                z_ss, z_ntnl, theta, cfg, self._n_arc_samples,
            )

            # Shaft collision check (unvisited nodes only)
            shaft_ok = True
            for bp in body:
                if np.sum((bp - target_pt) ** 2) < tip_excl_r_sq:
                    continue
                nearby = self._unvisited_tree.query_ball_point(bp, collision_r)
                for idx in nearby:
                    other = int(self._unvisited_indices[idx]) if idx < len(self._unvisited_indices) else idx
                    if other == node:
                        continue
                    if other not in self._unvisited:
                        continue
                    if other in neighbors:
                        continue
                    if self._tolerance_flag and self._tolerance > 0:
                        dist_sq = float(np.sum((self._points[other] - target_pt) ** 2))
                        if dist_sq < self._tolerance * self._tolerance:
                            continue
                    shaft_ok = False
                    break
                if not shaft_ok:
                    break

            if shaft_ok:
                return True  # First valid angle — short-circuit

        return False


class GimbalRealisticDetector(CTRCollisionDetector):
    """Gimbal-equipped CTR detector WITH body-drag (practical result).

    Tries multiple insertion angles within a cone. A node is valid if ANY
    angle yields a collision-free path (both shaft and body-drag checks).
    """

    def __init__(
        self,
        points: NDArray[np.floating],
        ctr_config: CTRConfig,
        nozzle_radius: float,
        graph: Optional[Graph] = None,
        tolerance: float = 0.0,
        tolerance_flag: bool = False,
        n_arc_samples: int = 20,
        rebuild_interval: int = 500,
        cone_angle_deg: float = 15.0,
        n_tilt: int = 3,
        n_azimuth: int = 8,
    ) -> None:
        super().__init__(
            points, ctr_config, nozzle_radius,
            graph=graph, tolerance=tolerance, tolerance_flag=tolerance_flag,
            n_arc_samples=n_arc_samples, rebuild_interval=rebuild_interval,
        )
        self._gimbal_configs = _build_gimbal_configs(
            ctr_config, cone_angle_deg, n_tilt, n_azimuth,
        )

    def is_valid(self, node: int) -> bool:
        """Check validity trying all gimbal angles; body-drag enforced."""
        if node not in self._unvisited:
            return False

        target_pt = self._points[node]
        collision_r = self._nozzle_radius
        tip_excl_r_sq = self._tip_exclusion_r ** 2

        if self._graph is not None and node in self._graph:
            neighbors = set(self._graph[node])
        else:
            neighbors = set()

        for cfg in self._gimbal_configs:
            snt = global_to_snt(self._points[node], cfg)
            if snt is None:
                continue
            z_ss, z_ntnl, theta = snt
            if z_ss < 0 or z_ss > cfg.ss_lim:
                continue
            if z_ntnl < 0 or z_ntnl > cfg.ntnl_lim:
                continue

            body = compute_needle_body(
                z_ss, z_ntnl, theta, cfg, self._n_arc_samples,
            )

            # Shaft collision check (unvisited nodes)
            shaft_ok = True
            for bp in body:
                if np.sum((bp - target_pt) ** 2) < tip_excl_r_sq:
                    continue
                nearby = self._unvisited_tree.query_ball_point(bp, collision_r)
                for idx in nearby:
                    other = int(self._unvisited_indices[idx]) if idx < len(self._unvisited_indices) else idx
                    if other == node:
                        continue
                    if other not in self._unvisited:
                        continue
                    if other in neighbors:
                        continue
                    if self._tolerance_flag and self._tolerance > 0:
                        dist_sq = float(np.sum((self._points[other] - target_pt) ** 2))
                        if dist_sq < self._tolerance * self._tolerance:
                            continue
                    shaft_ok = False
                    break
                if not shaft_ok:
                    break

            if not shaft_ok:
                continue

            # Body-drag check (visited nodes)
            drag_ok = True
            if self._visited_tree is not None and len(self._visited) > 0:
                for bp in body:
                    if np.sum((bp - target_pt) ** 2) < tip_excl_r_sq:
                        continue
                    nearby = self._visited_tree.query_ball_point(bp, collision_r)
                    if len(nearby) > 0:
                        drag_ok = False
                        break

            if drag_ok:
                return True  # First valid angle — short-circuit

        return False


def run_oracle(
    graph: Graph,
    points: NDArray[np.floating],
    ctr_config: CTRConfig,
    nozzle_radius: float,
    n_arc_samples: int = 20,
) -> Dict[int, List[int]]:
    """Run DFS pathfinding with the oracle detector (no body-drag).

    Parameters
    ----------
    graph : dict[int, list[int]]
        Adjacency list (reachable nodes only).
    points : ndarray (N, 3)
        Node coordinates.
    ctr_config : CTRConfig
    nozzle_radius : float
    n_arc_samples : int

    Returns
    -------
    dict[int, list[int]]
        ``{pass_index: [node_indices_in_visit_order]}``.
    """
    from xcavate.core.pathfinding import iterative_dfs

    detector = OracleDetector(
        points,
        ctr_config,
        nozzle_radius,
        graph=graph,
        n_arc_samples=n_arc_samples,
    )

    # Mark non-graph nodes as visited
    for n in range(len(points)):
        if n not in graph:
            detector.mark_visited(n)

    # Z-heap ordering
    z_heap: list[tuple] = []
    for node in graph:
        heapq.heappush(z_heap, (float(points[node, 2]), node))

    print_passes: Dict[int, List[int]] = {}
    pass_idx = 0
    nodes_visited = 0

    while detector.has_unvisited():
        start_node = None
        while z_heap:
            z_val, node = heapq.heappop(z_heap)
            if not detector.is_visited(node) and node in graph:
                start_node = node
                break
        if start_node is None:
            break

        pass_list = iterative_dfs(graph, start_node, detector, points)
        if pass_list:
            print_passes[pass_idx] = pass_list
            nodes_visited += len(pass_list)
            pass_idx += 1

    logger.info(
        "Oracle pathfinding: %d passes, %d nodes visited", pass_idx, nodes_visited,
    )
    return print_passes


def _run_gimbal(
    detector_cls,
    graph: Graph,
    points: NDArray[np.floating],
    ctr_config: CTRConfig,
    nozzle_radius: float,
    n_arc_samples: int,
    cone_angle_deg: float,
    n_tilt: int,
    n_azimuth: int,
) -> Dict[int, List[int]]:
    """Shared DFS loop for gimbal detectors."""
    from xcavate.core.pathfinding import iterative_dfs

    detector = detector_cls(
        points, ctr_config, nozzle_radius,
        graph=graph, n_arc_samples=n_arc_samples,
        cone_angle_deg=cone_angle_deg, n_tilt=n_tilt, n_azimuth=n_azimuth,
    )

    for n in range(len(points)):
        if n not in graph:
            detector.mark_visited(n)

    z_heap: list[tuple] = []
    for node in graph:
        heapq.heappush(z_heap, (float(points[node, 2]), node))

    print_passes: Dict[int, List[int]] = {}
    pass_idx = 0
    nodes_visited = 0

    while detector.has_unvisited():
        start_node = None
        while z_heap:
            z_val, node = heapq.heappop(z_heap)
            if not detector.is_visited(node) and node in graph:
                start_node = node
                break
        if start_node is None:
            break

        pass_list = iterative_dfs(graph, start_node, detector, points)
        if pass_list:
            print_passes[pass_idx] = pass_list
            nodes_visited += len(pass_list)
            pass_idx += 1

    logger.info(
        "%s pathfinding: %d passes, %d nodes visited",
        detector_cls.__name__, pass_idx, nodes_visited,
    )
    return print_passes


def run_gimbal_oracle(
    graph: Graph,
    points: NDArray[np.floating],
    ctr_config: CTRConfig,
    nozzle_radius: float,
    n_arc_samples: int = 20,
    cone_angle_deg: float = 15.0,
    n_tilt: int = 3,
    n_azimuth: int = 8,
) -> Dict[int, List[int]]:
    """Gimbal + no body-drag -> theoretical ceiling."""
    return _run_gimbal(
        GimbalOracleDetector, graph, points, ctr_config, nozzle_radius,
        n_arc_samples, cone_angle_deg, n_tilt, n_azimuth,
    )


def analyze_gimbal_workspace(graph, points, ctr_config, cone_angle_deg=15.0, n_tilt=3, n_azimuth=8):
    """Run kinematic analysis on all graph nodes."""
    from xcavate.core.ctr_kinematic_analysis import analyze_workspace
    return analyze_workspace(points, np.array(sorted(graph.keys()), dtype=np.intp),
                             ctr_config, cone_angle_deg, n_tilt, n_azimuth)


def run_gimbal_realistic(
    graph: Graph,
    points: NDArray[np.floating],
    ctr_config: CTRConfig,
    nozzle_radius: float,
    n_arc_samples: int = 20,
    cone_angle_deg: float = 15.0,
    n_tilt: int = 3,
    n_azimuth: int = 8,
) -> Dict[int, List[int]]:
    """Gimbal + body-drag -> practical result."""
    return _run_gimbal(
        GimbalRealisticDetector, graph, points, ctr_config, nozzle_radius,
        n_arc_samples, cone_angle_deg, n_tilt, n_azimuth,
    )
