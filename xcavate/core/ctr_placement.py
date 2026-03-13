"""Auto-optimize CTR base position and orientation for a given network.

Samples candidate placements around the network bounding box, evaluates
reachability for each, and returns the best (position, orientation) pair.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Geometric placement helpers
# ---------------------------------------------------------------------------

def _regular_directions(n: int) -> NDArray[np.floating]:
    """Return *n* unit vectors maximally separated on the unit sphere.

    Uses known optimal / regular-polyhedron solutions for n <= 6 and
    Fibonacci-sphere sampling for n > 6.

    N=1  single direction (nadir)
    N=2  antipodal pair (opposed)
    N=3  equilateral triangle (equatorial)
    N=4  tetrahedron vertices
    N=5  triangular bipyramid (3 equatorial + 2 poles)
    N=6  octahedron vertices (cube face centres)
    """
    if n == 1:
        return np.array([[0.0, 0.0, -1.0]])
    if n == 2:
        return np.array([[0.0, 0.0, 1.0],
                         [0.0, 0.0, -1.0]])
    if n == 3:
        angles = np.linspace(0, 2 * np.pi, 3, endpoint=False)
        dirs = np.zeros((3, 3))
        dirs[:, 0] = np.cos(angles)
        dirs[:, 1] = np.sin(angles)
        return dirs
    if n == 4:
        dirs = np.array([
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ])
        return dirs / np.linalg.norm(dirs, axis=1, keepdims=True)
    if n == 5:
        angles = np.linspace(0, 2 * np.pi, 3, endpoint=False)
        eq = np.zeros((3, 3))
        eq[:, 0] = np.cos(angles)
        eq[:, 1] = np.sin(angles)
        poles = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]])
        return np.vstack([eq, poles])
    if n == 6:
        return np.array([
            [1.0, 0.0, 0.0], [-1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0], [0.0, -1.0, 0.0],
            [0.0, 0.0, 1.0], [0.0, 0.0, -1.0],
        ])
    # General N > 6: Fibonacci sphere
    return _fibonacci_sphere(n)


def _fibonacci_sphere(n: int) -> NDArray[np.floating]:
    """Approximate *n* equidistant points on the unit sphere (Fibonacci lattice)."""
    golden = (1.0 + np.sqrt(5.0)) / 2.0
    indices = np.arange(n, dtype=np.float64)
    theta = 2.0 * np.pi * indices / golden
    phi = np.arccos(1.0 - 2.0 * (indices + 0.5) / n)
    return np.column_stack([
        np.sin(phi) * np.cos(theta),
        np.sin(phi) * np.sin(theta),
        np.cos(phi),
    ])


def _rotation_matrix(axis: NDArray, angle: float) -> NDArray:
    """Rodrigues' rotation matrix: rotate *angle* radians about *axis*."""
    ax = np.asarray(axis, dtype=np.float64)
    ax = ax / np.linalg.norm(ax)
    K = np.array([
        [0.0, -ax[2], ax[1]],
        [ax[2], 0.0, -ax[0]],
        [-ax[1], ax[0], 0.0],
    ])
    return np.eye(3) + np.sin(angle) * K + (1.0 - np.cos(angle)) * (K @ K)


def _octahedral_rotations() -> List[NDArray]:
    """All 24 proper rotation matrices of the octahedral symmetry group."""
    from itertools import permutations, product

    rotations: List[NDArray] = []
    for perm in permutations(range(3)):
        for signs in product([1, -1], repeat=3):
            R = np.zeros((3, 3))
            for i in range(3):
                R[i, perm[i]] = signs[i]
            if abs(np.linalg.det(R) - 1.0) < 1e-6:
                rotations.append(R)
    return rotations


def _random_rotation(rng: np.random.Generator) -> NDArray:
    """Uniform random rotation on SO(3) via QR decomposition."""
    A = rng.standard_normal((3, 3))
    Q, R = np.linalg.qr(A)
    Q *= np.sign(np.diag(R))
    if np.linalg.det(Q) < 0:
        Q[:, 0] *= -1
    return Q


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


