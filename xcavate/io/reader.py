"""Read and preprocess SimVascular network files and inlet/outlet specifications.

This module handles the first stage of the X-CAVATE pipeline: parsing the raw
text files exported from SimVascular, converting units, scaling geometry, and
locating inlet/outlet nodes within the network.

Refactored from xcavate.py lines 191-323 with the following improvements:
  - No intermediate files written to disk during parsing
  - Vectorised rounding via np.round() instead of triple-nested Python loops
  - Fuzzy coordinate matching via scipy.spatial.cKDTree instead of exact
    float comparison in nested loops
  - Arbitrary numbers of inlets and outlets (original assumed exactly one of each section)
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_network_file(
    path: Union[str, Path],
) -> tuple[NDArray[np.float64], dict[int, int]]:
    """Parse a SimVascular network file into a coordinate array.

    The file alternates between ``Vessel N`` header lines and data rows.
    Each data row contains at least three columns (x, y, z) and optionally
    a fourth (radius) and fifth (artven flag).  Blank lines are skipped.

    Parameters
    ----------
    path : str or Path
        Path to the SimVascular network text file.

    Returns
    -------
    points : ndarray, shape (N, C)
        Floating-point coordinate array where *C* is 3, 4, or 5 depending
        on whether radius and artven columns are present.
    coord_num_dict : dict[int, int]
        Mapping from vessel index (0-based) to the number of coordinate
        rows belonging to that vessel.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file contains no vessels or no coordinate rows.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Network file not found: {path}")

    # Two-pass approach: first pass collects raw text lines per vessel so we
    # never write an intermediate file to disk.
    coord_rows: list[list[float]] = []
    coord_num_dict: dict[int, int] = {}
    current_vessel: int = -1

    with open(path, "r") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("Vessel"):
                current_vessel += 1
                coord_num_dict[current_vessel] = 0
                continue
            # Data row -- split on whitespace and convert to float
            values = [float(v) for v in stripped.split()]
            coord_rows.append(values)
            coord_num_dict[current_vessel] += 1

    if current_vessel < 0:
        raise ValueError(f"No 'Vessel' headers found in {path}")
    if not coord_rows:
        raise ValueError(f"No coordinate rows found in {path}")

    points = np.array(coord_rows, dtype=np.float64)
    return points, coord_num_dict


def read_inlet_outlet_file(
    path: Union[str, Path],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Parse an inlet/outlet specification file.

    The file uses ``inlet`` and ``outlet`` keywords as section headers.
    Coordinate rows below ``inlet`` (and before ``outlet``) are treated as
    inlet positions; rows below ``outlet`` are treated as outlet positions.
    Multiple ``inlet`` / ``outlet`` sections are supported and their
    coordinates are concatenated in order of appearance.

    Parameters
    ----------
    path : str or Path
        Path to the inlet/outlet text file.

    Returns
    -------
    inlets : ndarray, shape (I, 3)
        Inlet coordinates (x, y, z).
    outlets : ndarray, shape (O, 3)
        Outlet coordinates (x, y, z).

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If neither ``inlet`` nor ``outlet`` sections are found.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Inlet/outlet file not found: {path}")

    inlet_rows: list[list[float]] = []
    outlet_rows: list[list[float]] = []
    current_section: str | None = None

    with open(path, "r") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if lower == "inlet":
                current_section = "inlet"
                continue
            if lower == "outlet":
                current_section = "outlet"
                continue
            # Data row
            values = [float(v) for v in stripped.split()]
            if current_section == "inlet":
                inlet_rows.append(values[:3])
            elif current_section == "outlet":
                outlet_rows.append(values[:3])

    if not inlet_rows and not outlet_rows:
        raise ValueError(
            f"No inlet or outlet sections found in {path}. "
            "Expected 'inlet' and/or 'outlet' section headers."
        )

    inlets = np.array(inlet_rows, dtype=np.float64) if inlet_rows else np.empty((0, 3), dtype=np.float64)
    outlets = np.array(outlet_rows, dtype=np.float64) if outlet_rows else np.empty((0, 3), dtype=np.float64)
    return inlets, outlets


def preprocess_coordinates(
    points: NDArray[np.float64],
    inlets: NDArray[np.float64],
    outlets: NDArray[np.float64],
    config,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], int]:
    """Apply unit conversion, scaling, and rounding to all coordinate arrays.

    The original xcavate.py (lines 280-305) performed three separate
    triple-nested Python loops for rounding.  This implementation uses
    vectorised ``np.round`` for all three arrays in a single pass.

    Parameters
    ----------
    points : ndarray, shape (N, C)
        Network coordinates (may include radius and artven columns).
    inlets : ndarray, shape (I, 3)
        Inlet coordinates.
    outlets : ndarray, shape (O, 3)
        Outlet coordinates.
    config : XcavateConfig
        Configuration object providing ``convert_factor`` (default 10.0 for
        cm -> mm) and ``scale_factor``.

    Returns
    -------
    points : ndarray
        Scaled and rounded network coordinates.
    inlets : ndarray
        Scaled and rounded inlet coordinates.
    outlets : ndarray
        Scaled and rounded outlet coordinates.
    num_decimals : int
        Number of decimal places detected from the first coordinate value,
        used for consistent rounding throughout the pipeline.
    """
    # Detect decimal precision from the raw data before any transforms.
    # We inspect the first x-coordinate, matching the original logic at line 265.
    first_value_str = str(abs(points[0, 0]))
    decimal_index = first_value_str.find(".")
    if decimal_index == -1:
        num_decimals = 0
    else:
        num_decimals = len(first_value_str[decimal_index + 1 :])

    convert = getattr(config, "convert_factor", 10.0)
    scale = getattr(config, "scale_factor", 1.0)
    factor = convert * scale

    # Vectorised multiply + round (replaces triple-nested loops)
    points = np.round(points * factor, decimals=num_decimals)
    inlets = np.round(inlets * factor, decimals=num_decimals)
    outlets = np.round(outlets * factor, decimals=num_decimals)

    return points, inlets, outlets, num_decimals


