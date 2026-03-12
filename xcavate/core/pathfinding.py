"""Collision-aware pathfinding for vascular network printing.

This module refactors the pathfinding logic from xcavate.py (lines 911-981)
into a clean architecture:

- **DFS strategy** -- modified depth-first search with collision validity
  checking.  Nodes are printed starting from the lowest unvisited node,
  traversing the graph via DFS while skipping nodes that would collide
  with unprinted nodes beneath them.

The :class:`CollisionDetector` is backed by :class:`scipy.spatial.cKDTree`
for O(k log N) spatial queries, replacing the original O(N) brute-force
validity check.

Usage
-----
::

    from xcavate.core.pathfinding import generate_print_passes
    from xcavate.config import XcavateConfig

    passes = generate_print_passes(graph, points, config)
"""

from __future__ import annotations

import heapq
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Set

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)

# Re-use the Graph type alias from the graph module
Graph = Dict[int, List[int]]


# ---------------------------------------------------------------------------
# Collision detection
# ---------------------------------------------------------------------------

class CollisionDetector:
    """Spatial collision detector for nozzle clearance during printing.

    Maintains a KD-tree over the XY coordinates of unvisited nodes so that
    the validity check (is a node safe to print without blocking nodes below
    it?) runs in O(k log N) instead of O(N).

    The collision rule is:
        A node is **invalid** if *any* unvisited node exists such that:
        1. Its XY distance from the candidate is less than ``nozzle_radius``,
           AND
        2. Its z-coordinate is strictly *below* the candidate's z-coordinate.

        Exception: if ``tolerance_flag`` is set and the full 3-D distance
        is less than ``tolerance``, the blocking node is ignored (it is
        considered close enough to be printed in the same extrusion move).

    Parameters
    ----------
    points : ndarray of shape (N, 3)
        Full coordinate array for all nodes.
    nozzle_radius : float
        Half the outer nozzle diameter (mm).
    tolerance : float
        3-D proximity tolerance for the exception rule (mm).
    tolerance_flag : bool
        Whether to apply the tolerance exception.
    rebuild_interval : int
        How many ``mark_visited`` calls between KD-tree rebuilds.
        A smaller value gives tighter spatial indexing at the cost of
        more rebuilds; 500 is a reasonable default for networks up to
        ~50 000 nodes.
    """

    def __init__(
        self,
        points: NDArray[np.floating],
        nozzle_radius: float,
        tolerance: float = 0.0,
        tolerance_flag: bool = False,
        rebuild_interval: int = 500,
    ) -> None:
        self._points = points
        self._nozzle_radius = nozzle_radius
        self._tolerance = tolerance
        self._tolerance_flag = tolerance_flag
        self._rebuild_interval = rebuild_interval

        self._n_total = points.shape[0]
        self._unvisited: Set[int] = set(range(self._n_total))
        self._removals_since_rebuild = 0

        # Build initial KD-tree on XY coordinates of all nodes
        self._xy_points = points[:, :2].copy()
        self._tree = cKDTree(self._xy_points)
        # Track which indices in the tree correspond to unvisited nodes
        self._tree_indices: NDArray[np.intp] = np.arange(self._n_total)

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def is_valid(self, node: int) -> bool:
        """Check whether printing *node* is collision-free.

        A node is valid (printable) if no unvisited node below it in z
        falls within the nozzle shadow in XY.

        Parameters
        ----------
        node : int
            Index of the candidate node.

        Returns
        -------
        bool
            ``True`` if the node can safely be printed now.
        """
        if node not in self._unvisited:
            return False

        x0, y0, z0 = self._points[node]

        # Query all unvisited nodes within nozzle_radius in XY
        nearby = self._tree.query_ball_point([x0, y0], self._nozzle_radius)

        for idx in nearby:
            other = self._tree_indices[idx] if idx < len(self._tree_indices) else idx
            if other == node:
                continue
            if other not in self._unvisited:
                continue

            x1, y1, z1 = self._points[other]

            # The other node is below this candidate
            if z1 < z0:
                if self._tolerance_flag:
                    dx = x1 - x0
                    dy = y1 - y0
                    dz = z1 - z0
                    dist_3d_sq = dx * dx + dy * dy + dz * dz
                    if dist_3d_sq < self._tolerance * self._tolerance:
                        # Within tolerance -- not a blocking collision
                        continue
                return False

        return True

    def mark_visited(self, node: int) -> None:
        """Record that *node* has been printed.

        Removes the node from the unvisited set and periodically rebuilds
        the KD-tree to maintain query efficiency.

        Parameters
        ----------
        node : int
        """
        self._unvisited.discard(node)
        self._removals_since_rebuild += 1

        if self._removals_since_rebuild >= self._rebuild_interval:
            self._rebuild_tree()

    def is_visited(self, node: int) -> bool:
        """Return ``True`` if *node* has already been printed."""
        return node not in self._unvisited

    def has_unvisited(self) -> bool:
        """Return ``True`` if any nodes remain unprinted."""
        return len(self._unvisited) > 0

    @property
    def unvisited(self) -> Set[int]:
        """The current set of unvisited node indices (read-only view)."""
        return self._unvisited

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _rebuild_tree(self) -> None:
        """Rebuild the KD-tree over currently unvisited nodes only."""
        if not self._unvisited:
            return
        indices = np.array(sorted(self._unvisited), dtype=np.intp)
        self._tree_indices = indices
        self._tree = cKDTree(self._xy_points[indices])
        self._removals_since_rebuild = 0
        logger.debug(
            "KD-tree rebuilt with %d unvisited nodes", len(indices)
        )


