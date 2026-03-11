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

from xcavate.config import OverlapAlgorithm, PathfindingAlgorithm, PrinterType, XcavateConfig

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
# Session state defaults
# ---------------------------------------------------------------------------

if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None
if "pipeline_config" not in st.session_state:
    st.session_state.pipeline_config = None
if "pipeline_output_dir" not in st.session_state:
    st.session_state.pipeline_output_dir = None

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
        help="Hardware target: Pressure (pneumatic extrusion), Positive Ink (displacement pump), or Aerotech (6-axis motion controller).",
    )
    printer_type = _printer_labels[printer_label]

    multimaterial = st.toggle(
        "Multimaterial", value=False,
        help="Enable two-nozzle arterial/venous printing. Requires a 5-column input file (x, y, z, radius, artven flag).",
    )

    # ------------------------------------------------------------------
    # Optional parameter sections (expandable)
    # ------------------------------------------------------------------

    st.divider()
    st.header("Optional Parameters")

    # -- Tolerancing --
    with st.expander("Tolerancing"):
        tolerance_flag = st.toggle(
            "Enable tolerance", value=False,
            help="When enabled, nodes within the tolerance distance are allowed in the same pass even if one geometrically blocks the other.",
        )
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
            help="Nozzle travel speed during extrusion. Typical range: 0.5–5.0 mm/s depending on ink viscosity.",
        )
        flow = st.number_input(
            "Flow (mm^3/s)",
            min_value=0.0,
            value=0.1609429886081009,
            step=0.001,
            format="%.16f",
            help="Volumetric flow rate used for speed calculation mode. Also used to compute per-node print speed when 'Speed calculation' is on.",
        )
        jog_speed = st.number_input(
            "Jog speed (mm/s)",
            min_value=0.001,
            value=5.0,
            step=0.5,
            format="%.2f",
            help="Speed for rapid non-printing travel moves between passes.",
        )
        jog_speed_lift = st.number_input(
            "Jog speed lift (mm/s)",
            min_value=0.001,
            value=0.25,
            step=0.01,
            format="%.2f",
            help="Speed for the gentle vertical lift at the end of each pass before rapid retraction.",
        )
        initial_lift = st.number_input(
            "Initial lift (mm)",
            min_value=0.0,
            value=0.5,
            step=0.1,
            format="%.2f",
            help="Height the nozzle lifts after finishing a pass before traveling to the next one.",
        )
        if printer_type == PrinterType.AEROTECH:
            dwell_start = st.number_input(
                "Dwell start (s)",
                min_value=0.0,
                value=0.08,
                step=0.01,
                format="%.3f",
                help="Pause duration (seconds) after starting extrusion, before the nozzle begins moving. Allows pressure to stabilize.",
            )
            dwell_end = st.number_input(
                "Dwell end (s)",
                min_value=0.0,
                value=0.08,
                step=0.01,
                format="%.3f",
                help="Pause duration (seconds) after the nozzle stops moving, before extrusion is turned off. Allows pressure bleed-off.",
            )
        else:
            dwell_start = 0.08
            dwell_end = 0.08

    # -- Geometry --
    with st.expander("Geometry"):
        container_x = st.number_input(
            "Container X (mm)", min_value=0.0, value=50.0, step=1.0, format="%.1f",
            help="Width of the print container (mm). Used to calculate centering instructions for the operator.",
        )
        container_y = st.number_input(
            "Container Y (mm)", min_value=0.0, value=50.0, step=1.0, format="%.1f",
            help="Depth of the print container (mm). Used to calculate centering instructions for the operator.",
        )
        scale_factor = st.number_input(
            "Scale factor", min_value=0.001, value=1.0, step=0.1, format="%.3f",
            help="Multiplier applied to all coordinates after unit conversion. Use 1.0 for no scaling.",
        )
        top_padding = st.number_input(
            "Top padding (mm)", min_value=0.0, value=0.0, step=0.5, format="%.1f",
            help="Extra clearance (mm) added above the highest network point for safe nozzle retraction moves.",
        )

    # -- Downsampling --
    with st.expander("Downsampling"):
        downsample = st.toggle(
            "Enable downsampling", value=False,
            help="Reduce point density to speed up printing. Branchpoints and endpoints are always preserved.",
        )
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
            help="Horizontal distance (mm) between the two printheads. Measured by positioning both nozzles on the same calibration point.",
        )
        offset_y = st.number_input(
            "Offset Y (mm)", value=0.5, step=0.1, format="%.1f",
            help="Vertical fine-tuning offset (mm) between the two printheads.",
        )
        front_nozzle = st.number_input(
            "Front nozzle",
            min_value=1,
            max_value=2,
            value=1,
            step=1,
            help="1 = venous nozzle in front, 2 = venous nozzle behind.",
        )
        printhead_1 = st.text_input(
            "Printhead 1 name", value="Aa",
            help="Axis designation for the arterial printhead in G-code commands (e.g. 'Aa').",
        )
        printhead_2 = st.text_input(
            "Printhead 2 name", value="Ab",
            help="Axis designation for the venous printhead in G-code commands (e.g. 'Ab').",
        )
        axis_1 = st.text_input(
            "Axis 1 name", value="A",
            help="Z-axis letter for the arterial printhead (e.g. 'A'). Must match the motion controller configuration.",
        )
        axis_2 = st.text_input(
            "Axis 2 name", value="B",
            help="Z-axis letter for the venous printhead (e.g. 'B'). Must match the motion controller configuration.",
        )
        jog_translation = st.number_input(
            "Jog translation speed (mm/s)",
            min_value=0.001,
            value=10.0,
            step=1.0,
            format="%.1f",
            help="Speed for rapid travel moves between nozzles during multimaterial printhead switching.",
        )
        resting_pressure = st.number_input(
            "Resting pressure (psi)", min_value=0.0, value=0.0, step=0.5, format="%.1f",
            help="Pneumatic pressure (psi) applied to the inactive printhead during multimaterial printing.",
        )
        active_pressure = st.number_input(
            "Active pressure (psi)", min_value=0.0, value=5.0, step=0.5, format="%.1f",
            help="Pneumatic pressure (psi) applied to the active printhead during extrusion.",
        )

    # -- Positive Ink Displacement --
    with st.expander("Positive Ink Displacement"):
        positive_ink_radii = st.toggle(
            "Use radii", value=False, key="pi_radii",
            help="When enabled, uses per-node vessel radii from SimVascular data instead of a fixed diameter for extrusion calculations.",
        )
        positive_ink_diam = st.number_input(
            "Diameter", min_value=0.001, value=1.0, step=0.1, format="%.3f",
            key="pi_diam",
            help="Fixed vessel diameter (mm) used for extrusion calculations when 'Use radii' is off.",
        )
        positive_ink_syringe_diam = st.number_input(
            "Syringe diameter", min_value=0.001, value=1.0, step=0.1, format="%.3f",
            key="pi_syr_diam",
            help="Inner diameter (mm) of the syringe barrel. Used to compute plunger displacement from vessel geometry.",
        )
        positive_ink_factor = st.number_input(
            "Factor", min_value=0.0, value=1.0, step=0.1, format="%.3f",
            key="pi_factor",
            help="Scaling multiplier for computed extrusion amounts. Use 1.0 for default; increase to extrude more ink per unit length.",
        )

        separate_artven = st.toggle(
            "Separate arterial / venous",
            value=False,
            key="pi_separate_artven",
            help="Enable to set different start/end displacements for arterial and venous syringes in multimaterial prints.",
        )

        if separate_artven:
            positive_ink_start = 0.0
            positive_ink_end = 0.0
            positive_ink_start_arterial = st.number_input(
                "Start (arterial)", min_value=0.0, value=0.0, step=0.1, format="%.2f",
                key="pi_start_art",
                help="Plunger displacement (mm) for the arterial syringe at the start of each pass. Typical values: 0.0\u20131.0 mm.",
            )
            positive_ink_start_venous = st.number_input(
                "Start (venous)", min_value=0.0, value=0.0, step=0.1, format="%.2f",
                key="pi_start_ven",
                help="Plunger displacement (mm) for the venous syringe at the start of each pass. Typical values: 0.0\u20131.0 mm.",
            )
            positive_ink_end_arterial = st.number_input(
                "End (arterial)", min_value=-10.0, value=0.0, step=0.1, format="%.2f",
                key="pi_end_art",
                help="Plunger displacement (mm) for the arterial syringe at the end of each pass. Typical values: -1.0 to 0.0 mm (negative retracts).",
            )
            positive_ink_end_venous = st.number_input(
                "End (venous)", min_value=-10.0, value=0.0, step=0.1, format="%.2f",
                key="pi_end_ven",
                help="Plunger displacement (mm) for the venous syringe at the end of each pass. Typical values: -1.0 to 0.0 mm (negative retracts).",
            )
        else:
            positive_ink_start = st.number_input(
                "Start", min_value=0.0, value=0.0, step=0.1, format="%.2f",
                key="pi_start",
                help="Plunger displacement (mm) added at the start of each print pass to prime ink flow. Typical values: 0.0\u20131.0 mm. Use 0.0 to disable.",
            )
            positive_ink_end = st.number_input(
                "End", min_value=-10.0, value=0.0, step=0.1, format="%.2f",
                key="pi_end",
                help="Plunger displacement (mm) added at the end of each print pass for retraction. Typical values: -1.0 to 0.0 mm (negative retracts the plunger). Use 0.0 to disable.",
            )
            positive_ink_start_arterial = 0.0
            positive_ink_start_venous = 0.0
            positive_ink_end_arterial = 0.0
            positive_ink_end_venous = 0.0

    # -- Advanced --
    with st.expander("Advanced"):
        custom_gcode = st.toggle(
            "Custom G-code",
            value=False,
            help="Enable to provide custom G-code templates for header, "
                 "extrusion start/stop, pressure, and dwell sections.",
        )
        _algo_labels = {
            "DFS": PathfindingAlgorithm.DFS,
            "Sweep Line": PathfindingAlgorithm.SWEEP_LINE,
        }
        algo_label = st.selectbox(
            "Pathfinding algorithm",
            options=list(_algo_labels.keys()),
            index=0,
            help="DFS: thorough collision detection via depth-first search. Sweep Line: faster bottom-up approach for large networks.",
        )
        algorithm = _algo_labels[algo_label]
        num_overlap = st.number_input(
            "Overlap nodes", min_value=0, value=0, step=1,
            help="Number of nodes to retrace at pass boundaries to bridge small gaps. Use 0 to disable.",
        )
        _overlap_algo_labels = {
            "Retrace (original)": OverlapAlgorithm.RETRACE,
            "Consecutive (fast)": OverlapAlgorithm.CONSECUTIVE,
        }
        overlap_algo_label = st.selectbox(
            "Overlap algorithm",
            options=list(_overlap_algo_labels.keys()),
            index=0,
            help="'Retrace' scans all previous passes for shared nodes (original behavior). "
                 "'Consecutive' only checks adjacent pass pairs (faster).",
        )
        overlap_algorithm = _overlap_algo_labels[overlap_algo_label]
        generate_plots = st.toggle(
            "Generate plots", value=True,
            help="Create interactive 3D HTML visualizations of the network and print passes in the output folder.",
        )
        speed_calc = st.toggle(
            "Speed calculation", value=False,
            help="Compute per-node print speed from vessel radius and flow rate instead of using a fixed print speed.",
        )
        close_sm = st.toggle(
            "Gap closure (single-material)", value=False,
            help="Load gap closure extension files for single-material prints from the inputs/extension directory.",
        )
        if close_sm:
            close_sm_pass_upload = st.file_uploader(
                "Pass indices (SM)", type=["txt"], key="close_sm_pass",
                help="Text file listing pass indices to extend (one per line). View X-CAVATE manual for more information.",
            )
            close_sm_delta_upload = st.file_uploader(
                "Deltas (SM)", type=["txt"], key="close_sm_delta",
                help="Text file with extension deltas (x y z per line). View X-CAVATE manual for more information.",
            )
        else:
            close_sm_pass_upload = None
            close_sm_delta_upload = None
        close_mm = st.toggle(
            "Gap closure (multimaterial)", value=False,
            help="Load gap closure extension files for multimaterial prints from the inputs/extension directory.",
        )
        if close_mm:
            close_mm_pass_upload = st.file_uploader(
                "Pass indices (MM)", type=["txt"], key="close_mm_pass",
                help="Text file listing pass indices to extend (one per line). View X-CAVATE manual for more information.",
            )
            close_mm_delta_upload = st.file_uploader(
                "Deltas (MM)", type=["txt"], key="close_mm_delta",
                help="Text file with extension deltas (x y z per line). View X-CAVATE manual for more information.",
            )
        else:
            close_mm_pass_upload = None
            close_mm_delta_upload = None


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
        jog_translation=jog_translation,
        resting_pressure=resting_pressure,
        active_pressure=active_pressure,
        positive_ink_start=positive_ink_start,
        positive_ink_end=positive_ink_end,
        positive_ink_radii=positive_ink_radii,
        positive_ink_diam=positive_ink_diam,
        positive_ink_syringe_diam=positive_ink_syringe_diam,
        positive_ink_factor=positive_ink_factor,
        positive_ink_start_arterial=positive_ink_start_arterial if separate_artven else positive_ink_start,
        positive_ink_start_venous=positive_ink_start_venous if separate_artven else positive_ink_start,
        positive_ink_end_arterial=positive_ink_end_arterial if separate_artven else positive_ink_end,
        positive_ink_end_venous=positive_ink_end_venous if separate_artven else positive_ink_end,
        custom_gcode=custom_gcode,
        algorithm=algorithm,
        num_overlap=num_overlap,
        overlap_algorithm=overlap_algorithm,
        generate_plots=generate_plots,
        speed_calc=speed_calc,
        close_sm=close_sm,
        close_mm=close_mm,
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
# Custom G-code Template Editor (main area, shown when toggle is on)
# ---------------------------------------------------------------------------

