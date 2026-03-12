"""Unit tests for CTR collision detector and oracle."""

import numpy as np
import pytest

from xcavate.core.ctr_kinematics import CTRConfig, _load_calibration
from xcavate.core.ctr_collision import CTRCollisionDetector
from xcavate.core.oracle import (
    GimbalOracleDetector,
    GimbalRealisticDetector,
    OracleDetector,
    make_gimbal_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_ctr_config():
    """CTR at origin, inserting along -Y, bend radius 22mm."""
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


def _make_line_points(start, direction, n_points, spacing):
    """Create n_points along a line from start in the given direction."""
    direction = np.array(direction, dtype=float)
    direction /= np.linalg.norm(direction)
    return np.array([
        np.array(start) + i * spacing * direction
        for i in range(n_points)
    ])


# ---------------------------------------------------------------------------
# Basic interface tests
# ---------------------------------------------------------------------------

class TestCTRCollisionDetectorInterface:
    def test_all_initially_unvisited(self, simple_ctr_config):
        points = _make_line_points([0, -10, 0], [0, -1, 0], 5, 5.0)
        det = CTRCollisionDetector(points, simple_ctr_config, nozzle_radius=0.125)
        assert det.has_unvisited()
        assert len(det.unvisited) == 5

    def test_mark_visited(self, simple_ctr_config):
        points = _make_line_points([0, -10, 0], [0, -1, 0], 5, 5.0)
        det = CTRCollisionDetector(points, simple_ctr_config, nozzle_radius=0.125)
        det.mark_visited(0)
        assert det.is_visited(0)
        assert not det.is_visited(1)
        assert len(det.unvisited) == 4

    def test_mark_all_visited(self, simple_ctr_config):
        points = _make_line_points([0, -10, 0], [0, -1, 0], 3, 5.0)
        det = CTRCollisionDetector(points, simple_ctr_config, nozzle_radius=0.125)
        for i in range(3):
            det.mark_visited(i)
        assert not det.has_unvisited()


# ---------------------------------------------------------------------------
# Collision detection tests
# ---------------------------------------------------------------------------

class TestCTRCollisionDetection:
    def test_reachable_isolated_node_is_valid(self, simple_ctr_config):
        """A single reachable node with no neighbors should be valid."""
        points = np.array([[0.0, -20.0, 0.0]])
        det = CTRCollisionDetector(points, simple_ctr_config, nozzle_radius=0.125)
        assert det.is_valid(0)

    def test_unreachable_node_is_invalid(self, simple_ctr_config):
        """A node far outside the workspace should be invalid."""
        points = np.array([[500.0, 500.0, 500.0]])
        det = CTRCollisionDetector(points, simple_ctr_config, nozzle_radius=0.125)
        assert not det.is_valid(0)

    def test_visited_node_is_invalid(self, simple_ctr_config):
        points = np.array([[0.0, -20.0, 0.0], [0.0, -25.0, 0.0]])
        det = CTRCollisionDetector(points, simple_ctr_config, nozzle_radius=0.125)
        det.mark_visited(0)
        assert not det.is_valid(0)

    def test_shaft_collision_with_non_neighbor(self, simple_ctr_config):
        """A non-neighbor node sitting on the SS tube shaft (far from the tip)
        should block the candidate."""
        # With radius=47, use z_ss=60 so we get enough body samples for dense
        # coverage. n_arc_samples=40 gives spacing ~1.8mm.
        # Point 0 is the target at -60mm along insertion axis.
        # Point 1 is at -30mm — midway along the shaft, NOT a graph neighbor.
        points = np.array([
            [0.0, -60.0, 0.0],   # target
            [0.05, -30.0, 0.0],  # on shaft, NOT a graph neighbor
        ])
        # No graph → no neighbor exemptions
        det = CTRCollisionDetector(
            points, simple_ctr_config, nozzle_radius=1.0, n_arc_samples=40,
        )
        assert not det.is_valid(0)

    def test_graph_neighbor_exempted_from_shaft_collision(self, simple_ctr_config):
        """A graph neighbor on the shaft should NOT block the candidate."""
        points = np.array([
            [0.0, -30.0, 0.0],   # target (node 0)
            [0.05, -15.0, 0.0],  # on shaft, but IS a graph neighbor of 0
        ])
        graph = {0: [0, 1], 1: [1, 0]}  # nodes 0 and 1 are neighbors
        det = CTRCollisionDetector(
            points, simple_ctr_config, nozzle_radius=1.0, graph=graph, n_arc_samples=20,
        )
        # Should be valid because node 1 is a graph neighbor → exempt
        assert det.is_valid(0)

    def test_well_separated_nodes_are_valid(self, simple_ctr_config):
        """Two nodes far apart in different directions should not block each other."""
        points = np.array([
            [0.0, -20.0, 0.0],
            [50.0, -20.0, 50.0],
        ])
        det = CTRCollisionDetector(
            points, simple_ctr_config, nozzle_radius=0.125, n_arc_samples=10,
        )
        assert det.is_valid(0)

    def test_body_drag_blocks_through_visited(self, simple_ctr_config):
        """After marking a node as visited, reaching another node whose body
        passes through it should be blocked (body-drag check)."""
        # With radius=47, use longer distances and more arc samples for dense
        # body coverage so the visited node falls within a body sample.
        points = np.array([
            [0.05, -30.0, 0.0],  # will be visited first — on the shaft
            [0.0, -60.0, 0.0],   # target whose SS tube passes through node 0
        ])
        det = CTRCollisionDetector(
            points, simple_ctr_config, nozzle_radius=1.0, n_arc_samples=40,
        )
        det.mark_visited(0)
        det._rebuild_trees()
        # Node 1's needle body passes through the visited node 0
        assert not det.is_valid(1)

    def test_tip_proximity_exclusion(self, simple_ctr_config):
        """Nodes very close to the candidate (near the tip) should NOT block it,
        thanks to tip-proximity exclusion."""
        # Two nodes very close together at the same depth
        points = np.array([
            [0.0, -20.0, 0.0],    # target
            [0.2, -20.1, 0.0],    # very close to target (within tip exclusion)
        ])
        det = CTRCollisionDetector(
            points, simple_ctr_config, nozzle_radius=1.0, n_arc_samples=10,
        )
        # Node 1 is near the tip → excluded from collision check
        assert det.is_valid(0)


# ---------------------------------------------------------------------------
# Tree rebuild
# ---------------------------------------------------------------------------

class TestTreeRebuild:
    def test_rebuild_after_interval(self, simple_ctr_config):
        points = _make_line_points([0, -10, 0], [0, -1, 0], 10, 3.0)
        det = CTRCollisionDetector(
            points, simple_ctr_config, nozzle_radius=0.125, rebuild_interval=3,
        )
        for i in range(3):
            det.mark_visited(i)
        assert det._removals_since_rebuild == 0


# ---------------------------------------------------------------------------
# OracleDetector tests
# ---------------------------------------------------------------------------

class TestOracleDetector:
    def test_oracle_skips_body_drag(self, simple_ctr_config):
        """OracleDetector should NOT block on visited nodes (body-drag skipped)."""
        points = np.array([
            [0.05, -30.0, 0.0],  # will be visited first — on the shaft
            [0.0, -60.0, 0.0],   # target whose SS tube passes through node 0
        ])
        oracle = OracleDetector(
            points, simple_ctr_config, nozzle_radius=1.0, n_arc_samples=40,
        )
        oracle.mark_visited(0)
        oracle._rebuild_trees()
        # Regular detector would block here; oracle should allow it
        assert oracle.is_valid(1)

    def test_oracle_still_checks_shaft_collision(self, simple_ctr_config):
        """OracleDetector should still block on unvisited shaft collisions."""
        points = np.array([
            [0.0, -60.0, 0.0],   # target
            [0.05, -30.0, 0.0],  # on shaft, NOT a graph neighbor
        ])
        oracle = OracleDetector(
            points, simple_ctr_config, nozzle_radius=1.0, n_arc_samples=40,
        )
        # Node 1 is unvisited and on the shaft → should still block
        assert not oracle.is_valid(0)

    def test_oracle_allows_more_nodes_than_regular(self, simple_ctr_config):
        """Oracle (no body-drag) should visit >= as many nodes as regular detector."""
        points = _make_line_points([0, -10, 0], [0, -1, 0], 5, 5.0)
        graph = {i: [i] + ([i-1] if i > 0 else []) + ([i+1] if i < 4 else []) for i in range(5)}

        # Regular detector
        regular = CTRCollisionDetector(
            points, simple_ctr_config, nozzle_radius=0.125, graph=graph,
        )
        regular_valid = sum(1 for i in range(5) if regular.is_valid(i))

        # Oracle detector
        oracle = OracleDetector(
            points, simple_ctr_config, nozzle_radius=0.125, graph=graph,
        )
        oracle_valid = sum(1 for i in range(5) if oracle.is_valid(i))

        # Before any visits, they should be identical (body-drag has no effect)
        assert oracle_valid == regular_valid


# ---------------------------------------------------------------------------
# Gimbal tests
# ---------------------------------------------------------------------------

class TestMakeGimbalConfig:
    def test_zero_alpha_returns_same_config(self, simple_ctr_config):
        """alpha=0 should return the original config object."""
        result = make_gimbal_config(simple_ctr_config, alpha=0.0, phi=0.0)
        assert result is simple_ctr_config

    def test_preserves_calibration(self, simple_ctr_config):
        """Calibration functions should be shared (same objects)."""
        tilted = make_gimbal_config(simple_ctr_config, alpha=0.2, phi=0.0)
        assert tilted.f_xr_yr is simple_ctr_config.f_xr_yr
        assert tilted.f_yr_ntnlss is simple_ctr_config.f_yr_ntnlss
        assert tilted.x_val is simple_ctr_config.x_val

    def test_preserves_position_and_limits(self, simple_ctr_config):
        """X, radius, ss_lim, ntnl_lim should be unchanged."""
        tilted = make_gimbal_config(simple_ctr_config, alpha=0.3, phi=1.0)
        np.testing.assert_array_equal(tilted.X, simple_ctr_config.X)
        assert tilted.radius == simple_ctr_config.radius
        assert tilted.ss_lim == simple_ctr_config.ss_lim
        assert tilted.ntnl_lim == simple_ctr_config.ntnl_lim

    def test_r_hat_is_tilted(self, simple_ctr_config):
        """Tilted R_hat should differ from original by the requested angle."""
        alpha = 0.25  # ~14.3 degrees
        tilted = make_gimbal_config(simple_ctr_config, alpha=alpha, phi=0.0)
        cos_angle = np.dot(tilted.R_hat, simple_ctr_config.R_hat)
        np.testing.assert_allclose(cos_angle, np.cos(alpha), atol=1e-10)

    def test_r_hat_remains_unit(self, simple_ctr_config):
        """Tilted R_hat should be a unit vector."""
        tilted = make_gimbal_config(simple_ctr_config, alpha=0.3, phi=2.5)
        np.testing.assert_allclose(np.linalg.norm(tilted.R_hat), 1.0, atol=1e-12)

    def test_n_hat_perpendicular_to_r_hat(self, simple_ctr_config):
        """n_hat should be perpendicular to the new R_hat."""
        tilted = make_gimbal_config(simple_ctr_config, alpha=0.2, phi=1.0)
        np.testing.assert_allclose(
            np.dot(tilted.n_hat, tilted.R_hat), 0.0, atol=1e-12,
        )


class TestGimbalOracleDetector:
    def test_untilted_matches_oracle(self, simple_ctr_config):
        """At cone_angle=0 the gimbal oracle should match the plain oracle."""
        points = np.array([
            [0.0, -20.0, 0.0],
            [0.0, -40.0, 0.0],
        ])
        oracle = OracleDetector(
            points, simple_ctr_config, nozzle_radius=0.125, n_arc_samples=20,
        )
        gimbal = GimbalOracleDetector(
            points, simple_ctr_config, nozzle_radius=0.125, n_arc_samples=20,
            cone_angle_deg=0.0,
        )
        for i in range(len(points)):
            assert gimbal.is_valid(i) == oracle.is_valid(i)

    def test_rescues_blocked_node(self, simple_ctr_config):
        """A node blocked by a shaft collision at alpha=0 should be rescued
        by a tilted insertion angle."""
        # Node 0 (target) is deep along -Y. Node 1 sits on the shaft (midway),
        # NOT a graph neighbor → shaft collision blocks at alpha=0.
        points = np.array([
            [0.0, -60.0, 0.0],   # target
            [0.05, -30.0, 0.0],  # blocker on shaft
        ])
        # Confirm blocked at alpha=0
        oracle = OracleDetector(
            points, simple_ctr_config, nozzle_radius=1.0, n_arc_samples=40,
        )
        assert not oracle.is_valid(0), "Should be blocked without gimbal"

        # With gimbal, a tilted angle should bypass the blocker
        gimbal = GimbalOracleDetector(
            points, simple_ctr_config, nozzle_radius=1.0, n_arc_samples=40,
            cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
        )
        assert gimbal.is_valid(0), "Gimbal should rescue the blocked node"


class TestGimbalRealisticDetector:
    def test_checks_body_drag(self, simple_ctr_config):
        """The realistic detector should reject a node when a visited node
        sits on the body path, even if a gimbal angle clears shaft collisions."""
        # Node 0 is visited. Node 1's body passes through node 0.
        # Even with gimbal, if the visited node blocks all angles,
        # the realistic detector should reject.
        points = np.array([
            [0.05, -30.0, 0.0],  # will be visited
            [0.0, -60.0, 0.0],   # target — body passes through node 0
        ])
        realistic = GimbalRealisticDetector(
            points, simple_ctr_config, nozzle_radius=1.0, n_arc_samples=40,
            cone_angle_deg=0.0,  # no tilt — must hit the visited node
        )
        realistic.mark_visited(0)
        realistic._rebuild_trees()
        assert not realistic.is_valid(1)

    def test_oracle_allows_what_realistic_rejects(self, simple_ctr_config):
        """The gimbal oracle (no body-drag) should accept a node that the
        gimbal realistic rejects due to body-drag."""
        points = np.array([
            [0.05, -30.0, 0.0],  # will be visited
            [0.0, -60.0, 0.0],   # target
        ])
        oracle = GimbalOracleDetector(
            points, simple_ctr_config, nozzle_radius=1.0, n_arc_samples=40,
            cone_angle_deg=0.0,
        )
        oracle.mark_visited(0)
        oracle._rebuild_trees()
        # Oracle skips body-drag, so node 1 should be valid
        assert oracle.is_valid(1)

        realistic = GimbalRealisticDetector(
            points, simple_ctr_config, nozzle_radius=1.0, n_arc_samples=40,
            cone_angle_deg=0.0,
        )
        realistic.mark_visited(0)
        realistic._rebuild_trees()
        # Realistic checks body-drag, so node 1 should be rejected
        assert not realistic.is_valid(1)