# ---------------------------------------------------------------------------
# Abstract strategy
# ---------------------------------------------------------------------------

class PathfindingStrategy(ABC):
    """Base class for print-pass generation strategies.

    Subclasses must implement :meth:`generate_print_passes`, which takes
    a graph, coordinate array, and configuration, and returns an ordered
    mapping of pass-index to node-visit-order.
    """

    @abstractmethod
    def generate_print_passes(
        self,
        graph: Graph,
        points: NDArray[np.floating],
        nozzle_radius: float,
        tolerance: float = 0.0,
        tolerance_flag: bool = False,
    ) -> Dict[int, List[int]]:
        """Partition graph nodes into collision-free print passes.

        Parameters
        ----------
        graph : dict[int, list[int]]
            Adjacency list (sorted neighbours with self-loops).
        points : ndarray of shape (N, 3)
            Node coordinates.
        nozzle_radius : float
        tolerance : float
        tolerance_flag : bool

        Returns
        -------
        dict[int, list[int]]
            ``{pass_index: [node_indices_in_visit_order]}``.
        """


# ---------------------------------------------------------------------------
# DFS strategy
# ---------------------------------------------------------------------------

class DFSStrategy(PathfindingStrategy):
    """Modified depth-first search with collision validity checking.

    Algorithm
    ---------
    1. Initialise a min-heap keyed on z-coordinate for O(log N) retrieval
       of the lowest unvisited node.
    2. While unvisited nodes remain:
       a. Pop the lowest-z unvisited node from the heap.
       b. Run an iterative (non-recursive) DFS from that node, adding
          each valid node to the current print pass.
       c. Store the pass and repeat.

    This replaces the original recursive DFS (which risks hitting Python's
    recursion limit on large networks) and the O(N) linear scan for the
    lowest unvisited node.
    """

    def generate_print_passes(
        self,
        graph: Graph,
        points: NDArray[np.floating],
        nozzle_radius: float,
        tolerance: float = 0.0,
        tolerance_flag: bool = False,
        config=None,
    ) -> Dict[int, List[int]]:
        """Generate print passes via collision-aware iterative DFS.

        Parameters
        ----------
        graph : dict[int, list[int]]
            Adjacency list produced by :func:`~xcavate.core.graph.build_graph`.
        points : ndarray of shape (N, 3)
            Node coordinates.
        nozzle_radius : float
            Half the outer nozzle diameter (mm).
        tolerance : float
            3-D proximity tolerance (mm).
        tolerance_flag : bool
            Whether to apply tolerance exception.
        config : XcavateConfig, optional
            Full configuration; used to select CTR collision detector when
            ``printer_type == PrinterType.CTR``.

        Returns
        -------
        dict[int, list[int]]
            Ordered mapping of pass index to node visit order.
        """
        # Select collision detector based on printer type
        from xcavate.config import PrinterType
        if config is not None and hasattr(config, 'printer_type') and config.printer_type == PrinterType.CTR:
            from xcavate.core.ctr_collision import CTRCollisionDetector
            from xcavate.core.ctr_kinematics import CTRConfig
            ctr_config = CTRConfig.from_xcavate_config(config)
            detector = CTRCollisionDetector(
                points,
                ctr_config,
                nozzle_radius,
                graph=graph,
                tolerance=tolerance,
                tolerance_flag=tolerance_flag,
                n_arc_samples=config.ctr_needle_body_samples,
            )
        else:
            detector = CollisionDetector(
                points,
                nozzle_radius,
                tolerance=tolerance,
                tolerance_flag=tolerance_flag,
            )

        # Build min-heap of (z, node_index) for efficient lowest-unvisited
        z_heap: List[tuple] = []
        for node in range(points.shape[0]):
            heapq.heappush(z_heap, (float(points[node, 2]), node))

        print_passes: Dict[int, List[int]] = {}
        pass_idx = 0

        while detector.has_unvisited():
            # Find the lowest unvisited node via the heap
            start_node = _pop_lowest_unvisited(z_heap, detector)
            if start_node is None:
                break  # All remaining heap entries are visited

            pass_list = iterative_dfs(graph, start_node, detector, points)

            if pass_list:
                print_passes[pass_idx] = pass_list
                pass_idx += 1

        logger.info(
            "DFS pathfinding complete: %d print passes generated", pass_idx
        )
        return print_passes


