"""Gimbal solver: collision-free pathfinding with config tracking.

Extends the gimbal realistic detector to record which (alpha, phi) config
succeeded for each visited node, enabling correct 5-DOF G-code generation
with solved gimbal coordinates.

The solver records a :class:`GimbalNodeSolution` for every visited node,
containing the exact actuator values (z_ss, z_ntnl, theta) computed under
the *specific tilted config* that passed collision checks, plus the gimbal
tilt/azimuth angles (alpha, phi).
"""

from __future__ import annotations

import heapq
import logging
from dataclasses import dataclass
from math import radians
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from numpy.typing import NDArray

from xcavate.core.ctr_collision import CTRCollisionDetector
from xcavate.core.ctr_kinematics import (
    CTRConfig,
    batch_is_reachable,
    compute_needle_body,
    fast_global_to_snt,
    global_to_snt,
)
from xcavate.core.oracle import _build_gimbal_configs

logger = logging.getLogger(__name__)

Graph = Dict[int, List[int]]


@dataclass
class GimbalNodeSolution:
    """Solved gimbal configuration for a single visited node."""

    config_idx: int       # index into gimbal_configs list
    alpha: float          # tilt angle (radians)
    phi: float            # azimuth angle (radians)
    z_ss: float           # stainless steel extension (mm)
    z_ntnl: float         # nitinol extension (mm)
    theta: float          # rotation angle (radians)


def _build_config_angles(
    cone_angle_deg: float,
    n_tilt: int,
    n_azimuth: int,
) -> Tuple[List[float], List[float]]:
    """Return (alphas, phis) lists parallel to ``_build_gimbal_configs`` output.

    Index 0 = (0, 0) for the base (untilted) config.
    """
    alphas: List[float] = [0.0]
    phis: List[float] = [0.0]

    if cone_angle_deg <= 0 or n_tilt <= 0:
        return alphas, phis

    alpha_values = np.linspace(0, radians(cone_angle_deg), n_tilt + 1)[1:]
    phi_values = np.linspace(0, 2 * np.pi, n_azimuth, endpoint=False)

    for alpha in alpha_values:
        for phi in phi_values:
            alphas.append(float(alpha))
            phis.append(float(phi))

    return alphas, phis