def match_inlet_outlet_nodes(
    points: NDArray[np.float64],
    inlets: NDArray[np.float64],
    outlets: NDArray[np.float64],
    tolerance: float = 1e-6,
) -> tuple[list[int], list[int]]:
    """Find the network node indices closest to each inlet and outlet.

    The original code (lines 307-323) used exact float comparison with
    triple-nested ``if`` statements.  This implementation builds a
    ``scipy.spatial.cKDTree`` over the network xyz coordinates and queries
    it once for all inlets and outlets, giving O(N log N + K log N) time
    instead of O(N * K).

    Parameters
    ----------
    points : ndarray, shape (N, C)
        Network coordinates.  Only the first three columns (x, y, z) are
        used for spatial queries.
    inlets : ndarray, shape (I, 3)
        Inlet coordinates to locate in the network.
    outlets : ndarray, shape (O, 3)
        Outlet coordinates to locate in the network.
    tolerance : float, optional
        Maximum Euclidean distance for a match to be accepted.  Defaults
        to 1e-6 (effectively requiring near-exact matches after rounding).

    Returns
    -------
    inlet_nodes : list[int]
        Indices into *points* for each inlet.
    outlet_nodes : list[int]
        Indices into *points* for each outlet.

    Raises
    ------
    ValueError
        If any inlet or outlet coordinate cannot be matched within
        *tolerance*.
    """
    # Build a KD-tree using only the spatial (xyz) columns.
    xyz = points[:, :3]
    tree = cKDTree(xyz)

    inlet_nodes: list[int] = []
    if inlets.size > 0:
        distances, indices = tree.query(inlets)
        for i, (dist, idx) in enumerate(zip(distances, indices)):
            if dist > tolerance:
                raise ValueError(
                    f"Inlet {i} at {inlets[i]} could not be matched in the "
                    f"network (nearest point distance = {dist:.2e}, "
                    f"tolerance = {tolerance:.2e})."
                )
            inlet_nodes.append(int(idx))

    outlet_nodes: list[int] = []
    if outlets.size > 0:
        distances, indices = tree.query(outlets)
        for i, (dist, idx) in enumerate(zip(distances, indices)):
            if dist > tolerance:
                raise ValueError(
                    f"Outlet {i} at {outlets[i]} could not be matched in the "
                    f"network (nearest point distance = {dist:.2e}, "
                    f"tolerance = {tolerance:.2e})."
                )
            outlet_nodes.append(int(idx))

    return inlet_nodes, outlet_nodes