# Define default placeholder text for all custom G-code fields.
_PLACEHOLDER = "; Paste your custom G-code here\n"

# Initialise session-state keys for all custom G-code fields so that the
# text areas survive Streamlit re-runs and the values are accessible even
# when the Custom G-code toggle is off.
_CUSTOM_GCODE_FIELDS = {
    "cg_header":                {"label": "Header code",                       "file": "header_code.txt"},
    "cg_start_extrusion":       {"label": "Start extrusion",                   "file": "start_extrusion_code.txt"},
    "cg_stop_extrusion":        {"label": "Stop extrusion",                    "file": "stop_extrusion_code.txt"},
    "cg_start_extrusion_ph1":   {"label": "Start extrusion \u2014 Printhead 1",   "file": "start_extrusion_code_printhead1.txt"},
    "cg_start_extrusion_ph2":   {"label": "Start extrusion \u2014 Printhead 2",   "file": "start_extrusion_code_printhead2.txt"},
    "cg_stop_extrusion_ph1":    {"label": "Stop extrusion \u2014 Printhead 1",    "file": "stop_extrusion_code_printhead1.txt"},
    "cg_stop_extrusion_ph2":    {"label": "Stop extrusion \u2014 Printhead 2",    "file": "stop_extrusion_code_printhead2.txt"},
    "cg_active_pressure_ph1":   {"label": "Active pressure \u2014 Printhead 1",   "file": "active_pressure_printhead1.txt"},
    "cg_active_pressure_ph2":   {"label": "Active pressure \u2014 Printhead 2",   "file": "active_pressure_printhead2.txt"},
    "cg_rest_pressure_ph1":     {"label": "Resting pressure \u2014 Printhead 1",  "file": "rest_pressure_printhead1.txt"},
    "cg_rest_pressure_ph2":     {"label": "Resting pressure \u2014 Printhead 2",  "file": "rest_pressure_printhead2.txt"},
    "cg_dwell_start":           {"label": "Dwell code (start of pass)",        "file": "dwell_start.txt"},
    "cg_dwell_end":             {"label": "Dwell code (end of pass)",          "file": "dwell_end.txt"},
}

