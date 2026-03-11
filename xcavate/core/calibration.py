"""Calibration helpers: validation and volumetric flow-rate computation.

Replaces the standalone ``calibration_validation.py`` script with reusable
functions that can be called from both the CLI and the Streamlit GUI.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def validate_calibration(
    target_diameters: list[float],
    measured_csv_bytes: bytes,
    measurements_per_target: int = 3,
) -> dict:
    """Compare target filament diameters against measured values.

    Args:
        target_diameters: Expected diameters in mm.
        measured_csv_bytes: Raw bytes of a CSV file with a ``"Length"`` column
            containing measured diameters in **microns**.
        measurements_per_target: Number of measurement rows to average per
            target diameter.

    Returns:
        Dict with keys:
            - ``target``: list of target diameters.
            - ``measured_avg``: list of averaged measured diameters (mm).
            - ``percent_error``: list of percent-error values.
            - ``csv_bytes``: CSV report as bytes (ready for download).
            - ``html_bytes``: Plotly table+chart as HTML bytes.
    """
    # Read CSV from bytes and extract the "Length" column
    df_raw = pd.read_csv(io.BytesIO(measured_csv_bytes))
    diameter_array = df_raw["Length"].to_numpy() / 1000  # microns -> mm

    # Average every `measurements_per_target` rows
    n_targets = len(target_diameters)
    expected_rows = n_targets * measurements_per_target
    diameter_array = diameter_array[:expected_rows]
    diameter_averages = np.mean(
        diameter_array.reshape(n_targets, measurements_per_target), axis=1,
    )

    # Percent error
    targets_arr = np.array(target_diameters)
    percent_error = ((diameter_averages - targets_arr) / targets_arr) * 100

    # Round for display
    percent_error_rounded = np.round(percent_error, 3).tolist()
    diameter_averages_rounded = np.round(diameter_averages, 3).tolist()
    target_diameters_rounded = [round(t, 3) for t in target_diameters]

    # Build CSV report
    df_report = pd.DataFrame({
        "Target Diameters (mm)": target_diameters_rounded,
        "Average Measured Diameters (mm)": diameter_averages_rounded,
        "Percent Error (%)": percent_error_rounded,
    })
    csv_bytes = df_report.to_csv(index=False).encode("utf-8")

    # Build Plotly figure (table + bar chart)
    fig = go.Figure(data=[
        go.Table(
            header=dict(values=list(df_report.columns)),
            cells=dict(values=[
                target_diameters_rounded,
                diameter_averages_rounded,
                percent_error_rounded,
            ]),
        ),
    ])
    fig.update_layout(
        title={"text": "Percent Error", "y": 0.9, "x": 0.5,
               "xanchor": "center", "yanchor": "top"},
        font_family="Avenir",
    )
    html_bytes = fig.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8")

    return {
        "target": target_diameters_rounded,
        "measured_avg": diameter_averages_rounded,
        "percent_error": percent_error_rounded,
        "csv_bytes": csv_bytes,
        "html_bytes": html_bytes,
        "figure": fig,
    }


def compute_flow_rate(
    target_diameters: list[float],
    measured_csv_bytes: bytes,
    print_speeds: list[float],
    measurements_per_target: int = 3,
    output_dir: Path | None = None,
) -> dict:
    """Compute volumetric flow rate (Q) from calibration measurements.

    During calibration the pressure is held constant and the print speed is
    varied for each target diameter group.  Each group therefore has its own
    print speed, and Q = v_i * pi * r_i^2 should be roughly constant across
    groups (since Q is set by the constant pressure).

    Args:
        target_diameters: Expected diameters in mm (used only to determine the
            number of groups).
        measured_csv_bytes: Raw bytes of a CSV with a ``"Length"`` column
            containing measured diameters in **microns**.
        print_speeds: Print speeds in mm/s used during calibration, one per
            target diameter group (same order as *target_diameters*).
        measurements_per_target: Number of measurement rows to average per
            target diameter.
        output_dir: If provided, ``Q_pressure.txt`` and
            ``radii_pressure.html`` are written here.

    Returns:
        Dict with keys ``q_value``, ``figure``, ``q_txt_bytes``,
        ``html_bytes``.
    """
    # Parse CSV
    df_raw = pd.read_csv(io.BytesIO(measured_csv_bytes))
    diameter_array = df_raw["Length"].to_numpy() / 1000  # microns -> mm

    n_targets = len(target_diameters)
    expected_rows = n_targets * measurements_per_target
    diameter_array = diameter_array[:expected_rows]
    diameter_averages = np.mean(
        diameter_array.reshape(n_targets, measurements_per_target), axis=1,
    )

    # Measured radii and per-target Q  (one speed per group)
    radii = diameter_averages / 2
    speeds_arr = np.array(print_speeds[:n_targets])
    q_per_target = speeds_arr * np.pi * radii ** 2
    q_value = float(np.mean(q_per_target))

    # Plotly figure: speed vs radius
    fig = go.Figure(
        data=go.Scatter(
            x=np.round(speeds_arr, 4).tolist(),
            y=np.round(radii, 4).tolist(),
            mode="lines+markers",
            name="Calibration Curve",
        ),
    )
    fig.update_layout(
        title={"text": "Radii vs Speed (Calibration Curve)", "x": 0.5},
        xaxis_title="Speed (mm/s)",
        yaxis_title="Radius (mm)",
        font_family="Avenir",
    )

    q_txt_bytes = f"{q_value}".encode("utf-8")
    html_bytes = fig.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8")

    # Optionally persist to disk
    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "Q_pressure.txt").write_bytes(q_txt_bytes)
        (output_dir / "radii_pressure.html").write_bytes(html_bytes)

    return {
        "q_value": q_value,
        "figure": fig,
        "q_txt_bytes": q_txt_bytes,
        "html_bytes": html_bytes,
    }
