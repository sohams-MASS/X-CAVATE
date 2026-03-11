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

        Returns
        -------
        dict[int, list[int]]
            Ordered mapping of pass index to node visit order.
        """
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
    else:
        raise ValueError(f"Unknown pathfinding algorithm: {config.algorithm}")

    return strategy.generate_print_passes(
        graph,
        points,
        nozzle_radius=config.nozzle_radius,
        tolerance=config.tolerance,
        tolerance_flag=config.tolerance_flag,
    )