for _key in _CUSTOM_GCODE_FIELDS:
    if _key not in st.session_state:
        st.session_state[_key] = ""

# ---------------------------------------------------------------------------
# Main area -- top-level tabs
# ---------------------------------------------------------------------------

tab_names = ["Pipeline"]
if custom_gcode:
    tab_names.append("Custom G-code")
tab_names += ["Print Instructions", "Calibration Validation"]

tabs = st.tabs(tab_names)
idx = 0
main_tab = tabs[idx]; idx += 1
cg_tab = tabs[idx] if custom_gcode else None; idx += (1 if custom_gcode else 0)
instr_tab = tabs[idx]; idx += 1
cal_tab = tabs[idx]

if cg_tab is not None:
    with cg_tab:
        st.subheader("Custom G-code Templates")
        st.caption(
            "Paste your printer-specific G-code snippets below. These replace "
            "the default commands for header, extrusion start/stop, pressure "
            "control, and dwell sections in the final output file."
        )

        cg_tabs = st.tabs(["Header", "Single Material", "Multimaterial", "Dwell"])

        # --- Tab 1: Header ---
        with cg_tabs[0]:
            st.markdown(
                "Custom G-code for the **header** section of the output file. "
                "Include any code required for your printer, such as establishing "
                "connections between external pressure boxes and syringes."
            )
            st.session_state["cg_header"] = st.text_area(
                "Header code",
                value=st.session_state["cg_header"],
                height=200,
                placeholder="; e.g. G28 ; Home all axes\n; M106 S255 ; Fan on",
                key="ta_cg_header",
            )

        # --- Tab 2: Single Material ---
        with cg_tabs[1]:
            st.markdown(
                "Custom G-code for **starting** and **stopping** extrusion in "
                "single-material mode."
            )
            sm_cols = st.columns(2)
            with sm_cols[0]:
                st.session_state["cg_start_extrusion"] = st.text_area(
                    "Start extrusion",
                    value=st.session_state["cg_start_extrusion"],
                    height=180,
                    placeholder="; G-code to begin extrusion",
                    key="ta_cg_start_extrusion",
                )
            with sm_cols[1]:
                st.session_state["cg_stop_extrusion"] = st.text_area(
                    "Stop extrusion",
                    value=st.session_state["cg_stop_extrusion"],
                    height=180,
                    placeholder="; G-code to stop extrusion",
                    key="ta_cg_stop_extrusion",
                )

        # --- Tab 3: Multimaterial ---
        with cg_tabs[2]:
            st.markdown(
                "Custom G-code for multimaterial printing. Provide start/stop "
                "extrusion and active/resting pressure codes for **each printhead**."
            )

            st.markdown("##### Extrusion Start / Stop")
            mm_cols_a = st.columns(2)
            with mm_cols_a[0]:
                st.session_state["cg_start_extrusion_ph1"] = st.text_area(
                    "Start extrusion \u2014 Printhead 1",
                    value=st.session_state["cg_start_extrusion_ph1"],
                    height=150,
                    placeholder="; Start extrusion PH1",
                    key="ta_cg_start_extrusion_ph1",
                )
                st.session_state["cg_stop_extrusion_ph1"] = st.text_area(
                    "Stop extrusion \u2014 Printhead 1",
                    value=st.session_state["cg_stop_extrusion_ph1"],
                    height=150,
                    placeholder="; Stop extrusion PH1",
                    key="ta_cg_stop_extrusion_ph1",
                )
            with mm_cols_a[1]:
                st.session_state["cg_start_extrusion_ph2"] = st.text_area(
                    "Start extrusion \u2014 Printhead 2",
                    value=st.session_state["cg_start_extrusion_ph2"],
                    height=150,
                    placeholder="; Start extrusion PH2",
                    key="ta_cg_start_extrusion_ph2",
                )
                st.session_state["cg_stop_extrusion_ph2"] = st.text_area(
                    "Stop extrusion \u2014 Printhead 2",
                    value=st.session_state["cg_stop_extrusion_ph2"],
                    height=150,
                    placeholder="; Stop extrusion PH2",
                    key="ta_cg_stop_extrusion_ph2",
                )

            st.markdown("##### Pressure Control")
            mm_cols_b = st.columns(2)
            with mm_cols_b[0]:
                st.session_state["cg_active_pressure_ph1"] = st.text_area(
                    "Active pressure \u2014 Printhead 1",
                    value=st.session_state["cg_active_pressure_ph1"],
                    height=150,
                    placeholder="; Active pressure for PH1",
                    key="ta_cg_active_pressure_ph1",
                    help="G-code for the ink extrusion pressure of Printhead 1 "
                         "when it is the **active** printhead.",
                )
                st.session_state["cg_rest_pressure_ph1"] = st.text_area(
                    "Resting pressure \u2014 Printhead 1",
                    value=st.session_state["cg_rest_pressure_ph1"],
                    height=150,
                    placeholder="; Resting pressure for PH1",
                    key="ta_cg_rest_pressure_ph1",
                    help="G-code for the ink extrusion pressure of Printhead 1 "
                         "when it is the **inactive** printhead.",
                )
            with mm_cols_b[1]:
                st.session_state["cg_active_pressure_ph2"] = st.text_area(
                    "Active pressure \u2014 Printhead 2",
                    value=st.session_state["cg_active_pressure_ph2"],
                    height=150,
                    placeholder="; Active pressure for PH2",
                    key="ta_cg_active_pressure_ph2",
                    help="G-code for the ink extrusion pressure of Printhead 2 "
                         "when it is the **active** printhead.",
                )
                st.session_state["cg_rest_pressure_ph2"] = st.text_area(
                    "Resting pressure \u2014 Printhead 2",
                    value=st.session_state["cg_rest_pressure_ph2"],
                    height=150,
                    placeholder="; Resting pressure for PH2",
                    key="ta_cg_rest_pressure_ph2",
                    help="G-code for the ink extrusion pressure of Printhead 2 "
                         "when it is the **inactive** printhead.",
                )

        # --- Tab 4: Dwell ---
        with cg_tabs[3]:
            st.markdown(
                "**Optional.** Incorporating time delays (\"dwells\") at the first "
                "and last node of each print pass deposits additional ink at each "
                "junction, improving the connection via a process similar to \"spot "
                "welding.\""
            )
            dwell_cols = st.columns(2)
            with dwell_cols[0]:
                st.session_state["cg_dwell_start"] = st.text_area(
                    "Dwell code (start of pass)",
                    value=st.session_state["cg_dwell_start"],
                    height=200,
                    placeholder="; e.g. G4 P80 ; dwell 80 ms",
                    key="ta_cg_dwell_start",
                )
            with dwell_cols[1]:
                st.session_state["cg_dwell_end"] = st.text_area(
                    "Dwell code (end of pass)",
                    value=st.session_state["cg_dwell_end"],
                    height=200,
                    placeholder="; e.g. G4 P80 ; dwell 80 ms",
                    key="ta_cg_dwell_end",
                )

