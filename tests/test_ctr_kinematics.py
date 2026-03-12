"""Unit tests for CTR kinematics module."""

import numpy as np
import pytest

from xcavate.core.ctr_kinematics import (
    CTRConfig,
    rodrigues_rotation,
    global_to_local,
    local_to_snt,
    global_to_snt,
    is_reachable,
    batch_global_to_local,
    batch_is_reachable,
    compute_needle_body,
    _perpendicular_unit,
    _load_calibration,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_ctr_config():
    """CTR at the origin, inserting along -Y, default analytical calibration."""
    f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(None, 47.0)
    return CTRConfig(
        X=np.array([0.0, 0.0, 0.0]),
        R_hat=np.array([0.0, -1.0, 0.0]),
        n_hat=np.array([1.0, 0.0, 0.0]),
        theta_match=0.0,
        radius=47.0,
        f_xr_yr=f_xr_yr,
        f_yr_ntnlss=f_yr_ntnlss,
        x_val=x_val,
        ss_lim=65.0,
        ntnl_lim=140.0,
    )


# ---------------------------------------------------------------------------
# rodrigues_rotation
# ---------------------------------------------------------------------------

class TestRodriguesRotation:
    def test_identity_at_zero_angle(self):
        R = rodrigues_rotation(0.0, np.array([0.0, 0.0, 1.0]))
        np.testing.assert_allclose(R, np.eye(3), atol=1e-12)

    def test_90_deg_about_z(self):
        R = rodrigues_rotation(np.pi / 2, np.array([0.0, 0.0, 1.0]))
        v = np.array([1.0, 0.0, 0.0])
        result = R @ v
        np.testing.assert_allclose(result, [0.0, 1.0, 0.0], atol=1e-12)

    def test_180_deg_about_z(self):
        R = rodrigues_rotation(np.pi, np.array([0.0, 0.0, 1.0]))
        v = np.array([1.0, 0.0, 0.0])
        result = R @ v
        np.testing.assert_allclose(result, [-1.0, 0.0, 0.0], atol=1e-12)

    def test_rotation_preserves_length(self):
        rng = np.random.default_rng(42)
        for _ in range(10):
            axis = rng.normal(size=3)
            axis /= np.linalg.norm(axis)
            theta = rng.uniform(-np.pi, np.pi)
            v = rng.normal(size=3)
            R = rodrigues_rotation(theta, axis)
            np.testing.assert_allclose(np.linalg.norm(R @ v), np.linalg.norm(v), atol=1e-12)

    def test_rotation_is_orthogonal(self):
        R = rodrigues_rotation(1.23, np.array([1.0, 2.0, 3.0]))
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)
        np.testing.assert_allclose(np.linalg.det(R), 1.0, atol=1e-12)


# ---------------------------------------------------------------------------
# global_to_local
# ---------------------------------------------------------------------------

class TestGlobalToLocal:
    def test_origin_maps_to_zero(self):
        X = np.array([0.0, 0.0, 0.0])
        R_hat = np.array([0.0, 0.0, 1.0])
        n_hat = np.array([1.0, 0.0, 0.0])
        result = global_to_local(X, X, R_hat, n_hat, 0.0)
        np.testing.assert_allclose(result, [0.0, 0.0, 0.0], atol=1e-12)

    def test_point_along_insertion_axis(self):
        X = np.array([0.0, 0.0, 0.0])
        R_hat = np.array([0.0, 0.0, 1.0])
        n_hat = np.array([1.0, 0.0, 0.0])
        point = np.array([0.0, 0.0, 5.0])
        result = global_to_local(point, X, R_hat, n_hat, 0.0)
        assert result[0] == pytest.approx(5.0, abs=1e-12)  # along R_hat
        assert abs(result[1]) < 1e-12
        assert abs(result[2]) < 1e-12

    def test_offset_base(self):
        X = np.array([10.0, 20.0, 30.0])
        R_hat = np.array([0.0, 0.0, 1.0])
        n_hat = np.array([1.0, 0.0, 0.0])
        point = np.array([10.0, 20.0, 35.0])
        result = global_to_local(point, X, R_hat, n_hat, 0.0)
        assert result[0] == pytest.approx(5.0, abs=1e-12)


