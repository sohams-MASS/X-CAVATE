"""Collision detector for Concentric Tube Robot (CTR) needle body.

Unlike the straight-needle :class:`CollisionDetector` which only checks the
tip's XY shadow, this detector models the full curved 3D needle body — both
the straight stainless-steel section and the pre-curved nitinol arc — and
checks it against unvisited *and* already-visited (printed) nodes.

The public interface (``is_valid``, ``mark_visited``, ``is_visited``,
``has_unvisited``, ``unvisited``) matches :class:`CollisionDetector` so that
``iterative_dfs`` and the rest of the pathfinding pipeline work unchanged.

Collision rules
---------------
1. **Tip proximity exclusion**: body sample points within ``tip_exclusion_r``
   of the candidate node are not checked for collisions.  This prevents
   adjacent graph neighbors (which are physically near the target) from
   blocking the candidate — they will be printed next in the DFS, just as
   the straight-needle detector uses Z-ordering to avoid blocking by nodes
   that will be visited later.

2. **Shaft collisions (unvisited)**: any unvisited node within
   ``nozzle_radius`` of a non-tip body sample is a blocker — the needle
   shaft would displace that node's gel before it is printed.

3. **Body-drag (visited)**: any visited node within ``nozzle_radius`` of a
   non-tip body sample is a blocker — the needle would drag through
   already-printed gel.

4. **Graph-neighbor exemption**: direct graph neighbors of the candidate
   are always exempt from shaft collision checks.  These nodes are reachable
   from the candidate and may be printed in the same DFS pass.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from xcavate.core.ctr_kinematics import (
    CTRConfig,
    compute_needle_body,
    fast_global_to_snt,
    global_to_snt,
)

logger = logging.getLogger(__name__)

# Type alias matching pathfinding.py
Graph = Dict[int, List[int]]


# ---------------------------------------------------------------------------
# Robot footprint for inter-robot collision avoidance
# ---------------------------------------------------------------------------

@dataclass
class RobotFootprint:
    """Physical envelope of a robot at a given state."""

    robot_idx: int
    ctr_config: CTRConfig
    body_points: NDArray[np.floating]  # (M, 3) sample points along needle
    body_tree: cKDTree                 # spatial index over body_points

    @classmethod
    def from_retracted(
        cls,
        robot_idx: int,
        config: CTRConfig,
        n_samples: int = 20,
    ) -> "RobotFootprint":
        """Footprint of a retracted (idle) robot — SS tube only at min extension."""
        min_ss = 1.0  # mm, minimum retracted extension
        ss_pts = np.linspace(0, min_ss, n_samples)
        body = config.X + ss_pts[:, None] * config.R_hat
        return cls(
            robot_idx=robot_idx,
            ctr_config=config,
            body_points=body,
            body_tree=cKDTree(body),
        )

    @classmethod
    def from_active(
        cls,
        robot_idx: int,
        config: CTRConfig,
        z_ss: float,
        z_ntnl: float,
        theta: float,
        n_arc_samples: int = 20,
    ) -> "RobotFootprint":
        """Footprint of robot actively printing a specific node."""
        body = compute_needle_body(z_ss, z_ntnl, theta, config, n_arc_samples)
        return cls(
            robot_idx=robot_idx,
            ctr_config=config,
            body_points=body,
            body_tree=cKDTree(body),
        )


# ---------------------------------------------------------------------------
# Shared visited state for multi-robot coordination
# ---------------------------------------------------------------------------

class SharedVisitedState:
    """Cross-robot visited/unvisited tracking.

    All robots share a single visited set so that body-drag checks
    account for material deposited by ANY robot, not just the current one.
    """

    def __init__(
        self,
        n_points: int,
        points: NDArray[np.floating],
        ss_od: float = 4.0,
        ntnl_od: float = 1.6,
    ) -> None:
        self._points = points[:, :3].copy()
        self._n_points = n_points
        self._unvisited: Set[int] = set(range(n_points))
        self._visited: Set[int] = set()
        self._visited_by: Dict[int, int] = {}  # node -> robot_idx
        self._rebuild_counter = 0
        self._rebuild_interval = 500
        # Shared KD-trees for body-drag checks
        self._visited_tree: cKDTree | None = None
        self._visited_indices: NDArray[np.intp] | None = None
        # Robot footprints for inter-robot physical collision
        self._robot_footprints: Dict[int, RobotFootprint] = {}
        self._ss_od = ss_od
        self._ntnl_od = ntnl_od

    @property
    def visited(self) -> Set[int]:
        return self._visited

    @property
    def unvisited(self) -> Set[int]:
        return self._unvisited

    @property
    def visited_by(self) -> Dict[int, int]:
        return self._visited_by

    def mark_visited(self, node: int, robot_idx: int) -> None:
        """Mark a node as printed by a specific robot."""
        self._unvisited.discard(node)
        self._visited.add(node)
        self._visited_by[node] = robot_idx
        self._rebuild_counter += 1
        if self._rebuild_counter >= self._rebuild_interval:
            self._rebuild_visited_tree()

    def get_visited_tree(self) -> cKDTree | None:
        return self._visited_tree

    def get_visited_indices(self) -> NDArray[np.intp] | None:
        return self._visited_indices

    def _rebuild_visited_tree(self) -> None:
        """Rebuild the shared visited KD-tree."""
        if self._visited:
            v_idx = np.array(sorted(self._visited), dtype=np.intp)
            self._visited_indices = v_idx
            self._visited_tree = cKDTree(self._points[v_idx])
        else:
            self._visited_tree = None
            self._visited_indices = None
        self._rebuild_counter = 0
        logger.debug(
            "Shared visited KD-tree rebuilt: %d visited",
            len(self._visited),
        )

    def set_robot_footprint(self, robot_idx: int, footprint: RobotFootprint) -> None:
        """Update a robot's physical footprint (called when robot state changes)."""
        self._robot_footprints[robot_idx] = footprint

    def check_inter_robot_collision(
        self,
        body_points: NDArray[np.floating],
        requesting_robot: int,
        clearance: float = 2.0,
    ) -> bool:
        """Check if a needle body collides with any OTHER robot's footprint.

        Returns True if collision detected. Uses combined tube radii + clearance
        as the collision envelope.
        """
        collision_r = (self._ss_od + self._ntnl_od) / 2.0 + clearance
        for ridx, footprint in self._robot_footprints.items():
            if ridx == requesting_robot:
                continue
            hits = footprint.body_tree.query_ball_point(body_points, collision_r)
            if any(len(h) > 0 for h in hits):
                return True
        return False


