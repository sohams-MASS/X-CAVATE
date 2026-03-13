"""Pure-numpy CTR kinematics extracted from generalized_CTR/hivemind/CTR.py.

Provides forward/inverse kinematics for a two-tube concentric tube robot (CTR)
consisting of a straight stainless-steel outer tube and a pre-curved nitinol
inner tube that traces a circular arc where it extends past the SS tip.

All functions are stateless (no class instance required beyond CTRConfig);
heavy dependencies (pyvista, trimesh, subprocess) are avoided entirely.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from scipy.interpolate import interp1d

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class CTRConfig:
    """All geometric and calibration parameters for a single CTR.

    Attributes
    ----------
    X : ndarray (3,)
        Robot base position in the Cartesian network frame (mm).
    R_hat : ndarray (3,)
        Unit vector along the insertion (axial) direction.
    n_hat : ndarray (3,)
        Unit vector normal to the insertion axis, defining the bending plane.
    theta_match : float
        Alignment angle (radians) between the tube's bending plane and
        the global frame at zero rotation.
    radius : float
        Bend radius of the pre-curved nitinol section (mm).
    f_xr_yr : interp1d
        Calibration: radial distance from axis -> arc parameter.
    f_yr_ntnlss : interp1d
        Calibration: arc parameter -> nitinol-minus-SS extension.
    x_val : ndarray
        Radial bounds of the calibration domain.
    ss_lim : float
        Maximum allowable SS tube extension (mm).
    ntnl_lim : float
        Maximum allowable nitinol tube extension (mm).
    """
    X: NDArray[np.floating]
    R_hat: NDArray[np.floating]
    n_hat: NDArray[np.floating]
    theta_match: float
    radius: float
    f_xr_yr: interp1d
    f_yr_ntnlss: interp1d
    x_val: NDArray[np.floating]
    ss_lim: float
    ntnl_lim: float

    def __post_init__(self):
        """Precompute direction matrix and cross product for fast IK."""
        R_rot = rodrigues_rotation(self.theta_match, self.R_hat)
        n_rot = R_rot @ self.n_hat
        t_hat = np.cross(self.R_hat, n_rot)
        # Direction matrix: rows are local axes in global frame
        self._D = np.ascontiguousarray(
            np.array([self.R_hat, n_rot, t_hat], dtype=np.float64)
        )
        # Cross product for simplified Rodrigues (R_hat ⊥ n_hat)
        self._Kn = np.cross(self.R_hat, self.n_hat)
        # Raw interpolation arrays for fast scalar interp
        self._xr = np.asarray(self.f_xr_yr.x, dtype=np.float64)
        self._yr = np.asarray(self.f_xr_yr.y, dtype=np.float64)
        self._yr2 = np.asarray(self.f_yr_ntnlss.x, dtype=np.float64)
        self._ntnlss = np.asarray(self.f_yr_ntnlss.y, dtype=np.float64)

    @classmethod
    def from_xcavate_config(cls, config) -> "CTRConfig":
        """Construct a CTRConfig from an XcavateConfig.

        Parameters
        ----------
        config : XcavateConfig
            Must have ``printer_type == PrinterType.CTR`` and either
            ``ctr_position_cartesian`` or ``ctr_position_cylindrical`` set.

        Returns
        -------
        CTRConfig
        """
        # --- Position ---
        if config.ctr_position_cartesian is not None:
            X = np.array(config.ctr_position_cartesian, dtype=np.float64)
        elif config.ctr_position_cylindrical is not None:
            r, phi, z = config.ctr_position_cylindrical
            # CTR.py convention: X = [z, r*cos(phi), r*sin(phi)]
            X = np.array([z, r * np.cos(phi), r * np.sin(phi)], dtype=np.float64)
        else:
            raise ValueError(
                "CTR printer_type requires either ctr_position_cartesian or "
                "ctr_position_cylindrical to be set."
            )

        # --- Orientation ---
        R_vec = np.array(config.ctr_orientation, dtype=np.float64)
        R_hat = R_vec / np.linalg.norm(R_vec)

        # Normal: pick an arbitrary perpendicular vector
        n_hat = _perpendicular_unit(R_hat)

        # theta_match: angle from n_hat to the global +x axis about R_hat
        theta_match = np.arctan2(
            np.dot(np.cross(n_hat, np.array([1.0, 0.0, 0.0])), R_hat),
            np.dot(n_hat, np.array([1.0, 0.0, 0.0])),
        )

        # --- Calibration ---
        f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(
            config.ctr_calibration_file, config.ctr_radius,
        )

        return cls(
            X=X,
            R_hat=R_hat,
            n_hat=n_hat,
            theta_match=theta_match,
            radius=config.ctr_radius,
            f_xr_yr=f_xr_yr,
            f_yr_ntnlss=f_yr_ntnlss,
            x_val=x_val,
            ss_lim=config.ctr_ss_max,
            ntnl_lim=config.ctr_ntnl_max,
        )

    @classmethod
    def from_robot_dict(
        cls,
        base_config: "CTRConfig",
        robot_dict: dict,
    ) -> "CTRConfig":
        """Construct a CTRConfig by merging per-robot overrides with a base config.

        Parameters
        ----------
        base_config : CTRConfig
            Shared base configuration (calibration, radius, limits).
        robot_dict : dict
            Per-robot overrides.  Supported keys:

            - ``position_cartesian``: ``(x, y, z)`` tuple
            - ``position_cylindrical``: ``(r, phi, z)`` tuple
            - ``orientation``: ``(rx, ry, rz)`` tuple (insertion direction)
            - ``calibration_file``: path to ``.npy`` calibration
            - ``radius``: bend radius override (mm)
            - ``ss_max``: SS extension limit override (mm)
            - ``ntnl_max``: nitinol extension limit override (mm)

        Returns
        -------
        CTRConfig
        """
        # --- Position ---
        if "position_cartesian" in robot_dict:
            X = np.array(robot_dict["position_cartesian"], dtype=np.float64)
        elif "position_cylindrical" in robot_dict:
            r, phi, z = robot_dict["position_cylindrical"]
            X = np.array([z, r * np.cos(phi), r * np.sin(phi)], dtype=np.float64)
        else:
            X = base_config.X.copy()

        # --- Orientation ---
        if "orientation" in robot_dict:
            R_vec = np.array(robot_dict["orientation"], dtype=np.float64)
            R_hat = R_vec / np.linalg.norm(R_vec)
        else:
            R_hat = base_config.R_hat.copy()

        n_hat = _perpendicular_unit(R_hat)
        theta_match = float(np.arctan2(
            np.dot(np.cross(n_hat, np.array([1.0, 0.0, 0.0])), R_hat),
            np.dot(n_hat, np.array([1.0, 0.0, 0.0])),
        ))

        # --- Calibration ---
        radius = robot_dict.get("radius", base_config.radius)
        cal_file = robot_dict.get("calibration_file", None)
        if cal_file is not None:
            f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(cal_file, radius)
        else:
            f_xr_yr = base_config.f_xr_yr
            f_yr_ntnlss = base_config.f_yr_ntnlss
            x_val = base_config.x_val

        ss_lim = robot_dict.get("ss_max", base_config.ss_lim)
        ntnl_lim = robot_dict.get("ntnl_max", base_config.ntnl_lim)

        return cls(
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


# ---------------------------------------------------------------------------
# Rotation and coordinate transforms
# ---------------------------------------------------------------------------

def rodrigues_rotation(theta: float, axis: NDArray[np.floating]) -> NDArray[np.floating]:
    """Rodrigues' rotation formula: 3x3 rotation matrix for angle *theta* about *axis*.

    Parameters
    ----------
    theta : float
        Rotation angle in radians.
    axis : ndarray (3,)
        Unit rotation axis.

    Returns
    -------
    ndarray (3, 3)
        Rotation matrix.
    """
    axis = axis / np.linalg.norm(axis)
    K = np.array([
        [0, -axis[2], axis[1]],
        [axis[2], 0, -axis[0]],
        [-axis[1], axis[0], 0],
    ])
    return np.eye(3) + np.sin(theta) * K + (1 - np.cos(theta)) * (K @ K)


def global_to_local(
    point_G: NDArray[np.floating],
    X: NDArray[np.floating],
    R_hat: NDArray[np.floating],
    n_hat: NDArray[np.floating],
    theta_match: float,
) -> NDArray[np.floating]:
    """Transform a point from the global (network) frame to the CTR local frame.

    The local frame has:
    - x_l along the insertion axis (R_hat)
    - y_l along the bending-plane normal (n_hat rotated by theta_match)
    - z_l = x_l cross y_l

    Parameters
    ----------
    point_G : ndarray (3,)
        Point in global coordinates.
    X, R_hat, n_hat, theta_match
        CTR configuration parameters.

    Returns
    -------
    ndarray (3,)
        Point in the local frame ``(x_l, y_l, z_l)``.
    """
    # Build local basis
    R_rot = rodrigues_rotation(theta_match, R_hat)
    n_rot = R_rot @ n_hat
    t_hat = np.cross(R_hat, n_rot)

    # Direction matrix (rows are local axes expressed in global frame)
    D = np.array([R_hat, n_rot, t_hat])

    delta = point_G - X
    return D @ delta


def local_to_snt(
    point_l: NDArray[np.floating],
    f_xr_yr: interp1d,
    f_yr_ntnlss: interp1d,
    x_val: NDArray[np.floating],
    radius: float,
) -> Optional[NDArray[np.floating]]:
    """Convert local-frame coordinates to SNT (SS extension, Nitinol extension, Theta).

    This is the inverse kinematics step: given a target in the local frame,
    compute the actuator values needed to reach it.

    Parameters
    ----------
    point_l : ndarray (3,)
        Target in the local frame ``(x_l, y_l, z_l)``.
    f_xr_yr, f_yr_ntnlss, x_val
        Calibration interpolants.
    radius : float
        Bend radius (mm).

    Returns
    -------
    ndarray (3,) or None
        ``(z_ss, z_ntnl, theta)`` actuator values, or ``None`` if the point
        falls outside the calibration domain.
    """
    x_l, y_l, z_l = point_l

    # Radial distance from insertion axis in the bending plane
    r_perp = np.sqrt(y_l ** 2 + z_l ** 2)

    # Theta: rotation angle about the insertion axis
    theta = np.arctan2(z_l, y_l)

    # Check calibration bounds
    if r_perp < x_val[0] or r_perp > x_val[-1]:
        return None

    # Arc parameter from radial distance
    yr = float(f_xr_yr(r_perp))

    # Nitinol-minus-SS extension
    ntnl_minus_ss = float(f_yr_ntnlss(yr))

    # SS extension = axial distance - arc contribution
    # The axial (along R_hat) component is x_l, and the arc has axial extent
    # radius * sin(yr / radius) if yr > 0
    arc_axial = radius * np.sin(yr / radius) if yr > 0 else 0.0
    z_ss = x_l - arc_axial

    # Nitinol extension
    z_ntnl = z_ss + ntnl_minus_ss

    return np.array([z_ss, z_ntnl, theta])


def global_to_snt(
    point_G: NDArray[np.floating],
    ctr_config: CTRConfig,
) -> Optional[NDArray[np.floating]]:
    """Convenience: global point -> SNT actuator values in one call.

    Returns
    -------
    ndarray (3,) or None
        ``(z_ss, z_ntnl, theta)`` or None if unreachable.
    """
    point_l = global_to_local(
        point_G,
        ctr_config.X, ctr_config.R_hat, ctr_config.n_hat, ctr_config.theta_match,
    )
    return local_to_snt(
        point_l,
        ctr_config.f_xr_yr, ctr_config.f_yr_ntnlss, ctr_config.x_val,
        ctr_config.radius,
    )


def is_reachable(point_G: NDArray[np.floating], ctr_config: CTRConfig) -> bool:
    """Check whether the CTR can reach a global-frame point.

    A point is reachable if:
    1. It falls within the calibration domain (radial bounds).
    2. The computed SS extension is within ``[0, ss_lim]``.
    3. The computed nitinol extension is within ``[0, ntnl_lim]``.

    Parameters
    ----------
    point_G : ndarray (3,)
    ctr_config : CTRConfig

    Returns
    -------
    bool
    """
    snt = global_to_snt(point_G, ctr_config)
    if snt is None:
        return False
    z_ss, z_ntnl, _theta = snt
    if z_ss < 0 or z_ss > ctr_config.ss_lim:
        return False
    if z_ntnl < 0 or z_ntnl > ctr_config.ntnl_lim:
        return False
    return True


# ---------------------------------------------------------------------------
# Vectorized (batch) reachability
# ---------------------------------------------------------------------------

def batch_global_to_local(
    points_G: NDArray[np.floating],
    X: NDArray[np.floating],
    R_hat: NDArray[np.floating],
    n_hat: NDArray[np.floating],
    theta_match: float,
) -> NDArray[np.floating]:
    """Transform N points from global frame to CTR local frame (vectorized).

    Parameters
    ----------
    points_G : ndarray (N, 3)
    X, R_hat, n_hat, theta_match
        CTR configuration parameters.

    Returns
    -------
    ndarray (N, 3)
        Points in the local frame ``(x_l, y_l, z_l)``.
    """
    R_rot = rodrigues_rotation(theta_match, R_hat)
    n_rot = R_rot @ n_hat
    t_hat = np.cross(R_hat, n_rot)
    D = np.array([R_hat, n_rot, t_hat])  # (3, 3)
    delta = points_G - X  # (N, 3)
    return delta @ D.T  # (N, 3)


def batch_local_to_snt(
    points_l: NDArray[np.floating],
    f_xr_yr: interp1d,
    f_yr_ntnlss: interp1d,
    x_val: NDArray[np.floating],
    radius: float,
) -> NDArray[np.floating]:
    """Convert local-frame coordinates to SNT for N points (vectorized).

    Parameters
    ----------
    points_l : ndarray (N, 3)
    f_xr_yr, f_yr_ntnlss, x_val
        Calibration interpolants.
    radius : float

    Returns
    -------
    ndarray (N, 3)
        ``(z_ss, z_ntnl, theta)`` per point. NaN for invalid points.
    """
    N = points_l.shape[0]
    result = np.full((N, 3), np.nan)

    x_l = points_l[:, 0]
    y_l = points_l[:, 1]
    z_l = points_l[:, 2]

    r_perp = np.sqrt(y_l ** 2 + z_l ** 2)
    theta = np.arctan2(z_l, y_l)

    valid = (r_perp >= x_val[0]) & (r_perp <= x_val[-1])
    if not np.any(valid):
        return result

    r_valid = r_perp[valid]
    yr = np.asarray(f_xr_yr(r_valid), dtype=np.float64)
    ntnl_minus_ss = np.asarray(f_yr_ntnlss(yr), dtype=np.float64)

    arc_axial = np.where(yr > 0, radius * np.sin(yr / radius), 0.0)
    z_ss = x_l[valid] - arc_axial
    z_ntnl = z_ss + ntnl_minus_ss

    result[valid, 0] = z_ss
    result[valid, 1] = z_ntnl
    result[valid, 2] = theta[valid]
    return result


def batch_is_reachable(
    points_G: NDArray[np.floating],
    ctr_config: CTRConfig,
) -> NDArray[np.bool_]:
    """Check reachability for N points (vectorized).

    Parameters
    ----------
    points_G : ndarray (N, 3)
    ctr_config : CTRConfig

    Returns
    -------
    ndarray (N,) of bool
    """
    if points_G.shape[0] == 0:
        return np.array([], dtype=np.bool_)

    local = batch_global_to_local(
        points_G, ctr_config.X, ctr_config.R_hat,
        ctr_config.n_hat, ctr_config.theta_match,
    )
    snt = batch_local_to_snt(
        local, ctr_config.f_xr_yr, ctr_config.f_yr_ntnlss,
        ctr_config.x_val, ctr_config.radius,
    )

    z_ss = snt[:, 0]
    z_ntnl = snt[:, 1]

    reachable = (
        ~np.isnan(z_ss)
        & (z_ss >= 0) & (z_ss <= ctr_config.ss_lim)
        & (z_ntnl >= 0) & (z_ntnl <= ctr_config.ntnl_lim)
    )
    return reachable


# ---------------------------------------------------------------------------
# Needle body computation (forward kinematics)
# ---------------------------------------------------------------------------

def fast_global_to_snt(
    point_G: NDArray[np.floating],
    ctr_config: CTRConfig,
) -> Optional[tuple]:
    """Fast scalar IK using precomputed direction matrix.

    Returns ``(z_ss, z_ntnl, theta)`` as a plain tuple, or ``None``.
    Uses ``np.interp`` instead of ``interp1d`` for lower overhead.
    """
    import math

    D = ctr_config._D
    X = ctr_config.X

    # global_to_local via precomputed D
    dx = float(point_G[0] - X[0])
    dy = float(point_G[1] - X[1])
    dz = float(point_G[2] - X[2])
    x_l = D[0, 0] * dx + D[0, 1] * dy + D[0, 2] * dz
    y_l = D[1, 0] * dx + D[1, 1] * dy + D[1, 2] * dz
    z_l = D[2, 0] * dx + D[2, 1] * dy + D[2, 2] * dz

    # local_to_snt
    r_perp = math.sqrt(y_l * y_l + z_l * z_l)
    if r_perp < ctr_config.x_val[0] or r_perp > ctr_config.x_val[-1]:
        return None

    theta = math.atan2(z_l, y_l)
    yr = float(np.interp(r_perp, ctr_config._xr, ctr_config._yr))
    ntnl_minus_ss = float(np.interp(yr, ctr_config._yr2, ctr_config._ntnlss))
    arc_axial = ctr_config.radius * math.sin(yr / ctr_config.radius) if yr > 0 else 0.0
    z_ss = x_l - arc_axial
    z_ntnl = z_ss + ntnl_minus_ss

    return z_ss, z_ntnl, theta


def compute_needle_body(
    z_ss: float,
    z_ntnl: float,
    theta: float,
    ctr_config: CTRConfig,
    n_arc_samples: int = 20,
) -> NDArray[np.floating]:
    """Compute the full 3D needle body for given actuator values.

    The body consists of two sections:
    1. **Straight SS section**: from the robot base along R_hat for length z_ss.
       Sampled at intervals of approximately ``nozzle_radius``-scale spacing,
       controlled by the density needed to match the arc sampling.
    2. **Curved nitinol arc**: from the SS tip through an arc of radius
       ``ctr_config.radius``, sampled at ``n_arc_samples`` points.

    Parameters
    ----------
    z_ss : float
        SS tube extension (mm).
    z_ntnl : float
        Nitinol tube extension (mm).
    theta : float
        Rotation angle about the insertion axis (radians).
    ctr_config : CTRConfig
    n_arc_samples : int
        Number of sample points along the nitinol arc.

    Returns
    -------
    ndarray (M, 3)
        3D positions of sample points along the needle body in the global frame.
    """
    R_hat = ctr_config.R_hat
    n_hat = ctr_config.n_hat
    X = ctr_config.X
    radius = ctr_config.radius

    # --- Straight SS section (vectorized) ---
    n_ss_samples = max(2, int(np.ceil(z_ss / (radius * np.pi / (2 * n_arc_samples)))) + 1)
    ss_positions = np.linspace(0, z_ss, n_ss_samples)
    ss_body = X + ss_positions[:, None] * R_hat  # (n_ss, 3)

    # --- Curved nitinol arc (vectorized) ---
    ntnl_extension = z_ntnl - z_ss
    if ntnl_extension > 0:
        # Simplified Rodrigues: R_hat ⊥ n_hat guaranteed
        a = ctr_config.theta_match + theta
        Kn = ctr_config._Kn
        bend_dir = n_hat * np.cos(a) + Kn * np.sin(a)

        max_angle = ntnl_extension / radius
        arc_angles = np.linspace(0, max_angle, n_arc_samples + 1)[1:]
        ss_tip = X + z_ss * R_hat
        arc_body = (
            ss_tip
            + radius * np.sin(arc_angles)[:, None] * R_hat
            + radius * (1 - np.cos(arc_angles))[:, None] * bend_dir
        )  # (n_arc, 3)
        return np.concatenate([ss_body, arc_body])

    return np.ascontiguousarray(ss_body)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _perpendicular_unit(v: NDArray[np.floating]) -> NDArray[np.floating]:
    """Return a unit vector perpendicular to *v*."""
    # Pick the axis least aligned with v
    abs_v = np.abs(v)
    if abs_v[0] <= abs_v[1] and abs_v[0] <= abs_v[2]:
        candidate = np.array([1.0, 0.0, 0.0])
    elif abs_v[1] <= abs_v[2]:
        candidate = np.array([0.0, 1.0, 0.0])
    else:
        candidate = np.array([0.0, 0.0, 1.0])
    perp = np.cross(v, candidate)
    return perp / np.linalg.norm(perp)


def _load_calibration(
    calibration_file: Optional["Path"],
    radius: float,
) -> tuple:
    """Load or generate CTR calibration interpolants.

    If a calibration file (.npy) is provided, it is loaded and used to build
    the interpolation functions. Otherwise, a default analytical calibration
    based on circular-arc geometry is generated.

    Parameters
    ----------
    calibration_file : Path or None
        Path to a numpy .npy file with calibration data.
    radius : float
        Bend radius (mm).

    Returns
    -------
    tuple of (f_xr_yr, f_yr_ntnlss, x_val)
    """
    if calibration_file is not None:
        from pathlib import Path
        cal_path = Path(calibration_file)
        if cal_path.exists():
            data = np.load(cal_path, allow_pickle=True)
            if isinstance(data, np.ndarray) and data.ndim == 2 and data.shape[1] >= 3:
                x_r = data[:, 0]
                y_r = data[:, 1]
                ntnl_ss = data[:, 2]
                f_xr_yr = interp1d(x_r, y_r, kind="linear", fill_value="extrapolate")
                f_yr_ntnlss = interp1d(y_r, ntnl_ss, kind="linear", fill_value="extrapolate")
                x_val = x_r
                logger.info("Loaded CTR calibration from %s (%d points)", cal_path, len(x_r))
                return f_xr_yr, f_yr_ntnlss, x_val
            else:
                logger.warning(
                    "Calibration file %s has unexpected shape %s, using default",
                    cal_path, data.shape,
                )

    # Default analytical calibration for a circular arc
    # radial distance = radius * (1 - cos(arc_angle))
    # arc parameter (y_r) = radius * arc_angle
    # ntnl_minus_ss = y_r  (for circular arc, extension equals arc length)
    n_cal = 100
    arc_angles = np.linspace(0, np.pi / 2, n_cal)
    x_r = radius * (1 - np.cos(arc_angles))       # radial distance
    y_r = radius * arc_angles                       # arc parameter
    ntnl_ss = y_r.copy()                            # ntnl - ss extension

    f_xr_yr = interp1d(x_r, y_r, kind="linear", fill_value="extrapolate")
    f_yr_ntnlss = interp1d(y_r, ntnl_ss, kind="linear", fill_value="extrapolate")
    x_val = x_r

    logger.info("Using default analytical CTR calibration (radius=%.1f mm)", radius)
    return f_xr_yr, f_yr_ntnlss, x_val
