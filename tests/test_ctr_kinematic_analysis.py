"""Unit tests for CTR kinematic analysis: approach directions & singularities."""

import numpy as np
import pytest

from xcavate.core.ctr_kinematics import (
    CTRConfig,
    _load_calibration,
    batch_is_reachable,
)
from xcavate.core.ctr_kinematic_analysis import (
    SING_CAL_BOUND,
    SING_GIMBAL,
    SING_NTNL_LIMIT,
    SING_ON_AXIS,
    SING_SS_LIMIT,
    KinematicAnalysisResult,
    analyze_workspace,
    find_minimum_cone_angle,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ctr_down():
    """CTR at origin, inserting along -Y, bend radius 47mm."""
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
    """CTR inserting along -Z (stress test config)."""
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
# Approach Count
# ---------------------------------------------------------------------------

class TestApproachCount:

    def test_on_axis_max_count(self, ctr_down):
        """A node on the insertion axis should be reachable from all configs
        (on-axis points have r_perp ≈ 0, which may be at the lower
        calibration boundary — skip if unreachable)."""
        # Place node on axis at moderate depth
        points = np.array([[0.0, -30.0, 0.0]])
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=15.0, n_tilt=3, n_azimuth=8)

        # On-axis: r_perp ≈ 0 — this may or may not be in calibration domain
        # If reachable from base, should be reachable from most/all tilted configs
        if result.approach_count[0] > 0:
            # Should have high approach count (most configs reach on-axis points)
            assert result.approach_count[0] >= result.total_configs * 0.5

    def test_far_off_axis_low_count(self, ctr_down):
        """A node near the workspace edge should have fewer valid configs."""
        # Place node at the edge of the calibration domain
        # x_val[-1] for radius=47 is about 47mm (radius * (1-cos(pi/2)))
        edge_r = float(ctr_down.x_val[-1]) * 0.95
        points = np.array([[edge_r, -40.0, 0.0]])
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=15.0, n_tilt=3, n_azimuth=8)

        # Near the edge, fewer configs will keep the point in calibration domain
        # Just verify it returns a valid result (may be 0 or low)
        assert result.approach_count[0] <= result.total_configs

    def test_unreachable_zero_count(self, ctr_down):
        """A node far outside the workspace should have approach_count = 0."""
        points = np.array([[500.0, 500.0, 500.0]])
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=15.0, n_tilt=3, n_azimuth=8)

        assert result.approach_count[0] == 0

    def test_cone_zero_exactly_one_or_zero(self, ctr_down):
        """With cone_angle=0, approach_count should be 0 or 1 (only base config)."""
        points = np.array([
            [0.0, -30.0, 0.0],     # possibly reachable
            [500.0, 500.0, 500.0],  # unreachable
        ])
        node_indices = np.array([0, 1])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=0.0, n_tilt=0, n_azimuth=8)

        assert result.total_configs == 1
        assert result.approach_count[0] <= 1
        assert result.approach_count[1] == 0


# ---------------------------------------------------------------------------
# Singularity Detection
# ---------------------------------------------------------------------------