# ---------------------------------------------------------------------------
# CTR collision detector
# ---------------------------------------------------------------------------

class CTRCollisionDetector:
    """Collision detector that models the full curved CTR needle body.

    Parameters
    ----------
    points : ndarray (N, 3)
        Node coordinates (xyz).
    ctr_config : CTRConfig
        CTR kinematics configuration.
    nozzle_radius : float
        Physical tube radius (mm) — used as the collision envelope.
    graph : dict or None
        Adjacency list. If provided, graph neighbors of a candidate are
        exempted from shaft-collision checks.
    tolerance : float
        3D proximity tolerance (mm) for exception rule.
    tolerance_flag : bool
        Whether to apply the tolerance exception.
    n_arc_samples : int
        Number of sample points along the nitinol arc for body discretization.
    rebuild_interval : int
        KD-tree rebuild frequency.
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
        shared_state: Optional[SharedVisitedState] = None,
        robot_idx: int = 0,
    ) -> None:
        self._points = points[:, :3].copy()
        self._ctr_config = ctr_config
        self._nozzle_radius = nozzle_radius
        self._graph = graph
        self._tolerance = tolerance
        self._tolerance_flag = tolerance_flag
        self._n_arc_samples = n_arc_samples
        self._rebuild_interval = rebuild_interval
        self._shared_state = shared_state
        self._robot_idx = robot_idx

        self._n_total = points.shape[0]
        self._unvisited: Set[int] = set(range(self._n_total))
        self._visited: Set[int] = set()
        self._removals_since_rebuild = 0

        # Tip exclusion: body sample points within this distance of the
        # candidate are not collision-checked. Set to 3× nozzle_radius so
        # that adjacent interpolated nodes (spaced at ~nozzle_radius) near
        # the tip are not falsely flagged as blockers.
        self._tip_exclusion_r = 3.0 * nozzle_radius

        # Build 3D KD-trees (unvisited and visited)
        self._unvisited_tree = cKDTree(self._points)
        self._unvisited_indices = np.arange(self._n_total)
        self._visited_tree: cKDTree | None = None
        self._visited_indices: NDArray[np.intp] | None = None

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def is_valid(self, node: int) -> bool:
        """Check whether printing *node* is collision-free with the CTR body.

        A node is valid if:
        1. It is unvisited.
        2. It is reachable by the CTR (within the toroidal workspace).
        3. The non-tip portion of the needle body does not collide with any
           **unvisited** node that is not a graph neighbor of the candidate.
        4. The non-tip portion of the needle body does not collide with any
           **visited** (already printed) node (body-drag check).
        """
        if node not in self._unvisited:
            return False

        # Fast reachability check with precomputed direction matrix
        snt = fast_global_to_snt(self._points[node], self._ctr_config)
        if snt is None:
            return False
        z_ss, z_ntnl, theta = snt
        if z_ss < 0 or z_ss > self._ctr_config.ss_lim:
            return False
        if z_ntnl < 0 or z_ntnl > self._ctr_config.ntnl_lim:
            return False

        # Compute needle body (vectorized, no Python loops)
        body = compute_needle_body(
            z_ss, z_ntnl, theta, self._ctr_config, self._n_arc_samples,
        )

        target_pt = self._points[node]
        collision_r = self._nozzle_radius
        tip_excl_r_sq = self._tip_exclusion_r ** 2

        # Vectorized tip exclusion
        dists_sq = np.sum((body - target_pt) ** 2, axis=1)
        far_body = body[dists_sq >= tip_excl_r_sq]

        if len(far_body) == 0:
            return True

        # Collect graph neighbors for exemption
        if self._graph is not None and node in self._graph:
            neighbors = set(self._graph[node])
        else:
            neighbors = set()

        # --- Batch shaft check (unvisited) ---
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
                return False

        # --- Batch drag check (visited) ---
        # Use shared visited tree if available (multi-robot mode),
        # otherwise fall back to local visited tree (single-robot mode).
        drag_tree = None
        if self._shared_state is not None:
            drag_tree = self._shared_state.get_visited_tree()
        elif self._visited_tree is not None and len(self._visited) > 0:
            drag_tree = self._visited_tree

        if drag_tree is not None:
            drag_counts = drag_tree.query_ball_point(
                far_body, collision_r, return_length=True,
            )
            if np.any(drag_counts > 0):
                return False

        # --- Inter-robot physical collision check ---
        if self._shared_state is not None:
            if self._shared_state.check_inter_robot_collision(
                far_body, self._robot_idx,
            ):
                return False

        return True

    def mark_visited(self, node: int) -> None:
        """Record that *node* has been printed."""
        self._unvisited.discard(node)
        self._visited.add(node)
        self._removals_since_rebuild += 1

        # Delegate to shared state for cross-robot visibility
        if self._shared_state is not None:
            self._shared_state.mark_visited(node, self._robot_idx)

        if self._removals_since_rebuild >= self._rebuild_interval:
            self._rebuild_trees()

    def is_visited(self, node: int) -> bool:
        """Return ``True`` if *node* has already been printed."""
        return node not in self._unvisited

    def has_unvisited(self) -> bool:
        """Return ``True`` if any nodes remain unprinted."""
        return len(self._unvisited) > 0

    @property
    def unvisited(self) -> Set[int]:
        """The current set of unvisited node indices."""
        return self._unvisited

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def bulk_init_visited(self, visited_nodes: Set[int]) -> None:
        """Batch-initialize visited/unvisited sets without per-node KD-tree rebuilds.

        Much faster than calling ``mark_visited()`` in a loop when a large
        number of nodes must be pre-marked (e.g. multi-robot init where all
        non-assigned nodes start as visited).
        """
        self._visited = visited_nodes.copy()
        self._unvisited = set(range(self._n_total)) - self._visited

        # Also update shared state (without triggering its incremental rebuilds)
        if self._shared_state is not None:
            for n in visited_nodes:
                self._shared_state._visited.add(n)
                self._shared_state._unvisited.discard(n)

        # Single rebuild of both trees
        self._rebuild_trees()
        if self._shared_state is not None:
            self._shared_state._rebuild_visited_tree()

    def _rebuild_trees(self) -> None:
        """Rebuild both KD-trees from current unvisited/visited sets."""
        if self._unvisited:
            uv_idx = np.array(sorted(self._unvisited), dtype=np.intp)
            self._unvisited_indices = uv_idx
            self._unvisited_tree = cKDTree(self._points[uv_idx])
        else:
            self._unvisited_indices = np.array([], dtype=np.intp)

        if self._visited:
            v_idx = np.array(sorted(self._visited), dtype=np.intp)
            self._visited_indices = v_idx
            self._visited_tree = cKDTree(self._points[v_idx])
        else:
            self._visited_tree = None
            self._visited_indices = None

        self._removals_since_rebuild = 0
        logger.debug(
            "CTR KD-trees rebuilt: %d unvisited, %d visited",
            len(self._unvisited), len(self._visited),
        )
