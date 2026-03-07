"""Tests for xcavate.core.preprocessing."""

import numpy as np
import pytest

from xcavate.core.preprocessing import interpolate_network


class TestInterpolateNetwork:
    """Tests for the interpolate_network function."""

    def test_interpolation_densifies(self, simple_network_points, coord_num_dict):
        """Interpolation should produce more points when spacing exceeds nozzle_radius."""
        nozzle_radius = 0.125  # half of 0.25 mm -- smaller than the 1.0 mm spacing
        num_columns = 3

        result = interpolate_network(
            simple_network_points, coord_num_dict, nozzle_radius, num_columns
        )

        # Original has 18 points; with 1.0 mm spacing and 0.125 nozzle_radius
        # each segment should be subdivided, so we expect many more points.
        assert result.shape[0] > simple_network_points.shape[0]

    def test_interpolation_preserves_endpoints(
        self, simple_network_points, coord_num_dict
    ):
        """First and last points of each vessel should remain after interpolation."""
        nozzle_radius = 0.125
        num_columns = 3

        result = interpolate_network(
            simple_network_points, coord_num_dict, nozzle_radius, num_columns
        )

        # The xyz columns of the result (ignoring the appended flag column)
        result_xyz = result[:, :3]

        # Vessel 0: first point (0,0,0), last point (0,0,5)
        # Vessel 1: first point (0,0,5), last point (2,0,10)
        # Vessel 2: first point (0,0,5), last point (-2,0,10)
        expected_endpoints = [
            simple_network_points[0],    # vessel 0 start
            simple_network_points[5],    # vessel 0 end
            simple_network_points[6],    # vessel 1 start
            simple_network_points[11],   # vessel 1 end
            simple_network_points[12],   # vessel 2 start
            simple_network_points[17],   # vessel 2 end
        ]

        for ep in expected_endpoints:
            # Check that at least one row in result matches this endpoint
            diffs = np.linalg.norm(result_xyz - ep, axis=1)
            assert np.min(diffs) < 1e-10, f"Endpoint {ep} not found in result"

    def test_no_interpolation_when_dense_enough(self, coord_num_dict):
        """If points are already closer than nozzle_radius, count should be preserved."""
        # Create a network with very small spacing (0.01 mm between consecutive points)
        v0 = np.array([[0.0, 0.0, i * 0.01] for i in range(6)])
        v1 = np.array([[0.0, 0.0, 0.05 + i * 0.01] for i in range(6)])
        v2 = np.array([[0.0, 0.0, 0.10 + i * 0.01] for i in range(6)])
        points = np.vstack([v0, v1, v2])

        nozzle_radius = 1.0  # much larger than the 0.01 spacing
        num_columns = 3

        result = interpolate_network(points, coord_num_dict, nozzle_radius, num_columns)

        # No interpolation needed, so the number of rows should equal the original
        assert result.shape[0] == points.shape[0]

    def test_flag_column_added(self, simple_network_points, coord_num_dict):
        """Output should have one more column than input, with 500 flags at vessel starts."""
        nozzle_radius = 0.125
        num_columns = 3

        result = interpolate_network(
            simple_network_points, coord_num_dict, nozzle_radius, num_columns
        )

        # Should have 4 columns (3 original + 1 flag)
        assert result.shape[1] == num_columns + 1

        # Flag column is the last column
        flag_col = result[:, -1]

        # There should be exactly 3 vessel starts flagged with 500
        vessel_start_flags = np.sum(flag_col == 500.0)
        assert vessel_start_flags == len(coord_num_dict)
