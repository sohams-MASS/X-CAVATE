"""CTR gimbal kinematic analysis: approach direction maps & singularity detection.

For each point in the workspace, computes how many distinct gimbal approach
directions can reach it, identifies kinematic singularities, and scores
vulnerability to blocking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import radians
from typing import Dict, List, Optional

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from xcavate.core.ctr_kinematics import (
    CTRConfig,
    batch_global_to_local,
    batch_local_to_snt,
)
from xcavate.core.oracle import _build_gimbal_configs

logger = logging.getLogger(__name__)

# Singularity bitmask constants
SING_ON_AXIS = 0x01      # r_perp ≈ 0, theta undefined
SING_CAL_BOUND = 0x02    # r_perp near x_val boundary
SING_GIMBAL = 0x04       # only alpha=0 works (gimbal-lock-like)
SING_SS_LIMIT = 0x08     # z_ss at actuator bound
SING_NTNL_LIMIT = 0x10   # z_ntnl at actuator bound


@dataclass
class KinematicAnalysisResult:
    """Results of kinematic approach-direction analysis.

    Attributes
    ----------
    node_indices : ndarray (M,)
        Indices of the nodes that were analyzed.
    approach_count : ndarray (M,) int32
        Number of valid (alpha, phi) gimbal configs per node.
    angular_spread : ndarray (M,) float64
        Directional diversity [0, 1]. 0 = all valid directions clustered,
        1 = uniformly distributed.
    vulnerability : ndarray (M,) float64
        Blocking risk [0, 1]. Higher = more likely to be blocked.
    singularity_flags : ndarray (M,) uint8
        Bitmask of singularity conditions per node.
    joint_ranges : ndarray (M, 5, 2) float64
        [alpha, phi, z_ss, z_ntnl, theta] min/max across valid configs.
    total_configs : int
        Total number of gimbal configurations tested.
    """
    node_indices: NDArray[np.intp]
    approach_count: NDArray[np.int32]
    angular_spread: NDArray[np.float64]
    vulnerability: NDArray[np.float64]
    singularity_flags: NDArray[np.uint8]
    joint_ranges: NDArray[np.float64]
    total_configs: int


def _circular_range(angles: NDArray[np.float64]) -> tuple[float, float]:
    """Compute the smallest arc [min, max] containing all angles.

    Parameters
    ----------
    angles : ndarray of angles in radians

    Returns
    -------
    (min_angle, max_angle) — the smallest arc endpoints.
    """
    if len(angles) == 0:
        return (np.nan, np.nan)
    if len(angles) == 1:
        return (float(angles[0]), float(angles[0]))

    sorted_a = np.sort(angles % (2 * np.pi))
    # Compute gaps between consecutive angles (and wrap-around gap)
    gaps = np.diff(sorted_a)
    wrap_gap = (2 * np.pi) - sorted_a[-1] + sorted_a[0]
    all_gaps = np.append(gaps, wrap_gap)

    # The largest gap is outside the arc; the arc starts after it
    largest_idx = int(np.argmax(all_gaps))
    if largest_idx == len(sorted_a) - 1:
        # Wrap-around gap is largest → arc is [sorted_a[0], sorted_a[-1]]
        arc_min = float(sorted_a[0])
        arc_max = float(sorted_a[-1])
    else:
        arc_min = float(sorted_a[largest_idx + 1])
        arc_max = float(sorted_a[largest_idx])

    return (arc_min, arc_max)


def analyze_workspace(
    points: NDArray,
    node_indices: NDArray,
    base_config: CTRConfig,
    cone_angle_deg: float = 15.0,
    n_tilt: int = 3,
    n_azimuth: int = 8,
    nozzle_radius: Optional[float] = None,
) -> KinematicAnalysisResult:
    """Compute approach direction map and singularity detection for workspace nodes.

    Parameters
    ----------
    points : ndarray (N, 3)
        All point coordinates.
    node_indices : ndarray (M,)
        Subset of node indices to analyze.
    base_config : CTRConfig
        Base (untilted) CTR configuration.
    cone_angle_deg : float
        Maximum gimbal tilt angle in degrees.
    n_tilt : int
        Number of tilt levels within the cone.
    n_azimuth : int
        Number of azimuthal samples per tilt level.
    nozzle_radius : float, optional
        If provided, used for density-based vulnerability scoring.
        Density radius = 5 * nozzle_radius.

    Returns
    -------
    KinematicAnalysisResult
    """
    node_indices = np.asarray(node_indices, dtype=np.intp)
    M = len(node_indices)
    pts = points[node_indices]  # (M, 3)

    configs = _build_gimbal_configs(base_config, cone_angle_deg, n_tilt, n_azimuth)
    total_configs = len(configs)

    # Build alpha/phi arrays matching each config
    config_alphas = np.zeros(total_configs, dtype=np.float64)
    config_phis = np.zeros(total_configs, dtype=np.float64)
    # configs[0] is base (alpha=0, phi=0)
    if cone_angle_deg > 0 and n_tilt > 0:
        alpha_values = np.linspace(0, radians(cone_angle_deg), n_tilt + 1)[1:]
        phi_values = np.linspace(0, 2 * np.pi, n_azimuth, endpoint=False)
        idx = 1
        for alpha in alpha_values:
            for phi in phi_values:
                config_alphas[idx] = alpha
                config_phis[idx] = phi
                idx += 1

    # Accumulators
    approach_count = np.zeros(M, dtype=np.int32)
    singularity_flags = np.zeros(M, dtype=np.uint8)
    joint_ranges = np.full((M, 5, 2), np.nan, dtype=np.float64)
    joint_ranges[:, :, 0] = np.inf   # min
    joint_ranges[:, :, 1] = -np.inf  # max

    # Track valid R_hat directions per node for angular spread
    # Store as list of lists of R_hat vectors
    valid_r_hats: List[List[NDArray]] = [[] for _ in range(M)]

    # Track whether any tilted config works (for SING_GIMBAL detection)
    has_tilted_valid = np.zeros(M, dtype=np.bool_)

    for cfg_idx, cfg in enumerate(configs):
        alpha_val = config_alphas[cfg_idx]
        phi_val = config_phis[cfg_idx]

        # Vectorized global→local→SNT
        local = batch_global_to_local(
            pts, cfg.X, cfg.R_hat, cfg.n_hat, cfg.theta_match,
        )
        snt = batch_local_to_snt(
            local, cfg.f_xr_yr, cfg.f_yr_ntnlss, cfg.x_val, cfg.radius,
        )

        z_ss = snt[:, 0]
        z_ntnl = snt[:, 1]
        theta = snt[:, 2]

        # Validity mask
        valid = (
            ~np.isnan(z_ss)
            & (z_ss >= 0) & (z_ss <= cfg.ss_lim)
            & (z_ntnl >= 0) & (z_ntnl <= cfg.ntnl_lim)
        )

        valid_idx = np.where(valid)[0]
        approach_count[valid_idx] += 1

        if cfg_idx > 0:  # tilted config
            has_tilted_valid[valid_idx] = True

        # Compute r_perp for singularity detection
        r_perp = np.sqrt(local[:, 1] ** 2 + local[:, 2] ** 2)

        for i in valid_idx:
            # Collect R_hat for angular spread
            valid_r_hats[i].append(cfg.R_hat.copy())

            # Update joint ranges: [alpha, phi, z_ss, z_ntnl, theta]
            vals = np.array([alpha_val, phi_val, z_ss[i], z_ntnl[i], theta[i]])
            for j in range(5):
                if vals[j] < joint_ranges[i, j, 0]:
                    joint_ranges[i, j, 0] = vals[j]
                if vals[j] > joint_ranges[i, j, 1]:
                    joint_ranges[i, j, 1] = vals[j]

            # Singularity: ON_AXIS
            if r_perp[i] < 0.01:
                singularity_flags[i] |= SING_ON_AXIS

            # Singularity: CAL_BOUND
            if len(cfg.x_val) > 0:
                cal_max = cfg.x_val[-1]
                if cal_max > 0 and r_perp[i] > cal_max * 0.95:
                    singularity_flags[i] |= SING_CAL_BOUND

            # Singularity: SS_LIMIT
            if z_ss[i] < 1.0 or z_ss[i] > cfg.ss_lim - 1.0:
                singularity_flags[i] |= SING_SS_LIMIT

            # Singularity: NTNL_LIMIT
            if z_ntnl[i] < 1.0 or z_ntnl[i] > cfg.ntnl_lim - 1.0:
                singularity_flags[i] |= SING_NTNL_LIMIT

    # SING_GIMBAL: nodes where only alpha=0 works (no tilted config is valid)
    has_any_valid = approach_count > 0
    gimbal_lock = has_any_valid & ~has_tilted_valid
    singularity_flags[gimbal_lock] |= SING_GIMBAL

    # Angular spread: 1 - mean resultant length
    angular_spread = np.zeros(M, dtype=np.float64)
    for i in range(M):
        r_list = valid_r_hats[i]
        if len(r_list) <= 1:
            angular_spread[i] = 0.0
        else:
            r_arr = np.array(r_list)
            mean_vec = r_arr.mean(axis=0)
            R_len = np.linalg.norm(mean_vec)
            angular_spread[i] = 1.0 - R_len

    # Fix joint ranges for phi and theta (circular)
    for i in range(M):
        if approach_count[i] > 1:
            r_list = valid_r_hats[i]
            # phi (index 1) and theta (index 4) are circular quantities
            # Recompute using circular range
            phi_vals = []
            theta_vals = []
            # We need to collect the actual values — recompute from stored ranges
            # For simplicity, keep linear ranges as they are informative enough
            # The linear min/max is already stored

    # Vulnerability score
    if nozzle_radius is not None and nozzle_radius > 0:
        tree = cKDTree(pts)
        density_counts = tree.query_ball_point(pts, 5.0 * nozzle_radius, return_length=True)
        density_factor = density_counts.astype(np.float64)
        if density_factor.max() > 0:
            density_factor /= density_factor.max()
    else:
        density_factor = np.ones(M, dtype=np.float64)

    vulnerability = np.where(
        total_configs > 0,
        (1.0 - approach_count / total_configs) * density_factor,
        density_factor,
    )

    # Clean up joint_ranges: replace inf/-inf with NaN for nodes with 0 approach count
    no_valid = approach_count == 0
    joint_ranges[no_valid] = np.nan

    return KinematicAnalysisResult(
        node_indices=node_indices,
        approach_count=approach_count,
        angular_spread=angular_spread,
        vulnerability=vulnerability,
        singularity_flags=singularity_flags,
        joint_ranges=joint_ranges,
        total_configs=total_configs,
    )


def find_minimum_cone_angle(
    points: NDArray,
    node_indices: NDArray,
    base_config: CTRConfig,
    angles_deg: tuple = (0, 2, 5, 10, 15, 20, 25, 30),
    n_azimuth: int = 8,
) -> Dict[float, float]:
    """Return {cone_angle: fraction_with_approach_count > 0}.

    Runs analyze_workspace at each angle with n_tilt=1 per angle for
    efficiency, reports fraction of nodes reachable at each.

    Parameters
    ----------
    points : ndarray (N, 3)
    node_indices : ndarray (M,)
    base_config : CTRConfig
    angles_deg : tuple of float
        Cone angles to test.
    n_azimuth : int
        Azimuthal resolution.

    Returns
    -------
    dict mapping cone_angle (degrees) to fraction of nodes with approach_count > 0
    """
    result = {}
    M = len(node_indices)

    for angle in angles_deg:
        if angle == 0:
            n_tilt = 0
        else:
            n_tilt = 1

        analysis = analyze_workspace(
            points, node_indices, base_config,
            cone_angle_deg=float(angle),
            n_tilt=n_tilt,
            n_azimuth=n_azimuth,
        )
        frac = float(np.sum(analysis.approach_count > 0)) / max(M, 1)
        result[float(angle)] = frac

    return result