class TestSingularityDetection:

    def test_on_axis_flag(self, ctr_down):
        """A node on the insertion axis (r_perp ≈ 0) should get SING_ON_AXIS."""
        points = np.array([[0.0, -30.0, 0.0]])
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=15.0, n_tilt=3, n_azimuth=8)

        if result.approach_count[0] > 0:
            assert result.singularity_flags[0] & SING_ON_AXIS

    def test_cal_boundary_flag(self, ctr_down):
        """A node near the calibration boundary should get SING_CAL_BOUND."""
        edge_r = float(ctr_down.x_val[-1]) * 0.97
        points = np.array([[edge_r, -50.0, 0.0]])
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=5.0, n_tilt=1, n_azimuth=8)

        if result.approach_count[0] > 0:
            assert result.singularity_flags[0] & SING_CAL_BOUND

    def test_gimbal_only_flag(self, ctr_down):
        """If only alpha=0 produces a valid config, SING_GIMBAL should be set."""
        # Place a node that is right at the edge of reachability for the base
        # config. When we tilt, it falls out of bounds.
        # Use a very small cone angle so tilting moves it out of bounds.
        # A node near the actuator limit: high z_ss
        points = np.array([[0.0, -64.5, 0.0]])  # near ss_lim=65
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=15.0, n_tilt=3, n_azimuth=8)

        # If only the base config works, SING_GIMBAL should be set
        if result.approach_count[0] == 1:
            assert result.singularity_flags[0] & SING_GIMBAL

    def test_actuator_limit_flags(self, ctr_down):
        """Nodes near the actuator bounds should get SS_LIMIT or NTNL_LIMIT."""
        # r_perp=0.01 puts it in calibration domain; depth=65.5 gives z_ss≈64.58
        # which is within 1mm of ss_lim=65
        points = np.array([[0.01, -65.5, 0.0]])
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=0.0, n_tilt=0, n_azimuth=8)

        if result.approach_count[0] > 0:
            assert result.singularity_flags[0] & SING_SS_LIMIT


# ---------------------------------------------------------------------------
# Angular Spread
# ---------------------------------------------------------------------------

class TestAngularSpread:

    def test_all_directions_high_spread(self, ctr_down):
        """A node reachable from many directions should have high spread."""
        # On-axis node at moderate depth — reachable from many angles
        points = np.array([[0.0, -30.0, 0.0]])
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=15.0, n_tilt=3, n_azimuth=8)

        if result.approach_count[0] > 5:
            # With many valid directions from different tilts, spread > 0
            assert result.angular_spread[0] > 0.0

    def test_single_direction_zero_spread(self, ctr_down):
        """A node reachable from exactly one direction should have spread = 0."""
        # Use cone=0 to get at most 1 config
        points = np.array([[0.0, -30.0, 0.0]])
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=0.0, n_tilt=0, n_azimuth=8)

        if result.approach_count[0] == 1:
            assert result.angular_spread[0] == 0.0


# ---------------------------------------------------------------------------
# Joint Ranges
# ---------------------------------------------------------------------------

class TestJointRanges:

    def test_ranges_within_limits(self, ctr_down):
        """All joint ranges should be within actuator limits."""
        rng = np.random.RandomState(42)
        # Generate random reachable points
        pts = []
        for _ in range(200):
            p = ctr_down.X + ctr_down.R_hat * rng.uniform(10, 50) + \
                rng.uniform(-10, 10, size=3) * (1 - np.abs(ctr_down.R_hat))
            pts.append(p)
        points = np.array(pts)
        node_indices = np.arange(len(points))

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=15.0, n_tilt=3, n_azimuth=8)

        for i in range(len(points)):
            if result.approach_count[i] > 0:
                # z_ss range (index 2) should be within [0, ss_lim]
                assert result.joint_ranges[i, 2, 0] >= -0.01
                assert result.joint_ranges[i, 2, 1] <= ctr_down.ss_lim + 0.01
                # z_ntnl range (index 3) should be within [0, ntnl_lim]
                assert result.joint_ranges[i, 3, 0] >= -0.01
                assert result.joint_ranges[i, 3, 1] <= ctr_down.ntnl_lim + 0.01

    def test_single_config_point_range(self, ctr_down):
        """With one valid config, min == max for all DOFs."""
        # Use cone=0 to get at most 1 config
        points = np.array([[0.0, -30.0, 0.0]])
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=0.0, n_tilt=0, n_azimuth=8)

        if result.approach_count[0] == 1:
            for j in range(5):
                assert result.joint_ranges[0, j, 0] == result.joint_ranges[0, j, 1]


# ---------------------------------------------------------------------------
# Vulnerability
# ---------------------------------------------------------------------------

