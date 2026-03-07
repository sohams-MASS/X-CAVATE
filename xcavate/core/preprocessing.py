"""Interpolation and preprocessing of the vascular network geometry.

This module handles densification of the SimVascular network so that the
spacing between consecutive points never exceeds the nozzle radius.  This
is required for accurate collision detection and G-code generation
downstream.

Refactored from xcavate.py lines 396-516 with the following improvement:

  **O(n) interpolation instead of O(n^2).**  The original code called
  ``np.insert()`` inside a ``while`` loop.  Each insertion copies the
  entire array, making the algorithm quadratic in the number of output
  points.  This implementation pre-computes all interpolated points per
  vessel segment and concatenates them in a single ``np.concatenate()``
  call, reducing the complexity to O(n) where *n* is the final number of
  points.
"""

from __future__ import annotations

import math
from typing import Union

import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FLAG_VESSEL_START: float = 500.0
"""Sentinel value written into the flag column to mark original vessel
start points.  Used downstream to recover vessel boundaries after
interpolation."""

_FLAG_INTERPOLATED: float = 400.0
"""Placeholder value for the flag column of interpolated (synthetic) points."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def interpolate_network(
    points: NDArray[np.float64],
    coord_num_dict: dict[int, int],
    nozzle_radius: float,
    num_columns: int,
) -> NDArray[np.float64]:
    """Densify a vascular network so that no consecutive pair exceeds *nozzle_radius*.

    For every consecutive pair of points (p1, p2) within a vessel, if
    ``euclidean_distance(p1, p2) > nozzle_radius``, evenly-spaced
    intermediate points are inserted so that each sub-segment is at most
    *nozzle_radius* long.

    A **flag column** is appended as the last column of the output array:

    * ``500`` -- marks the first point of each original vessel (used by
      :func:`get_vessel_boundaries` and downstream graph construction).
    * ``400`` -- placeholder for interpolated points.
    * ``0``   -- all other original points.

    Parameters
    ----------
    points : ndarray, shape (N, C)
        Network coordinates.  *C* is 3, 4, or 5 depending on whether
        radius and artven columns are present.
    coord_num_dict : dict[int, int]
        Mapping from vessel index to the number of coordinate rows in
        that vessel (as returned by :func:`~xcavate.io.reader.read_network_file`).
    nozzle_radius : float
        Maximum allowed spacing between consecutive points (mm).
    num_columns : int
        Number of data columns in *points* (3, 4, or 5).  Determines how
        interpolated rows are constructed.

    Returns
    -------
    points_interp : ndarray, shape (M, C+1)
        Interpolated coordinate array with the appended flag column.
        ``M >= N`` because intermediate points have been added.

    Notes
    -----
    The radius and artven values for interpolated points are copied from
    the segment's start point, matching the original behaviour.
    """
    num_vessels = len(coord_num_dict)

    # --- 1. Append a flag column to the original points -----------------------
    #     Flag original vessel start points with 500.
    flag_col = np.zeros((points.shape[0], 1), dtype=np.float64)

    # Compute the start index of each vessel in the flat points array.
    vessel_starts: list[int] = []
    cumulative = 0
    for v in range(num_vessels):
        vessel_starts.append(cumulative)
        cumulative += coord_num_dict[v]

    for start_idx in vessel_starts:
        flag_col[start_idx, 0] = _FLAG_VESSEL_START

    # points_flagged has shape (N, C+1) -- original data + flag column
    points_flagged = np.hstack([points, flag_col])
    total_cols = points_flagged.shape[1]  # C + 1

    # --- 2. Pre-compute all output chunks (one list entry per segment) --------
    #     Instead of calling np.insert() in a loop (O(n^2)), we collect
    #     sub-arrays and concatenate once at the end (O(n)).
    chunks: list[NDArray[np.float64]] = []
    num_interpolated = 0

    for v in range(num_vessels):
        v_start = vessel_starts[v]
        v_count = coord_num_dict[v]

        for local_idx in range(v_count):
            global_idx = v_start + local_idx
            current_point = points_flagged[global_idx]

            # Always emit the current (original) point.
            chunks.append(current_point.reshape(1, total_cols))

            # If this is the last point of the vessel, no forward segment.
            if local_idx == v_count - 1:
                continue

            next_point = points_flagged[global_idx + 1]

            # Euclidean distance using only xyz (first 3 columns).
            dx = next_point[0] - current_point[0]
            dy = next_point[1] - current_point[1]
            dz = next_point[2] - current_point[2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)

            if dist <= nozzle_radius:
                continue

            # Number of sub-segments needed so each is <= nozzle_radius.
            scale = math.ceil(dist / nozzle_radius)
            num_new = scale - 1  # points to insert between current and next

            # Vectorised computation of all intermediate points at once.
            # fractions: array of shape (num_new,) with values 1/scale .. (scale-1)/scale
            fractions = np.arange(1, scale, dtype=np.float64) / scale

            # Interpolate xyz columns.
            interp_xyz = (
                current_point[:3]
                + np.outer(fractions, np.array([dx, dy, dz]))
            )

            # Build full rows for the interpolated points.
            interp_rows = np.empty((num_new, total_cols), dtype=np.float64)
            interp_rows[:, :3] = interp_xyz

            # Fill optional columns (radius, artven) from the segment start point.
            if num_columns >= 4:
                interp_rows[:, 3] = current_point[3]  # radius
            if num_columns >= 5:
                interp_rows[:, 4] = current_point[4]  # artven

            # Flag column: mark all interpolated points with the placeholder 400.
            interp_rows[:, -1] = _FLAG_INTERPOLATED

            # If num_columns == 3, the row is [x, y, z, flag].  Columns 3
            # through -2 (exclusive) are empty in that case, which is fine
            # because total_cols == 4 and column 3 IS the flag column.
            # For num_columns == 4, total_cols == 5 and columns are
            # [x, y, z, radius, flag].  For 5, [x, y, z, radius, artven, flag].

            chunks.append(interp_rows)
            num_interpolated += num_new

    # --- 3. Single concatenation ------------------------------------------
    points_interp = np.concatenate(chunks, axis=0)

    return points_interp


def get_vessel_boundaries(
    points_interp: NDArray[np.float64],
    coord_num_dict: dict[int, int],
) -> dict[int, dict[str, Union[int, int]]]:
    """Recover per-vessel start/end indices and counts after interpolation.

    After :func:`interpolate_network` has densified the array, vessel
    boundaries are identified by scanning for the ``500`` flag in the
    last column.

    Parameters
    ----------
    points_interp : ndarray, shape (M, C+1)
        Interpolated coordinate array (output of :func:`interpolate_network`).
    coord_num_dict : dict[int, int]
        Original vessel-to-count mapping (used only for its length to
        determine the expected number of vessels).

    Returns
    -------
    boundaries : dict[int, dict]
        Mapping from vessel index to a dictionary with keys:

        * ``"start"`` -- row index of the vessel's first point.
        * ``"end"``   -- row index of the vessel's last point (inclusive).
        * ``"count"`` -- number of points belonging to this vessel.
        * ``"nodes"`` -- list of all row indices for this vessel.

    Notes
    -----
    This replaces the manual loop at xcavate.py lines 500-516.  The
    ``coord_num_dict_interp`` computed there is available as
    ``{v: info["count"] for v, info in boundaries.items()}``.
    """
    num_vessels = len(coord_num_dict)

    # Locate all rows where the flag column equals 500 (vessel start markers).
    flag_col = points_interp[:, -1]
    start_indices = np.flatnonzero(flag_col == _FLAG_VESSEL_START).tolist()

    if len(start_indices) != num_vessels:
        raise ValueError(
            f"Expected {num_vessels} vessel start markers (flag=500) in the "
            f"interpolated array, but found {len(start_indices)}."
        )

    total_points = points_interp.shape[0]
    boundaries: dict[int, dict[str, Union[int, int]]] = {}

    for v in range(num_vessels):
        v_start = start_indices[v]

        if v < num_vessels - 1:
            v_end = start_indices[v + 1] - 1
        else:
            v_end = total_points - 1

        count = v_end - v_start + 1
        nodes = list(range(v_start, v_end + 1))

        boundaries[v] = {
            "start": v_start,
            "end": v_end,
            "count": count,
            "nodes": nodes,
        }

    return boundaries
