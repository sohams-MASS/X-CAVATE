"""Visualization module for vascular network print passes.

Replaces 5 duplicated ~50-line plotting blocks in xcavate.py with a single
parameterized function.
"""

import numpy as np
import plotly.graph_objects as go
from pathlib import Path
from typing import Dict, List, Optional


def create_network_plot(
    print_passes: Dict[int, List[int]],
    points: np.ndarray,
    title: str,
    output_path: Optional[Path] = None,
    colors: Optional[List[str]] = None,
) -> go.Figure:
    """Create interactive 3D Plotly plot with slider for print passes.

    Each print pass is rendered as a separate trace. A slider allows
    progressively revealing passes to visualize the print order.

    Args:
        print_passes: Dict mapping pass_index -> list of node indices.
        points: ndarray of shape (N, 3+) with at least XYZ coordinates.
        title: Plot title displayed at top.
        output_path: If provided, write interactive HTML to this path.
        colors: Optional per-pass color strings (e.g., 'red', 'blue').

    Returns:
        The Plotly Figure object (can be used with st.plotly_chart in Streamlit).
    """
    fig = go.Figure(layout_title_text=title)

    for i in print_passes:
        node_indices = print_passes[i]
        coords = points[node_indices]
        trace_kwargs = dict(
            x=coords[:, 0],
            y=coords[:, 1],
            z=coords[:, 2],
            mode="lines",
            name=f"Pass {i}",
        )
        if colors and i < len(colors):
            trace_kwargs["line"] = dict(color=colors[i])
        fig.add_trace(go.Scatter3d(**trace_kwargs))

    # Slider: progressively reveal passes (vectorized)
    n = len(fig.data)
    vis_matrix = np.tri(n, dtype=bool)
    steps = [
        dict(
            method="update",
            args=[
                {"visible": vis_matrix[i].tolist()},
                {"title": f"{title} <br>[Print Pass: {i}]"},
            ],
        )
        for i in range(n)
    ]

    fig.update_layout(
        sliders=[dict(currentvalue={"prefix": "Print pass: "}, steps=steps)],
        margin=dict(l=30, r=30, t=30, b=30),
        title_x=0.5,
    )
    fig.update_scenes(aspectmode="cube")

    if output_path:
        fig.write_html(str(output_path), include_plotlyjs="cdn")

    return fig


def create_original_network_plot(
    points: np.ndarray,
    coord_num_dict: Dict[int, int],
    title: str = "Original Network",
    output_path: Optional[Path] = None,
) -> go.Figure:
    """Create plot of the original (pre-interpolation) network.

    Each vessel is a separate trace, colored automatically.

    Args:
        points: ndarray of original network coordinates.
        coord_num_dict: Dict mapping vessel_index -> number_of_coordinates.
        title: Plot title.
        output_path: Optional HTML output path.

    Returns:
        Plotly Figure object.
    """
    fig = go.Figure(layout_title_text=title)
    offset = 0

    for vessel_idx in range(len(coord_num_dict)):
        n = coord_num_dict[vessel_idx]
        vessel_pts = points[offset : offset + n]
        fig.add_trace(
            go.Scatter3d(
                x=vessel_pts[:, 0],
                y=vessel_pts[:, 1],
                z=vessel_pts[:, 2],
                mode="lines",
                name=f"Vessel {vessel_idx}",
            )
        )
        offset += n

    # Slider (vectorized)
    num_traces = len(fig.data)
    vis_matrix = np.tri(num_traces, dtype=bool)
    steps = [
        dict(
            method="update",
            args=[
                {"visible": vis_matrix[i].tolist()},
                {"title": f"{title} <br>[Vessel: {i}]"},
            ],
        )
        for i in range(num_traces)
    ]

    fig.update_layout(
        sliders=[dict(currentvalue={"prefix": "Vessel: "}, steps=steps)],
        margin=dict(l=30, r=30, t=30, b=30),
        title_x=0.5,
    )
    fig.update_scenes(aspectmode="cube")

    if output_path:
        fig.write_html(str(output_path), include_plotlyjs="cdn")

    return fig


def create_network_plot_merged(
    print_passes: Dict[int, List[int]],
    points: np.ndarray,
    title: str,
    output_path: Optional[Path] = None,
    colors: Optional[List[str]] = None,
) -> go.Figure:
    """Create a single-trace 3D plot by merging all passes with NaN separators.

    Unlike create_network_plot, this produces one Scatter3d trace instead of
    one per pass (256 draw calls -> 1). Much faster browser rendering, but
    no interactive slider.

    Args:
        print_passes: Dict mapping pass_index -> list of node indices.
        points: ndarray of shape (N, 3+) with at least XYZ coordinates.
        title: Plot title.
        output_path: If provided, write interactive HTML to this path.
        colors: Optional per-pass color strings (length == len(print_passes)).

    Returns:
        Plotly Figure object with a single merged trace.
    """
    pass_keys = sorted(print_passes.keys())
    segments = []
    color_list = [] if colors else None

    for idx, key in enumerate(pass_keys):
        node_indices = print_passes[key]
        if not node_indices:
            continue
        coords = points[node_indices][:, :3]

        if segments:
            # NaN separator between passes
            segments.append(np.array([[np.nan, np.nan, np.nan]]))
            if color_list is not None:
                color_list.append(None)  # placeholder for NaN row

        segments.append(coords)
        if color_list is not None:
            pass_color = colors[idx] if idx < len(colors) else "gray"
            color_list.extend([pass_color] * len(coords))

    if not segments:
        fig = go.Figure(layout_title_text=title)
        fig.update_layout(margin=dict(l=30, r=30, t=30, b=30), title_x=0.5)
        fig.update_scenes(aspectmode="cube")
        if output_path:
            fig.write_html(str(output_path), include_plotlyjs="cdn")
        return fig

    all_coords = np.vstack(segments)

    trace_kwargs = dict(
        x=all_coords[:, 0],
        y=all_coords[:, 1],
        z=all_coords[:, 2],
        mode="lines",
        name="All Passes",
    )

    if color_list is not None:
        # Fill NaN-separator slots with adjacent color
        for i in range(len(color_list)):
            if color_list[i] is None:
                color_list[i] = color_list[i - 1] if i > 0 else "gray"
        trace_kwargs["line"] = dict(color=color_list)

    fig = go.Figure(data=[go.Scatter3d(**trace_kwargs)], layout_title_text=title)
    fig.update_layout(
        margin=dict(l=30, r=30, t=30, b=30),
        title_x=0.5,
    )
    fig.update_scenes(aspectmode="cube")

    if output_path:
        fig.write_html(str(output_path), include_plotlyjs="cdn")

    return fig
