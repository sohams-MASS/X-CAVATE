"""CTR needle simulation: animated gimbal + SS + nitinol visualization.

Computes needle geometry from actuator values and builds Plotly animations
showing the CTR mechanism moving node-by-node during printing.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

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

    # Round helper — reduces JSON float precision from ~16 chars to ~6
    def _r(arr: np.ndarray) -> np.ndarray:
        return np.round(arr, 2)

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
        trail_pts = _r(points[trail_nodes, :3])

        sol = gimbal_solutions.get(node)
        config_label = ""
        if sol is not None:
            config_label = (
                f"Config {sol.config_idx} | "
                f"\u03b1={np.degrees(sol.alpha):.1f}\u00b0 "
                f"\u03c6={np.degrees(sol.phi):.1f}\u00b0"
            )

        # Only include dynamic traces (indices 2-7); skip static ghost/base
        ss = _r(geom["ss_line"])
        arc = _r(geom["arc_line"])
        tip = _r(geom["tip"])
        gdir = _r(gimbal["direction_line"])
        bdir = _r(gimbal["base_direction_line"])

        frame_data = [
            go.Scatter3d(x=ss[:, 0], y=ss[:, 1], z=ss[:, 2]),
            go.Scatter3d(
                x=arc[:, 0] if len(arc) > 0 else [],
                y=arc[:, 1] if len(arc) > 0 else [],
                z=arc[:, 2] if len(arc) > 0 else [],
            ),
            go.Scatter3d(x=[float(tip[0])], y=[float(tip[1])], z=[float(tip[2])]),
            go.Scatter3d(x=trail_pts[:, 0], y=trail_pts[:, 1], z=trail_pts[:, 2]),
            go.Scatter3d(x=gdir[:, 0], y=gdir[:, 1], z=gdir[:, 2]),
            go.Scatter3d(x=bdir[:, 0], y=bdir[:, 1], z=bdir[:, 2]),
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
            x=[], y=[], z=[], mode="markers",
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

    # Round helper — reduces JSON float precision from ~16 chars to ~6
    def _r(arr: np.ndarray) -> np.ndarray:
        return np.round(arr, 2)

    # Build frames
    frames = []
    for k in frame_indices:
        node, current_pass = flat_sequence[k]
        geom, gimbal = _compute_frame_data(
            node, gimbal_solutions, ctr_base, R_hat_base,
            n_hat_base, theta_match, radius,
        )

        # Trail: all nodes up to k (markers only — NaN separators removed
        # to avoid massive overhead with thousands of single-node passes)
        trail_nodes_list: List[int] = []
        count = 0
        for pk in pass_keys:
            pass_nodes = print_passes[pk]
            if count + len(pass_nodes) <= k:
                trail_nodes_list.extend(pass_nodes)
                count += len(pass_nodes)
            elif count <= k:
                n_from_this = k - count + 1
                trail_nodes_list.extend(pass_nodes[:n_from_this])
                count += len(pass_nodes)
            else:
                break

        # Subsample to trail_max_points
        if len(trail_nodes_list) > trail_max_points:
            step_s = max(1, len(trail_nodes_list) // trail_max_points)
            trail_nodes_list = trail_nodes_list[::step_s]
        trail_all = _r(points[trail_nodes_list, :3]) if trail_nodes_list else np.empty((0, 3))

        sol = gimbal_solutions.get(node)
        config_label = ""
        if sol is not None:
            config_label = (
                f"Config {sol.config_idx} | "
                f"\u03b1={np.degrees(sol.alpha):.1f}\u00b0 "
                f"\u03c6={np.degrees(sol.phi):.1f}\u00b0"
            )

        # Only include dynamic traces (indices 2-7); skip static ghost/base
        ss = _r(geom["ss_line"])
        arc = _r(geom["arc_line"])
        tip = _r(geom["tip"])
        gdir = _r(gimbal["direction_line"])
        bdir = _r(gimbal["base_direction_line"])

        frame_data = [
            go.Scatter3d(x=ss[:, 0], y=ss[:, 1], z=ss[:, 2]),
            go.Scatter3d(
                x=arc[:, 0] if len(arc) > 0 else [],
                y=arc[:, 1] if len(arc) > 0 else [],
                z=arc[:, 2] if len(arc) > 0 else [],
            ),
            go.Scatter3d(x=[float(tip[0])], y=[float(tip[1])], z=[float(tip[2])]),
            go.Scatter3d(
                x=trail_all[:, 0] if len(trail_all) > 0 else [],
                y=trail_all[:, 1] if len(trail_all) > 0 else [],
                z=trail_all[:, 2] if len(trail_all) > 0 else [],
                mode="markers",
                marker=dict(size=2, color="red"),
            ),
            go.Scatter3d(x=gdir[:, 0], y=gdir[:, 1], z=gdir[:, 2]),
            go.Scatter3d(x=bdir[:, 0], y=bdir[:, 1], z=bdir[:, 2]),
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


# ---------------------------------------------------------------------------
# Multi-CTR color palette
# ---------------------------------------------------------------------------

_ROBOT_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]


def _dimmed(hex_color: str, factor: float = 0.5) -> str:
    """Return a dimmed (desaturated toward gray) version of *hex_color*."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    gray = 180
    r2 = int(r + (gray - r) * factor)
    g2 = int(g + (gray - g) * factor)
    b2 = int(b + (gray - b) * factor)
    return f"#{r2:02x}{g2:02x}{b2:02x}"