class AngularSectorStrategy(PathfindingStrategy):
    """Angular sector partitioning with Eades ordering and greedy DFS.

    Algorithm
    ---------
    1. Compute theta for all reachable nodes via vectorized inverse kinematics.
    2. Partition into K equal-width angular sectors covering [-pi, pi].
    3. Build conflict graph once (shared across sectors).
    4. For each sector: extract intra-sector conflict subgraph, compute Eades
       ordering, run DFS passes with greedy neighbor selection.
    5. Cleanup sweep: remaining unvisited nodes get a final Z-heap DFS pass.
    """

    def generate_print_passes(
        self,
        graph: Graph,
        points: NDArray[np.floating],
        nozzle_radius: float,
        tolerance: float = 0.0,
        tolerance_flag: bool = False,
        config=None,
    ) -> Dict[int, List[int]]:
        from xcavate.config import PrinterType
        from xcavate.core.ctr_kinematics import (
            CTRConfig,
            batch_global_to_local,
            batch_local_to_snt,
        )
        from xcavate.core.swept_volume import (
            build_conflict_graph,
            eades_greedy_fas,
        )

        if config is None or config.printer_type != PrinterType.CTR:
            raise ValueError("AngularSectorStrategy requires printer_type == CTR")

        from xcavate.core.ctr_collision import CTRCollisionDetector

        ctr_config = CTRConfig.from_xcavate_config(config)
        n_arc_samples = getattr(config, 'ctr_needle_body_samples', 20)
        num_sectors = getattr(config, 'ctr_num_sectors', 8)

        graph_nodes = sorted(graph.keys())
        graph_node_set = set(graph_nodes)

        # --- Step 1: Compute theta for all graph nodes (vectorized) ---
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
        theta_values = snt[:, 2]  # (N,), NaN for unreachable

        # Map node -> theta
        node_theta: Dict[int, float] = {}
        for i, node in enumerate(graph_nodes):
            t = theta_values[i]
            if not np.isnan(t):
                node_theta[node] = float(t)

        # --- Step 2: Partition into K sectors ---
        sector_width = 2.0 * np.pi / num_sectors
        sectors: Dict[int, List[int]] = {k: [] for k in range(num_sectors)}
        no_theta_nodes: List[int] = []

        for node in graph_nodes:
            if node in node_theta:
                t = node_theta[node]
                k = int(np.clip((t + np.pi) / sector_width, 0, num_sectors - 1))
                sectors[k].append(node)
            else:
                no_theta_nodes.append(node)

        logger.info(
            "Angular sectors: %d sectors, %d nodes with theta, %d without",
            num_sectors,
            sum(len(v) for v in sectors.values()),
            len(no_theta_nodes),
        )

        # --- Step 3: Build conflict graph once ---
        logger.info("Building swept-volume conflict graph...")
        conflict_graph = build_conflict_graph(
            points, ctr_config, graph, nozzle_radius, n_arc_samples,
        )

        # Precompute conflict outdegree for greedy DFS
        conflict_outdegree: Dict[int, int] = {}
        for node in graph_nodes:
            conflict_outdegree[node] = len(conflict_graph.get(node, set()))

        # --- Step 4: Create collision detector ---
        detector = CTRCollisionDetector(
            points,
            ctr_config,
            nozzle_radius,
            graph=graph,
            tolerance=tolerance,
            tolerance_flag=tolerance_flag,
            n_arc_samples=n_arc_samples,
        )

        print_passes: Dict[int, List[int]] = {}
        pass_idx = 0

        # --- Step 4a: Process each sector ---
        for sector_idx in range(num_sectors):
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

            # Build priority heap for this sector
            sector_heap: List[tuple] = []
            for node in sector_order:
                heapq.heappush(sector_heap, (priority[node], node))

            # Run DFS passes from sector start nodes
            while sector_heap:
                start_node = _pop_lowest_unvisited(sector_heap, detector)
                if start_node is None:
                    break
                if start_node not in graph_node_set:
                    continue

                pass_list = iterative_dfs_greedy(
                    graph, start_node, detector, points,
                    conflict_outdegree=conflict_outdegree,
                )

                if pass_list:
                    print_passes[pass_idx] = pass_list
                    pass_idx += 1

            logger.debug(
                "Sector %d: %d nodes, %d passes so far",
                sector_idx, len(sector_nodes), pass_idx,
            )

        # --- Step 5: Cleanup sweep for remaining unvisited nodes ---
        if detector.has_unvisited():
            cleanup_nodes = sorted(
                [n for n in graph_nodes if not detector.is_visited(n)],
            )
            if cleanup_nodes:
                # Include no-theta nodes
                cleanup_nodes = sorted(
                    set(cleanup_nodes) | set(n for n in no_theta_nodes if not detector.is_visited(n)),
                )
                z_heap: List[tuple] = []
                for node in cleanup_nodes:
                    heapq.heappush(z_heap, (float(points[node, 2]), node))

                while z_heap:
                    start_node = _pop_lowest_unvisited(z_heap, detector)
                    if start_node is None:
                        break
                    pass_list = iterative_dfs_greedy(
                        graph, start_node, detector, points,
                        conflict_outdegree=conflict_outdegree,
                    )
                    if pass_list:
                        print_passes[pass_idx] = pass_list
                        pass_idx += 1

        logger.info(
            "AngularSector pathfinding complete: %d print passes generated",
            pass_idx,
        )
        return print_passes


