"""Auto-optimize CTR base position and orientation for a given network.

Samples candidate placements around the network bounding box, evaluates
reachability for each, and returns the best (position, orientation) pair.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


def optimize_ctr_placement(
    points: NDArray[np.floating],
    radius: float = 55.0,
    ss_lim: float = 65.0,
    ntnl_lim: float = 140.0,
    calibration_file=None,
    n_azimuth: int = 12,
    n_elevation: int = 7,
    n_distances: int = 4,
    standoff_min: float = 1.2,
    standoff_max: float = 2.5,
) -> dict:
    """Find the CTR placement that maximizes reachable nodes.

    Generates candidate base positions on a spherical shell around the network
    centroid, with R_hat pointing inward toward the centroid.  Evaluates
    batch reachability for each candidate and returns the best.

    Parameters
    ----------
    points : ndarray (N, 3+)
        Network coordinates (at least XYZ).
    radius : float
        CTR bend radius (mm).
    ss_lim : float
        Maximum SS extension (mm).
    ntnl_lim : float
        Maximum nitinol extension (mm).
    calibration_file : Path or None
        Optional calibration file; None uses default analytical calibration.
    n_azimuth : int
        Azimuthal samples around the network.
    n_elevation : int
        Elevation samples (from below to above).
    n_distances : int
        Number of standoff distances to try.
    standoff_min, standoff_max : float
        Standoff range as multiples of the network half-extent.

    Returns
    -------
    dict with keys:
        'position': ndarray (3,) — optimal base position
        'orientation': ndarray (3,) — optimal insertion direction (unit vector)
        'reachable_count': int
        'reachable_fraction': float
        'total_nodes': int
        'candidates_tested': int
    """
    from xcavate.core.ctr_kinematics import (
        CTRConfig,
        _perpendicular_unit,
        _load_calibration,
        batch_is_reachable,
    )

    pts = np.asarray(points[:, :3], dtype=np.float64)
    N = pts.shape[0]

    # Network centroid and bounding sphere
    centroid = pts.mean(axis=0)
    dists_from_centroid = np.linalg.norm(pts - centroid, axis=1)
    network_radius = float(dists_from_centroid.max())

    # The CTR axial reach: SS extends along R_hat, then the arc contributes
    # axially.  Max axial reach ≈ ss_lim + radius (for a 90° arc).
    # The radial reach = radius (at 90° arc).
    # We want the network to sit within this volume.  Place the base at a
    # distance where the midpoint of the workspace overlaps the centroid.
    axial_reach = ss_lim + radius
    half_axial = axial_reach / 2.0

    # Standoff distances: multiples of (network_radius + half_axial)
    base_dist = network_radius + half_axial
    standoffs = np.linspace(
        standoff_min * base_dist * 0.5,
        standoff_max * base_dist,
        n_distances,
    )

    # Load calibration once
    f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(calibration_file, radius)

    # Generate candidate directions on a sphere (azimuth × elevation)
    phis = np.linspace(0, 2 * np.pi, n_azimuth, endpoint=False)
    # Elevation from -70° to +70° (avoid poles where R_hat is degenerate)
    thetas = np.linspace(-np.radians(70), np.radians(70), n_elevation)

    best_count = -1
    best_position = centroid.copy()
    best_orientation = np.array([0.0, 0.0, -1.0])
    candidates_tested = 0

    for d in standoffs:
        for theta in thetas:
            for phi in phis:
                # Candidate position on sphere around centroid
                direction = np.array([
                    np.cos(theta) * np.cos(phi),
                    np.cos(theta) * np.sin(phi),
                    np.sin(theta),
                ])
                X = centroid + d * direction

                # R_hat points from base toward centroid
                R_hat = centroid - X
                norm = np.linalg.norm(R_hat)
                if norm < 1e-12:
                    continue
                R_hat = R_hat / norm

                # Build a minimal CTRConfig for reachability check
                n_hat = _perpendicular_unit(R_hat)
                theta_match = float(np.arctan2(
                    np.dot(np.cross(n_hat, np.array([1.0, 0.0, 0.0])), R_hat),
                    np.dot(n_hat, np.array([1.0, 0.0, 0.0])),
                ))

                try:
                    cfg = CTRConfig(
                        X=X,
                        R_hat=R_hat,
                        n_hat=n_hat,
                        theta_match=theta_match,
                        radius=radius,
                        f_xr_yr=f_xr_yr,
                        f_yr_ntnlss=f_yr_ntnlss,
                        x_val=x_val,
                        ss_lim=ss_lim,
                        ntnl_lim=ntnl_lim,
                    )
                except Exception:
                    continue

                reachable = batch_is_reachable(pts, cfg)
                count = int(reachable.sum())
                candidates_tested += 1

                if count > best_count:
                    best_count = count
                    best_position = X.copy()
                    best_orientation = R_hat.copy()

    logger.info(
        "CTR placement optimizer: best %d/%d reachable (%.1f%%) from %d candidates",
        best_count, N, 100.0 * best_count / max(N, 1), candidates_tested,
    )

    return {
        "position": best_position,
        "orientation": best_orientation,
        "reachable_count": best_count,
        "reachable_fraction": best_count / max(N, 1),
        "total_nodes": N,
        "candidates_tested": candidates_tested,
    }
