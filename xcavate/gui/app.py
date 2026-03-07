"""Streamlit GUI for X-CAVATE.

Provides a web interface for users who are not familiar with coding to
convert vascular network geometry into 3D printer G-code.

Launch with:
    streamlit run xcavate/gui/app.py
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

import streamlit as st

from xcavate.config import PathfindingAlgorithm, PrinterType, XcavateConfig

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="X-CAVATE",
    page_icon=":dna:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("X-CAVATE")
st.markdown(
    "Convert vascular network geometry into collision-free 3D printer G-code.  "
    "Upload your input files, configure parameters in the sidebar, then click "
    "**Run X-CAVATE**."
)

st.divider()

# ---------------------------------------------------------------------------
# Sidebar -- file uploads and parameter inputs
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Input Files")

    network_upload = st.file_uploader(
        "Network file (.txt)",
        type=["txt"],
        help="Text file containing vascular network coordinates.",
    )
    inletoutlet_upload = st.file_uploader(
        "Inlet / Outlet file (.txt)",
        type=["txt"],
        help="Text file with inlet and outlet node coordinates.",
    )

    st.divider()
    st.header("Required Parameters")

    nozzle_diameter = st.number_input(
        "Nozzle diameter (mm)",
        min_value=0.001,
        value=0.5,
        step=0.01,
        format="%.3f",
        help="Outer diameter of the print nozzle in millimeters.",
    )
    container_height = st.number_input(
        "Container height (mm)",
        min_value=0.1,
        value=10.0,
        step=0.5,
        format="%.1f",
        help="Height of the print container in millimeters.",
    )
    num_decimals = st.number_input(
        "Decimal places",
        min_value=0,
        max_value=10,
        value=3,
        step=1,
        help="Number of decimal places for output rounding.",
    )
    amount_up = st.number_input(
        "Amount up (mm)",
        min_value=0.0,
        value=10.0,
        step=0.5,
        format="%.1f",
        help="Distance to raise nozzle above the container between passes.",
    )

    _printer_labels = {
        "Pressure": PrinterType.PRESSURE,
        "Positive Ink": PrinterType.POSITIVE_INK,
        "Aerotech": PrinterType.AEROTECH,
    }
    printer_label = st.selectbox(
        "Printer type",
        options=list(_printer_labels.keys()),
        index=0,
    )
    printer_type = _printer_labels[printer_label]

    multimaterial = st.toggle("Multimaterial", value=False)

    # ------------------------------------------------------------------
    # Optional parameter sections (expandable)
    # ------------------------------------------------------------------

    st.divider()
    st.header("Optional Parameters")

    # -- Tolerancing --
    with st.expander("Tolerancing"):
        tolerance_flag = st.toggle("Enable tolerance", value=False)
        tolerance = st.number_input(
            "Tolerance",
            min_value=0.0,
            value=0.0,
            step=0.01,
            format="%.2f",
            help="Amount of tolerance. 0 means none.",
        )

    # -- Print Settings --
    with st.expander("Print Settings"):
        print_speed = st.number_input(
            "Print speed (mm/s)",
            min_value=0.001,
            value=1.0,
            step=0.1,
            format="%.3f",
        )
        flow = st.number_input(
            "Flow (mm^3/s)",
            min_value=0.0,
            value=0.1272265034574846,
            step=0.001,
            format="%.16f",
        )
        jog_speed = st.number_input(
            "Jog speed (mm/s)",
            min_value=0.001,
            value=5.0,
            step=0.5,
            format="%.2f",
        )
        jog_speed_lift = st.number_input(
            "Jog speed lift (mm/s)",
            min_value=0.001,
            value=0.25,
            step=0.01,
            format="%.2f",
        )
        initial_lift = st.number_input(
            "Initial lift (mm)",
            min_value=0.0,
            value=0.5,
            step=0.1,
            format="%.2f",
        )
        dwell_start = st.number_input(
            "Dwell start (s)",
            min_value=0.0,
            value=0.08,
            step=0.01,
            format="%.3f",
        )
        dwell_end = st.number_input(
            "Dwell end (s)",
            min_value=0.0,
            value=0.08,
            step=0.01,
            format="%.3f",
        )

    # -- Geometry --
    with st.expander("Geometry"):
        container_x = st.number_input(
            "Container X (mm)", min_value=0.0, value=50.0, step=1.0, format="%.1f",
        )
        container_y = st.number_input(
            "Container Y (mm)", min_value=0.0, value=50.0, step=1.0, format="%.1f",
        )
        scale_factor = st.number_input(
            "Scale factor", min_value=0.001, value=1.0, step=0.1, format="%.3f",
        )
        top_padding = st.number_input(
            "Top padding (mm)", min_value=0.0, value=0.0, step=0.5, format="%.1f",
        )

    # -- Downsampling --
    with st.expander("Downsampling"):
        downsample = st.toggle("Enable downsampling", value=False)
        downsample_factor = st.number_input(
            "Downsample factor",
            min_value=1,
            value=1,
            step=1,
            help="Factor by which to downsample the network after processing.",
        )

    # -- Multimaterial --
    with st.expander("Multimaterial"):
        offset_x = st.number_input(
            "Offset X (mm)", min_value=0.0, value=103.0, step=1.0, format="%.1f",
        )
        offset_y = st.number_input(
            "Offset Y (mm)", value=0.5, step=0.1, format="%.1f",
        )
        front_nozzle = st.number_input(
            "Front nozzle",
            min_value=1,
            max_value=2,
            value=1,
            step=1,
            help="1 = venous nozzle in front, 2 = venous nozzle behind.",
        )
        printhead_1 = st.text_input("Printhead 1 name", value="Aa")
        printhead_2 = st.text_input("Printhead 2 name", value="Ab")
        axis_1 = st.text_input("Axis 1 name", value="A")
        axis_2 = st.text_input("Axis 2 name", value="B")
        resting_pressure = st.number_input(
            "Resting pressure (psi)", min_value=0.0, value=0.0, step=0.5, format="%.1f",
        )
        active_pressure = st.number_input(
            "Active pressure (psi)", min_value=0.0, value=5.0, step=0.5, format="%.1f",
        )

    # -- Positive Ink Displacement --
    with st.expander("Positive Ink Displacement"):
        positive_ink_start = st.number_input(
            "Start", min_value=0.0, value=0.0, step=0.1, format="%.2f",
            key="pi_start",
        )
        positive_ink_end = st.number_input(
            "End", min_value=0.0, value=0.0, step=0.1, format="%.2f",
            key="pi_end",
        )
        positive_ink_radii = st.toggle("Use radii", value=False, key="pi_radii")
        positive_ink_diam = st.number_input(
            "Diameter", min_value=0.001, value=1.0, step=0.1, format="%.3f",
            key="pi_diam",
        )
        positive_ink_syringe_diam = st.number_input(
            "Syringe diameter", min_value=0.001, value=1.0, step=0.1, format="%.3f",
            key="pi_syr_diam",
        )
        positive_ink_factor = st.number_input(
            "Factor", min_value=0.0, value=1.0, step=0.1, format="%.3f",
            key="pi_factor",
        )
        st.markdown("**Arterial / Venous overrides**")
        positive_ink_start_arterial = st.number_input(
            "Start (arterial)", min_value=0.0, value=0.0, step=0.1, format="%.2f",
            key="pi_start_art",
        )
        positive_ink_start_venous = st.number_input(
            "Start (venous)", min_value=0.0, value=0.0, step=0.1, format="%.2f",
            key="pi_start_ven",
        )
        positive_ink_end_arterial = st.number_input(
            "End (arterial)", min_value=0.0, value=0.0, step=0.1, format="%.2f",
            key="pi_end_art",
        )
        positive_ink_end_venous = st.number_input(
            "End (venous)", min_value=0.0, value=0.0, step=0.1, format="%.2f",
            key="pi_end_ven",
        )

    # -- Advanced --
    with st.expander("Advanced"):
        custom_gcode = st.toggle("Custom G-code", value=False)
        _algo_labels = {
            "DFS": PathfindingAlgorithm.DFS,
            "Sweep Line": PathfindingAlgorithm.SWEEP_LINE,
        }
        algo_label = st.selectbox(
            "Pathfinding algorithm",
            options=list(_algo_labels.keys()),
            index=0,
        )
        algorithm = _algo_labels[algo_label]
        num_overlap = st.number_input(
            "Overlap nodes", min_value=0, value=0, step=1,
        )
        generate_plots = st.toggle("Generate plots", value=True)
        speed_calc = st.toggle("Speed calculation", value=False)


# ---------------------------------------------------------------------------
# Helper: build config from sidebar state
# ---------------------------------------------------------------------------

def _build_config(
    network_path: Path,
    inletoutlet_path: Path,
    output_dir: Path,
) -> XcavateConfig:
    """Assemble an XcavateConfig from the current sidebar widget values."""
    return XcavateConfig(
        network_file=network_path,
        inletoutlet_file=inletoutlet_path,
        nozzle_diameter=nozzle_diameter,
        container_height=container_height,
        num_decimals=num_decimals,
        amount_up=amount_up,
        printer_type=printer_type,
        multimaterial=multimaterial,
        tolerance_flag=tolerance_flag,
        tolerance=tolerance,
        print_speed=print_speed,
        flow=flow,
        jog_speed=jog_speed,
        jog_speed_lift=jog_speed_lift,
        initial_lift=initial_lift,
        dwell_start=dwell_start,
        dwell_end=dwell_end,
        container_x=container_x,
        container_y=container_y,
        scale_factor=scale_factor,
        top_padding=top_padding,
        downsample=downsample,
        downsample_factor=downsample_factor,
        offset_x=offset_x,
        offset_y=offset_y,
        front_nozzle=front_nozzle,
        printhead_1=printhead_1,
        printhead_2=printhead_2,
        axis_1=axis_1,
        axis_2=axis_2,
        resting_pressure=resting_pressure,
        active_pressure=active_pressure,
        positive_ink_start=positive_ink_start,
        positive_ink_end=positive_ink_end,
        positive_ink_radii=positive_ink_radii,
        positive_ink_diam=positive_ink_diam,
        positive_ink_syringe_diam=positive_ink_syringe_diam,
        positive_ink_factor=positive_ink_factor,
        positive_ink_start_arterial=positive_ink_start_arterial,
        positive_ink_start_venous=positive_ink_start_venous,
        positive_ink_end_arterial=positive_ink_end_arterial,
        positive_ink_end_venous=positive_ink_end_venous,
        custom_gcode=custom_gcode,
        algorithm=algorithm,
        num_overlap=num_overlap,
        generate_plots=generate_plots,
        speed_calc=speed_calc,
        output_dir=output_dir,
    )


# ---------------------------------------------------------------------------
# Helper: collect downloadable output files
# ---------------------------------------------------------------------------

def _read_file_bytes(path: Path) -> Optional[bytes]:
    """Return file contents as bytes, or None if the file does not exist."""
    if path.exists():
        return path.read_bytes()
    return None


def _find_gcode_file(gcode_dir: Path) -> Optional[Path]:
    """Return the first G-code .txt file found in the gcode directory."""
    if not gcode_dir.exists():
        return None
    for f in sorted(gcode_dir.iterdir()):
        if f.suffix == ".txt" and f.name.startswith("gcode_"):
            return f
    return None


def _find_all_gcode_files(gcode_dir: Path) -> list[Path]:
    """Return all G-code .txt files found in the gcode directory."""
    if not gcode_dir.exists():
        return []
    return sorted(f for f in gcode_dir.iterdir() if f.suffix == ".txt" and f.name.startswith("gcode_"))


def _find_coordinate_files(graph_dir: Path) -> list[Path]:
    """Return all coordinate output files."""
    if not graph_dir.exists():
        return []
    return sorted(
        f for f in graph_dir.iterdir()
        if f.suffix == ".txt" and f.name != "graph.txt" and f.name != "special_nodes.txt"
    )


# ---------------------------------------------------------------------------
# Pipeline step descriptions (used for progress bar)
# ---------------------------------------------------------------------------

_STEP_DESCRIPTIONS = {
    1: "Reading network and inlet/outlet files",
    2: "Interpolating network to nozzle resolution",
    3: "Building adjacency graph and detecting branchpoints",
    4: "Generating collision-free print passes",
    5: "Post-processing: subdivision, gap closure, overlap",
    6: "Processing multimaterial passes",
    7: "Writing output files and G-code",
}

_TOTAL_STEPS = 7


# ---------------------------------------------------------------------------
# Main area -- run button and results
# ---------------------------------------------------------------------------

run_button = st.button(
    "Run X-CAVATE",
    type="primary",
    use_container_width=True,
    disabled=(network_upload is None or inletoutlet_upload is None),
)

if network_upload is None or inletoutlet_upload is None:
    st.info("Upload both a network file and an inlet/outlet file in the sidebar to get started.")

if run_button:
    # Create a temporary working directory
    tmp_dir = Path(tempfile.mkdtemp(prefix="xcavate_"))
    input_dir = tmp_dir / "inputs"
    input_dir.mkdir()
    output_dir = tmp_dir / "outputs"
    output_dir.mkdir()

    # Save uploaded files
    network_path = input_dir / "network.txt"
    network_path.write_bytes(network_upload.getvalue())

    inletoutlet_path = input_dir / "inletoutlet.txt"
    inletoutlet_path.write_bytes(inletoutlet_upload.getvalue())

    # Build config
    try:
        config = _build_config(network_path, inletoutlet_path, output_dir)
    except Exception as exc:
        st.error(f"Invalid configuration: {exc}")
        st.stop()

    # Progress bar and status
    progress_bar = st.progress(0, text="Initializing...")
    status_text = st.empty()

    def _progress_callback(step: int, description: str) -> None:
        """Update the Streamlit progress bar from the pipeline."""
        fraction = step / _TOTAL_STEPS
        progress_bar.progress(fraction, text=f"Step {step}/{_TOTAL_STEPS}: {description}")

    # Run the pipeline
    try:
        from xcavate.pipeline import run_xcavate

        result = run_xcavate(config, progress_cb=_progress_callback)
        progress_bar.progress(1.0, text="Complete!")
        st.success("X-CAVATE finished successfully.")
    except Exception as exc:
        progress_bar.empty()
        st.error(f"Pipeline failed: {exc}")
        st.exception(exc)
        # Clean up temp directory on failure
        shutil.rmtree(tmp_dir, ignore_errors=True)
        st.stop()

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("3D Visualization")

    if config.generate_plots:
        from xcavate.viz.plotting import create_network_plot

        # Single-material plot
        if result.get("print_passes_sm") is not None and result.get("points") is not None:
            st.markdown("**Single Material Print Passes**")
            fig_sm = create_network_plot(
                result["print_passes_sm"],
                result["points"],
                title="Single Material",
            )
            st.plotly_chart(fig_sm, use_container_width=True)

        # Multimaterial plot
        if result.get("print_passes_mm") is not None and result.get("points") is not None:
            from xcavate.core.multimaterial import generate_multimaterial_colors

            st.markdown("**Multimaterial Print Passes**")
            colors = generate_multimaterial_colors(
                result["print_passes_mm"], result["material_map"],
            )
            fig_mm = create_network_plot(
                result["print_passes_mm"],
                result["points"],
                title="Multimaterial",
                colors=colors,
            )
            st.plotly_chart(fig_mm, use_container_width=True)
    else:
        st.info("Plot generation was disabled. Enable it in the Advanced section to see visualizations.")

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("Download Results")

    dl_cols = st.columns(3)

    # G-code files
    with dl_cols[0]:
        st.markdown("**G-code**")
        gcode_files = _find_all_gcode_files(config.gcode_dir)
        if gcode_files:
            for gf in gcode_files:
                data = _read_file_bytes(gf)
                if data:
                    st.download_button(
                        label=gf.name,
                        data=data,
                        file_name=gf.name,
                        mime="text/plain",
                        key=f"dl_gcode_{gf.name}",
                    )
        else:
            st.caption("No G-code files generated.")

    # Coordinate files
    with dl_cols[1]:
        st.markdown("**Coordinate Files**")
        coord_files = _find_coordinate_files(config.graph_dir)
        if coord_files:
            for cf in coord_files:
                data = _read_file_bytes(cf)
                if data:
                    st.download_button(
                        label=cf.name,
                        data=data,
                        file_name=cf.name,
                        mime="text/plain",
                        key=f"dl_coord_{cf.name}",
                    )
        else:
            st.caption("No coordinate files generated.")

    # Changelog
    with dl_cols[2]:
        st.markdown("**Changelog**")
        changelog_path = config.output_dir / "changelog.txt"
        changelog_data = _read_file_bytes(changelog_path)
        if changelog_data:
            st.download_button(
                label="changelog.txt",
                data=changelog_data,
                file_name="changelog.txt",
                mime="text/plain",
                key="dl_changelog",
            )
        else:
            st.caption("No changelog generated.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Allow running directly: python xcavate/gui/app.py
    # Streamlit must be invoked as: streamlit run xcavate/gui/app.py
    import sys

    try:
        from streamlit.web.cli import main as st_main

        sys.argv = ["streamlit", "run", __file__]
        st_main()
    except ImportError:
        print(
            "Streamlit is not installed. Install it with:\n"
            "  pip install streamlit\n"
            "Then run:\n"
            "  streamlit run xcavate/gui/app.py"
        )
        sys.exit(1)