with main_tab:

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

        # Write custom G-code templates to temp directory (if enabled)
        custom_dir = input_dir / "custom"
        if custom_gcode:
            custom_dir.mkdir(exist_ok=True)
            for _key, _meta in _CUSTOM_GCODE_FIELDS.items():
                content = st.session_state.get(_key, "")
                if content.strip():
                    (custom_dir / _meta["file"]).write_text(content)

        # Save gap closure extension files (if enabled)
        extension_dir = input_dir / "extension"
        if close_sm or close_mm:
            extension_dir.mkdir(exist_ok=True)
        if close_sm:
            if close_sm_pass_upload is not None:
                (extension_dir / "pass_to_extend_SM.txt").write_bytes(close_sm_pass_upload.getvalue())
            if close_sm_delta_upload is not None:
                (extension_dir / "deltas_to_extend_SM.txt").write_bytes(close_sm_delta_upload.getvalue())
        if close_mm:
            if close_mm_pass_upload is not None:
                (extension_dir / "pass_to_extend_MM.txt").write_bytes(close_mm_pass_upload.getvalue())
            if close_mm_delta_upload is not None:
                (extension_dir / "deltas_to_extend_MM.txt").write_bytes(close_mm_delta_upload.getvalue())

        # Build config
        try:
            config = _build_config(network_path, inletoutlet_path, output_dir)
            # Point custom_gcode_dir to the temp directory where we wrote the files
            config.custom_gcode_dir = custom_dir
            config.extension_dir = extension_dir
        except Exception as exc:
            st.error(f"Invalid configuration: {exc}")
            st.stop()

        # Progress bar and status
        progress_bar = st.progress(0, text="Initializing...")

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

            # Persist results in session state so downloads survive re-runs
            st.session_state.pipeline_result = result
            st.session_state.pipeline_config = config
            st.session_state.pipeline_output_dir = str(output_dir)
        except Exception as exc:
            progress_bar.empty()
            st.error(f"Pipeline failed: {exc}")
            st.exception(exc)
            # Clean up temp directory on failure
            shutil.rmtree(tmp_dir, ignore_errors=True)
            st.stop()

    # ------------------------------------------------------------------
    # Show results (persisted in session state so downloads work across
    # re-runs)
    # ------------------------------------------------------------------

    result = st.session_state.pipeline_result
    config_saved = st.session_state.pipeline_config

    if result is not None and config_saved is not None:
        # --------------------------------------------------------------
        # Visualization
        # --------------------------------------------------------------
        st.divider()
        st.subheader("3D Visualization")

        if config_saved.generate_plots:
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

        # --------------------------------------------------------------
        # Downloads
        # --------------------------------------------------------------
        st.divider()
        st.subheader("Download Results")

        dl_cols = st.columns(3)

        # G-code files
        with dl_cols[0]:
            st.markdown("**G-code**")
            gcode_files = _find_all_gcode_files(config_saved.gcode_dir)
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
            coord_files = _find_coordinate_files(config_saved.graph_dir)
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
            changelog_path = config_saved.output_dir / "changelog.txt"
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
# Print Instructions tab
# ---------------------------------------------------------------------------