# ---------------------------------------------------------------------------
# is_reachable
# ---------------------------------------------------------------------------

class TestIsReachable:
    def test_base_position_reachable(self, default_ctr_config):
        # A point exactly at the base might not be reachable (needs extension)
        # but a point slightly along the insertion axis should be
        point = default_ctr_config.X + 10.0 * default_ctr_config.R_hat
        assert is_reachable(point, default_ctr_config)

    def test_far_away_point_unreachable(self, default_ctr_config):
        point = np.array([1000.0, 1000.0, 1000.0])
        assert not is_reachable(point, default_ctr_config)

    def test_point_along_insertion_axis_reachable(self, default_ctr_config):
        # Point at moderate distance along insertion direction
        point = default_ctr_config.X + 30.0 * default_ctr_config.R_hat
        assert is_reachable(point, default_ctr_config)


# ---------------------------------------------------------------------------
# compute_needle_body
# ---------------------------------------------------------------------------

class TestComputeNeedleBody:
    def test_returns_array(self, default_ctr_config):
        body = compute_needle_body(20.0, 30.0, 0.0, default_ctr_config, n_arc_samples=10)
        assert isinstance(body, np.ndarray)
        assert body.ndim == 2
        assert body.shape[1] == 3

    def test_body_starts_at_base(self, default_ctr_config):
        body = compute_needle_body(20.0, 30.0, 0.0, default_ctr_config, n_arc_samples=10)
        np.testing.assert_allclose(body[0], default_ctr_config.X, atol=1e-10)

    def test_straight_only_body(self, default_ctr_config):
        """When z_ntnl == z_ss, there's no arc — body is a straight line."""
        body = compute_needle_body(20.0, 20.0, 0.0, default_ctr_config, n_arc_samples=10)
        # All points should be along the insertion axis
        for pt in body:
            # Perpendicular distance to the insertion axis should be ~0
            delta = pt - default_ctr_config.X
            axial = np.dot(delta, default_ctr_config.R_hat)
            perp = np.linalg.norm(delta - axial * default_ctr_config.R_hat)
            assert perp < 1e-10

    def test_more_samples_gives_more_points(self, default_ctr_config):
        body_10 = compute_needle_body(20.0, 40.0, 0.0, default_ctr_config, n_arc_samples=10)
        body_30 = compute_needle_body(20.0, 40.0, 0.0, default_ctr_config, n_arc_samples=30)
        assert body_30.shape[0] > body_10.shape[0]


# ---------------------------------------------------------------------------
# Round-trip: global_to_snt → compute_needle_body → tip matches input
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_tip_matches_target(self, default_ctr_config):
        """The needle body tip should be close to the original target point."""
        # Choose a target along the insertion axis with some offset
        target = default_ctr_config.X + 30.0 * default_ctr_config.R_hat
        snt = global_to_snt(target, default_ctr_config)
        assert snt is not None

        z_ss, z_ntnl, theta = snt
        body = compute_needle_body(z_ss, z_ntnl, theta, default_ctr_config, n_arc_samples=20)

        # The last point of the body should be near the target
        tip = body[-1]
        dist = np.linalg.norm(tip - target)
        # Allow some tolerance due to arc discretization
        assert dist < 2.0, f"Tip-to-target distance: {dist:.4f} mm"


# ---------------------------------------------------------------------------
# CTRConfig.from_xcavate_config
# ---------------------------------------------------------------------------