def _unpack_robot_config(cfg: dict) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    """Unpack a ctr_configs_multi dict entry into (X, R_hat, n_hat, theta_match, radius)."""
    return (
        np.asarray(cfg["X"], dtype=float),
        np.asarray(cfg["R_hat"], dtype=float),
        np.asarray(cfg["n_hat"], dtype=float),
        float(cfg["theta_match"]),
        float(cfg["radius"]),
    )


# ---------------------------------------------------------------------------
# Multi-CTR animated simulation
# ---------------------------------------------------------------------------

def create_multi_ctr_simulation(
    per_robot_passes: Dict[int, Dict[int, List[int]]],
    per_robot_solutions: Dict[int, Dict[int, GimbalNodeSolution]],
    ctr_configs_multi: List[dict],
    points: np.ndarray,
    max_frames: int = 300,
    trail_max_points: int = 20000,
) -> go.Figure:
    """Build a Plotly animation showing ALL N robots simultaneously.

    Each robot has its own base marker, needle (SS + nitinol), and color-coded
    printed trail.  Robots are animated sequentially: robot 0 all passes, then
    robot 1, etc.  While a robot is active, idle robots are shown with short
    retracted needles.

    Parameters
    ----------
    per_robot_passes : dict[int, dict[int, list[int]]]
        ``{robot_idx: {pass_idx: [node_indices]}}``.
    per_robot_solutions : dict[int, dict[int, GimbalNodeSolution]]
        ``{robot_idx: {node_idx: GimbalNodeSolution}}``.
    ctr_configs_multi : list of dict
        One dict per robot with keys ``X, R_hat, n_hat, theta_match, radius,
        ss_lim, ntnl_lim``.
    points : ndarray (N, 3+)
        Full coordinate array.
    max_frames : int
        Maximum animation frames (subsamples the timeline).
    trail_max_points : int
        Maximum points in the printed trail trace.

    Returns
    -------
    go.Figure
        Animated Plotly figure with play / pause and slider.
    """
    n_robots = len(ctr_configs_multi)
    if n_robots == 0:
        return go.Figure()

    robot_indices = sorted(per_robot_passes.keys())

    # ------------------------------------------------------------------
    # 1. Build flat timeline: list of (robot_idx, pass_idx, node, pass_total_nodes, node_within_pass)
    # ------------------------------------------------------------------
    FlatEntry = Tuple[int, int, int, int, int]
    flat_sequence: List[FlatEntry] = []

    for ridx in robot_indices:
        passes = per_robot_passes[ridx]
        pass_keys = sorted(passes.keys())
        for pk in pass_keys:
            nodes = passes[pk]
            for ni, node in enumerate(nodes):
                flat_sequence.append((ridx, pk, node, len(nodes), ni))

    n_total = len(flat_sequence)
    if n_total == 0:
        return go.Figure()

    # Per-robot pass counts for title
    per_robot_n_passes = {
        ridx: len(per_robot_passes.get(ridx, {})) for ridx in robot_indices
    }

    # ------------------------------------------------------------------
    # 2. Subsample to max_frames
    # ------------------------------------------------------------------
    if n_total <= max_frames:
        frame_indices = list(range(n_total))
    else:
        step = n_total / max_frames
        frame_indices = [int(i * step) for i in range(max_frames)]
        if frame_indices[-1] != n_total - 1:
            frame_indices[-1] = n_total - 1

    # ------------------------------------------------------------------
    # 3. Ghost points and axis range
    # ------------------------------------------------------------------
    all_pts = points[:, :3]
    ghost_max = 10000
    if len(all_pts) > ghost_max:
        ghost_idx = np.linspace(0, len(all_pts) - 1, ghost_max, dtype=int)
        ghost_pts = all_pts[ghost_idx]
    else:
        ghost_pts = all_pts

    pad = 5.0
    x_min, x_max = float(all_pts[:, 0].min()) - pad, float(all_pts[:, 0].max()) + pad
    y_min, y_max = float(all_pts[:, 1].min()) - pad, float(all_pts[:, 1].max()) + pad
    z_min, z_max = float(all_pts[:, 2].min()) - pad, float(all_pts[:, 2].max()) + pad
    for ridx in range(n_robots):
        base = np.asarray(ctr_configs_multi[ridx]["X"], dtype=float)
        for i, (lo, hi) in enumerate([(x_min, x_max), (y_min, y_max), (z_min, z_max)]):
            v = float(base[i])
            if v < lo:
                if i == 0: x_min = v - pad
                elif i == 1: y_min = v - pad
                else: z_min = v - pad
            if v > hi:
                if i == 0: x_max = v + pad
                elif i == 1: y_max = v + pad
                else: z_max = v + pad

    # ------------------------------------------------------------------
    # 4. Initial traces
    # ------------------------------------------------------------------
    # Trace 0: Network ghost
    # Traces 1..N: Robot base markers
    # Trace N+1: Active SS tube
    # Trace N+2: Active nitinol arc
    # Trace N+3: Active tip
    # Trace N+4: Printed trail (all robots)
    # Trace N+5: Gimbal direction
    # Trace N+6: Base direction reference
    # Traces N+7..N+6+N_idle: Retracted needles for idle robots
    N = n_robots

    # First frame data
    first_ridx, first_pk, first_node, _, _ = flat_sequence[0]
    first_cfg = ctr_configs_multi[first_ridx]
    fX, fR, fn, ftm, frad = _unpack_robot_config(first_cfg)
    first_sols = per_robot_solutions.get(first_ridx, {})
    first_geom, first_gimbal = _compute_frame_data(
        first_node, first_sols, fX, fR, fn, ftm, frad,
    )
    active_color = _ROBOT_COLORS[first_ridx % len(_ROBOT_COLORS)]

    traces = [
        # 0: Network ghost
        go.Scatter3d(
            x=ghost_pts[:, 0], y=ghost_pts[:, 1], z=ghost_pts[:, 2],
            mode="markers", marker=dict(size=1, color="gray", opacity=0.3),
            name="Network", hoverinfo="skip",
        ),
    ]

    # 1..N: Base markers
    for ridx in range(N):
        base = np.asarray(ctr_configs_multi[ridx]["X"], dtype=float)
        color = _ROBOT_COLORS[ridx % len(_ROBOT_COLORS)]
        traces.append(go.Scatter3d(
            x=[float(base[0])], y=[float(base[1])], z=[float(base[2])],
            mode="markers",
            marker=dict(size=8, color=color, symbol="diamond"),
            name=f"Robot {ridx} Base",
        ))

    # N+1: Active SS tube
    traces.append(go.Scatter3d(
        x=first_geom["ss_line"][:, 0], y=first_geom["ss_line"][:, 1],
        z=first_geom["ss_line"][:, 2],
        mode="lines", line=dict(color=active_color, width=6), name="SS Tube",
    ))

    # N+2: Active nitinol arc
    arc = first_geom["arc_line"]
    traces.append(go.Scatter3d(
        x=arc[:, 0] if len(arc) > 0 else [],
        y=arc[:, 1] if len(arc) > 0 else [],
        z=arc[:, 2] if len(arc) > 0 else [],
        mode="lines", line=dict(color=active_color, width=6), name="Nitinol Arc",
    ))

    # N+3: Active tip
    traces.append(go.Scatter3d(
        x=[float(first_geom["tip"][0])],
        y=[float(first_geom["tip"][1])],
        z=[float(first_geom["tip"][2])],
        mode="markers", marker=dict(size=6, color="lime"), name="Tip",
    ))

    # N+4: Printed trail (starts empty)
    traces.append(go.Scatter3d(
        x=[], y=[], z=[], mode="lines+markers",
        line=dict(color="red", width=3),
        marker=dict(size=2, color="red"),
        name="Printed Trail",
    ))

    # N+5: Gimbal direction
    traces.append(go.Scatter3d(
        x=first_gimbal["direction_line"][:, 0],
        y=first_gimbal["direction_line"][:, 1],
        z=first_gimbal["direction_line"][:, 2],
        mode="lines", line=dict(color="cyan", width=4), name="Gimbal Direction",
    ))

    # N+6: Base direction reference
    traces.append(go.Scatter3d(
        x=first_gimbal["base_direction_line"][:, 0],
        y=first_gimbal["base_direction_line"][:, 1],
        z=first_gimbal["base_direction_line"][:, 2],
        mode="lines", line=dict(color="gray", width=2, dash="dot"), name="Base Direction",
    ))

    # N+7 .. N+6+N_idle: Retracted needles for idle robots
    # For each robot except the active one, show a short retracted SS tube
    idle_robots = [r for r in range(N) if r != first_ridx]
    for idle_r in idle_robots:
        icfg = ctr_configs_multi[idle_r]
        iX, iR, iN, iTM, iRad = _unpack_robot_config(icfg)
        idle_geom = compute_needle_geometry(
            iX, iR, iN, iTM, z_ss=1.0, z_ntnl=1.0, theta=0.0, radius=iRad,
        )
        idle_color = _dimmed(_ROBOT_COLORS[idle_r % len(_ROBOT_COLORS)])
        traces.append(go.Scatter3d(
            x=idle_geom["ss_line"][:, 0], y=idle_geom["ss_line"][:, 1],
            z=idle_geom["ss_line"][:, 2],
            mode="lines", line=dict(color=idle_color, width=3),
            name=f"Robot {idle_r} (idle)", showlegend=False,
        ))

    fig = go.Figure(data=traces)

    # ------------------------------------------------------------------
    # 5. Dynamic trace index mapping
    # ------------------------------------------------------------------
    # Trace indices for the dynamic portion:
    IDX_SS = N + 1
    IDX_ARC = N + 2
    IDX_TIP = N + 3
    IDX_TRAIL = N + 4
    IDX_GIMBAL = N + 5
    IDX_BASEDIR = N + 6
    IDX_IDLE_START = N + 7
    n_idle = N - 1  # number of idle robot traces (all except active)

    dynamic_trace_indices = list(range(IDX_SS, IDX_IDLE_START + n_idle))

    # ------------------------------------------------------------------
    # 6. Precompute cumulative trail segments per robot
    # ------------------------------------------------------------------
    # For efficiency, precompute the flat ordering of nodes per robot
    robot_flat_nodes: Dict[int, List[int]] = {}
    robot_flat_pass_boundaries: Dict[int, List[int]] = {}
    for ridx in robot_indices:
        nodes_list: List[int] = []
        boundaries: List[int] = []
        passes = per_robot_passes[ridx]
        for pk in sorted(passes.keys()):
            boundaries.append(len(nodes_list))
            nodes_list.extend(passes[pk])
        robot_flat_nodes[ridx] = nodes_list
        robot_flat_pass_boundaries[ridx] = boundaries

    # For each entry in flat_sequence, compute how many nodes each robot
    # has printed up to that point.  robot_progress[ridx] = count of nodes
    # completed so far for that robot.
    # We track this incrementally as we iterate over frame_indices.
    robot_progress: Dict[int, int] = {r: 0 for r in range(N)}

    # Map: flat_sequence index -> robot_progress snapshot
    # We need to build this for each frame_index.  Since frame_indices are
    # subsampled, we need the progress at each frame.

    # ------------------------------------------------------------------
    # 7. Precompute idle robot geometry (constant across frames)
    # ------------------------------------------------------------------
    _idle_geom_cache: Dict[int, Dict[str, np.ndarray]] = {}
    _idle_color_cache: Dict[int, str] = {}
    for ridx in range(N):
        icfg = ctr_configs_multi[ridx]
        iX, iR, iN_hat, iTM, iRad = _unpack_robot_config(icfg)
        _idle_geom_cache[ridx] = compute_needle_geometry(
            iX, iR, iN_hat, iTM,
            z_ss=1.0, z_ntnl=1.0, theta=0.0, radius=iRad,
        )
        _idle_color_cache[ridx] = _dimmed(_ROBOT_COLORS[ridx % len(_ROBOT_COLORS)])

    # Round helper — reduces JSON float precision from ~16 chars to ~6
    def _r(arr: np.ndarray) -> np.ndarray:
        return np.round(arr, 2)

    # Precompute robot progress at every flat_sequence index incrementally
    # so we avoid the O(k) inner loop per frame (was O(n_total * n_frames))
    _cum_progress: List[Dict[int, int]] = []
    _rp_running: Dict[int, int] = {r: 0 for r in range(N)}
    for j in range(n_total):
        _rp_running[flat_sequence[j][0]] += 1
        _cum_progress.append(dict(_rp_running))

    # ------------------------------------------------------------------
    # 8. Build frames
    # ------------------------------------------------------------------
    frames = []

    for k in frame_indices:
        active_ridx, active_pk, active_node, pass_total, node_in_pass = flat_sequence[k]
        active_color_k = _ROBOT_COLORS[active_ridx % len(_ROBOT_COLORS)]

        # Robot progress at index k (O(1) lookup)
        rp = _cum_progress[k]

        # Active robot geometry
        acfg = ctr_configs_multi[active_ridx]
        aX, aR, aN, aTM, aRad = _unpack_robot_config(acfg)
        active_sols = per_robot_solutions.get(active_ridx, {})
        geom, gimbal = _compute_frame_data(
            active_node, active_sols, aX, aR, aN, aTM, aRad,
        )

        # Trail: accumulate nodes for ALL robots up to their progress
        # Use a single color per robot (no per-point color arrays — major size saving)
        trail_segments: List[np.ndarray] = []
        for ridx in robot_indices:
            if ridx not in robot_flat_nodes or rp.get(ridx, 0) == 0:
                continue
            count = rp[ridx]
            flat_nodes = robot_flat_nodes[ridx][:count]
            boundaries = robot_flat_pass_boundaries[ridx]

            # Split into passes for NaN separators
            for bi, bstart in enumerate(boundaries):
                if bstart >= count:
                    break
                bend = boundaries[bi + 1] if bi + 1 < len(boundaries) else count
                bend = min(bend, count)
                seg_nodes = flat_nodes[bstart:bend]
                if not seg_nodes:
                    continue

                # Subsample long segments
                max_per_seg = max(50, trail_max_points // max(N * len(boundaries), 1))
                if len(seg_nodes) > max_per_seg:
                    step_s = max(1, len(seg_nodes) // max_per_seg)
                    seg_nodes = seg_nodes[::step_s]
                    if seg_nodes[-1] != flat_nodes[min(bend - 1, len(flat_nodes) - 1)]:
                        seg_nodes.append(flat_nodes[min(bend - 1, len(flat_nodes) - 1)])

                seg_pts = _r(points[seg_nodes, :3])
                if trail_segments:
                    trail_segments.append(np.array([[np.nan, np.nan, np.nan]]))
                trail_segments.append(seg_pts)

        if trail_segments:
            trail_all = np.vstack(trail_segments)
        else:
            trail_all = np.empty((0, 3))

        # Config label
        sol = active_sols.get(active_node)
        config_label = ""
        if sol is not None:
            config_label = (
                f"Config {sol.config_idx} | "
                f"\u03b1={np.degrees(sol.alpha):.1f}\u00b0 "
                f"\u03c6={np.degrees(sol.phi):.1f}\u00b0"
            )

        # Determine which pass within this robot
        robot_pass_keys = sorted(per_robot_passes.get(active_ridx, {}).keys())
        pass_within_robot = robot_pass_keys.index(active_pk) + 1 if active_pk in robot_pass_keys else 0
        total_robot_passes = len(robot_pass_keys)

        # Frame title
        title = (
            f"Robot {active_ridx} | "
            f"Pass {pass_within_robot}/{total_robot_passes} | "
            f"Node {node_in_pass + 1}/{pass_total} | "
            f"{config_label}"
        )

        # Build frame data — same order as dynamic_trace_indices
        frame_data = []

        # IDX_SS: Active SS tube
        ss = _r(geom["ss_line"])
        frame_data.append(go.Scatter3d(
            x=ss[:, 0], y=ss[:, 1], z=ss[:, 2],
            line=dict(color=active_color_k, width=6),
        ))

        # IDX_ARC: Active nitinol arc
        arc = _r(geom["arc_line"])
        frame_data.append(go.Scatter3d(
            x=arc[:, 0] if len(arc) > 0 else [],
            y=arc[:, 1] if len(arc) > 0 else [],
            z=arc[:, 2] if len(arc) > 0 else [],
            line=dict(color=active_color_k, width=6),
        ))

        # IDX_TIP: Active tip
        tip = _r(geom["tip"])
        frame_data.append(go.Scatter3d(
            x=[float(tip[0])],
            y=[float(tip[1])],
            z=[float(tip[2])],
        ))

        # IDX_TRAIL: Printed trail (single color — no per-point array)
        frame_data.append(go.Scatter3d(
            x=trail_all[:, 0] if len(trail_all) > 0 else [],
            y=trail_all[:, 1] if len(trail_all) > 0 else [],
            z=trail_all[:, 2] if len(trail_all) > 0 else [],
            line=dict(color="red", width=3),
        ))

        # IDX_GIMBAL: Gimbal direction
        gdir = _r(gimbal["direction_line"])
        frame_data.append(go.Scatter3d(
            x=gdir[:, 0], y=gdir[:, 1], z=gdir[:, 2],
        ))

        # IDX_BASEDIR: Base direction reference
        bdir = _r(gimbal["base_direction_line"])
        frame_data.append(go.Scatter3d(
            x=bdir[:, 0], y=bdir[:, 1], z=bdir[:, 2],
        ))

        # IDX_IDLE_START..: Retracted needles for idle robots (from cache)
        all_others = [r for r in range(N) if r != active_ridx]
        for idle_r in all_others:
            ig = _idle_geom_cache[idle_r]
            ig_ss = _r(ig["ss_line"])
            frame_data.append(go.Scatter3d(
                x=ig_ss[:, 0], y=ig_ss[:, 1], z=ig_ss[:, 2],
                line=dict(color=_idle_color_cache[idle_r], width=3),
            ))

        frames.append(go.Frame(
            data=frame_data,
            traces=dynamic_trace_indices,
            name=str(k),
            layout=go.Layout(title_text=title),
        ))

    fig.frames = frames

    # ------------------------------------------------------------------
    # 8. Slider and play/pause
    # ------------------------------------------------------------------
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
        title_text=f"Multi-CTR Simulation — {N} Robots ({len(frame_indices)} frames)",
    )

    return fig


# ---------------------------------------------------------------------------
# Multi-CTR parallel animated simulation
# ---------------------------------------------------------------------------

def create_multi_ctr_parallel_simulation(
    per_robot_passes: Dict[int, Dict[int, List[int]]],
    per_robot_solutions: Dict[int, Dict[int, GimbalNodeSolution]],
    ctr_configs_multi: List[dict],
    points: np.ndarray,
    max_frames: int = 300,
    trail_max_points: int = 20000,
    ghost_max: int = 20000,
    trail_marker_size: float = 2.5,
    needle_width: float = 7,
) -> go.Figure:
    """Build a Plotly animation showing ALL robots printing simultaneously.

    Unlike ``create_multi_ctr_simulation`` which serializes robots, this version
    advances all robots in lockstep: at each frame, every active robot progresses
    proportionally through its own node sequence.

    Trace layout per robot: SS tube, nitinol arc, tip, trail (4 traces each).
    Plus shared: network ghost, base markers.

    Parameters
    ----------
    per_robot_passes, per_robot_solutions, ctr_configs_multi, points
        Same as ``create_multi_ctr_simulation``.
    max_frames : int
        Maximum animation frames.
    trail_max_points : int
        Maximum trail points per robot.
    ghost_max : int
        Maximum network ghost points for background display.
    trail_marker_size : float
        Marker size for printed trail dots.
    needle_width : float
        Line width for SS tube and nitinol arc.
    """
    n_robots = len(ctr_configs_multi)
    if n_robots == 0:
        return go.Figure()

    robot_indices = sorted(per_robot_passes.keys())
    active_robots = [r for r in robot_indices if per_robot_passes.get(r)]

    # Build flat node list per robot
    robot_flat_nodes: Dict[int, List[int]] = {}
    robot_flat_pass_bounds: Dict[int, List[int]] = {}
    for ridx in active_robots:
        nodes_list: List[int] = []
        bounds: List[int] = []
        for pk in sorted(per_robot_passes[ridx].keys()):
            bounds.append(len(nodes_list))
            nodes_list.extend(per_robot_passes[ridx][pk])
        robot_flat_nodes[ridx] = nodes_list
        robot_flat_pass_bounds[ridx] = bounds

    # Total steps = longest robot sequence
    max_steps = max((len(robot_flat_nodes[r]) for r in active_robots), default=0)
    if max_steps == 0:
        return go.Figure()

    # Subsample to max_frames
    if max_steps <= max_frames:
        frame_steps = list(range(max_steps))
    else:
        step_size = max_steps / max_frames
        frame_steps = [int(i * step_size) for i in range(max_frames)]
        if frame_steps[-1] != max_steps - 1:
            frame_steps[-1] = max_steps - 1

    # Ghost points and axis range
    all_pts = points[:, :3]
    if len(all_pts) > ghost_max:
        ghost_idx = np.linspace(0, len(all_pts) - 1, ghost_max, dtype=int)
        ghost_pts = all_pts[ghost_idx]
    else:
        ghost_pts = all_pts

    pad = 5.0
    x_min, x_max = float(all_pts[:, 0].min()) - pad, float(all_pts[:, 0].max()) + pad
    y_min, y_max = float(all_pts[:, 1].min()) - pad, float(all_pts[:, 1].max()) + pad
    z_min, z_max = float(all_pts[:, 2].min()) - pad, float(all_pts[:, 2].max()) + pad
    for ridx in range(n_robots):
        base = np.asarray(ctr_configs_multi[ridx]["X"], dtype=float)
        for dim in range(3):
            v = float(base[dim])
            if dim == 0:
                x_min, x_max = min(x_min, v - pad), max(x_max, v + pad)
            elif dim == 1:
                y_min, y_max = min(y_min, v - pad), max(y_max, v + pad)
            else:
                z_min, z_max = min(z_min, v - pad), max(z_max, v + pad)

    def _r(arr: np.ndarray) -> np.ndarray:
        return np.round(arr, 2)

    # ------------------------------------------------------------------
    # Trace layout:
    # [0]           Network ghost
    # [1..N]        Base markers
    # [N+1 + r*4]   SS tube for robot r
    # [N+1 + r*4+1] Arc for robot r
    # [N+1 + r*4+2] Tip for robot r
    # [N+1 + r*4+3] Trail for robot r
    # ------------------------------------------------------------------
    N = n_robots

    # Unpack configs
    robot_cfgs = {}
    for ridx in range(N):
        robot_cfgs[ridx] = _unpack_robot_config(ctr_configs_multi[ridx])

    traces = [
        go.Scatter3d(
            x=ghost_pts[:, 0], y=ghost_pts[:, 1], z=ghost_pts[:, 2],
            mode="markers", marker=dict(size=1, color="gray", opacity=0.3),
            name="Network", hoverinfo="skip",
        ),
    ]

    # Base markers
    for ridx in range(N):
        base = np.asarray(ctr_configs_multi[ridx]["X"], dtype=float)
        color = _ROBOT_COLORS[ridx % len(_ROBOT_COLORS)]
        traces.append(go.Scatter3d(
            x=[float(base[0])], y=[float(base[1])], z=[float(base[2])],
            mode="markers",
            marker=dict(size=8, color=color, symbol="diamond"),
            name=f"Robot {ridx} Base",
        ))

    # Per-robot dynamic traces (SS, Arc, Tip, Trail)
    for ridx in range(N):
        color = _ROBOT_COLORS[ridx % len(_ROBOT_COLORS)]
        X, R_hat, n_hat, tm, rad = robot_cfgs[ridx]

        if ridx in active_robots and robot_flat_nodes[ridx]:
            first_node = robot_flat_nodes[ridx][0]
            sols = per_robot_solutions.get(ridx, {})
            geom, _ = _compute_frame_data(first_node, sols, X, R_hat, n_hat, tm, rad)
        else:
            geom = compute_needle_geometry(X, R_hat, n_hat, tm,
                                           z_ss=1.0, z_ntnl=1.0, theta=0.0, radius=rad)

        # SS tube
        traces.append(go.Scatter3d(
            x=geom["ss_line"][:, 0], y=geom["ss_line"][:, 1], z=geom["ss_line"][:, 2],
            mode="lines", line=dict(color=color, width=needle_width),
            name=f"Robot {ridx} SS",
        ))
        # Arc
        arc = geom["arc_line"]
        traces.append(go.Scatter3d(
            x=arc[:, 0] if len(arc) > 0 else [],
            y=arc[:, 1] if len(arc) > 0 else [],
            z=arc[:, 2] if len(arc) > 0 else [],
            mode="lines", line=dict(color=color, width=needle_width),
            name=f"Robot {ridx} Arc",
        ))
        # Tip
        traces.append(go.Scatter3d(
            x=[float(geom["tip"][0])], y=[float(geom["tip"][1])], z=[float(geom["tip"][2])],
            mode="markers", marker=dict(size=needle_width, color="lime"),
            name=f"Robot {ridx} Tip", showlegend=False,
        ))
        # Trail (markers only — passes are disjoint, no connecting lines)
        traces.append(go.Scatter3d(
            x=[], y=[], z=[], mode="markers",
            marker=dict(size=trail_marker_size, color=color),
            name=f"Robot {ridx} Trail",
        ))

    fig = go.Figure(data=traces)

    # Dynamic trace indices: N+1 to N+1+N*4-1
    dynamic_indices = list(range(N + 1, N + 1 + N * 4))

    # Precompute idle geometry for robots with no nodes
    idle_geom = {}
    for ridx in range(N):
        if ridx not in active_robots:
            X, R_hat, n_hat, tm, rad = robot_cfgs[ridx]
            idle_geom[ridx] = compute_needle_geometry(
                X, R_hat, n_hat, tm, z_ss=1.0, z_ntnl=1.0, theta=0.0, radius=rad,
            )

    # ------------------------------------------------------------------
    # Build frames — all robots advance in parallel
    # ------------------------------------------------------------------
    from scipy.spatial.distance import cdist

    frames = []
    for step in frame_steps:
        frame_data = []

        # Status parts for title
        status_parts = []

        # Collect needle body points per robot for inter-robot distance
        robot_bodies: Dict[int, np.ndarray] = {}

        for ridx in range(N):
            color = _ROBOT_COLORS[ridx % len(_ROBOT_COLORS)]

            if ridx in active_robots and robot_flat_nodes[ridx]:
                n_nodes = len(robot_flat_nodes[ridx])
                # Each robot advances proportionally
                robot_step = min(step, n_nodes - 1)
                node = robot_flat_nodes[ridx][robot_step]
                sols = per_robot_solutions.get(ridx, {})
                X, R_hat, n_hat, tm, rad = robot_cfgs[ridx]
                geom, _ = _compute_frame_data(node, sols, X, R_hat, n_hat, tm, rad)

                # Collect body points for collision distance calc
                body_parts = [geom["ss_line"]]
                if len(geom["arc_line"]) > 0:
                    body_parts.append(geom["arc_line"])
                robot_bodies[ridx] = np.vstack(body_parts)

                # SS
                ss = _r(geom["ss_line"])
                frame_data.append(go.Scatter3d(
                    x=ss[:, 0], y=ss[:, 1], z=ss[:, 2],
                    line=dict(color=color, width=needle_width),
                ))
                # Arc
                arc = _r(geom["arc_line"])
                frame_data.append(go.Scatter3d(
                    x=arc[:, 0] if len(arc) > 0 else [],
                    y=arc[:, 1] if len(arc) > 0 else [],
                    z=arc[:, 2] if len(arc) > 0 else [],
                    line=dict(color=color, width=needle_width),
                ))
                # Tip
                tip = _r(geom["tip"])
                frame_data.append(go.Scatter3d(
                    x=[float(tip[0])], y=[float(tip[1])], z=[float(tip[2])],
                ))

                # Trail: all nodes printed by this robot up to robot_step
                # Render as markers (no lines) — passes are disjoint so
                # connecting them with lines would create artifacts.
                # Subsample to keep payload small.
                count = robot_step + 1
                trail_nodes = robot_flat_nodes[ridx][:count]
                max_trail = trail_max_points // max(len(active_robots), 1)
                if len(trail_nodes) > max_trail:
                    step_s = max(1, len(trail_nodes) // max_trail)
                    trail_nodes = trail_nodes[::step_s]
                trail_pts = _r(points[trail_nodes, :3]) if trail_nodes else np.empty((0, 3))

                frame_data.append(go.Scatter3d(
                    x=trail_pts[:, 0] if len(trail_pts) > 0 else [],
                    y=trail_pts[:, 1] if len(trail_pts) > 0 else [],
                    z=trail_pts[:, 2] if len(trail_pts) > 0 else [],
                    mode="markers",
                    marker=dict(size=trail_marker_size, color=color),
                ))

                status_parts.append(
                    f"R{ridx}: {robot_step + 1}/{n_nodes}"
                )

            else:
                # Idle robot — retracted
                if ridx in idle_geom:
                    ig = idle_geom[ridx]
                else:
                    X, R_hat, n_hat, tm, rad = robot_cfgs[ridx]
                    ig = compute_needle_geometry(
                        X, R_hat, n_hat, tm, z_ss=1.0, z_ntnl=1.0,
                        theta=0.0, radius=rad,
                    )
                dimmed = _dimmed(color)
                ig_ss = _r(ig["ss_line"])
                frame_data.append(go.Scatter3d(
                    x=ig_ss[:, 0], y=ig_ss[:, 1], z=ig_ss[:, 2],
                    line=dict(color=dimmed, width=3),
                ))
                frame_data.append(go.Scatter3d(x=[], y=[], z=[]))  # arc
                frame_data.append(go.Scatter3d(x=[], y=[], z=[]))  # tip
                frame_data.append(go.Scatter3d(x=[], y=[], z=[]))  # trail

        # Compute minimum inter-robot needle body distance
        min_dist = float("inf")
        min_pair = (-1, -1)
        body_keys = sorted(robot_bodies.keys())
        for i in range(len(body_keys)):
            for j in range(i + 1, len(body_keys)):
                ri, rj = body_keys[i], body_keys[j]
                d = cdist(robot_bodies[ri], robot_bodies[rj]).min()
                if d < min_dist:
                    min_dist = d
                    min_pair = (ri, rj)

        collision_tag = ""
        if min_dist < float("inf"):
            if min_dist < 4.0:  # SS OD = 4mm
                collision_tag = f" | MIN DIST: {min_dist:.1f}mm R{min_pair[0]}-R{min_pair[1]} ⚠️"
            else:
                collision_tag = f" | min dist: {min_dist:.1f}mm"

        title = f"Parallel | Step {step + 1}/{max_steps}{collision_tag}"

        frames.append(go.Frame(
            data=frame_data,
            traces=dynamic_indices,
            name=str(step),
            layout=go.Layout(title_text=title),
        ))

    fig.frames = frames

    # Slider and play/pause
    slider_steps = [
        dict(
            args=[[str(s)], dict(frame=dict(duration=50, redraw=True), mode="immediate")],
            label=str(s),
            method="animate",
        )
        for s in frame_steps
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
        title_text=f"Multi-CTR Parallel Simulation — {len(active_robots)} Active Robots ({len(frame_steps)} frames)",
    )

    return fig


# ---------------------------------------------------------------------------
# Multi-CTR static overview
# ---------------------------------------------------------------------------

def create_multi_ctr_static_view(
    per_robot_passes: Dict[int, Dict[int, List[int]]],
    per_robot_solutions: Dict[int, Dict[int, GimbalNodeSolution]],
    ctr_configs_multi: List[dict],
    points: np.ndarray,
) -> go.Figure:
    """Create a non-animated 3D overview of all robots and their printed paths.

    Shows:
    - Network as gray dots
    - All robot bases as colored diamonds
    - All printed trails color-coded by robot
    - Each robot's workspace sphere (transparent) centered at its base

    Parameters
    ----------
    per_robot_passes : dict[int, dict[int, list[int]]]
    per_robot_solutions : dict[int, dict[int, GimbalNodeSolution]]
    ctr_configs_multi : list of dict
    points : ndarray (N, 3+)

    Returns
    -------
    go.Figure
    """
    n_robots = len(ctr_configs_multi)
    if n_robots == 0:
        return go.Figure()

    all_pts = points[:, :3]
    ghost_max = 10000
    if len(all_pts) > ghost_max:
        ghost_idx = np.linspace(0, len(all_pts) - 1, ghost_max, dtype=int)
        ghost_pts = all_pts[ghost_idx]
    else:
        ghost_pts = all_pts

    traces = [
        # Network ghost
        go.Scatter3d(
            x=ghost_pts[:, 0], y=ghost_pts[:, 1], z=ghost_pts[:, 2],
            mode="markers", marker=dict(size=1, color="gray", opacity=0.3),
            name="Network", hoverinfo="skip",
        ),
    ]

    # Per-robot: base marker, trail, workspace sphere
    for ridx in range(n_robots):
        cfg = ctr_configs_multi[ridx]
        base = np.asarray(cfg["X"], dtype=float)
        color = _ROBOT_COLORS[ridx % len(_ROBOT_COLORS)]

        # Base marker
        traces.append(go.Scatter3d(
            x=[float(base[0])], y=[float(base[1])], z=[float(base[2])],
            mode="markers",
            marker=dict(size=8, color=color, symbol="diamond"),
            name=f"Robot {ridx} Base",
        ))

        # Printed trail for this robot (subsample to 5K points per robot)
        robot_passes = per_robot_passes.get(ridx, {})
        trail_segments: List[np.ndarray] = []
        _max_trail_per_robot = 5000
        _total_robot_nodes = sum(len(v) for v in robot_passes.values())
        for pk in sorted(robot_passes.keys()):
            seg_nodes = robot_passes[pk]
            if not seg_nodes:
                continue
            if _total_robot_nodes > _max_trail_per_robot:
                step_s = max(1, _total_robot_nodes // _max_trail_per_robot)
                seg_nodes = seg_nodes[::step_s]
            seg_pts = np.round(points[seg_nodes, :3], 2)
            if trail_segments:
                trail_segments.append(np.array([[np.nan, np.nan, np.nan]]))
            trail_segments.append(seg_pts)

        if trail_segments:
            trail_all = np.vstack(trail_segments)
            traces.append(go.Scatter3d(
                x=trail_all[:, 0], y=trail_all[:, 1], z=trail_all[:, 2],
                mode="lines", line=dict(color=color, width=3),
                name=f"Robot {ridx} Trail",
            ))

        # Workspace sphere — use ss_lim + ntnl_lim as approximate reach radius
        reach = float(cfg.get("ss_lim", 0)) + float(cfg.get("ntnl_lim", 0))
        if reach > 0:
            # Generate sphere mesh
            n_phi = 20
            n_theta = 20
            phi_vals = np.linspace(0, 2 * np.pi, n_phi)
            theta_vals = np.linspace(0, np.pi, n_theta)
            phi_grid, theta_grid = np.meshgrid(phi_vals, theta_vals)
            sx = base[0] + reach * np.sin(theta_grid) * np.cos(phi_grid)
            sy = base[1] + reach * np.sin(theta_grid) * np.sin(phi_grid)
            sz = base[2] + reach * np.cos(theta_grid)
            traces.append(go.Surface(
                x=sx, y=sy, z=sz,
                opacity=0.08,
                colorscale=[[0, color], [1, color]],
                showscale=False,
                name=f"Robot {ridx} Workspace",
                hoverinfo="skip",
            ))

    fig = go.Figure(data=traces)

    # Axis ranges
    pad = 5.0
    x_min, x_max = float(all_pts[:, 0].min()) - pad, float(all_pts[:, 0].max()) + pad
    y_min, y_max = float(all_pts[:, 1].min()) - pad, float(all_pts[:, 1].max()) + pad
    z_min, z_max = float(all_pts[:, 2].min()) - pad, float(all_pts[:, 2].max()) + pad
    for ridx in range(n_robots):
        base = np.asarray(ctr_configs_multi[ridx]["X"], dtype=float)
        reach = float(ctr_configs_multi[ridx].get("ss_lim", 0)) + float(ctr_configs_multi[ridx].get("ntnl_lim", 0))
        for i, (lo, hi) in enumerate([(x_min, x_max), (y_min, y_max), (z_min, z_max)]):
            v_lo = float(base[i]) - reach - pad
            v_hi = float(base[i]) + reach + pad
            if v_lo < lo:
                if i == 0: x_min = v_lo
                elif i == 1: y_min = v_lo
                else: z_min = v_lo
            if v_hi > hi:
                if i == 0: x_max = v_hi
                elif i == 1: y_max = v_hi
                else: z_max = v_hi

    fig.update_layout(
        scene=dict(
            xaxis=dict(range=[x_min, x_max]),
            yaxis=dict(range=[y_min, y_max]),
            zaxis=dict(range=[z_min, z_max]),
            aspectmode="data",
        ),
        margin=dict(l=30, r=30, t=50, b=30),
        title_text=f"Multi-CTR Overview — {n_robots} Robots",
    )

    return fig