with instr_tab:
    result = st.session_state.pipeline_result
    config_saved = st.session_state.pipeline_config

    if result is not None and config_saved is not None:
        instructions = result.get("instructions")
        if instructions is not None:
            # Start position metrics
            pos = instructions["start_position"]
            pos_cols = st.columns(3)
            pos_cols[0].metric("Start X (mm)", pos["x"])
            pos_cols[1].metric("Start Y (mm)", pos["y"])
            pos_cols[2].metric("Start Z (mm)", pos["z"])

            # Padding info
            pad = instructions["padding"]
            pad_cols = st.columns(4)
            pad_cols[0].metric("Left padding", f"{pad['left']} mm")
            pad_cols[1].metric("Right padding", f"{pad['right']} mm")
            pad_cols[2].metric("Front padding", f"{pad['front']} mm")
            pad_cols[3].metric("Back padding", f"{pad['back']} mm")

            if config_saved.multimaterial:
                with st.expander("Multimaterial Calibration", expanded=True):
                    for line in instructions["mm_calibration"]:
                        st.markdown(line)

                with st.expander("Multimaterial Positioning", expanded=True):
                    for line in instructions["mm_instructions"]:
                        st.markdown(line)
            else:
                with st.expander("Single Material Instructions", expanded=True):
                    for line in instructions["sm_instructions"]:
                        st.markdown(line)
    else:
        st.info("Run the pipeline first to see print instructions.")