class GimbalSolverDetector(CTRCollisionDetector):
    """Gimbal-equipped CTR detector that records which config worked.

    Same collision logic as ``GimbalRealisticDetector`` (shaft + body-drag
    checks for each config), but **records** which config succeeded so that
    the G-code writer can use the correct actuator values.
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
        self._config_alphas, self._config_phis = _build_config_angles(
            cone_angle_deg, n_tilt, n_azimuth,
        )
        self._active_config_idx: int = 0
        self._node_solutions: Dict[int, GimbalNodeSolution] = {}
        self._pending_valid_configs: List[int] = []

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def is_valid(self, node: int) -> bool:
        """Check validity trying gimbal angles; records valid configs.

        Tries the *active* config first for continuity.  If it works, caches
        just that index.  Otherwise iterates remaining configs and collects
        all valid indices.

        Uses batch KD-tree queries and fast scalar IK for performance.
        """
        if node not in self._unvisited:
            return False

        target_pt = self._points[node]
        collision_r = self._nozzle_radius
        tip_excl_r_sq = self._tip_exclusion_r ** 2

        if self._graph is not None and node in self._graph:
            neighbors = set(self._graph[node])
        else:
            neighbors = set()

        valid_configs: List[int] = []

        # Try active config first for continuity
        order = [self._active_config_idx] + [
            i for i in range(len(self._gimbal_configs))
            if i != self._active_config_idx
        ]

        for cfg_idx in order:
            cfg = self._gimbal_configs[cfg_idx]

            snt = fast_global_to_snt(self._points[node], cfg)
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

            # Vectorized tip exclusion
            dists_sq = np.sum((body - target_pt) ** 2, axis=1)
            far_body = body[dists_sq >= tip_excl_r_sq]

            if len(far_body) == 0:
                valid_configs.append(cfg_idx)
                if cfg_idx == self._active_config_idx:
                    break
                continue

            # Batch shaft collision check (unvisited nodes)
            shaft_ok = True
            shaft_hits = self._unvisited_tree.query_ball_point(far_body, collision_r)
            for hit_list in shaft_hits:
                for idx in hit_list:
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

            # Batch drag check (visited nodes)
            drag_ok = True
            if self._visited_tree is not None and len(self._visited) > 0:
                drag_counts = self._visited_tree.query_ball_point(
                    far_body, collision_r, return_length=True,
                )
                if np.any(drag_counts > 0):
                    drag_ok = False

            if drag_ok:
                valid_configs.append(cfg_idx)
                if cfg_idx == self._active_config_idx:
                    break

        self._pending_valid_configs = valid_configs
        return len(valid_configs) > 0

    def mark_visited(self, node: int) -> None:
        """Record visited node with its solved gimbal configuration."""
        if self._pending_valid_configs:
            # Prefer active config if in list, else first valid
            if self._active_config_idx in self._pending_valid_configs:
                chosen_idx = self._active_config_idx
            else:
                chosen_idx = self._pending_valid_configs[0]

            # Compute SNT for chosen config
            cfg = self._gimbal_configs[chosen_idx]
            snt = fast_global_to_snt(self._points[node], cfg)
            if snt is not None:
                z_ss, z_ntnl, theta = snt
                self._node_solutions[node] = GimbalNodeSolution(
                    config_idx=chosen_idx,
                    alpha=self._config_alphas[chosen_idx],
                    phi=self._config_phis[chosen_idx],
                    z_ss=float(z_ss),
                    z_ntnl=float(z_ntnl),
                    theta=float(theta),
                )

            self._active_config_idx = chosen_idx

        self._pending_valid_configs = []
        super().mark_visited(node)

    def get_solutions(self) -> Dict[int, GimbalNodeSolution]:
        """Return all solved gimbal configurations."""
        return self._node_solutions

    def set_active_config(self, idx: int) -> None:
        """Set the preferred config index for continuity."""
        self._active_config_idx = idx

    def get_active_config(self) -> CTRConfig:
        """Return the currently active gimbal config."""
        return self._gimbal_configs[self._active_config_idx]


# ---------------------------------------------------------------------------
# Runner functions
# ---------------------------------------------------------------------------

def run_gimbal_solver(
    graph: Graph,
    points: NDArray[np.floating],
    ctr_config: CTRConfig,
    nozzle_radius: float,
    cone_angle_deg: float = 15.0,
    n_tilt: int = 3,
    n_azimuth: int = 8,
    n_arc_samples: int = 20,
    strategy: str = "angular_sector",
    n_sectors: int = 8,
) -> Tuple[Dict[int, List[int]], Dict[int, GimbalNodeSolution]]:
    """Run gimbal-aware pathfinding with config tracking.

    Parameters
    ----------
    graph : dict[int, list[int]]
        Adjacency list (reachable nodes only).
    points : ndarray (N, 3)
        Node coordinates.
    ctr_config : CTRConfig
    nozzle_radius : float
    cone_angle_deg, n_tilt, n_azimuth
        Gimbal grid parameters.
    n_arc_samples : int
        Needle body discretization.
    strategy : str
        ``"z_heap"`` or ``"angular_sector"`` (default).
    n_sectors : int
        Angular sectors (only for ``"angular_sector"`` strategy).

    Returns
    -------
    tuple of (passes, solutions)
        passes: ``{pass_index: [node_indices]}``
        solutions: ``{node_index: GimbalNodeSolution}``
    """
    detector = GimbalSolverDetector(
        points, ctr_config, nozzle_radius,
        graph=graph, n_arc_samples=n_arc_samples,
        cone_angle_deg=cone_angle_deg, n_tilt=n_tilt, n_azimuth=n_azimuth,
    )

    # Mark non-graph nodes as visited
    for n in range(len(points)):
        if n not in graph:
            detector.mark_visited(n)

    if strategy == "z_heap":
        return _run_z_heap(graph, points, detector)
    elif strategy == "angular_sector":
        return _run_angular_sector(
            graph, points, ctr_config, detector,
            n_sectors, nozzle_radius, n_arc_samples,
        )
    else:
        raise ValueError(f"Unknown gimbal solver strategy: {strategy}")


def _run_z_heap(
    graph: Graph,
    points: NDArray[np.floating],
    detector: GimbalSolverDetector,
) -> Tuple[Dict[int, List[int]], Dict[int, GimbalNodeSolution]]:
    """Z-ordered DFS passes."""
    from xcavate.core.pathfinding import iterative_dfs

    z_heap: list[tuple] = []
    for node in graph:
        heapq.heappush(z_heap, (float(points[node, 2]), node))

    print_passes: Dict[int, List[int]] = {}
    pass_idx = 0

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
            pass_idx += 1

    logger.info(
        "Gimbal solver (z_heap): %d passes, %d solutions",
        pass_idx, len(detector.get_solutions()),
    )
    return print_passes, detector.get_solutions()


def _run_angular_sector(
    graph: Graph,
    points: NDArray[np.floating],
    ctr_config: CTRConfig,
    detector: GimbalSolverDetector,
    n_sectors: int,
    nozzle_radius: float,
    n_arc_samples: int,
) -> Tuple[Dict[int, List[int]], Dict[int, GimbalNodeSolution]]:
    """Angular sector partitioned DFS with conflict graph ordering."""
    from xcavate.core.ctr_kinematics import batch_global_to_local, batch_local_to_snt
    from xcavate.core.pathfinding import iterative_dfs_gimbal
    from xcavate.core.swept_volume import build_conflict_graph, eades_greedy_fas

    graph_nodes = sorted(graph.keys())
    graph_node_set = set(graph_nodes)

    # Compute theta for all graph nodes (vectorized)
    node_arr = np.array(graph_nodes, dtype=np.intp)
    pts = points[node_arr]
    local = batch_global_to_local(
        pts, ctr_config.X, ctr_config.R_hat,
        ctr_config.n_hat, ctr_config.theta_match,
    )
    snt = batch_local_to_snt(
        local, ctr_config.f_xr_yr, ctr_config.f_yr_ntnlss,
        ctr_config.x_val, ctr_config.radius,
    )
    theta_values = snt[:, 2]

    node_theta: Dict[int, float] = {}
    for i, node in enumerate(graph_nodes):
        t = theta_values[i]
        if not np.isnan(t):
            node_theta[node] = float(t)

    # Partition into sectors
    sector_width = 2.0 * np.pi / n_sectors
    sectors: Dict[int, List[int]] = {k: [] for k in range(n_sectors)}
    no_theta_nodes: List[int] = []

    for node in graph_nodes:
        if node in node_theta:
            t = node_theta[node]
            k = int(np.clip((t + np.pi) / sector_width, 0, n_sectors - 1))
            sectors[k].append(node)
        else:
            no_theta_nodes.append(node)

    # Build conflict graph
    logger.info("Gimbal solver: building conflict graph...")
    conflict_graph = build_conflict_graph(
        points, ctr_config, graph, nozzle_radius, n_arc_samples,
    )

    conflict_outdegree: Dict[int, int] = {}
    for node in graph_nodes:
        conflict_outdegree[node] = len(conflict_graph.get(node, set()))

    print_passes: Dict[int, List[int]] = {}
    pass_idx = 0

    # Process each sector
    for sector_idx in range(n_sectors):
        sector_nodes = sectors[sector_idx]
        if not sector_nodes:
            continue

        # Extract intra-sector conflict subgraph
        sector_set = set(sector_nodes)
        sector_adj: Dict[int, Set[int]] = {n: set() for n in sector_nodes}
        for u in sector_nodes:
            for v in conflict_graph.get(u, set()):
                if v in sector_set:
                    sector_adj[u].add(v)

        # Eades ordering within sector
        sector_order = eades_greedy_fas(sector_adj, sector_nodes)
        priority = {node: idx for idx, node in enumerate(sector_order)}

        sector_heap: list[tuple] = []
        for node in sector_order:
            heapq.heappush(sector_heap, (priority[node], node))

        while sector_heap:
            start_node = None
            while sector_heap:
                prio_val, node = heapq.heappop(sector_heap)
                if not detector.is_visited(node) and node in graph_node_set:
                    start_node = node
                    break
            if start_node is None:
                break

            pass_list = iterative_dfs_gimbal(
                graph, start_node, detector, points,
                conflict_outdegree=conflict_outdegree,
            )
            if pass_list:
                print_passes[pass_idx] = pass_list
                pass_idx += 1

    # Cleanup sweep for remaining unvisited nodes
    if detector.has_unvisited():
        cleanup_nodes = sorted(
            set(n for n in graph_nodes if not detector.is_visited(n))
            | set(n for n in no_theta_nodes if not detector.is_visited(n))
        )
        if cleanup_nodes:
            z_heap: list[tuple] = []
            for node in cleanup_nodes:
                heapq.heappush(z_heap, (float(points[node, 2]), node))

            while z_heap:
                start_node = None
                while z_heap:
                    z_val, node = heapq.heappop(z_heap)
                    if not detector.is_visited(node) and node in graph_node_set:
                        start_node = node
                        break
                if start_node is None:
                    break
                pass_list = iterative_dfs_gimbal(
                    graph, start_node, detector, points,
                    conflict_outdegree=conflict_outdegree,
                )
                if pass_list:
                    print_passes[pass_idx] = pass_list
                    pass_idx += 1

    logger.info(
        "Gimbal solver (angular_sector): %d passes, %d solutions",
        pass_idx, len(detector.get_solutions()),
    )
    return print_passes, detector.get_solutions()


def gimbal_reachable_nodes(
    points: NDArray[np.floating],
    graph_nodes: NDArray[np.intp],
    base_config: CTRConfig,
    cone_angle_deg: float,
    n_tilt: int,
    n_azimuth: int,
) -> NDArray[np.bool_]:
    """Return boolean mask: True if node is reachable from ANY gimbal config.

    Parameters
    ----------
    points : ndarray (N, 3)
        Full coordinate array.
    graph_nodes : ndarray of int
        Indices of graph nodes to check.
    base_config : CTRConfig
        Untilted CTR configuration.
    cone_angle_deg, n_tilt, n_azimuth
        Gimbal grid parameters.

    Returns
    -------
    ndarray (len(graph_nodes),) of bool
    """
    configs = _build_gimbal_configs(base_config, cone_angle_deg, n_tilt, n_azimuth)

    pts = points[graph_nodes]
    combined = np.zeros(len(graph_nodes), dtype=np.bool_)

    for cfg in configs:
        mask = batch_is_reachable(pts, cfg)
        combined |= mask

    return combined