class SweptVolumeStrategy(PathfindingStrategy):
    """Swept-volume conflict graph ordering with DFS traversal.

    Algorithm
    ---------
    1. Build a conflict graph from needle-body swept volumes.
    2. Topological sort (with greedy cycle breaking) → priority ordering.
    3. Use the topo order as the start-node priority for DFS passes,
       rather than Z-ordering.
    4. Run DFS with CTR collision detector (same as DFSStrategy).
    """

    def generate_print_passes(
        self,
        graph: Graph,
        points: NDArray[np.floating],
        nozzle_radius: float,
        tolerance: float = 0.0,
        tolerance_flag: bool = False,
        config=None,
    ) -> Dict[int, List[int]]:
        from xcavate.config import PrinterType
        from xcavate.core.swept_volume import (
            build_conflict_graph,
            topological_order_with_cycle_breaking,
        )

        if config is None or config.printer_type != PrinterType.CTR:
            raise ValueError("SweptVolumeStrategy requires printer_type == CTR")

        from xcavate.core.ctr_collision import CTRCollisionDetector
        from xcavate.core.ctr_kinematics import CTRConfig

        ctr_config = CTRConfig.from_xcavate_config(config)
        n_arc_samples = getattr(config, 'ctr_needle_body_samples', 20)

        # Step 1: Build conflict graph
        logger.info("Building swept-volume conflict graph...")
        conflict_graph = build_conflict_graph(
            points, ctr_config, graph, nozzle_radius, n_arc_samples,
        )

        # Step 2: Topological sort
        graph_nodes = sorted(graph.keys())
        topo_order = topological_order_with_cycle_breaking(conflict_graph, graph_nodes)

        # Step 3: Build priority map (lower index = earlier in topo order = print first)
        priority = {node: idx for idx, node in enumerate(topo_order)}

        # Step 4: Create collision detector
        detector = CTRCollisionDetector(
            points,
            ctr_config,
            nozzle_radius,
            graph=graph,
            tolerance=tolerance,
            tolerance_flag=tolerance_flag,
            n_arc_samples=n_arc_samples,
        )

        # Build priority heap using topo order instead of Z
        priority_heap: List[tuple] = []
        for node in graph_nodes:
            heapq.heappush(priority_heap, (priority.get(node, len(topo_order)), node))

        print_passes: Dict[int, List[int]] = {}
        pass_idx = 0

        while detector.has_unvisited():
            start_node = _pop_lowest_unvisited(priority_heap, detector)
            if start_node is None:
                break

            pass_list = iterative_dfs(graph, start_node, detector, points)

            if pass_list:
                print_passes[pass_idx] = pass_list
                pass_idx += 1

        logger.info(
            "SweptVolume pathfinding complete: %d print passes generated", pass_idx
        )
        return print_passes


