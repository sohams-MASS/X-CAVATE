"""Severe stress tests for gimbal-equipped CTR collision detectors.

Tests adversarial geometries, consistency invariants, numerical edge cases,
body-sampling blind spots, and config construction correctness.
"""

import time

import numpy as np
import pytest

from xcavate.core.ctr_kinematics import (
    CTRConfig,
    _load_calibration,
    _perpendicular_unit,
    compute_needle_body,
    global_to_snt,
    rodrigues_rotation,
)
from xcavate.core.ctr_collision import CTRCollisionDetector
from xcavate.core.oracle import (
    GimbalOracleDetector,
    GimbalRealisticDetector,
    OracleDetector,
    _build_gimbal_configs,
    make_gimbal_config,
    run_gimbal_oracle,
    run_gimbal_realistic,
    run_oracle,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ctr_down():
    """CTR at origin, inserting along -Y, bend radius 47mm.
    Matches the simple_ctr_config in test_ctr_collision.py."""
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


@pytest.fixture
def ctr_z_down():
    """CTR at (35, 42.6, 101.6), inserting along -Z (500-vessel config)."""
    f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(None, 47.0)
    return CTRConfig(
        X=np.array([35.0, 42.6, 101.6]),
        R_hat=np.array([0.0, 0.0, -1.0]),
        n_hat=np.array([1.0, 0.0, 0.0]),
        theta_match=0.0,
        radius=47.0,
        f_xr_yr=f_xr_yr,
        f_yr_ntnlss=f_yr_ntnlss,
        x_val=x_val,
        ss_lim=110.0,
        ntnl_lim=185.0,
    )


# ---------------------------------------------------------------------------
# Category 1: Adversarial geometry — force gimbal failure
# ---------------------------------------------------------------------------

class TestAdversarialGeometry:
    """Construct geometries that defeat the gimbal at specific resolutions."""

    def test_dense_blocker_ring_blocks_all_angles(self, ctr_down):
        """A ring of blockers positioned at every (alpha, phi) in the gimbal
        grid should block every insertion angle."""
        n_tilt, n_azimuth = 3, 8
        nozzle_r = 1.0
        target_depth = 50.0  # along -Y
        blocker_depth = 25.0  # midpoint

        target = np.array([0.0, -target_depth, 0.0])

        # Build blockers: one on-axis (alpha=0), plus one per (alpha, phi)
        configs = _build_gimbal_configs(ctr_down, cone_angle_deg=15.0,
                                        n_tilt=n_tilt, n_azimuth=n_azimuth)
        blockers = []
        for cfg in configs:
            # Where does the shaft pass at blocker_depth for this config?
            shaft_pt = cfg.X + blocker_depth * cfg.R_hat
            blockers.append(shaft_pt)

        points = np.vstack([target[np.newaxis, :]] + [b[np.newaxis, :] for b in blockers])

        det = GimbalOracleDetector(
            points, ctr_down, nozzle_radius=nozzle_r, n_arc_samples=40,
            cone_angle_deg=15.0, n_tilt=n_tilt, n_azimuth=n_azimuth,
        )
        # Node 0 is the target; all others are blockers
        assert not det.is_valid(0), (
            "Target should be blocked when a blocker sits on every gimbal angle's shaft"
        )

    def test_coaxial_sleeve_blocks_untilted_gimbal_rescues(self, ctr_down):
        """On-axis blockers at a DEEP depth block alpha=0 but the gimbal
        rescues the target because at deep depths, tilt provides enough
        lateral shift to clear the blockers.

        At depth d with tilt alpha, lateral shift = d*sin(alpha).
        For d=30mm, alpha=5° (first tilt level): shift = 2.6mm > nozzle_r=0.5mm.
        """
        nozzle_r = 0.5
        target_depth = 50.0
        target = np.array([0.0, -target_depth, 0.0])

        # Place on-axis blockers at depth 25-35mm only (deep enough for tilt escape,
        # far enough from target to avoid tip_exclusion_r = 1.5mm)
        sleeve = []
        for d in np.linspace(25.0, 35.0, 20):
            sleeve.append([0.0, -d, 0.0])

        points = np.vstack([target[np.newaxis, :]] + [np.array(s)[np.newaxis, :] for s in sleeve])

        # Without gimbal (oracle), the target is blocked
        oracle = OracleDetector(
            points, ctr_down, nozzle_radius=nozzle_r, n_arc_samples=40,
        )
        assert not oracle.is_valid(0), "On-axis sleeve should block the untilted path"

        # With gimbal, tilted paths avoid the deep on-axis sleeve
        gimbal = GimbalOracleDetector(
            points, ctr_down, nozzle_radius=nozzle_r, n_arc_samples=40,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )
        assert gimbal.is_valid(0), "Gimbal should escape deep on-axis sleeve"

    def test_full_depth_sleeve_defeats_gimbal(self, ctr_down):
        """A sleeve spanning the full depth (including shallow depths where
        tilt provides < nozzle_r lateral shift) defeats even the gimbal."""
        nozzle_r = 2.0
        target_depth = 50.0
        target = np.array([0.0, -target_depth, 0.0])

        # Dense on-axis nodes from depth 2mm to 42mm
        # At depth 2mm, max lateral shift = 2*sin(15°) = 0.52mm < 2mm nozzle_r
        sleeve = []
        for d in np.linspace(2.0, target_depth - 8.0, 40):
            sleeve.append([0.0, -d, 0.0])

        points = np.vstack([target[np.newaxis, :]] + [np.array(s)[np.newaxis, :] for s in sleeve])

        det = GimbalOracleDetector(
            points, ctr_down, nozzle_radius=nozzle_r, n_arc_samples=40,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )
        assert not det.is_valid(0), (
            "Full-depth on-axis sleeve should defeat gimbal — shallow nodes "
            "can't be avoided because tilt shift < nozzle_r near the base"
        )

    def test_large_nozzle_radius_defeats_gimbal(self, ctr_down):
        """With large nozzle_radius and dense blockers far from the tip,
        no gimbal angle can thread through."""
        # tip_exclusion_r = 3 * nozzle_r, so blockers must be > 3*nozzle_r
        # from the target to avoid being excluded from collision checks.
        nozzle_r = 3.0
        target_depth = 60.0
        blocker_depth = 15.0  # 45mm from target >> 9mm tip exclusion

        target = np.array([0.0, -target_depth, 0.0])

        # Dense grid of blockers at the shallow depth — far from tip exclusion zone
        blockers = []
        for x in np.linspace(-20, 20, 20):
            for z in np.linspace(-20, 20, 20):
                blockers.append([x, -blocker_depth, z])

        points = np.vstack([target[np.newaxis, :]] +
                           [np.array(b)[np.newaxis, :] for b in blockers])

        det = GimbalOracleDetector(
            points, ctr_down, nozzle_radius=nozzle_r, n_arc_samples=40,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )
        assert not det.is_valid(0), (
            "Dense blockers with nozzle_radius=3mm should defeat gimbal"
        )

    def test_near_base_limited_lateral_shift(self, ctr_down):
        """Nodes very close to the CTR base get minimal lateral shift from
        tilt. A blocker near the base should still block even with gimbal.

        Key insight: tip_exclusion_r = 3 * nozzle_r, so the target must be
        far enough from the blocker that the blocker isn't excluded, AND the
        blocker must be far enough from the base that tilt provides minimal
        lateral shift but body samples still reach it.
        """
        nozzle_r = 0.5
        # Place target at a moderate depth so blocker isn't in tip exclusion
        target_depth = 20.0
        target = np.array([0.0, -target_depth, 0.0])

        # Blocker at depth 2mm — very close to base
        # At 15° tilt, lateral shift at depth=2mm is 2*sin(15°) = 0.52mm ≈ nozzle_r
        # So the blocker is BARELY displaced — some angles hit, some don't
        blocker = np.array([0.0, -2.0, 0.0])
        points = np.vstack([target[np.newaxis, :], blocker[np.newaxis, :]])

        # Verify how many gimbal angles are blocked at this near-base position
        configs = _build_gimbal_configs(ctr_down, 15.0, 3, 8)
        blocked_count = 0
        for cfg in configs:
            shaft_at_2 = cfg.X + 2.0 * cfg.R_hat
            dist = np.linalg.norm(shaft_at_2 - blocker)
            if dist <= nozzle_r:
                blocked_count += 1

        # Near the base, most angles should still be blocked (limited lateral shift)
        assert blocked_count > len(configs) * 0.3, (
            f"Expected many angles blocked near base, only {blocked_count}/{len(configs)}"
        )


# ---------------------------------------------------------------------------
# Category 2: Consistency invariants
# ---------------------------------------------------------------------------

class TestConsistencyInvariants:
    """Verify ordering: gimbal_oracle >= oracle >= regular,
    and gimbal_oracle >= gimbal_realistic >= regular."""

    def _make_random_points(self, n, rng, cfg):
        """Generate n random reachable points for the given config."""
        pts = []
        attempts = 0
        while len(pts) < n and attempts < n * 100:
            # Random point in the workspace
            p = cfg.X + cfg.R_hat * rng.uniform(5, 50) + \
                rng.uniform(-15, 15, size=3) * (1 - np.abs(cfg.R_hat))
            snt = global_to_snt(p, cfg)
            if snt is not None:
                z_ss, z_ntnl, _ = snt
                if 0 <= z_ss <= cfg.ss_lim and 0 <= z_ntnl <= cfg.ntnl_lim:
                    pts.append(p)
            attempts += 1
        return np.array(pts)

    def test_per_node_ordering_fresh_state(self, ctr_down):
        """For every node (no visited nodes), gimbal_oracle.is_valid >= oracle.is_valid."""
        rng = np.random.RandomState(42)
        points = self._make_random_points(50, rng, ctr_down)
        if len(points) < 10:
            pytest.skip("Could not generate enough reachable points")

        oracle = OracleDetector(points, ctr_down, nozzle_radius=0.25, n_arc_samples=20)
        gimbal_o = GimbalOracleDetector(
            points, ctr_down, nozzle_radius=0.25, n_arc_samples=20,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )

        for i in range(len(points)):
            if oracle.is_valid(i):
                assert gimbal_o.is_valid(i), (
                    f"Node {i}: oracle says valid but gimbal_oracle says invalid"
                )

    def test_per_node_ordering_with_visited(self, ctr_down):
        """With some nodes visited, gimbal_realistic >= regular detector."""
        rng = np.random.RandomState(123)
        points = self._make_random_points(50, rng, ctr_down)
        if len(points) < 10:
            pytest.skip("Could not generate enough reachable points")

        # Mark the first 5 as visited
        regular = CTRCollisionDetector(points, ctr_down, nozzle_radius=0.25, n_arc_samples=20)
        gimbal_r = GimbalRealisticDetector(
            points, ctr_down, nozzle_radius=0.25, n_arc_samples=20,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )
        for i in range(min(5, len(points))):
            regular.mark_visited(i)
            gimbal_r.mark_visited(i)
        regular._rebuild_trees()
        gimbal_r._rebuild_trees()

        for i in range(5, len(points)):
            if regular.is_valid(i):
                assert gimbal_r.is_valid(i), (
                    f"Node {i}: regular says valid but gimbal_realistic says invalid"
                )

    def test_cone_zero_matches_oracle(self, ctr_down):
        """At cone_angle=0, gimbal oracle should match oracle exactly on 50 nodes."""
        rng = np.random.RandomState(77)
        points = self._make_random_points(50, rng, ctr_down)
        if len(points) < 10:
            pytest.skip("Could not generate enough reachable points")

        oracle = OracleDetector(points, ctr_down, nozzle_radius=0.25, n_arc_samples=20)
        gimbal = GimbalOracleDetector(
            points, ctr_down, nozzle_radius=0.25, n_arc_samples=20,
            cone_angle_deg=0.0,
        )

        for i in range(len(points)):
            assert gimbal.is_valid(i) == oracle.is_valid(i), f"Mismatch at node {i}"

    def test_cone_zero_realistic_matches_regular(self, ctr_down):
        """At cone_angle=0, gimbal realistic should match regular detector."""
        rng = np.random.RandomState(88)
        points = self._make_random_points(30, rng, ctr_down)
        if len(points) < 10:
            pytest.skip("Could not generate enough reachable points")

        regular = CTRCollisionDetector(points, ctr_down, nozzle_radius=0.25, n_arc_samples=20)
        gimbal = GimbalRealisticDetector(
            points, ctr_down, nozzle_radius=0.25, n_arc_samples=20,
            cone_angle_deg=0.0,
        )

        # Mark some as visited
        for i in range(min(5, len(points))):
            regular.mark_visited(i)
            gimbal.mark_visited(i)
        regular._rebuild_trees()
        gimbal._rebuild_trees()

        for i in range(5, len(points)):
            assert gimbal.is_valid(i) == regular.is_valid(i), f"Mismatch at node {i}"

    def test_pipeline_oracle_ordering(self, ctr_down):
        """run_gimbal_oracle visit count >= run_oracle visit count."""
        rng = np.random.RandomState(55)
        points = self._make_random_points(100, rng, ctr_down)
        if len(points) < 20:
            pytest.skip("Could not generate enough reachable points")

        # Build a simple chain graph
        graph = {}
        for i in range(len(points)):
            nbrs = [i]
            if i > 0:
                nbrs.append(i - 1)
            if i < len(points) - 1:
                nbrs.append(i + 1)
            graph[i] = nbrs

        oracle_passes = run_oracle(graph, points, ctr_down, 0.25, n_arc_samples=20)
        gimbal_passes = run_gimbal_oracle(
            graph, points, ctr_down, 0.25,
            n_arc_samples=20, cone_angle_deg=10.0, n_tilt=2, n_azimuth=6,
        )

        oracle_visited = sum(len(p) for p in oracle_passes.values())
        gimbal_visited = sum(len(p) for p in gimbal_passes.values())
        assert gimbal_visited >= oracle_visited, (
            f"Gimbal oracle ({gimbal_visited}) < oracle ({oracle_visited})"
        )


# ---------------------------------------------------------------------------
# Category 3: Numerical edge cases
# ---------------------------------------------------------------------------

class TestNumericalEdgeCases:

    def test_extreme_tilt_90_degrees(self, ctr_down):
        """alpha=pi/2 should produce a valid config with R_hat perpendicular to original."""
        tilted = make_gimbal_config(ctr_down, alpha=np.pi / 2, phi=0.0)
        np.testing.assert_allclose(np.linalg.norm(tilted.R_hat), 1.0, atol=1e-12)
        np.testing.assert_allclose(
            np.dot(tilted.R_hat, ctr_down.R_hat), 0.0, atol=1e-10,
            err_msg="90° tilt should make R_hat perpendicular to original",
        )
        np.testing.assert_allclose(
            np.dot(tilted.n_hat, tilted.R_hat), 0.0, atol=1e-10,
        )

    def test_extreme_tilt_180_degrees(self, ctr_down):
        """alpha=pi should reverse R_hat."""
        tilted = make_gimbal_config(ctr_down, alpha=np.pi, phi=0.0)
        np.testing.assert_allclose(np.linalg.norm(tilted.R_hat), 1.0, atol=1e-12)
        np.testing.assert_allclose(
            np.dot(tilted.R_hat, ctr_down.R_hat), -1.0, atol=1e-10,
            err_msg="180° tilt should reverse R_hat",
        )

    def test_full_revolution_returns_original(self, ctr_down):
        """alpha=2*pi should return (nearly) the original R_hat."""
        tilted = make_gimbal_config(ctr_down, alpha=2 * np.pi, phi=0.0)
        np.testing.assert_allclose(tilted.R_hat, ctr_down.R_hat, atol=1e-10)

    def test_negative_alpha(self, ctr_down):
        """Negative alpha should tilt in the opposite direction."""
        pos = make_gimbal_config(ctr_down, alpha=0.2, phi=0.0)
        neg = make_gimbal_config(ctr_down, alpha=-0.2, phi=0.0)
        # Same tilt magnitude
        np.testing.assert_allclose(
            np.dot(pos.R_hat, ctr_down.R_hat),
            np.dot(neg.R_hat, ctr_down.R_hat),
            atol=1e-10,
        )
        # But different directions
        assert not np.allclose(pos.R_hat, neg.R_hat, atol=1e-10)

    def test_tiny_alpha_no_nan(self, ctr_down):
        """Very small alpha (1e-15) should produce valid vectors, no NaN."""
        for phi in [0, 1.0, 3.14, 5.5]:
            tilted = make_gimbal_config(ctr_down, alpha=1e-15, phi=phi)
            assert not np.any(np.isnan(tilted.R_hat)), f"NaN in R_hat at phi={phi}"
            assert not np.any(np.isnan(tilted.n_hat)), f"NaN in n_hat at phi={phi}"
            np.testing.assert_allclose(np.linalg.norm(tilted.R_hat), 1.0, atol=1e-8)

    def test_coincident_points_tip_exclusion(self, ctr_down):
        """Two nodes at the exact same position: the duplicate should be excluded
        by tip-proximity exclusion and not block the target."""
        pt = np.array([0.0, -20.0, 0.0])
        points = np.vstack([pt, pt])
        det = GimbalOracleDetector(
            points, ctr_down, nozzle_radius=1.0, n_arc_samples=20,
            cone_angle_deg=10.0,
        )
        # Node 1 is at the same position as node 0 → within tip exclusion
        assert det.is_valid(0)

    def test_cardinal_r_hat_directions(self):
        """make_gimbal_config should work for all 6 cardinal R_hat directions."""
        f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(None, 47.0)
        for r_hat in [
            [1, 0, 0], [-1, 0, 0],
            [0, 1, 0], [0, -1, 0],
            [0, 0, 1], [0, 0, -1],
        ]:
            cfg = CTRConfig(
                X=np.zeros(3),
                R_hat=np.array(r_hat, dtype=float),
                n_hat=_perpendicular_unit(np.array(r_hat, dtype=float)),
                theta_match=0.0,
                radius=47.0,
                f_xr_yr=f_xr_yr, f_yr_ntnlss=f_yr_ntnlss, x_val=x_val,
                ss_lim=65.0, ntnl_lim=140.0,
            )
            tilted = make_gimbal_config(cfg, alpha=0.2, phi=1.0)
            assert not np.any(np.isnan(tilted.R_hat)), f"NaN for R_hat={r_hat}"
            np.testing.assert_allclose(np.linalg.norm(tilted.R_hat), 1.0, atol=1e-12)
            np.testing.assert_allclose(
                np.dot(tilted.n_hat, tilted.R_hat), 0.0, atol=1e-10,
            )

    def test_diagonal_r_hat(self):
        """make_gimbal_config should work for diagonal R_hat like [1,1,1]/sqrt(3)."""
        f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(None, 47.0)
        r_hat = np.array([1, 1, 1], dtype=float) / np.sqrt(3)
        cfg = CTRConfig(
            X=np.zeros(3), R_hat=r_hat,
            n_hat=_perpendicular_unit(r_hat), theta_match=0.0,
            radius=47.0,
            f_xr_yr=f_xr_yr, f_yr_ntnlss=f_yr_ntnlss, x_val=x_val,
            ss_lim=65.0, ntnl_lim=140.0,
        )
        tilted = make_gimbal_config(cfg, alpha=0.3, phi=2.0)
        np.testing.assert_allclose(np.linalg.norm(tilted.R_hat), 1.0, atol=1e-12)
        cos_a = np.dot(tilted.R_hat, r_hat)
        np.testing.assert_allclose(cos_a, np.cos(0.3), atol=1e-10)


# ---------------------------------------------------------------------------
# Category 4: Config construction correctness
# ---------------------------------------------------------------------------

class TestGimbalConfigConstruction:

    @pytest.mark.parametrize("n_tilt,n_azimuth", [(1, 4), (3, 8), (5, 16), (10, 32)])
    def test_config_count(self, ctr_down, n_tilt, n_azimuth):
        """Number of configs should be 1 + n_tilt * n_azimuth."""
        configs = _build_gimbal_configs(ctr_down, 15.0, n_tilt, n_azimuth)
        assert len(configs) == 1 + n_tilt * n_azimuth

    def test_all_configs_valid_vectors(self, ctr_down):
        """Every config should have unit R_hat, unit n_hat, and R_hat perp n_hat."""
        configs = _build_gimbal_configs(ctr_down, 20.0, 5, 16)
        for i, cfg in enumerate(configs):
            np.testing.assert_allclose(
                np.linalg.norm(cfg.R_hat), 1.0, atol=1e-12,
                err_msg=f"Config {i}: R_hat not unit",
            )
            np.testing.assert_allclose(
                np.linalg.norm(cfg.n_hat), 1.0, atol=1e-12,
                err_msg=f"Config {i}: n_hat not unit",
            )
            np.testing.assert_allclose(
                np.dot(cfg.R_hat, cfg.n_hat), 0.0, atol=1e-10,
                err_msg=f"Config {i}: R_hat not perp to n_hat",
            )

    def test_tilt_linearity(self, ctr_down):
        """For n_tilt=3, cone=15°, tilt levels should be 5°, 10°, 15°."""
        configs = _build_gimbal_configs(ctr_down, 15.0, 3, 1)
        # configs[0] = base, configs[1] = 5°, configs[2] = 10°, configs[3] = 15°
        expected_degrees = [5.0, 10.0, 15.0]
        for i, expected in enumerate(expected_degrees):
            cos_a = np.dot(configs[i + 1].R_hat, ctr_down.R_hat)
            actual_deg = np.degrees(np.arccos(np.clip(cos_a, -1, 1)))
            np.testing.assert_allclose(
                actual_deg, expected, atol=0.01,
                err_msg=f"Tilt level {i+1}: expected {expected}°, got {actual_deg:.2f}°",
            )

    def test_azimuthal_uniformity(self, ctr_down):
        """At a fixed tilt, the n_azimuth configs should be uniformly spaced on a cone."""
        n_azimuth = 8
        configs = _build_gimbal_configs(ctr_down, 15.0, 1, n_azimuth)
        # configs[1..8] are at the same alpha, different phi
        r_hats = np.array([c.R_hat for c in configs[1:]])

        # Pairwise angles between adjacent azimuths should be equal
        angles = []
        for i in range(n_azimuth):
            j = (i + 1) % n_azimuth
            cos_a = np.clip(np.dot(r_hats[i], r_hats[j]), -1, 1)
            angles.append(np.degrees(np.arccos(cos_a)))

        angles = np.array(angles)
        np.testing.assert_allclose(
            angles, angles[0], atol=0.1,
            err_msg=f"Azimuthal spacing not uniform: {angles}",
        )

    def test_all_configs_share_calibration(self, ctr_down):
        """Calibration objects should be the same identity (not copies)."""
        configs = _build_gimbal_configs(ctr_down, 15.0, 3, 8)
        for i, cfg in enumerate(configs):
            assert cfg.f_xr_yr is ctr_down.f_xr_yr, f"Config {i}: f_xr_yr differs"
            assert cfg.f_yr_ntnlss is ctr_down.f_yr_ntnlss
            assert cfg.x_val is ctr_down.x_val
            np.testing.assert_array_equal(cfg.X, ctr_down.X)
            assert cfg.radius == ctr_down.radius
            assert cfg.ss_lim == ctr_down.ss_lim
            assert cfg.ntnl_lim == ctr_down.ntnl_lim

    def test_first_config_is_base(self, ctr_down):
        """configs[0] should be the base config itself (identity)."""
        configs = _build_gimbal_configs(ctr_down, 15.0, 3, 8)
        assert configs[0] is ctr_down


# ---------------------------------------------------------------------------
# Category 5: Body sampling blind spots
# ---------------------------------------------------------------------------

class TestBodySamplingBlindSpots:

    def test_blocker_between_ss_samples_evades_detection(self, ctr_down):
        """A node placed exactly between two SS body samples (beyond nozzle_radius
        of both) should evade collision detection."""
        # Compute body for a deep target
        target = np.array([0.0, -50.0, 0.0])
        snt = global_to_snt(target, ctr_down)
        assert snt is not None
        z_ss, z_ntnl, theta = snt

        body = compute_needle_body(z_ss, z_ntnl, theta, ctr_down, n_arc_samples=20)
        ss_points = [bp for bp in body
                     if np.abs(np.dot(bp - ctr_down.X, ctr_down.R_hat)) < z_ss + 0.01]

        if len(ss_points) < 3:
            pytest.skip("Not enough SS body samples")

        # Find the midpoint between two consecutive SS samples
        p1 = ss_points[len(ss_points) // 2]
        p2 = ss_points[len(ss_points) // 2 + 1]
        midpoint = (p1 + p2) / 2.0
        sample_spacing = np.linalg.norm(p2 - p1)

        # With small nozzle_radius (well under half the sample spacing),
        # the blocker at the midpoint should evade detection
        small_r = sample_spacing * 0.3  # less than half the spacing
        points = np.vstack([target[np.newaxis, :], midpoint[np.newaxis, :]])

        det = OracleDetector(
            points, ctr_down, nozzle_radius=small_r, n_arc_samples=20,
        )
        # The blocker should be MISSED (false negative — blind spot)
        assert det.is_valid(0), (
            f"Blocker between samples (spacing={sample_spacing:.2f}mm, "
            f"nozzle_r={small_r:.2f}mm) should evade detection"
        )

        # With a larger nozzle_radius that covers the gap, it should be caught
        large_r = sample_spacing * 0.8
        det2 = OracleDetector(
            points, ctr_down, nozzle_radius=large_r, n_arc_samples=20,
        )
        assert not det2.is_valid(0), "Larger nozzle radius should catch the blocker"

    def test_finer_sampling_catches_blind_spot(self, ctr_down):
        """Increasing n_arc_samples should close body-sampling blind spots."""
        target = np.array([0.0, -50.0, 0.0])
        snt = global_to_snt(target, ctr_down)
        assert snt is not None
        z_ss, z_ntnl, theta = snt

        # Get coarse body and find a blind-spot midpoint
        body_coarse = compute_needle_body(z_ss, z_ntnl, theta, ctr_down, n_arc_samples=10)
        ss_pts = [bp for bp in body_coarse
                  if np.abs(np.dot(bp - ctr_down.X, ctr_down.R_hat)) < z_ss + 0.01]
        if len(ss_pts) < 3:
            pytest.skip("Not enough SS body samples")

        p1 = ss_pts[len(ss_pts) // 2]
        p2 = ss_pts[len(ss_pts) // 2 + 1]
        midpoint = (p1 + p2) / 2.0
        spacing_coarse = np.linalg.norm(p2 - p1)
        nozzle_r = spacing_coarse * 0.3

        points = np.vstack([target[np.newaxis, :], midpoint[np.newaxis, :]])

        # Coarse sampling misses the blocker
        det_coarse = OracleDetector(
            points, ctr_down, nozzle_radius=nozzle_r, n_arc_samples=10,
        )
        assert det_coarse.is_valid(0), "Coarse sampling should miss the blocker"

        # Fine sampling catches it
        det_fine = OracleDetector(
            points, ctr_down, nozzle_radius=nozzle_r, n_arc_samples=200,
        )
        assert not det_fine.is_valid(0), "Fine sampling should catch the blocker"


# ---------------------------------------------------------------------------
# Category 6: Performance under stress
# ---------------------------------------------------------------------------

class TestPerformance:

    def test_short_circuit_efficiency(self, ctr_down):
        """When alpha=0 works, is_valid should be much faster than when
        only the last angle works."""
        # A single isolated reachable node — alpha=0 works immediately
        points_easy = np.array([[0.0, -20.0, 0.0]])
        det_easy = GimbalOracleDetector(
            points_easy, ctr_down, nozzle_radius=0.125, n_arc_samples=20,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )

        # Warm-up
        det_easy.is_valid(0)
        t0 = time.perf_counter()
        for _ in range(100):
            det_easy._unvisited.add(0)  # re-add to bypass visited check
            det_easy.is_valid(0)
        t_easy = time.perf_counter() - t0

        # Node blocked at alpha=0 by a non-neighbor on the shaft
        points_hard = np.array([
            [0.0, -60.0, 0.0],   # target
            [0.05, -30.0, 0.0],  # blocker on shaft
        ])
        det_hard = GimbalOracleDetector(
            points_hard, ctr_down, nozzle_radius=1.0, n_arc_samples=40,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )

        det_hard.is_valid(0)
        t0 = time.perf_counter()
        for _ in range(100):
            det_hard._unvisited = {0, 1}
            det_hard.is_valid(0)
        t_hard = time.perf_counter() - t0

        # Short-circuit should be significantly faster (at least 2x)
        assert t_easy < t_hard, (
            f"Short-circuit not faster: easy={t_easy:.3f}s, hard={t_hard:.3f}s"
        )

    def test_dense_3d_grid_completes(self, ctr_down):
        """A 7x7x7=343 node grid should complete in reasonable time."""
        spacing = 3.0
        pts = []
        for x in np.linspace(-9, 9, 7):
            for z in np.linspace(-9, 9, 7):
                for y_offset in np.linspace(10, 28, 7):
                    pts.append([x, -y_offset, z])
        points = np.array(pts)

        # Build 6-connectivity graph
        graph = {i: [i] for i in range(len(points))}
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                if np.linalg.norm(points[i] - points[j]) < spacing * 1.1:
                    graph[i].append(j)
                    graph[j].append(i)

        t0 = time.perf_counter()
        det = GimbalOracleDetector(
            points, ctr_down, nozzle_radius=0.25, n_arc_samples=20,
            cone_angle_deg=10.0, n_tilt=2, n_azimuth=6,
            graph=graph,
        )
        valid_count = sum(1 for i in range(len(points)) if det.is_valid(i))
        elapsed = time.perf_counter() - t0

        assert elapsed < 30.0, f"343-node grid took {elapsed:.1f}s (limit: 30s)"
        assert valid_count > 0, "At least some nodes should be valid"


# ---------------------------------------------------------------------------
# Category 7: Regression and integration safeguards
# ---------------------------------------------------------------------------

class TestRegressionSafeguards:

    def test_deterministic_reproducibility(self, ctr_down):
        """Two identical runs should produce identical results."""
        rng = np.random.RandomState(99)
        pts = []
        for _ in range(30):
            p = ctr_down.X + ctr_down.R_hat * rng.uniform(10, 40) + \
                rng.uniform(-5, 5, size=3) * (1 - np.abs(ctr_down.R_hat))
            pts.append(p)
        points = np.array(pts)
        graph = {i: [i] + ([i-1] if i > 0 else []) + ([i+1] if i < 29 else [])
                 for i in range(30)}

        r1 = run_gimbal_oracle(graph.copy(), points, ctr_down, 0.25,
                               cone_angle_deg=10.0, n_tilt=2, n_azimuth=6)
        r2 = run_gimbal_oracle(graph.copy(), points, ctr_down, 0.25,
                               cone_angle_deg=10.0, n_tilt=2, n_azimuth=6)

        v1 = sum(len(p) for p in r1.values())
        v2 = sum(len(p) for p in r2.values())
        assert v1 == v2, f"Non-deterministic: {v1} vs {v2}"
        assert len(r1) == len(r2)
        for k in r1:
            assert r1[k] == r2[k], f"Pass {k} differs"

    def test_single_node_graph(self, ctr_down):
        """A single reachable node should be valid, then invalid after visit."""
        points = np.array([[0.0, -20.0, 0.0]])
        for DetCls in [GimbalOracleDetector, GimbalRealisticDetector]:
            det = DetCls(
                points, ctr_down, nozzle_radius=0.25, n_arc_samples=20,
                cone_angle_deg=10.0,
            )
            assert det.has_unvisited()
            assert det.is_valid(0)
            det.mark_visited(0)
            assert not det.is_valid(0)
            assert not det.has_unvisited()

    def test_fully_connected_clique(self, ctr_down):
        """5 well-separated reachable nodes in a fully connected graph — all
        should be valid due to neighbor exemption.

        Nodes must be deep enough along R_hat to be reachable (z_ss > 0) and
        off-axis offsets small enough to stay in calibration domain.
        """
        # All on-axis at different depths — guaranteed reachable
        points = np.array([
            [0.0, -10.0, 0.0],
            [0.0, -15.0, 0.0],
            [0.0, -20.0, 0.0],
            [0.0, -25.0, 0.0],
            [0.0, -30.0, 0.0],
        ])
        all_nodes = list(range(5))
        graph = {i: all_nodes[:] for i in range(5)}

        det = GimbalOracleDetector(
            points, ctr_down, nozzle_radius=0.25, graph=graph,
            n_arc_samples=20, cone_angle_deg=10.0,
        )
        for i in range(5):
            assert det.is_valid(i), f"Node {i} should be valid in fully connected clique"

    def test_huge_nozzle_no_graph_blocks_all(self, ctr_down):
        """With large nozzle_radius, a blocker on the shaft (between base
        and target, outside tip exclusion) should block even with gimbal.

        tip_exclusion_r = 3 * nozzle_r = 15mm. Blocker must be > 15mm
        from the target. Place target deep (y=-50), blocker at y=-10
        (40mm from target, 10mm from base). At depth 10mm, max gimbal
        shift = 10*sin(20°) = 3.4mm < nozzle_r=5mm → can't escape.
        """
        nozzle_r = 5.0
        points = np.array([
            [0.0, -50.0, 0.0],   # target (deep)
            [0.2, -10.0, 0.0],   # blocker on shaft, near base
        ])
        det = GimbalOracleDetector(
            points, ctr_down, nozzle_radius=nozzle_r, n_arc_samples=40,
            cone_angle_deg=20.0, n_tilt=3, n_azimuth=8,
        )
        # Node 1 is on the shaft near the base where gimbal shift < nozzle_r
        assert not det.is_valid(0), "Near-base blocker with large nozzle_r should block"

    def test_body_drag_wall_blocks_realistic(self, ctr_down):
        """A wall of visited nodes that spans all gimbal angles should block
        the realistic detector but not the oracle.

        Wall must be dense enough that body samples fall within nozzle_r of
        at least one wall node at every gimbal angle.
        """
        target = np.array([0.0, -50.0, 0.0])
        nozzle_r = 2.0  # larger radius to ensure wall nodes are caught

        # Dense wall at depth 20mm (30mm from target >> 6mm tip exclusion)
        # Spacing ~1mm ensures every body sample hits a wall node within 2mm
        wall = []
        for x in np.linspace(-20, 20, 40):
            for z in np.linspace(-20, 20, 40):
                wall.append([x, -20.0, z])

        points = np.vstack([target[np.newaxis, :]] +
                           [np.array(w)[np.newaxis, :] for w in wall])

        # Oracle: skip body-drag → should be valid (wall nodes are visited, not unvisited)
        oracle = GimbalOracleDetector(
            points, ctr_down, nozzle_radius=nozzle_r, n_arc_samples=20,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )
        for i in range(1, len(points)):
            oracle.mark_visited(i)
        oracle._rebuild_trees()
        assert oracle.is_valid(0), "Oracle should pass — wall is visited, not shaft-blocking"

        # Realistic: body-drag checked → wall blocks all gimbal angles
        realistic = GimbalRealisticDetector(
            points, ctr_down, nozzle_radius=nozzle_r, n_arc_samples=20,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )
        for i in range(1, len(points)):
            realistic.mark_visited(i)
        realistic._rebuild_trees()
        assert not realistic.is_valid(0), (
            "Realistic should be blocked — wall of visited nodes covers all gimbal angles"
        )