def optimize_multi_ctr_placement(
    points: NDArray[np.floating],
    n_robots: int,
    radius: float = 55.0,
    ss_lim: float = 65.0,
    ntnl_lim: float = 140.0,
    calibration_file=None,
    n_azimuth: int = 12,
    n_elevation: int = 7,
    n_distances: int = 4,
    clearance: float = 2.0,
) -> List[dict]:
    """Place *n_robots* CTRs in a regular geometric arrangement.

    Robots are positioned on a spherical shell around the network centroid
    using regular-polyhedron directions (N<=6) or Fibonacci-sphere sampling
    (N>6).  The standoff distance and a global rotation of the arrangement
    are optimised to maximise **max-min fairness** — the robot with the
    fewest reachable nodes is as large as possible.

    N=2  opposed (180 deg)
    N=3  equilateral triangle (120 deg)
    N=4  tetrahedron
    N=5  triangular bipyramid
    N=6  octahedron / cube face centres

    This ensures each robot sees approximately equal workspace regardless
    of the geometry being printed.

    Parameters
    ----------
    points : ndarray (N, 3+)
    n_robots : int
    radius, ss_lim, ntnl_lim, calibration_file
        Shared CTR parameters.
    n_azimuth, n_elevation
        Rotation search grid density (azimuth x elevation).
    n_distances
        Number of standoff distances to evaluate.
    clearance : float
        Minimum inter-robot base distance margin (mm).

    Returns
    -------
    list of dict
        One placement dict per robot.
    """
    from xcavate.core.ctr_kinematics import (
        CTRConfig,
        _perpendicular_unit,
        _load_calibration,
        batch_is_reachable,
    )

    pts = np.asarray(points[:, :3], dtype=np.float64)
    N = pts.shape[0]

    if n_robots == 1:
        result = optimize_ctr_placement(
            pts, radius=radius, ss_lim=ss_lim, ntnl_lim=ntnl_lim,
            calibration_file=calibration_file,
            n_azimuth=n_azimuth, n_elevation=n_elevation,
            n_distances=n_distances,
        )
        return [result]

    # ---- regular polyhedron directions ------------------------------------
    base_dirs = _regular_directions(n_robots)

    # ---- network geometry -------------------------------------------------
    centroid = pts.mean(axis=0)
    dists_from_centroid = np.linalg.norm(pts - centroid, axis=1)
    network_radius = float(dists_from_centroid.max())

    axial_reach = ss_lim + radius
    half_axial = axial_reach / 2.0
    base_dist = network_radius + half_axial
    # Minimum standoff: robots must be visually outside the network
    # but close enough for the CTR to reach the full network.
    min_standoff = network_radius + 25.0
    standoffs = np.linspace(
        min_standoff, 2.5 * base_dist, n_distances,
    )

    # ---- calibration (loaded once) ----------------------------------------
    f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(calibration_file, radius)

    # ---- rotation search grid ---------------------------------------------
    az_angles = np.linspace(0, 2 * np.pi, n_azimuth, endpoint=False)
    el_angles = np.linspace(-np.radians(60), np.radians(60), n_elevation)

    best_min_count = -1
    best_total_count = -1
    best_placements: Optional[List[dict]] = None
    best_dirs: Optional[NDArray] = None
    candidates_tested = 0

    for d in standoffs:
        for az in az_angles:
            Rz = _rotation_matrix(np.array([0.0, 0.0, 1.0]), az)
            for el in el_angles:
                Rx = _rotation_matrix(np.array([1.0, 0.0, 0.0]), el)
                R = Rx @ Rz
                dirs = (R @ base_dirs.T).T  # (n_robots, 3)

                per_robot_counts: List[int] = []
                placements: List[dict] = []
                valid = True

                for k in range(n_robots):
                    X = centroid + d * dirs[k]
                    R_hat = -dirs[k]  # inward toward centroid

                    n_hat = _perpendicular_unit(R_hat)
                    theta_match = float(np.arctan2(
                        np.dot(
                            np.cross(n_hat, np.array([1.0, 0.0, 0.0])),
                            R_hat,
                        ),
                        np.dot(n_hat, np.array([1.0, 0.0, 0.0])),
                    ))

                    try:
                        cfg = CTRConfig(
                            X=X, R_hat=R_hat, n_hat=n_hat,
                            theta_match=theta_match, radius=radius,
                            f_xr_yr=f_xr_yr, f_yr_ntnlss=f_yr_ntnlss,
                            x_val=x_val, ss_lim=ss_lim, ntnl_lim=ntnl_lim,
                        )
                    except Exception:
                        valid = False
                        break

                    reachable = batch_is_reachable(pts, cfg)
                    count = int(reachable.sum())
                    per_robot_counts.append(count)
                    placements.append({
                        "position": X.copy(),
                        "orientation": R_hat.copy(),
                        "reachable_count": count,
                        "reachable_fraction": count / max(N, 1),
                        "total_nodes": N,
                    })

                candidates_tested += 1
                if not valid:
                    continue

                min_count = min(per_robot_counts)
                total_count = sum(per_robot_counts)

                # Max-min fairness: maximise worst-case robot coverage,
                # break ties with total coverage
                if (min_count > best_min_count
                        or (min_count == best_min_count
                            and total_count > best_total_count)):
                    best_min_count = min_count
                    best_total_count = total_count
                    best_placements = placements
                    best_dirs = dirs.copy()

    if best_placements is None:
        logger.error(
            "Multi-CTR regular placement failed — falling back to single best"
        )
        single = optimize_ctr_placement(
            pts, radius=radius, ss_lim=ss_lim, ntnl_lim=ntnl_lim,
            calibration_file=calibration_file,
        )
        return [single] * n_robots

    # ---- Per-robot standoff refinement for maximum individual coverage ----
    # Lock the best rotation, but let each robot independently find its
    # best standoff distance.  Maximizing individual coverage creates more
    # overlapping zones between adjacent robots, which the load-balanced
    # assignment step can then redistribute to equalize workload.
    # Enforce min_standoff so robots stay outside the network.
    fine_standoffs = np.linspace(
        min_standoff, standoffs[-1] * 1.5, 20,
    )

    refined_placements: List[dict] = []
    for k in range(n_robots):
        dir_k = best_dirs[k]
        R_hat_k = -dir_k
        n_hat_k = _perpendicular_unit(R_hat_k)
        theta_match_k = float(np.arctan2(
            np.dot(
                np.cross(n_hat_k, np.array([1.0, 0.0, 0.0])),
                R_hat_k,
            ),
            np.dot(n_hat_k, np.array([1.0, 0.0, 0.0])),
        ))

        best_cnt_k = -1
        best_pk: Optional[dict] = None

        for d_k in fine_standoffs:
            X_k = centroid + d_k * dir_k
            try:
                cfg_k = CTRConfig(
                    X=X_k, R_hat=R_hat_k, n_hat=n_hat_k,
                    theta_match=theta_match_k, radius=radius,
                    f_xr_yr=f_xr_yr, f_yr_ntnlss=f_yr_ntnlss,
                    x_val=x_val, ss_lim=ss_lim, ntnl_lim=ntnl_lim,
                )
            except Exception:
                continue
            reach_k = batch_is_reachable(pts, cfg_k)
            cnt_k = int(reach_k.sum())
            if cnt_k > best_cnt_k:
                best_cnt_k = cnt_k
                best_pk = {
                    "position": X_k.copy(),
                    "orientation": R_hat_k.copy(),
                    "reachable_count": cnt_k,
                    "reachable_fraction": cnt_k / max(N, 1),
                    "total_nodes": N,
                }

        refined_placements.append(best_pk if best_pk is not None
                                  else best_placements[k])

    for p in refined_placements:
        p["candidates_tested"] = candidates_tested

    counts = [p["reachable_count"] for p in refined_placements]
    logger.info(
        "Multi-CTR regular placement (%d robots): "
        "per-robot reachable = %s, min=%d, max=%d, imbalance=%.1f%%",
        n_robots, counts, min(counts), max(counts),
        100.0 * (max(counts) - min(counts)) / max(max(counts), 1),
    )

    return refined_placements


