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
    ) -> None:
        self._points = points[:, :3].copy()
        self._ctr_config = ctr_config
        self._nozzle_radius = nozzle_radius
        self._graph = graph
        self._tolerance = tolerance
        self._tolerance_flag = tolerance_flag
        self._n_arc_samples = n_arc_samples
        self._rebuild_interval = rebuild_interval

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
        if self._visited_tree is not None and len(self._visited) > 0:
            drag_counts = self._visited_tree.query_ball_point(
                far_body, collision_r, return_length=True,
            )
            if np.any(drag_counts > 0):
                return False

        return True

    def mark_visited(self, node: int) -> None:
        """Record that *node* has been printed."""
        self._unvisited.discard(node)
        self._visited.add(node)
        self._removals_since_rebuild += 1

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
