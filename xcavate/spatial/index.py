"""Spatial indexing for efficient collision detection using KD-trees."""

import numpy as np
from scipy.spatial import cKDTree
from typing import Optional, Set


class SpatialIndex:
    """KD-tree wrapper for XY-plane proximity queries.

    Used by the collision detector to efficiently find nodes within
    nozzle radius in the XY plane, replacing O(n) linear scan with
    O(k * log n) radius queries.
    """

    def __init__(self, points_xy: np.ndarray):
        """Build KD-tree from 2D (XY) coordinates.

        Args:
            points_xy: ndarray of shape (N, 2) with XY coordinates.
        """
        self._tree = cKDTree(points_xy) if len(points_xy) > 0 else None
        self._points = points_xy

    def query_radius(self, xy: np.ndarray, radius: float) -> list:
        """Find all points within radius of query point in XY plane.

        Args:
            xy: 2D query point [x, y].
            radius: Search radius.

        Returns:
            List of indices of points within radius.
        """
        if self._tree is None:
            return []
        return self._tree.query_ball_point(xy, r=radius)

    def query_nearest(self, xy: np.ndarray, k: int = 1):
        """Find k nearest neighbors to query point.

        Args:
            xy: 2D query point [x, y].
            k: Number of neighbors.

        Returns:
            (distances, indices) tuple.
        """
        if self._tree is None:
            return np.array([]), np.array([])
        return self._tree.query(xy, k=k)

    @property
    def size(self) -> int:
        return len(self._points)


class DynamicSpatialIndex:
    """Spatial index that supports efficient removal of visited nodes.

    Maintains a mapping between local (tree) indices and global (point array)
    indices. Rebuilds the tree periodically after removals to keep queries
    accurate.
    """

    def __init__(self, points: np.ndarray, rebuild_interval: int = 500):
        """Initialize with full point set.

        Args:
            points: ndarray of shape (N, 3+) with at least XYZ coordinates.
            rebuild_interval: Rebuild KD-tree after this many removals.
        """
        self._points = points
        self._unvisited: Set[int] = set(range(len(points)))
        self._rebuild_interval = rebuild_interval
        self._removals_since_rebuild = 0
        self._rebuild()

    def _rebuild(self):
        """Rebuild KD-tree from current unvisited nodes."""
        self._index_array = np.array(sorted(self._unvisited), dtype=np.intp)
        if len(self._index_array) > 0:
            self._tree = cKDTree(self._points[self._index_array, :2])
        else:
            self._tree = None
        self._removals_since_rebuild = 0

    def query_ball_xy(self, node: int, radius: float) -> list:
        """Find unvisited nodes within radius of node in XY plane.

        Args:
            node: Global index of the query node.
            radius: Search radius in XY.

        Returns:
            List of global indices of nearby unvisited nodes.
        """
        if self._tree is None:
            return []
        xy = self._points[node, :2]
        local_indices = self._tree.query_ball_point(xy, r=radius)
        return [self._index_array[i] for i in local_indices]

    def mark_visited(self, node: int):
        """Remove node from unvisited set."""
        self._unvisited.discard(node)
        self._removals_since_rebuild += 1
        if self._removals_since_rebuild >= self._rebuild_interval:
            self._rebuild()

    def is_visited(self, node: int) -> bool:
        return node not in self._unvisited

    def has_unvisited(self) -> bool:
        return len(self._unvisited) > 0

    @property
    def unvisited_count(self) -> int:
        return len(self._unvisited)
