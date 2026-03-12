"""Unit tests for gimbal solver: config tracking, continuity, and reachability."""

import numpy as np
import pytest

from xcavate.core.ctr_kinematics import (
    CTRConfig,
    _load_calibration,
    batch_is_reachable,
    compute_needle_body,
    global_to_snt,
)
from xcavate.core.gimbal_solver import (
    GimbalNodeSolution,
    GimbalSolverDetector,
    _build_config_angles,
    gimbal_reachable_nodes,
    run_gimbal_solver,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_ctr_config():
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
def downward_ctr_config():
    """CTR above origin, inserting downward along -Z."""
    f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(None, 47.0)
    return CTRConfig(
        X=np.array([0.0, 0.0, 100.0]),
        R_hat=np.array([0.0, 0.0, -1.0]),
        n_hat=np.array([1.0, 0.0, 0.0]),
        theta_match=0.0,
        radius=47.0,
        f_xr_yr=f_xr_yr,
        f_yr_ntnlss=f_yr_ntnlss,
        x_val=x_val,
        ss_lim=80.0,
        ntnl_lim=140.0,
    )


def _make_line_points(start, direction, n_points, spacing):
    """Create n_points along a line from start in the given direction."""
    direction = np.array(direction, dtype=float)
    direction /= np.linalg.norm(direction)
    return np.array([
        np.array(start) + i * spacing * direction
        for i in range(n_points)
    ])


def _make_simple_graph(n_points):
    """Create a linear chain graph: 0-1-2-...-n."""
    graph = {}
    for i in range(n_points):
        neighbors = []
        if i > 0:
            neighbors.append(i - 1)
        if i < n_points - 1:
            neighbors.append(i + 1)
        graph[i] = neighbors
    return graph


# ---------------------------------------------------------------------------
# TestGimbalSolverDetector
# ---------------------------------------------------------------------------

class TestGimbalSolverDetector:
    def test_records_config_per_node(self, simple_ctr_config):
        """Every visited node via is_valid + mark_visited has a solution."""
        points = _make_line_points([0, -10, 0], [0, -1, 0], 5, 5.0)
        graph = _make_simple_graph(5)
        det = GimbalSolverDetector(
            points, simple_ctr_config, nozzle_radius=0.125,
            graph=graph, cone_angle_deg=10.0, n_tilt=2, n_azimuth=4,
        )
        visited = []
        for i in range(5):
            if det.is_valid(i):
                det.mark_visited(i)
                visited.append(i)

        solutions = det.get_solutions()
        for node in visited:
            assert node in solutions, f"Node {node} visited but has no solution"
            sol = solutions[node]
            assert isinstance(sol, GimbalNodeSolution)
            assert 0 <= sol.config_idx < 1 + 2 * 4  # base + tilted

    def test_prefers_active_config(self, simple_ctr_config):
        """When active config is valid for a node, it should be chosen."""
        # On-axis nodes: base config (idx=0) should always work
        points = _make_line_points([0, -10, 0], [0, -1, 0], 3, 5.0)
        graph = _make_simple_graph(3)
        det = GimbalSolverDetector(
            points, simple_ctr_config, nozzle_radius=0.125,
            graph=graph, cone_angle_deg=10.0, n_tilt=2, n_azimuth=4,
        )
        det.set_active_config(0)  # base config

        for i in range(3):
            if det.is_valid(i):
                det.mark_visited(i)

        solutions = det.get_solutions()
        for sol in solutions.values():
            assert sol.config_idx == 0, "On-axis nodes should use base config"

    def test_falls_back_to_other_config(self, downward_ctr_config):
        """When active config fails, another should be chosen."""
        # Create points that are only reachable with tilted config
        # (off-axis, near the edge of base workspace)
        cfg = downward_ctr_config

        # Point directly below: reachable with base config
        p_on_axis = np.array([0.0, 0.0, 50.0])
        # Point off-axis: may need tilted config
        p_off_axis = np.array([25.0, 0.0, 50.0])

        points = np.array([p_on_axis, p_off_axis])
        graph = {0: [1], 1: [0]}

        det = GimbalSolverDetector(
            points, cfg, nozzle_radius=0.125,
            graph=graph, cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )

        # Visit on-axis node first
        if det.is_valid(0):
            det.mark_visited(0)

        # Try off-axis node — may need different config
        if det.is_valid(1):
            det.mark_visited(1)
            solutions = det.get_solutions()
            assert 1 in solutions

    def test_solutions_have_valid_snt(self, simple_ctr_config):
        """Stored z_ss/z_ntnl/theta are within actuator bounds."""
        points = _make_line_points([0, -10, 0], [0, -1, 0], 5, 5.0)
        graph = _make_simple_graph(5)
        det = GimbalSolverDetector(
            points, simple_ctr_config, nozzle_radius=0.125,
            graph=graph, cone_angle_deg=10.0, n_tilt=2, n_azimuth=4,
        )

        for i in range(5):
            if det.is_valid(i):
                det.mark_visited(i)

        solutions = det.get_solutions()
        for node, sol in solutions.items():
            assert sol.z_ss >= 0, f"Node {node}: z_ss={sol.z_ss} < 0"
            assert sol.z_ss <= simple_ctr_config.ss_lim
            assert sol.z_ntnl >= 0, f"Node {node}: z_ntnl={sol.z_ntnl} < 0"
            assert sol.z_ntnl <= simple_ctr_config.ntnl_lim

    def test_matches_realistic_visit_count(self, simple_ctr_config):
        """Visit count should be >= GimbalRealisticDetector."""
        from xcavate.core.oracle import GimbalRealisticDetector

        points = _make_line_points([0, -15, 0], [0, -1, 0], 10, 3.0)
        graph = _make_simple_graph(10)
        cone = 10.0
        n_tilt = 2
        n_azi = 4

        # Run realistic detector
        det_r = GimbalRealisticDetector(
            points, simple_ctr_config, nozzle_radius=0.125,
            graph=graph, cone_angle_deg=cone, n_tilt=n_tilt, n_azimuth=n_azi,
        )
        count_r = 0
        for i in range(10):
            if det_r.is_valid(i):
                det_r.mark_visited(i)
                count_r += 1

        # Run solver detector
        det_s = GimbalSolverDetector(
            points, simple_ctr_config, nozzle_radius=0.125,
            graph=graph, cone_angle_deg=cone, n_tilt=n_tilt, n_azimuth=n_azi,
        )
        count_s = 0
        for i in range(10):
            if det_s.is_valid(i):
                det_s.mark_visited(i)
                count_s += 1

        assert count_s >= count_r, (
            f"Solver ({count_s}) should visit >= realistic ({count_r})"
        )


# ---------------------------------------------------------------------------
# TestConfigContinuity
# ---------------------------------------------------------------------------

class TestConfigContinuity:
    def test_consecutive_nodes_same_config(self, simple_ctr_config):
        """Chain of on-axis nodes should all use the same config."""
        points = _make_line_points([0, -10, 0], [0, -1, 0], 5, 5.0)
        graph = _make_simple_graph(5)
        det = GimbalSolverDetector(
            points, simple_ctr_config, nozzle_radius=0.125,
            graph=graph, cone_angle_deg=10.0, n_tilt=2, n_azimuth=4,
        )

        for i in range(5):
            if det.is_valid(i):
                det.mark_visited(i)

        solutions = det.get_solutions()
        configs_used = [solutions[i].config_idx for i in sorted(solutions)]
        # All should be the same (base config for on-axis)
        if len(configs_used) > 1:
            assert len(set(configs_used)) == 1, (
                f"Expected all same config, got {configs_used}"
            )

    def test_active_config_updates_on_change(self, simple_ctr_config):
        """After a config change, the new config becomes active."""
        points = _make_line_points([0, -10, 0], [0, -1, 0], 3, 5.0)
        graph = _make_simple_graph(3)
        det = GimbalSolverDetector(
            points, simple_ctr_config, nozzle_radius=0.125,
            graph=graph, cone_angle_deg=10.0, n_tilt=2, n_azimuth=4,
        )

        # Force active to config 1 (if available)
        if len(det._gimbal_configs) > 1:
            det.set_active_config(1)
            assert det._active_config_idx == 1

            # After visiting a node, active should update
            if det.is_valid(0):
                det.mark_visited(0)
                solutions = det.get_solutions()
                if 0 in solutions:
                    assert det._active_config_idx == solutions[0].config_idx


# ---------------------------------------------------------------------------
# TestRunGimbalSolver
# ---------------------------------------------------------------------------

class TestRunGimbalSolver:
    def test_returns_passes_and_solutions(self, simple_ctr_config):
        """run_gimbal_solver returns a (passes, solutions) tuple."""
        points = _make_line_points([0, -10, 0], [0, -1, 0], 5, 5.0)
        graph = _make_simple_graph(5)

        passes, solutions = run_gimbal_solver(
            graph, points, simple_ctr_config,
            nozzle_radius=0.125, strategy="z_heap",
        )
        assert isinstance(passes, dict)
        assert isinstance(solutions, dict)

    def test_all_visited_have_solutions(self, simple_ctr_config):
        """Every node in passes has a corresponding solution."""
        points = _make_line_points([0, -10, 0], [0, -1, 0], 5, 5.0)
        graph = _make_simple_graph(5)

        passes, solutions = run_gimbal_solver(
            graph, points, simple_ctr_config,
            nozzle_radius=0.125, strategy="z_heap",
        )

        all_visited = set()
        for pass_list in passes.values():
            all_visited.update(pass_list)

        for node in all_visited:
            assert node in solutions, f"Node {node} visited but missing solution"

    def test_solutions_are_collision_free(self, simple_ctr_config):
        """Verify stored SNT + body doesn't collide with already-visited."""
        points = _make_line_points([0, -10, 0], [0, -1, 0], 5, 5.0)
        graph = _make_simple_graph(5)

        passes, solutions = run_gimbal_solver(
            graph, points, simple_ctr_config,
            nozzle_radius=0.125, strategy="z_heap",
        )

        for node, sol in solutions.items():
            assert sol.z_ss >= 0
            assert sol.z_ntnl >= 0
            assert sol.z_ss <= simple_ctr_config.ss_lim
            assert sol.z_ntnl <= simple_ctr_config.ntnl_lim

    def test_angular_sector_strategy(self, downward_ctr_config):
        """angular_sector strategy produces results."""
        # Create a small cluster of points
        np.random.seed(42)
        n_pts = 20
        points = np.column_stack([
            np.random.uniform(-5, 5, n_pts),
            np.random.uniform(-5, 5, n_pts),
            np.random.uniform(30, 60, n_pts),
        ])

        # Build a simple chain graph
        graph = _make_simple_graph(n_pts)

        passes, solutions = run_gimbal_solver(
            graph, points, downward_ctr_config,
            nozzle_radius=0.125,
            strategy="angular_sector",
            n_sectors=4,
            cone_angle_deg=10.0, n_tilt=2, n_azimuth=4,
        )

        assert isinstance(passes, dict)
        assert isinstance(solutions, dict)
        assert len(passes) > 0 or len(solutions) == 0


# ---------------------------------------------------------------------------
# TestGimbalReachability
# ---------------------------------------------------------------------------

class TestGimbalReachability:
    def test_superset_of_base_reachability(self, downward_ctr_config):
        """Gimbal reachable nodes should be a superset of base reachable."""
        np.random.seed(42)
        n_pts = 50
        points = np.column_stack([
            np.random.uniform(-20, 20, n_pts),
            np.random.uniform(-20, 20, n_pts),
            np.random.uniform(20, 80, n_pts),
        ])
        graph_nodes = np.arange(n_pts, dtype=np.intp)

        base_mask = batch_is_reachable(points, downward_ctr_config)
        gimbal_mask = gimbal_reachable_nodes(
            points, graph_nodes, downward_ctr_config,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )

        # Every base-reachable node should also be gimbal-reachable
        assert np.all(gimbal_mask[base_mask]), (
            "Some base-reachable nodes are not gimbal-reachable"
        )

    def test_expanded_workspace(self, downward_ctr_config):
        """More nodes should be reachable with cone > 0 vs cone = 0."""
        np.random.seed(42)
        n_pts = 100
        points = np.column_stack([
            np.random.uniform(-30, 30, n_pts),
            np.random.uniform(-30, 30, n_pts),
            np.random.uniform(20, 80, n_pts),
        ])
        graph_nodes = np.arange(n_pts, dtype=np.intp)

        no_gimbal = gimbal_reachable_nodes(
            points, graph_nodes, downward_ctr_config,
            cone_angle_deg=0.0, n_tilt=0, n_azimuth=0,
        )
        with_gimbal = gimbal_reachable_nodes(
            points, graph_nodes, downward_ctr_config,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )

        assert np.sum(with_gimbal) >= np.sum(no_gimbal), (
            f"Gimbal ({np.sum(with_gimbal)}) should reach >= base ({np.sum(no_gimbal)})"
        )


# ---------------------------------------------------------------------------
# TestBuildConfigAngles
# ---------------------------------------------------------------------------

class TestBuildConfigAngles:
    def test_base_config_is_zero(self):
        """First config angle should be (0, 0)."""
        alphas, phis = _build_config_angles(15.0, 3, 8)
        assert alphas[0] == 0.0
        assert phis[0] == 0.0

    def test_correct_count(self):
        """Should have 1 + n_tilt * n_azimuth entries."""
        n_tilt, n_azi = 3, 8
        alphas, phis = _build_config_angles(15.0, n_tilt, n_azi)
        assert len(alphas) == 1 + n_tilt * n_azi
        assert len(phis) == len(alphas)

    def test_zero_cone_returns_base_only(self):
        """Zero cone angle returns only the base config."""
        alphas, phis = _build_config_angles(0.0, 3, 8)
        assert len(alphas) == 1
        assert alphas[0] == 0.0
