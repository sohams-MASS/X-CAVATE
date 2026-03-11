"""Tests for xcavate.viz.plotting."""

import numpy as np
import plotly.graph_objects as go
import pytest

from xcavate.viz.plotting import create_network_plot, create_original_network_plot


@pytest.fixture
def simple_print_passes():
    """3 print passes over 18 synthetic points."""
    return {
        0: [0, 1, 2, 3, 4, 5],
        1: [6, 7, 8, 9, 10, 11],
        2: [12, 13, 14, 15, 16, 17],
    }


@pytest.fixture
def points_18():
    """18 synthetic 3D points (6 per pass)."""
    rng = np.random.RandomState(42)
    return rng.rand(18, 3)


class TestCreateNetworkPlot:
    """Tests for create_network_plot."""

    def test_basic(self, simple_print_passes, points_18):
        """Returns go.Figure with correct trace count and slider steps."""
        fig = create_network_plot(simple_print_passes, points_18, "Test Plot")
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 3
        assert len(fig.layout.sliders[0].steps) == 3

    def test_slider_visibility(self, simple_print_passes, points_18):
        """Progressive-reveal: step i makes traces 0..i visible."""
        fig = create_network_plot(simple_print_passes, points_18, "Test")
        steps = fig.layout.sliders[0].steps

        for i, step in enumerate(steps):
            vis = step.args[0]["visible"]
            assert vis == [j <= i for j in range(3)]

    def test_with_colors(self, simple_print_passes, points_18):
        """Per-pass colors are applied to trace lines."""
        colors = ["red", "green", "blue"]
        fig = create_network_plot(
            simple_print_passes, points_18, "Test", colors=colors
        )
        for idx, trace in enumerate(fig.data):
            assert trace.line.color == colors[idx]

    def test_write_html(self, simple_print_passes, points_18, tmp_path):
        """HTML file is written when output_path provided."""
        out = tmp_path / "test.html"
        fig = create_network_plot(
            simple_print_passes, points_18, "Test", output_path=out
        )
        assert out.exists()
        content = out.read_text()
        assert "plotly" in content.lower()

    def test_lines_only_mode(self, simple_print_passes, points_18):
        """Traces use lines mode without markers."""
        fig = create_network_plot(simple_print_passes, points_18, "Test")
        for trace in fig.data:
            assert trace.mode == "lines"


class TestCreateOriginalNetworkPlot:
    """Tests for create_original_network_plot."""

    def test_basic(self, simple_network_points, coord_num_dict):
        """Correct vessel trace count from coord_num_dict."""
        fig = create_original_network_plot(
            simple_network_points, coord_num_dict, title="Original"
        )
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == len(coord_num_dict)
        assert len(fig.layout.sliders[0].steps) == len(coord_num_dict)

    def test_lines_only_mode(self, simple_network_points, coord_num_dict):
        """Traces use lines mode without markers."""
        fig = create_original_network_plot(
            simple_network_points, coord_num_dict, title="Original"
        )
        for trace in fig.data:
            assert trace.mode == "lines"


class TestCreateNetworkPlotMerged:
    """Tests for create_network_plot_merged."""

    def test_single_trace(self, simple_print_passes, points_18):
        from xcavate.viz.plotting import create_network_plot_merged

        fig = create_network_plot_merged(simple_print_passes, points_18, "Merged")
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1

    def test_nan_separators(self, simple_print_passes, points_18):
        """NaN rows separate passes in the merged trace."""
        from xcavate.viz.plotting import create_network_plot_merged

        fig = create_network_plot_merged(simple_print_passes, points_18, "Merged")
        x = np.array(fig.data[0].x, dtype=float)
        nan_count = np.isnan(x).sum()
        # 3 passes => 2 NaN separators between them
        assert nan_count == 2

    def test_color_mapping(self, simple_print_passes, points_18):
        """Per-point color array maps each point to its pass color."""
        from xcavate.viz.plotting import create_network_plot_merged

        colors = ["red", "green", "blue"]
        fig = create_network_plot_merged(
            simple_print_passes, points_18, "Merged", colors=colors
        )
        line_colors = fig.data[0].line.color
        assert line_colors is not None
        # Total entries = 18 points + 2 NaN separators = 20
        assert len(line_colors) == 20

    def test_no_slider(self, simple_print_passes, points_18):
        """Merged mode has no slider (static view)."""
        from xcavate.viz.plotting import create_network_plot_merged

        fig = create_network_plot_merged(simple_print_passes, points_18, "Merged")
        assert fig.layout.sliders is None or len(fig.layout.sliders) == 0