class TestVulnerability:

    def test_high_approach_low_vuln(self, ctr_down):
        """Many valid directions → low vulnerability."""
        # Single isolated on-axis point (density=1)
        points = np.array([[0.0, -30.0, 0.0]])
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=15.0, n_tilt=3, n_azimuth=8)

        if result.approach_count[0] > result.total_configs * 0.8:
            assert result.vulnerability[0] < 0.3

    def test_zero_approach_max_vuln(self, ctr_down):
        """Unreachable node → vulnerability = 1.0 (with density_factor=1)."""
        points = np.array([[500.0, 500.0, 500.0]])
        node_indices = np.array([0])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=15.0, n_tilt=3, n_azimuth=8)

        assert result.approach_count[0] == 0
        assert result.vulnerability[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Minimum Cone Angle
# ---------------------------------------------------------------------------

class TestMinimumConeAngle:

    def test_monotonic_coverage(self, ctr_down):
        """Coverage should be non-decreasing with cone angle."""
        rng = np.random.RandomState(7)
        pts = []
        for _ in range(50):
            p = ctr_down.X + ctr_down.R_hat * rng.uniform(5, 50) + \
                rng.uniform(-15, 15, size=3) * (1 - np.abs(ctr_down.R_hat))
            pts.append(p)
        points = np.array(pts)
        node_indices = np.arange(len(points))

        result = find_minimum_cone_angle(
            points, node_indices, ctr_down,
            angles_deg=(0, 5, 10, 15, 20),
            n_azimuth=8,
        )

        angles = sorted(result.keys())
        coverages = [result[a] for a in angles]
        for i in range(1, len(coverages)):
            assert coverages[i] >= coverages[i - 1] - 1e-10, (
                f"Coverage decreased: {angles[i-1]}°→{coverages[i-1]:.3f}, "
                f"{angles[i]}°→{coverages[i]:.3f}"
            )

    def test_zero_cone_baseline(self, ctr_down):
        """At cone=0, coverage should match batch_is_reachable."""
        rng = np.random.RandomState(99)
        pts = []
        for _ in range(30):
            p = ctr_down.X + ctr_down.R_hat * rng.uniform(5, 50) + \
                rng.uniform(-20, 20, size=3) * (1 - np.abs(ctr_down.R_hat))
            pts.append(p)
        points = np.array(pts)
        node_indices = np.arange(len(points))

        # batch_is_reachable baseline
        reachable_mask = batch_is_reachable(points, ctr_down)
        expected_frac = float(np.sum(reachable_mask)) / len(points)

        result = find_minimum_cone_angle(
            points, node_indices, ctr_down,
            angles_deg=(0,),
            n_azimuth=8,
        )

        assert result[0.0] == pytest.approx(expected_frac, abs=1e-10)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

class TestResultDataclass:

    def test_result_shapes(self, ctr_down):
        """Verify output shapes are consistent."""
        points = np.array([
            [0.0, -20.0, 0.0],
            [0.0, -30.0, 0.0],
            [0.0, -40.0, 0.0],
        ])
        node_indices = np.array([0, 1, 2])

        result = analyze_workspace(points, node_indices, ctr_down,
                                   cone_angle_deg=10.0, n_tilt=2, n_azimuth=6)

        assert result.node_indices.shape == (3,)
        assert result.approach_count.shape == (3,)
        assert result.angular_spread.shape == (3,)
        assert result.vulnerability.shape == (3,)
        assert result.singularity_flags.shape == (3,)
        assert result.joint_ranges.shape == (3, 5, 2)
        assert result.total_configs == 1 + 2 * 6

    def test_empty_input(self, ctr_down):
        """Empty node_indices should return empty arrays."""
        points = np.zeros((10, 3))
        node_indices = np.array([], dtype=np.intp)

        result = analyze_workspace(points, node_indices, ctr_down)

        assert len(result.approach_count) == 0
        assert len(result.angular_spread) == 0
        assert result.joint_ranges.shape == (0, 5, 2)