class TestCTRConfigFromXcavate:
    def test_cartesian_position(self, tmp_path):
        from xcavate.config import XcavateConfig, PrinterType
        config = XcavateConfig(
            network_file=tmp_path / "net.txt",
            inletoutlet_file=tmp_path / "io.txt",
            nozzle_diameter=0.5,
            container_height=50.0,
            num_decimals=3,
            printer_type=PrinterType.CTR,
            ctr_position_cartesian=(10.0, 20.0, 30.0),
        )
        ctr = CTRConfig.from_xcavate_config(config)
        np.testing.assert_allclose(ctr.X, [10.0, 20.0, 30.0])

    def test_cylindrical_position(self, tmp_path):
        from xcavate.config import XcavateConfig, PrinterType
        config = XcavateConfig(
            network_file=tmp_path / "net.txt",
            inletoutlet_file=tmp_path / "io.txt",
            nozzle_diameter=0.5,
            container_height=50.0,
            num_decimals=3,
            printer_type=PrinterType.CTR,
            ctr_position_cylindrical=(10.0, 0.0, 5.0),
        )
        ctr = CTRConfig.from_xcavate_config(config)
        # r=10, phi=0, z=5 → X=[z, r*cos(0), r*sin(0)] = [5, 10, 0]
        np.testing.assert_allclose(ctr.X, [5.0, 10.0, 0.0], atol=1e-10)

    def test_missing_position_raises(self, tmp_path):
        from xcavate.config import XcavateConfig, PrinterType
        config = XcavateConfig(
            network_file=tmp_path / "net.txt",
            inletoutlet_file=tmp_path / "io.txt",
            nozzle_diameter=0.5,
            container_height=50.0,
            num_decimals=3,
            printer_type=PrinterType.CTR,
        )
        with pytest.raises(ValueError, match="ctr_position"):
            CTRConfig.from_xcavate_config(config)


# ---------------------------------------------------------------------------
# _perpendicular_unit
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Batch reachability (vectorized)
# ---------------------------------------------------------------------------

class TestBatchGlobalToLocal:
    def test_matches_scalar(self, default_ctr_config):
        """Batch result matches per-point scalar calls for 50 random points."""
        rng = np.random.default_rng(123)
        cfg = default_ctr_config
        points = cfg.X + rng.uniform(-30, 30, size=(50, 3))

        batch_result = batch_global_to_local(
            points, cfg.X, cfg.R_hat, cfg.n_hat, cfg.theta_match,
        )

        for i in range(len(points)):
            scalar = global_to_local(
                points[i], cfg.X, cfg.R_hat, cfg.n_hat, cfg.theta_match,
            )
            np.testing.assert_allclose(batch_result[i], scalar, atol=1e-12)


class TestBatchIsReachable:
    def test_matches_scalar(self, default_ctr_config):
        """Batch boolean matches per-point scalar calls for 100 random points."""
        rng = np.random.default_rng(456)
        cfg = default_ctr_config
        points = cfg.X + rng.uniform(-60, 60, size=(100, 3))

        batch_result = batch_is_reachable(points, cfg)

        for i in range(len(points)):
            scalar = is_reachable(points[i], cfg)
            assert batch_result[i] == scalar, (
                f"Mismatch at point {i}: batch={batch_result[i]}, scalar={scalar}"
            )

    def test_handles_empty_input(self, default_ctr_config):
        result = batch_is_reachable(np.zeros((0, 3)), default_ctr_config)
        assert len(result) == 0

    def test_handles_all_unreachable(self, default_ctr_config):
        far_points = np.array([[1000, 1000, 1000], [-1000, -1000, -1000]])
        result = batch_is_reachable(far_points, default_ctr_config)
        assert not np.any(result)


# ---------------------------------------------------------------------------
# _perpendicular_unit
# ---------------------------------------------------------------------------

class TestPerpendicularUnit:
    def test_is_unit_length(self):
        v = np.array([1.0, 2.0, 3.0])
        v = v / np.linalg.norm(v)
        perp = _perpendicular_unit(v)
        assert abs(np.linalg.norm(perp) - 1.0) < 1e-12

    def test_is_perpendicular(self):
        v = np.array([1.0, 0.0, 0.0])
        perp = _perpendicular_unit(v)
        assert abs(np.dot(v, perp)) < 1e-12