def _pop_lowest_unvisited(
    z_heap: List[tuple],
    detector: CollisionDetector,
) -> int | None:
    """Pop the lowest-z unvisited node from the min-heap.

    Skips over already-visited entries (lazy deletion).

    Parameters
    ----------
    z_heap : list of (z, node_index)
    detector : CollisionDetector

    Returns
    -------
    int or None
        Node index, or ``None`` if the heap is exhausted.
    """
    while z_heap:
        z_val, node = heapq.heappop(z_heap)
        if not detector.is_visited(node):
            return node
    return None


def iterative_dfs(
    graph: Graph,
    start_node: int,
    detector: CollisionDetector,
    points: NDArray[np.floating],
) -> List[int]:
    """Explicit-stack DFS with collision validity checking.

    Replaces the recursive ``dfs()`` from the original script to avoid
    Python's recursion limit on large networks.

    For each node popped from the stack:
    1. Skip if already visited.
    2. Skip if not valid (would collide with unvisited nodes below).
    3. Mark visited, append to the pass list.
    4. Push unvisited neighbours in *reverse* sorted order so that the
       lowest-indexed neighbour is processed first (matching the original
       traversal order).

    Parameters
    ----------
    graph : dict[int, list[int]]
        Adjacency list.
    start_node : int
        Node to begin DFS from.
    detector : CollisionDetector
        Tracks visited state and collision validity.
    points : ndarray of shape (N, 3)
        Node coordinates (used only for logging/debugging).

    Returns
    -------
    list[int]
        Nodes visited in this pass, in visit order.
    """
    pass_list: List[int] = []
    stack: List[int] = [start_node]

    while stack:
        node = stack.pop()

        if detector.is_visited(node):
            continue

        if not detector.is_valid(node):
            continue

        detector.mark_visited(node)
        pass_list.append(node)

        # Push neighbours in reverse order so that the smallest index
        # (first in the sorted adjacency list) is popped first
        for neighbour in reversed(graph[node]):
            if not detector.is_visited(neighbour):
                stack.append(neighbour)

    return pass_list


def iterative_dfs_gimbal(
    graph: Graph,
    start_node: int,
    detector,
    points: NDArray[np.floating],
    conflict_outdegree: Dict[int, int] | None = None,
) -> List[int]:
    """DFS that prioritizes neighbors reachable with the active gimbal config.

    Sorts unvisited neighbors into two tiers:
    1. Reachable with the detector's active config (quick IK + bounds check)
    2. All others

    Within each tier, sort by ``conflict_outdegree`` ascending if provided.
    Tier 1 nodes are pushed onto the stack last (LIFO) so they are processed
    first, promoting gimbal config continuity.

    Parameters
    ----------
    graph : dict[int, list[int]]
    start_node : int
    detector
        Must have ``get_active_config()`` method returning a ``CTRConfig``.
    points : ndarray (N, 3)
    conflict_outdegree : dict[int, int] or None

    Returns
    -------
    list[int]
        Nodes visited in this pass, in visit order.
    """
    from xcavate.core.ctr_kinematics import fast_global_to_snt as _fast_snt

    pass_list: List[int] = []
    stack: List[int] = [start_node]

    while stack:
        node = stack.pop()

        if detector.is_visited(node):
            continue

        if not detector.is_valid(node):
            continue

        detector.mark_visited(node)
        pass_list.append(node)

        neighbors = graph[node]
        unvisited = [n for n in neighbors if not detector.is_visited(n)]

        if not unvisited:
            continue

        # Quick IK-only reachability check with active config
        active_cfg = detector.get_active_config()
        tier1: List[int] = []  # reachable with active config
        tier2: List[int] = []  # all others

        for n in unvisited:
            snt = _fast_snt(points[n], active_cfg)
            if (
                snt is not None
                and 0 <= snt[0] <= active_cfg.ss_lim
                and 0 <= snt[1] <= active_cfg.ntnl_lim
            ):
                tier1.append(n)
            else:
                tier2.append(n)

        # Sort within tiers: descending by conflict outdegree (LIFO stack
        # means last pushed = first popped, so descending → lowest first)
        if conflict_outdegree is not None:
            tier1.sort(key=lambda n: conflict_outdegree.get(n, 0), reverse=True)
            tier2.sort(key=lambda n: conflict_outdegree.get(n, 0), reverse=True)
        else:
            tier1 = list(reversed(tier1))
            tier2 = list(reversed(tier2))

        # Push tier2 first (processed last), then tier1 (processed first)
        for neighbour in tier2:
            stack.append(neighbour)
        for neighbour in tier1:
            stack.append(neighbour)

    return pass_list


