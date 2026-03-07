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
            mode="lines+markers",
            marker=dict(size=2),
            name=f"Pass {i}",
        )
        if colors and i < len(colors):
            trace_kwargs["line"] = dict(color=colors[i])
        fig.add_trace(go.Scatter3d(**trace_kwargs))

    # Slider: progressively reveal passes
    steps = []
    for i in range(len(fig.data)):
        step = dict(
            method="update",
            args=[
                {"visible": [j <= i for j in range(len(fig.data))]},
                {"title": f"{title} <br>[Print Pass: {i}]"},
            ],
        )
        steps.append(step)

    fig.update_layout(
        sliders=[dict(currentvalue={"prefix": "Print pass: "}, steps=steps)],
        margin=dict(l=30, r=30, t=30, b=30),
        title_x=0.5,
    )
    fig.update_scenes(aspectmode="cube")

    if output_path:
        fig.write_html(str(output_path))

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
                mode="lines+markers",
                marker=dict(size=2),
                name=f"Vessel {vessel_idx}",
            )
        )
        offset += n

    # Slider
    steps = []
    for i in range(len(fig.data)):
        step = dict(
            method="update",
            args=[
                {"visible": [j <= i for j in range(len(fig.data))]},
                {"title": f"{title} <br>[Vessel: {i}]"},
            ],
        )
        steps.append(step)

    fig.update_layout(
        sliders=[dict(currentvalue={"prefix": "Vessel: "}, steps=steps)],
        margin=dict(l=30, r=30, t=30, b=30),
        title_x=0.5,
    )
    fig.update_scenes(aspectmode="cube")

    if output_path:
        fig.write_html(str(output_path))

    return fig
