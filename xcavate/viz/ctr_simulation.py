"""CTR needle simulation: animated gimbal + SS + nitinol visualization.

Computes needle geometry from actuator values and builds Plotly animations
showing the CTR mechanism moving node-by-node during printing.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import plotly.graph_objects as go

from xcavate.core.gimbal_solver import GimbalNodeSolution


# ---------------------------------------------------------------------------
# Forward kinematics helpers
# ---------------------------------------------------------------------------

def compute_needle_geometry(
    X: np.ndarray,
    R_hat: np.ndarray,
    n_hat: np.ndarray,
    theta_match: float,
    z_ss: float,
    z_ntnl: float,
    theta: float,
    radius: float,
    n_ss_samples: int = 12,
    n_arc_samples: int = 20,
) -> dict:
    """Compute 3D geometry of the full CTR needle for visualization.

    Returns dict with keys:
        'base': (3,) base point
        'ss_tip': (3,) end of SS tube
        'ss_line': (n_ss, 3) SS tube centerline points
        'arc_line': (n_arc, 3) nitinol arc centerline points
        'tip': (3,) final tip position
    """
    # SS straight section
    n_ss = max(2, n_ss_samples)
    ss_positions = np.linspace(0, z_ss, n_ss)
    ss_line = X + ss_positions[:, None] * R_hat
    ss_tip = ss_line[-1]

    # Nitinol arc
    ntnl_extension = z_ntnl - z_ss
    if ntnl_extension > 0:
        # Bend direction via simplified Rodrigues (R_hat perp n_hat)
        Kn = np.cross(R_hat, n_hat)
        a = theta_match + theta
        bend_dir = n_hat * np.cos(a) + Kn * np.sin(a)

        max_angle = ntnl_extension / radius
        arc_angles = np.linspace(0, max_angle, n_arc_samples + 1)[1:]
        arc_line = (
            ss_tip
            + radius * np.sin(arc_angles)[:, None] * R_hat
            + radius * (1 - np.cos(arc_angles))[:, None] * bend_dir
        )
        tip = arc_line[-1]
    else:
        arc_line = np.empty((0, 3))
        tip = ss_tip.copy()

    return {
        "base": X.copy(),
        "ss_tip": ss_tip,
        "ss_line": ss_line,
        "arc_line": arc_line,
        "tip": tip,
    }


def compute_gimbal_frame(
    X: np.ndarray,
    R_hat_base: np.ndarray,
    n_hat_base: np.ndarray,
    alpha: float,
    phi: float,
    frame_length: float = 15.0,
) -> dict:
    """Compute the gimbal tilt frame for visualization.

    Returns dict with keys:
        'R_hat_tilted': (3,) tilted insertion direction
        'n_hat_tilted': (3,) tilted bend normal
        'theta_match_tilted': float
        'direction_line': (2, 3) line segment from base along R_hat_tilted
        'base_direction_line': (2, 3) line segment from base along untilted R_hat_base
    """
    if alpha == 0.0:
        R_hat_tilted = R_hat_base.copy()
    else:
        # Rodrigues rotation of R_hat about tilt axis
        b_hat = np.cross(R_hat_base, n_hat_base)
        b_hat /= np.linalg.norm(b_hat)
        tilt_axis = np.cos(phi) * n_hat_base + np.sin(phi) * b_hat
        tilt_axis /= np.linalg.norm(tilt_axis)

        K = np.array([
            [0, -tilt_axis[2], tilt_axis[1]],
            [tilt_axis[2], 0, -tilt_axis[0]],
            [-tilt_axis[1], tilt_axis[0], 0],
        ])
        R_tilt = np.eye(3) + np.sin(alpha) * K + (1 - np.cos(alpha)) * (K @ K)
        R_hat_tilted = R_tilt @ R_hat_base
        R_hat_tilted /= np.linalg.norm(R_hat_tilted)

    # Compute new n_hat and theta_match for tilted config
    n_hat_tilted = _perpendicular_unit(R_hat_tilted)
    theta_match_tilted = float(np.arctan2(
        np.dot(np.cross(n_hat_tilted, np.array([1.0, 0.0, 0.0])), R_hat_tilted),
        np.dot(n_hat_tilted, np.array([1.0, 0.0, 0.0])),
    ))

    direction_line = np.array([X, X + frame_length * R_hat_tilted])
    base_direction_line = np.array([X, X + frame_length * R_hat_base])

    return {
        "R_hat_tilted": R_hat_tilted,
        "n_hat_tilted": n_hat_tilted,
        "theta_match_tilted": theta_match_tilted,
        "direction_line": direction_line,
        "base_direction_line": base_direction_line,
    }


def _perpendicular_unit(v: np.ndarray) -> np.ndarray:
    """Return a unit vector perpendicular to v."""
    abs_v = np.abs(v)
    if abs_v[0] <= abs_v[1] and abs_v[0] <= abs_v[2]:
        candidate = np.array([1.0, 0.0, 0.0])
    elif abs_v[1] <= abs_v[2]:
        candidate = np.array([0.0, 1.0, 0.0])
    else:
        candidate = np.array([0.0, 0.0, 1.0])
    perp = np.cross(v, candidate)
    return perp / np.linalg.norm(perp)


# ---------------------------------------------------------------------------
# Animation builder
# ---------------------------------------------------------------------------

def create_ctr_simulation(
    print_pass: List[int],
    points: np.ndarray,
    gimbal_solutions: Dict[int, GimbalNodeSolution],
    ctr_base: np.ndarray,
    R_hat_base: np.ndarray,
    radius: float,
    n_hat_base: np.ndarray,
    theta_match: float,
    max_frames: int = 200,
    trail_max_points: int = 20000,
) -> go.Figure:
    """Build a Plotly animation of the CTR needle printing one pass.

    Parameters
    ----------
    print_pass : list of int
        Node indices for one pass.
    points : ndarray (N, 3+)
        Full coordinate array.
    gimbal_solutions : dict[int, GimbalNodeSolution]
        Per-node solved actuator values and gimbal config.
    ctr_base : ndarray (3,)
        CTR base position X.
    R_hat_base : ndarray (3,)
        Base insertion direction.
    radius : float
        Bend radius.
    n_hat_base : ndarray (3,)
        Base bend normal.
    theta_match : float
        Base alignment angle.
    max_frames : int
        Maximum animation frames (subsamples the pass).
    trail_max_points : int
        Maximum points in the printed trail trace.

    Returns
    -------
    go.Figure
        Animated Plotly figure with play/pause and slider.
    """
    n_nodes = len(print_pass)
    if n_nodes == 0:
        return go.Figure()

    # Subsample to max_frames (preserve first and last)
    if n_nodes <= max_frames:
        frame_indices = list(range(n_nodes))
    else:
        step = n_nodes / max_frames
        frame_indices = [int(i * step) for i in range(max_frames)]
        if frame_indices[-1] != n_nodes - 1:
            frame_indices[-1] = n_nodes - 1

    # Network ghost: all points as tiny gray dots
    all_pts = points[:, :3]
    # Subsample ghost if too many points
    ghost_max = 10000
    if len(all_pts) > ghost_max:
        ghost_idx = np.linspace(0, len(all_pts) - 1, ghost_max, dtype=int)
        ghost_pts = all_pts[ghost_idx]
    else:
        ghost_pts = all_pts

    # Axis ranges from network extents + padding
    pad = 5.0
    x_min, x_max = float(all_pts[:, 0].min()) - pad, float(all_pts[:, 0].max()) + pad
    y_min, y_max = float(all_pts[:, 1].min()) - pad, float(all_pts[:, 1].max()) + pad
    z_min, z_max = float(all_pts[:, 2].min()) - pad, float(all_pts[:, 2].max()) + pad
    # Include CTR base in range
    for i, (lo, hi) in enumerate([(x_min, x_max), (y_min, y_max), (z_min, z_max)]):
        v = float(ctr_base[i])
        if v < lo:
            if i == 0: x_min = v - pad
            elif i == 1: y_min = v - pad
            else: z_min = v - pad
        if v > hi:
            if i == 0: x_max = v + pad
            elif i == 1: y_max = v + pad
            else: z_max = v + pad

    # Build initial (empty) traces for the first frame
    # Trace 0: Network ghost (static)
    # Trace 1: CTR Base marker (static)
    # Trace 2: SS Tube line
    # Trace 3: Nitinol Arc line
    # Trace 4: Tip Marker
    # Trace 5: Printed Trail
    # Trace 6: Gimbal Direction line

    # Compute first frame geometry
    first_node = print_pass[0]
    first_geom, first_gimbal = _compute_frame_data(
        first_node, gimbal_solutions, ctr_base, R_hat_base,
        n_hat_base, theta_match, radius,
    )

    traces = [
        # 0: Network ghost
        go.Scatter3d(
            x=ghost_pts[:, 0], y=ghost_pts[:, 1], z=ghost_pts[:, 2],
            mode="markers",
            marker=dict(size=1, color="gray", opacity=0.3),
            name="Network",
            hoverinfo="skip",
        ),
        # 1: CTR Base
        go.Scatter3d(
            x=[float(ctr_base[0])], y=[float(ctr_base[1])], z=[float(ctr_base[2])],
            mode="markers",
            marker=dict(size=8, color="orange", symbol="diamond"),
            name="CTR Base",
        ),
        # 2: SS Tube
        go.Scatter3d(
            x=first_geom["ss_line"][:, 0], y=first_geom["ss_line"][:, 1],
            z=first_geom["ss_line"][:, 2],
            mode="lines",
            line=dict(color="orange", width=6),
            name="SS Tube",
        ),
        # 3: Nitinol Arc
        go.Scatter3d(
            x=first_geom["arc_line"][:, 0] if len(first_geom["arc_line"]) > 0 else [],
            y=first_geom["arc_line"][:, 1] if len(first_geom["arc_line"]) > 0 else [],
            z=first_geom["arc_line"][:, 2] if len(first_geom["arc_line"]) > 0 else [],
            mode="lines",
            line=dict(color="dodgerblue", width=6),
            name="Nitinol Arc",
        ),
        # 4: Tip Marker
        go.Scatter3d(
            x=[float(first_geom["tip"][0])],
            y=[float(first_geom["tip"][1])],
            z=[float(first_geom["tip"][2])],
            mode="markers",
            marker=dict(size=6, color="lime"),
            name="Tip",
        ),
        # 5: Printed Trail
        go.Scatter3d(
            x=[], y=[], z=[],
            mode="lines+markers",
            line=dict(color="red", width=3),
            marker=dict(size=2, color="red"),
            name="Printed Trail",
        ),
        # 6: Gimbal Direction (tilted)
        go.Scatter3d(
            x=first_gimbal["direction_line"][:, 0],
            y=first_gimbal["direction_line"][:, 1],
            z=first_gimbal["direction_line"][:, 2],
            mode="lines",
            line=dict(color="cyan", width=4),
            name="Gimbal Direction",
        ),
        # 7: Base Direction (untilted reference)
        go.Scatter3d(
            x=first_gimbal["base_direction_line"][:, 0],
            y=first_gimbal["base_direction_line"][:, 1],
            z=first_gimbal["base_direction_line"][:, 2],
            mode="lines",
            line=dict(color="gray", width=2, dash="dot"),
            name="Base Direction",
        ),
    ]

    fig = go.Figure(data=traces)

    # Build frames
    frames = []
    for k_idx, k in enumerate(frame_indices):
        node = print_pass[k]
        geom, gimbal = _compute_frame_data(
            node, gimbal_solutions, ctr_base, R_hat_base,
            n_hat_base, theta_match, radius,
        )

        # Trail: all pass nodes up to current step
        trail_nodes = print_pass[:k + 1]
        if len(trail_nodes) > trail_max_points:
            trail_step = max(1, len(trail_nodes) // trail_max_points)
            trail_nodes = trail_nodes[::trail_step]
            if trail_nodes[-1] != print_pass[k]:
                trail_nodes.append(print_pass[k])
        trail_pts = points[trail_nodes, :3]

        # Color trail by config_idx
        sol = gimbal_solutions.get(node)
        config_label = ""
        if sol is not None:
            config_label = (
                f"Config {sol.config_idx} | "
                f"\u03b1={np.degrees(sol.alpha):.1f}\u00b0 "
                f"\u03c6={np.degrees(sol.phi):.1f}\u00b0"
            )

        # Only include dynamic traces (indices 2-7); skip static ghost/base
        frame_data = [
            # 2: SS Tube
            go.Scatter3d(
                x=geom["ss_line"][:, 0], y=geom["ss_line"][:, 1],
                z=geom["ss_line"][:, 2],
            ),
            # 3: Nitinol Arc
            go.Scatter3d(
                x=geom["arc_line"][:, 0] if len(geom["arc_line"]) > 0 else [],
                y=geom["arc_line"][:, 1] if len(geom["arc_line"]) > 0 else [],
                z=geom["arc_line"][:, 2] if len(geom["arc_line"]) > 0 else [],
            ),
            # 4: Tip
            go.Scatter3d(
                x=[float(geom["tip"][0])],
                y=[float(geom["tip"][1])],
                z=[float(geom["tip"][2])],
            ),
            # 5: Printed Trail
            go.Scatter3d(
                x=trail_pts[:, 0], y=trail_pts[:, 1], z=trail_pts[:, 2],
            ),
            # 6: Gimbal Direction (tilted)
            go.Scatter3d(
                x=gimbal["direction_line"][:, 0],
                y=gimbal["direction_line"][:, 1],
                z=gimbal["direction_line"][:, 2],
            ),
            # 7: Base Direction (untilted reference)
            go.Scatter3d(
                x=gimbal["base_direction_line"][:, 0],
                y=gimbal["base_direction_line"][:, 1],
                z=gimbal["base_direction_line"][:, 2],
            ),
        ]

        frames.append(go.Frame(
            data=frame_data,
            traces=[2, 3, 4, 5, 6, 7],  # only update dynamic traces
            name=str(k),
            layout=go.Layout(
                title_text=f"Node {node} ({k}/{n_nodes}) {config_label}",
            ),
        ))

    fig.frames = frames

    # Slider
    slider_steps = [
        dict(
            args=[[str(frame_indices[i])],
                  dict(frame=dict(duration=50, redraw=True), mode="immediate")],
            label=str(frame_indices[i]),
            method="animate",
        )
        for i in range(len(frame_indices))
    ]

    fig.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                showactive=False,
                x=0.05, y=0.05,
                xanchor="left", yanchor="bottom",
                buttons=[
                    dict(
                        label="Play",
                        method="animate",
                        args=[None, dict(
                            frame=dict(duration=50, redraw=True),
                            fromcurrent=True,
                            transition=dict(duration=0),
                        )],
                    ),
                    dict(
                        label="Pause",
                        method="animate",
                        args=[[None], dict(
                            frame=dict(duration=0, redraw=False),
                            mode="immediate",
                            transition=dict(duration=0),
                        )],
                    ),
                ],
            ),
        ],
        sliders=[dict(
            active=0,
            currentvalue=dict(prefix="Step: "),
            steps=slider_steps,
            x=0.05, len=0.9,
            xanchor="left",
            y=0, yanchor="top",
        )],
        scene=dict(
            xaxis=dict(range=[x_min, x_max]),
            yaxis=dict(range=[y_min, y_max]),
            zaxis=dict(range=[z_min, z_max]),
            aspectmode="data",
        ),
        margin=dict(l=30, r=30, t=50, b=80),
        title_text=f"CTR Needle Simulation ({len(frame_indices)} frames)",
    )

    return fig


def create_ctr_simulation_all_passes(
    print_passes: Dict[int, List[int]],
    points: np.ndarray,
    gimbal_solutions: Dict[int, GimbalNodeSolution],
    ctr_base: np.ndarray,
    R_hat_base: np.ndarray,
    radius: float,
    n_hat_base: np.ndarray,
    theta_match: float,
    max_frames: int = 300,
    trail_max_points: int = 20000,
) -> go.Figure:
    """Build a Plotly animation of the CTR needle printing ALL passes.

    Concatenates passes in order, with retract frames between passes.
    Each frame shows the needle at the current node, the accumulated trail
    colored by pass, and a pass counter annotation.

    Parameters
    ----------
    print_passes : dict[int, list[int]]
        All print passes {pass_idx: [node_indices]}.
    points, gimbal_solutions, ctr_base, R_hat_base, radius, n_hat_base, theta_match
        Same as ``create_ctr_simulation``.
    max_frames : int
        Maximum animation frames across all passes.
    trail_max_points : int
        Maximum points in the accumulated trail.

    Returns
    -------
    go.Figure
    """
    pass_keys = sorted(print_passes.keys())
    if not pass_keys:
        return go.Figure()

    # Build flat sequence: list of (node, pass_idx) in print order
    flat_sequence: List[tuple] = []
    for pk in pass_keys:
        for node in print_passes[pk]:
            flat_sequence.append((node, pk))

    n_total = len(flat_sequence)
    if n_total == 0:
        return go.Figure()

    # Subsample
    if n_total <= max_frames:
        frame_indices = list(range(n_total))
    else:
        step = n_total / max_frames
        frame_indices = [int(i * step) for i in range(max_frames)]
        if frame_indices[-1] != n_total - 1:
            frame_indices[-1] = n_total - 1

    # Ghost points
    all_pts = points[:, :3]
    ghost_max = 10000
    if len(all_pts) > ghost_max:
        ghost_idx = np.linspace(0, len(all_pts) - 1, ghost_max, dtype=int)
        ghost_pts = all_pts[ghost_idx]
    else:
        ghost_pts = all_pts

    # Axis ranges
    pad = 5.0
    x_min, x_max = float(all_pts[:, 0].min()) - pad, float(all_pts[:, 0].max()) + pad
    y_min, y_max = float(all_pts[:, 1].min()) - pad, float(all_pts[:, 1].max()) + pad
    z_min, z_max = float(all_pts[:, 2].min()) - pad, float(all_pts[:, 2].max()) + pad
    for i, (lo, hi) in enumerate([(x_min, x_max), (y_min, y_max), (z_min, z_max)]):
        v = float(ctr_base[i])
        if v < lo:
            if i == 0: x_min = v - pad
            elif i == 1: y_min = v - pad
            else: z_min = v - pad
        if v > hi:
            if i == 0: x_max = v + pad
            elif i == 1: y_max = v + pad
            else: z_max = v + pad

    # Assign a color per pass using a colorscale
    n_passes = len(pass_keys)
    _cmap = [
        "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
        "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990",
        "#dcbeff", "#9A6324", "#800000", "#aaffc3", "#808000",
        "#ffd8b1", "#000075", "#a9a9a9",
    ]
    pass_color = {pk: _cmap[i % len(_cmap)] for i, pk in enumerate(pass_keys)}

    # First frame data
    first_node, first_pass = flat_sequence[0]
    first_geom, first_gimbal = _compute_frame_data(
        first_node, gimbal_solutions, ctr_base, R_hat_base,
        n_hat_base, theta_match, radius,
    )

    traces = [
        go.Scatter3d(
            x=ghost_pts[:, 0], y=ghost_pts[:, 1], z=ghost_pts[:, 2],
            mode="markers", marker=dict(size=1, color="gray", opacity=0.3),
            name="Network", hoverinfo="skip",
        ),
        go.Scatter3d(
            x=[float(ctr_base[0])], y=[float(ctr_base[1])], z=[float(ctr_base[2])],
            mode="markers", marker=dict(size=8, color="orange", symbol="diamond"),
            name="CTR Base",
        ),
        go.Scatter3d(
            x=first_geom["ss_line"][:, 0], y=first_geom["ss_line"][:, 1],
            z=first_geom["ss_line"][:, 2],
            mode="lines", line=dict(color="orange", width=6), name="SS Tube",
        ),
        go.Scatter3d(
            x=first_geom["arc_line"][:, 0] if len(first_geom["arc_line"]) > 0 else [],
            y=first_geom["arc_line"][:, 1] if len(first_geom["arc_line"]) > 0 else [],
            z=first_geom["arc_line"][:, 2] if len(first_geom["arc_line"]) > 0 else [],
            mode="lines", line=dict(color="dodgerblue", width=6), name="Nitinol Arc",
        ),
        go.Scatter3d(
            x=[float(first_geom["tip"][0])], y=[float(first_geom["tip"][1])],
            z=[float(first_geom["tip"][2])],
            mode="markers", marker=dict(size=6, color="lime"), name="Tip",
        ),
        go.Scatter3d(
            x=[], y=[], z=[], mode="lines+markers",
            line=dict(color="red", width=3),
            marker=dict(size=2, color="red"),
            name="Printed Trail",
        ),
        # 6: Gimbal Direction (tilted)
        go.Scatter3d(
            x=first_gimbal["direction_line"][:, 0],
            y=first_gimbal["direction_line"][:, 1],
            z=first_gimbal["direction_line"][:, 2],
            mode="lines", line=dict(color="cyan", width=4),
            name="Gimbal Direction",
        ),
        # 7: Base Direction (untilted reference)
        go.Scatter3d(
            x=first_gimbal["base_direction_line"][:, 0],
            y=first_gimbal["base_direction_line"][:, 1],
            z=first_gimbal["base_direction_line"][:, 2],
            mode="lines", line=dict(color="gray", width=2, dash="dot"),
            name="Base Direction",
        ),
    ]

    fig = go.Figure(data=traces)

    # Build frames
    frames = []
    for k in frame_indices:
        node, current_pass = flat_sequence[k]
        geom, gimbal = _compute_frame_data(
            node, gimbal_solutions, ctr_base, R_hat_base,
            n_hat_base, theta_match, radius,
        )

        # Trail: all nodes up to k, with NaN separators between passes
        # and per-pass coloring
        trail_segments = []
        trail_colors = []
        count = 0
        for pk in pass_keys:
            pass_nodes = print_passes[pk]
            # How many nodes from this pass are before index k?
            if count + len(pass_nodes) <= k:
                # Entire pass is in the trail
                seg_nodes = pass_nodes
                count += len(pass_nodes)
            elif count <= k:
                # Partial pass
                n_from_this = k - count + 1
                seg_nodes = pass_nodes[:n_from_this]
                count += len(pass_nodes)
            else:
                break

            if seg_nodes:
                # Subsample long segments
                if len(seg_nodes) > trail_max_points // max(n_passes, 1):
                    step_s = max(1, len(seg_nodes) * n_passes // trail_max_points)
                    seg_nodes = seg_nodes[::step_s]
                seg_pts = points[seg_nodes, :3]
                if trail_segments:
                    trail_segments.append(np.array([[np.nan, np.nan, np.nan]]))
                    trail_colors.append(pass_color[pk])
                trail_segments.append(seg_pts)
                trail_colors.extend([pass_color[pk]] * len(seg_pts))

        if trail_segments:
            trail_all = np.vstack(trail_segments)
        else:
            trail_all = np.empty((0, 3))

        sol = gimbal_solutions.get(node)
        config_label = ""
        if sol is not None:
            config_label = (
                f"Config {sol.config_idx} | "
                f"\u03b1={np.degrees(sol.alpha):.1f}\u00b0 "
                f"\u03c6={np.degrees(sol.phi):.1f}\u00b0"
            )

        # Only include dynamic traces (indices 2-7); skip static ghost/base
        frame_data = [
            go.Scatter3d(x=geom["ss_line"][:, 0], y=geom["ss_line"][:, 1], z=geom["ss_line"][:, 2]),
            go.Scatter3d(
                x=geom["arc_line"][:, 0] if len(geom["arc_line"]) > 0 else [],
                y=geom["arc_line"][:, 1] if len(geom["arc_line"]) > 0 else [],
                z=geom["arc_line"][:, 2] if len(geom["arc_line"]) > 0 else [],
            ),
            go.Scatter3d(x=[float(geom["tip"][0])], y=[float(geom["tip"][1])], z=[float(geom["tip"][2])]),
            go.Scatter3d(
                x=trail_all[:, 0] if len(trail_all) > 0 else [],
                y=trail_all[:, 1] if len(trail_all) > 0 else [],
                z=trail_all[:, 2] if len(trail_all) > 0 else [],
                line=dict(color=trail_colors if trail_colors else "red", width=3),
            ),
            # 6: Gimbal Direction (tilted)
            go.Scatter3d(
                x=gimbal["direction_line"][:, 0],
                y=gimbal["direction_line"][:, 1],
                z=gimbal["direction_line"][:, 2],
            ),
            # 7: Base Direction (untilted reference)
            go.Scatter3d(
                x=gimbal["base_direction_line"][:, 0],
                y=gimbal["base_direction_line"][:, 1],
                z=gimbal["base_direction_line"][:, 2],
            ),
        ]

        frames.append(go.Frame(
            data=frame_data,
            traces=[2, 3, 4, 5, 6, 7],  # only update dynamic traces
            name=str(k),
            layout=go.Layout(
                title_text=(
                    f"Pass {current_pass}/{n_passes-1} | "
                    f"Node {k}/{n_total} {config_label}"
                ),
            ),
        ))

    fig.frames = frames

    slider_steps = [
        dict(
            args=[[str(frame_indices[i])],
                  dict(frame=dict(duration=50, redraw=True), mode="immediate")],
            label=str(frame_indices[i]),
            method="animate",
        )
        for i in range(len(frame_indices))
    ]

    fig.update_layout(
        updatemenus=[dict(
            type="buttons", showactive=False,
            x=0.05, y=0.05, xanchor="left", yanchor="bottom",
            buttons=[
                dict(label="Play", method="animate",
                     args=[None, dict(frame=dict(duration=50, redraw=True),
                                      fromcurrent=True, transition=dict(duration=0))]),
                dict(label="Pause", method="animate",
                     args=[[None], dict(frame=dict(duration=0, redraw=False),
                                        mode="immediate", transition=dict(duration=0))]),
            ],
        )],
        sliders=[dict(
            active=0, currentvalue=dict(prefix="Step: "),
            steps=slider_steps, x=0.05, len=0.9, xanchor="left", y=0, yanchor="top",
        )],
        scene=dict(
            xaxis=dict(range=[x_min, x_max]),
            yaxis=dict(range=[y_min, y_max]),
            zaxis=dict(range=[z_min, z_max]),
            aspectmode="data",
        ),
        margin=dict(l=30, r=30, t=50, b=80),
        title_text=f"CTR Simulation — All {n_passes} Passes ({len(frame_indices)} frames)",
    )

    return fig


def _compute_frame_data(
    node: int,
    gimbal_solutions: Dict[int, GimbalNodeSolution],
    ctr_base: np.ndarray,
    R_hat_base: np.ndarray,
    n_hat_base: np.ndarray,
    theta_match_base: float,
    radius: float,
) -> tuple:
    """Compute needle geometry and gimbal frame for a single node.

    Returns (geom_dict, gimbal_dict).
    """
    sol = gimbal_solutions.get(node)
    if sol is None:
        # Fallback: retracted position
        geom = compute_needle_geometry(
            ctr_base, R_hat_base, n_hat_base, theta_match_base,
            z_ss=0.0, z_ntnl=0.0, theta=0.0, radius=radius,
        )
        gimbal = compute_gimbal_frame(
            ctr_base, R_hat_base, n_hat_base, alpha=0.0, phi=0.0,
        )
        return geom, gimbal

    # Compute tilted frame
    gimbal = compute_gimbal_frame(
        ctr_base, R_hat_base, n_hat_base, alpha=sol.alpha, phi=sol.phi,
    )

    # Compute needle geometry using tilted config
    geom = compute_needle_geometry(
        ctr_base,
        gimbal["R_hat_tilted"],
        gimbal["n_hat_tilted"],
        gimbal["theta_match_tilted"],
        z_ss=sol.z_ss,
        z_ntnl=sol.z_ntnl,
        theta=sol.theta,
        radius=radius,
    )

    return geom, gimbal


# ---------------------------------------------------------------------------
# Non-gimbal fallback: build synthetic solutions using IK
# ---------------------------------------------------------------------------

def build_fallback_solutions(
    print_passes: Dict[int, List[int]],
    points: np.ndarray,
    ctr_config_params: dict,
) -> Dict[int, GimbalNodeSolution]:
    """Build synthetic GimbalNodeSolution for each pass node using base IK.

    Used when gimbal solver was not enabled but CTR mode is active.
    """
    from xcavate.core.ctr_kinematics import CTRConfig

    # We need a CTRConfig to use fast_global_to_snt, but the full config
    # requires interp1d objects. Instead, use the vectorized batch approach.
    # For the simulation, we'll reconstruct using from_xcavate_config.
    # But we don't have the full XcavateConfig here. Instead, we use a
    # simpler approach: compute IK per node using the stored params.
    X = np.array(ctr_config_params["X"])
    R_hat = np.array(ctr_config_params["R_hat"])
    n_hat = np.array(ctr_config_params["n_hat"])
    theta_match = ctr_config_params["theta_match"]
    radius = ctr_config_params["radius"]

    # Build direction matrix for fast local transform
    from xcavate.core.ctr_kinematics import rodrigues_rotation
    R_rot = rodrigues_rotation(theta_match, R_hat)
    n_rot = R_rot @ n_hat
    t_hat = np.cross(R_hat, n_rot)
    D = np.array([R_hat, n_rot, t_hat])

    solutions: Dict[int, GimbalNodeSolution] = {}
    unique_nodes = set()
    for nodes in print_passes.values():
        unique_nodes.update(nodes)

    for node in unique_nodes:
        pt = points[node, :3]
        delta = pt - X
        local = D @ delta
        x_l, y_l, z_l = local

        r_perp = np.sqrt(y_l ** 2 + z_l ** 2)
        theta = float(np.arctan2(z_l, y_l))

        # Simple analytical IK for default calibration
        if r_perp > 0:
            # arc_angle from radial distance: r_perp = radius * (1 - cos(angle))
            cos_val = 1.0 - r_perp / radius
            cos_val = np.clip(cos_val, -1.0, 1.0)
            arc_angle = float(np.arccos(cos_val))
            yr = radius * arc_angle
            ntnl_minus_ss = yr
            arc_axial = radius * np.sin(arc_angle)
            z_ss = x_l - arc_axial
            z_ntnl = z_ss + ntnl_minus_ss
        else:
            z_ss = x_l
            z_ntnl = x_l

        solutions[node] = GimbalNodeSolution(
            config_idx=0,
            alpha=0.0,
            phi=0.0,
            z_ss=float(z_ss),
            z_ntnl=float(z_ntnl),
            theta=theta,
        )

    return solutions