def iterative_dfs_greedy(
    graph: Graph,
    start_node: int,
    detector: CollisionDetector,
    points: NDArray[np.floating],
    conflict_outdegree: Dict[int, int] | None = None,
) -> List[int]:
    """Explicit-stack DFS with greedy neighbor ordering.

    Identical to :func:`iterative_dfs` except neighbor ordering: neighbors
    are sorted by ``conflict_outdegree[node]`` (ascending) so that nodes
    whose bodies block fewer future nodes are visited first.

    Parameters
    ----------
    graph : dict[int, list[int]]
        Adjacency list.
    start_node : int
        Node to begin DFS from.
    detector : CollisionDetector
        Tracks visited state and collision validity.
    points : ndarray (N, 3)
        Node coordinates.
    conflict_outdegree : dict[int, int] or None
        Number of outgoing conflict edges per node.  If ``None``, falls
        back to index ordering (same as :func:`iterative_dfs`).

    Returns
    -------
    list[int]
        Nodes visited in this pass, in visit order.
    """
    pass_list: List[int] = []
    stack: List[int] = [start_node]

    while stack:
        node = stack.pop()

        if detector.is_visited(node):
            continue

        if not detector.is_valid(node):
            continue

        detector.mark_visited(node)
        pass_list.append(node)

        neighbors = graph[node]
        unvisited_neighbors = [n for n in neighbors if not detector.is_visited(n)]

        if conflict_outdegree is not None and unvisited_neighbors:
            # Sort by conflict outdegree DESCENDING (highest pushed first,
            # popped last → lowest outdegree processed first)
            unvisited_neighbors.sort(
                key=lambda n: conflict_outdegree.get(n, 0),
                reverse=True,
            )
        else:
            # Fall back to reversed index order (same as iterative_dfs)
            unvisited_neighbors = list(reversed(unvisited_neighbors))

        for neighbour in unvisited_neighbors:
            stack.append(neighbour)

    return pass_list


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------

def generate_print_passes(
    graph: Graph,
    points: NDArray[np.floating],
    config,
) -> Dict[int, List[int]]:
    """Generate collision-free print passes using the configured strategy.

    This is the primary entry point consumed by the pipeline.  It reads
    the algorithm selection and collision parameters from the config
    object and dispatches to the appropriate strategy.

    Parameters
    ----------
    graph : dict[int, list[int]]
        Adjacency list from :func:`~xcavate.core.graph.build_graph`.
    points : ndarray of shape (N, 3)
        Interpolated node coordinates.
    config : XcavateConfig
        Runtime configuration.  The following fields are used:

        - ``config.algorithm`` -- selects the pathfinding strategy (DFS).
        - ``config.nozzle_radius`` -- half the nozzle outer diameter.
        - ``config.tolerance`` -- 3-D proximity tolerance.
        - ``config.tolerance_flag`` -- whether to apply the tolerance
          exception.

    Returns
    -------
    dict[int, list[int]]
        ``{pass_index: [node_indices_in_visit_order]}``.

    Raises
    ------
    ValueError
        If the configured algorithm is not recognised.
    """
    # Import here to avoid circular dependency at module level
    from xcavate.config import PathfindingAlgorithm

    if config.algorithm == PathfindingAlgorithm.DFS:
        strategy: PathfindingStrategy = DFSStrategy()
    elif config.algorithm == PathfindingAlgorithm.SWEPT_VOLUME:
        strategy = SweptVolumeStrategy()
    elif config.algorithm == PathfindingAlgorithm.ANGULAR_SECTOR:
        strategy = AngularSectorStrategy()
    else:
        raise ValueError(f"Unknown pathfinding algorithm: {config.algorithm}")

    return strategy.generate_print_passes(
        graph,
        points,
        nozzle_radius=config.nozzle_radius,
        tolerance=config.tolerance,
        tolerance_flag=config.tolerance_flag,
        config=config,
    )