# ---------------------------------------------------------------------------
# Calibration Validation tab
# ---------------------------------------------------------------------------

with cal_tab:
    st.caption(
        "Compare target filament diameters against measured values from a CSV. "
        "The CSV must have a column named **Length** with measurements in microns."
    )

    cal_csv_upload = st.file_uploader(
        "Upload measured diameters CSV",
        type=["csv"],
        help="CSV file with a 'Length' column containing measured filament diameters in microns.",
    )

    cal_targets_str = st.text_input(
        "Target diameters (comma-separated, mm)",
        value="0.4, 0.375, 0.35, 0.325, 0.3, 0.275, 0.25, 0.225, 0.2, 0.175, 0.15, 0.125, 0.1, 0.075",
        help="Comma-separated list of expected filament diameters in mm, in the same order as the measurements.",
    )

    cal_measurements_per = st.number_input(
        "Measurements per target",
        value=3,
        min_value=1,
        step=1,
        help="Number of rows in the CSV to average for each target diameter.",
    )

    cal_run = st.button("Run Validation", disabled=(cal_csv_upload is None))

    if cal_run and cal_csv_upload is not None:
        try:
            target_diameters = [float(x.strip()) for x in cal_targets_str.split(",")]
            csv_bytes = cal_csv_upload.getvalue()

            from xcavate.core.calibration import validate_calibration

            cal_result = validate_calibration(
                target_diameters=target_diameters,
                measured_csv_bytes=csv_bytes,
                measurements_per_target=cal_measurements_per,
            )

            st.session_state.cal_result = cal_result
        except Exception as exc:
            st.error(f"Calibration validation failed: {exc}")
            st.exception(exc)

    if "cal_result" in st.session_state and st.session_state.cal_result is not None:
        cal_result = st.session_state.cal_result

        st.plotly_chart(cal_result["figure"], use_container_width=True)

        cal_dl_cols = st.columns(2)
        with cal_dl_cols[0]:
            st.download_button(
                label="Download CSV report",
                data=cal_result["csv_bytes"],
                file_name="calibration_error.csv",
                mime="text/csv",
                key="dl_cal_csv",
            )
        with cal_dl_cols[1]:
            st.download_button(
                label="Download HTML report",
                data=cal_result["html_bytes"],
                file_name="calibration_error.html",
                mime="text/html",
                key="dl_cal_html",
            )