# ---------------------------------------------------------------------------
# Oracle orientation optimiser
# ---------------------------------------------------------------------------

def oracle_multi_ctr_placement(
    points: NDArray[np.floating],
    n_robots: int,
    radius: float = 55.0,
    ss_lim: float = 65.0,
    ntnl_lim: float = 140.0,
    calibration_file=None,
    n_distances: int = 6,
    n_random: int = 200,
) -> List[dict]:
    """Oracle-optimised multi-CTR placement with full SO(3) rotation search.

    Finds the 3D rotation of the regular N-robot arrangement that maximises
    coverage and balance on the given network geometry.

    Phase 1 — **PCA-guided**: compute the network's principal axes and try
    all 24 octahedral rotations of that frame.  This aligns the polyhedron
    axes with the network's natural extents.

    Phase 2 — **Stochastic**: sample *n_random* uniform-random SO(3)
    rotations to explore orientations PCA might miss.

    Phase 3 — **Local refinement**: small angular perturbations (±10 deg)
    around the current best.

    Phase 4 — **Per-robot standoff**: independently optimise each robot's
    distance to maximise its individual coverage.

    Scoring priority: (1) unique coverage — nodes reachable by *any* robot;
    (2) min per-robot count — max-min fairness; (3) total count.

    Parameters
    ----------
    points : ndarray (N, 3+)
    n_robots : int
    radius, ss_lim, ntnl_lim, calibration_file
        Shared CTR parameters.
    n_distances : int
        Standoff distances to try per rotation.
    n_random : int
        Uniform random SO(3) samples.

    Returns
    -------
    list of dict
        One placement dict per robot.
    """
    from xcavate.core.ctr_kinematics import (
        CTRConfig,
        _perpendicular_unit,
        _load_calibration,
        batch_is_reachable,
    )

    pts = np.asarray(points[:, :3], dtype=np.float64)
    N = pts.shape[0]

    if n_robots == 1:
        return [optimize_ctr_placement(
            pts, radius=radius, ss_lim=ss_lim, ntnl_lim=ntnl_lim,
            calibration_file=calibration_file,
        )]

    base_dirs = _regular_directions(n_robots)

    # ---- network geometry -------------------------------------------------
    centroid = pts.mean(axis=0)
    dists_from_centroid = np.linalg.norm(pts - centroid, axis=1)
    network_radius = float(dists_from_centroid.max())
    axial_reach = ss_lim + radius
    half_axial = axial_reach / 2.0
    base_dist = network_radius + half_axial
    # Minimum standoff: robots must be visually outside the network
    # but close enough for the CTR to reach the full network.
    min_standoff = network_radius + 25.0
    standoffs = np.linspace(min_standoff, 2.5 * base_dist, n_distances)

    f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(calibration_file, radius)

    # ---- PCA of network → principal axes ----------------------------------
    pts_c = pts - centroid
    cov = pts_c.T @ pts_c / max(N - 1, 1)
    eigvals, eigvecs = np.linalg.eigh(cov)
    pca_axes = eigvecs[:, ::-1].T  # rows = v1 (longest), v2, v3
    if np.linalg.det(pca_axes) < 0:
        pca_axes[2] *= -1

    # ---- build candidate rotations ----------------------------------------
    oct_rots = _octahedral_rotations()

    candidates: List[NDArray] = []
    # Phase 1: PCA-aligned octahedral rotations
    for R_oct in oct_rots:
        R_cand = R_oct @ pca_axes
        if np.linalg.det(R_cand) < 0:
            R_cand = -R_cand
        candidates.append(R_cand)

    # Phase 2: uniform random SO(3)
    rng = np.random.default_rng(42)
    for _ in range(n_random):
        candidates.append(_random_rotation(rng))

    # ---- helper: evaluate one (rotation, standoff) pair -------------------
    def _eval(R_rot: NDArray, d: float):
        """Return (unique_cov, min_count, total_count, placements)."""
        dirs = (R_rot @ base_dirs.T).T
        combined = np.zeros(N, dtype=np.bool_)
        per_counts: List[int] = []
        pls: List[dict] = []
        for k in range(n_robots):
            X = centroid + d * dirs[k]
            R_hat = -dirs[k]
            n_hat = _perpendicular_unit(R_hat)
            theta_m = float(np.arctan2(
                np.dot(np.cross(n_hat, np.array([1.0, 0.0, 0.0])), R_hat),
                np.dot(n_hat, np.array([1.0, 0.0, 0.0])),
            ))
            try:
                cfg = CTRConfig(
                    X=X, R_hat=R_hat, n_hat=n_hat,
                    theta_match=theta_m, radius=radius,
                    f_xr_yr=f_xr_yr, f_yr_ntnlss=f_yr_ntnlss,
                    x_val=x_val, ss_lim=ss_lim, ntnl_lim=ntnl_lim,
                )
            except Exception:
                return -1, -1, -1, []
            mask = batch_is_reachable(pts, cfg)
            combined |= mask
            cnt = int(mask.sum())
            per_counts.append(cnt)
            pls.append({
                "position": X.copy(),
                "orientation": R_hat.copy(),
                "reachable_count": cnt,
                "reachable_fraction": cnt / max(N, 1),
                "total_nodes": N,
            })
        return int(combined.sum()), min(per_counts), sum(per_counts), pls

    # ---- sweep all candidates × standoffs ---------------------------------
    best_ucov, best_min, best_total = -1, -1, -1
    best_placements: Optional[List[dict]] = None
    best_R: Optional[NDArray] = None
    n_eval = 0

    def _is_better(ucov, mn, tot):
        nonlocal best_ucov, best_min, best_total
        # Balance-first: maximise worst-case robot, then unique coverage,
        # then total (more overlap → better load-balancing potential).
        return (mn > best_min
                or (mn == best_min and ucov > best_ucov)
                or (mn == best_min and ucov == best_ucov and tot > best_total))

    for R_rot in candidates:
        for d in standoffs:
            ucov, mn, tot, pls = _eval(R_rot, d)
            n_eval += 1
            if ucov < 0:
                continue
            if _is_better(ucov, mn, tot):
                best_ucov, best_min, best_total = ucov, mn, tot
                best_placements = pls
                best_R = R_rot

    # ---- Phase 3: local refinement (±10 deg around best) ------------------
    if best_R is not None:
        n_refine = n_random // 2
        for _ in range(n_refine):
            angle = rng.uniform(-np.radians(10), np.radians(10))
            axis = rng.standard_normal(3)
            axis /= np.linalg.norm(axis)
            R_perturb = _rotation_matrix(axis, angle) @ best_R
            for d in standoffs:
                ucov, mn, tot, pls = _eval(R_perturb, d)
                n_eval += 1
                if ucov < 0:
                    continue
                if _is_better(ucov, mn, tot):
                    best_ucov, best_min, best_total = ucov, mn, tot
                    best_placements = pls
                    best_R = R_perturb

    if best_placements is None:
        logger.error("Oracle placement failed — falling back to regular")
        return optimize_multi_ctr_placement(
            points, n_robots, radius=radius, ss_lim=ss_lim,
            ntnl_lim=ntnl_lim, calibration_file=calibration_file,
        )

    # ---- Phase 4: per-robot standoff refinement ----------------------------
    # Enforce min_standoff so robots stay outside the network.
    fine_standoffs = np.linspace(
        min_standoff, standoffs[-1] * 1.5, 20,
    )
    dirs = (best_R @ base_dirs.T).T

    refined: List[dict] = []
    for k in range(n_robots):
        dir_k = dirs[k]
        R_hat_k = -dir_k
        n_hat_k = _perpendicular_unit(R_hat_k)
        theta_m_k = float(np.arctan2(
            np.dot(np.cross(n_hat_k, np.array([1.0, 0.0, 0.0])), R_hat_k),
            np.dot(n_hat_k, np.array([1.0, 0.0, 0.0])),
        ))
        best_cnt_k = -1
        best_pk: Optional[dict] = None
        for d_k in fine_standoffs:
            X_k = centroid + d_k * dir_k
            try:
                cfg_k = CTRConfig(
                    X=X_k, R_hat=R_hat_k, n_hat=n_hat_k,
                    theta_match=theta_m_k, radius=radius,
                    f_xr_yr=f_xr_yr, f_yr_ntnlss=f_yr_ntnlss,
                    x_val=x_val, ss_lim=ss_lim, ntnl_lim=ntnl_lim,
                )
            except Exception:
                continue
            cnt_k = int(batch_is_reachable(pts, cfg_k).sum())
            if cnt_k > best_cnt_k:
                best_cnt_k = cnt_k
                best_pk = {
                    "position": X_k.copy(),
                    "orientation": R_hat_k.copy(),
                    "reachable_count": cnt_k,
                    "reachable_fraction": cnt_k / max(N, 1),
                    "total_nodes": N,
                    "candidates_tested": n_eval,
                }
        refined.append(best_pk if best_pk is not None else best_placements[k])

    counts = [p["reachable_count"] for p in refined]
    logger.info(
        "Oracle multi-CTR placement (%d robots, %d evals): "
        "unique_cov=%d, per-robot = %s, min=%d, max=%d, imbalance=%.1f%%",
        n_robots, n_eval, best_ucov, counts, min(counts), max(counts),
        100.0 * (max(counts) - min(counts)) / max(max(counts), 1),
    )

    return refined


def _optimize_with_clearance(
    points: NDArray[np.floating],
    existing_positions: List[NDArray[np.floating]],
    min_base_dist: float,
    **kwargs,
) -> dict:
    """Run placement optimization rejecting positions too close to existing robots.

    Falls back to standard optimization if all clearance-respecting candidates
    have zero coverage.
    """
    from xcavate.core.ctr_kinematics import (
        CTRConfig,
        _perpendicular_unit,
        _load_calibration,
        batch_is_reachable,
    )

    radius = kwargs.get("radius", 55.0)
    ss_lim = kwargs.get("ss_lim", 65.0)
    ntnl_lim = kwargs.get("ntnl_lim", 140.0)
    calibration_file = kwargs.get("calibration_file", None)
    n_azimuth = kwargs.get("n_azimuth", 12)
    n_elevation = kwargs.get("n_elevation", 7)
    n_distances = kwargs.get("n_distances", 4)

    pts = np.asarray(points[:, :3], dtype=np.float64)
    N = pts.shape[0]

    centroid = pts.mean(axis=0)
    dists_from_centroid = np.linalg.norm(pts - centroid, axis=1)
    network_radius = float(dists_from_centroid.max())
    axial_reach = ss_lim + radius
    half_axial = axial_reach / 2.0
    base_dist = network_radius + half_axial
    standoffs = np.linspace(1.2 * base_dist * 0.5, 2.5 * base_dist, n_distances)

    f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(calibration_file, radius)

    phis = np.linspace(0, 2 * np.pi, n_azimuth, endpoint=False)
    thetas = np.linspace(-np.radians(70), np.radians(70), n_elevation)

    best_score = -1.0
    best_count = -1
    best_position = centroid.copy()
    best_orientation = np.array([0.0, 0.0, -1.0])
    candidates_tested = 0

    for d in standoffs:
        for theta in thetas:
            for phi in phis:
                direction = np.array([
                    np.cos(theta) * np.cos(phi),
                    np.cos(theta) * np.sin(phi),
                    np.sin(theta),
                ])
                X = centroid + d * direction
                R_hat = centroid - X
                norm = np.linalg.norm(R_hat)
                if norm < 1e-12:
                    continue
                R_hat = R_hat / norm

                # Clearance check against existing robots
                too_close = False
                min_sep = float("inf")
                for existing_pos in existing_positions:
                    sep = float(np.linalg.norm(X - existing_pos))
                    min_sep = min(min_sep, sep)
                    if sep < min_base_dist:
                        too_close = True
                        break
                if too_close:
                    continue

                n_hat = _perpendicular_unit(R_hat)
                theta_match = float(np.arctan2(
                    np.dot(np.cross(n_hat, np.array([1.0, 0.0, 0.0])), R_hat),
                    np.dot(n_hat, np.array([1.0, 0.0, 0.0])),
                ))

                try:
                    cfg = CTRConfig(
                        X=X, R_hat=R_hat, n_hat=n_hat, theta_match=theta_match,
                        radius=radius, f_xr_yr=f_xr_yr, f_yr_ntnlss=f_yr_ntnlss,
                        x_val=x_val, ss_lim=ss_lim, ntnl_lim=ntnl_lim,
                    )
                except Exception:
                    continue

                reachable = batch_is_reachable(pts, cfg)
                count = int(reachable.sum())
                candidates_tested += 1

                # Score: primarily coverage, secondarily separation from existing
                # Separation bonus (0-1 range) breaks ties and helps when all
                # candidates have similar coverage
                sep_bonus = min(min_sep / (min_base_dist * 3), 1.0) if existing_positions else 0.0
                score = count + sep_bonus

                if score > best_score:
                    best_score = score
                    best_count = count
                    best_position = X.copy()
                    best_orientation = R_hat.copy()

    # Fallback if no clearance-safe candidate was found at all
    if candidates_tested == 0:
        logger.warning(
            "No clearance-safe candidates found, relaxing clearance constraint"
        )
        # Try again with halved clearance
        return _optimize_with_clearance(
            points, existing_positions, min_base_dist * 0.5,
            **kwargs,
        )

    return {
        "position": best_position,
        "orientation": best_orientation,
        "reachable_count": best_count,
        "reachable_fraction": best_count / max(N, 1),
        "total_nodes": N,
        "candidates_tested": candidates_tested,
    }
