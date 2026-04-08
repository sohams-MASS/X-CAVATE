"""Streamlit GUI for X-CAVATE.

Original Code Author: Jessica Herrmann

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

from xcavate.config import OverlapAlgorithm, PathfindingAlgorithm, PrinterType, SpeedUnit, XcavateConfig

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

# Sync calibrated f/s into sidebar widget keys before widgets render.
# This runs every rerun, so after calibration sets pdp_cal_factor/shift,
# the next rerun will push those values into the widget keys.
if "pdp_cal_factor" in st.session_state:
    st.session_state.pi_factor = st.session_state.pdp_cal_factor
if "pdp_cal_shift" in st.session_state:
    st.session_state.pi_shift = st.session_state.pdp_cal_shift

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("X-CAVATE")
st.markdown(
    "Convert vascular network geometry into collision-free 3D printer G-code.  "
    "Upload your input files, configure parameters in the sidebar, then click "
    "**Run X-CAVATE**."
)
st.caption("**SM** = single-material \u00a0|\u00a0 **MM** = multimaterial")

st.divider()

# ---------------------------------------------------------------------------
# Sidebar -- file uploads and parameter inputs
# ---------------------------------------------------------------------------

with st.sidebar:
    # User guide download
    _guide_path = Path(__file__).resolve().parent.parent.parent / "docs" / "user_guide.pdf"
    if _guide_path.exists():
        st.download_button(
            label="Download User Guide (PDF)",
            data=_guide_path.read_bytes(),
            file_name="user_guide.pdf",
            mime="application/pdf",
            key="dl_user_guide",
        )
        st.divider()

    st.header("Input Files")

    network_upload = st.file_uploader(
        "Network file (.txt)",
        type=["txt"],
        help="Text file containing vascular network coordinates.",
    )
    inletoutlet_upload = st.file_uploader(
        "Inlet / Outlet file (.txt)",
        type=["txt"],
        help="Text file marking the physiological entry (inlet) and exit (outlet) points "
             "of the vascular network. These points are excluded from branchpoint detection "
             "(so they remain as endpoints rather than false branches) and from gap closure "
             "(since gaps at inlets/outlets are intentional network boundaries, not errors).",
    )

    st.divider()
    st.header("Scene")
    scene_upload = st.file_uploader("Load scene (.json)", type=["json"], key="scene_upload")
    if st.session_state.get("pipeline_config") is not None:
        cfg_dict = st.session_state.pipeline_config.to_dict()
        for k in ("network_file", "inletoutlet_file", "custom_gcode_dir", "extension_dir", "output_dir"):
            cfg_dict.pop(k, None)
        import json as _json
        scene_json = _json.dumps({"version": 1, "config": cfg_dict}, indent=2)
        st.download_button("Save scene", data=scene_json,
                           file_name="xcavate_scene.json", mime="application/json",
                           use_container_width=True)

    if scene_upload is not None and "scene_loaded" not in st.session_state:
        import json as _json
        scene_data = _json.loads(scene_upload.getvalue())
        st.session_state["_scene_values"] = scene_data.get("config", {})
        st.session_state["scene_loaded"] = True
        st.rerun()

    def _scene_val(key, default):
        """Read a value from loaded scene, falling back to default."""
        vals = st.session_state.get("_scene_values", {})
        return vals.get(key, default)

    st.divider()
    st.header("Required Parameters")

    _printer_labels = {
        "Pressure": PrinterType.PRESSURE,
        "Positive Ink": PrinterType.POSITIVE_INK,
        "Aerotech": PrinterType.AEROTECH,
    }
    _printer_type_val = _scene_val("printer_type", 0)
    _printer_index = {0: 0, 1: 1, 2: 2}.get(_printer_type_val, 0)
    printer_label = st.selectbox(
        "Printer type",
        options=list(_printer_labels.keys()),
        index=_printer_index,
        help="Hardware target: Pressure (pneumatic extrusion), Positive Ink (displacement pump), or Aerotech (6-axis motion controller).",
    )
    printer_type = _printer_labels[printer_label]

    _speed_unit_labels = {
        "mm/min": SpeedUnit.MM_PER_MIN,
        "mm/s": SpeedUnit.MM_PER_S,
    }
    _speed_unit_default = "mm/s" if printer_type == PrinterType.AEROTECH else _scene_val("speed_unit", "mm/min")
    _speed_unit_index = 1 if _speed_unit_default == "mm/s" else 0
    speed_unit_label = st.selectbox(
        "G-code speed unit",
        options=list(_speed_unit_labels.keys()),
        index=_speed_unit_index,
        help="Unit for F (feedrate) values in generated G-code. Most printers use mm/min; Aerotech uses mm/s.",
    )
    speed_unit = _speed_unit_labels[speed_unit_label]

    _hide_nozzle = (
        printer_type == PrinterType.POSITIVE_INK
        and st.session_state.get("pi_radii", False)
    )
    if not _hide_nozzle:
        nozzle_diameter = st.number_input(
            "Nozzle diameter (mm)",
            min_value=0.001,
            value=_scene_val("nozzle_diameter", 0.5),
            step=0.01,
            format="%.3f",
            help="Inner diameter of the print nozzle in millimeters.",
        )
    else:
        nozzle_diameter = 0.5

    container_height = st.number_input(
        "Container height (mm)",
        min_value=0.1,
        value=_scene_val("container_height", 10.0),
        step=0.5,
        format="%.1f",
        help="Height of the print container in millimeters.",
    )
    num_decimals = st.number_input(
        "Decimal places",
        min_value=0,
        max_value=10,
        value=_scene_val("num_decimals", 3),
        step=1,
        help="Number of decimal places for output rounding.",
    )
    amount_up = st.number_input(
        "Amount up (mm)",
        min_value=0.0,
        value=_scene_val("amount_up", 10.0),
        step=0.5,
        format="%.1f",
        help="Distance to raise nozzle above the container between passes.",
    )

    multimaterial = st.toggle(
        "Multimaterial", value=_scene_val("multimaterial", False),
        help="Enable two-nozzle arterial/venous printing. Requires a 5-column input file (x, y, z, radius, artven flag).",
    )

    # ------------------------------------------------------------------
    # Optional parameter sections (expandable)
    # ------------------------------------------------------------------

    st.divider()
    st.header("Optional Parameters")

    # -- Advanced --
    with st.expander("Advanced"):
        custom_gcode = st.toggle(
            "Custom G-code",
            value=False,
            help="Enable to provide custom G-code templates for header, "
                 "extrusion start/stop, pressure, and dwell sections.",
        )
        algorithm = PathfindingAlgorithm.DFS
        num_overlap = st.number_input(
            "Overlap nodes", min_value=0, value=0, step=1,
            help="Number of nodes to retrace at pass boundaries to bridge small gaps. Use 0 to disable.",
        )
        overlap_algorithm = OverlapAlgorithm.RETRACE
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

        branchpoint_distance_threshold = st.number_input(
            "Branchpoint distance threshold (mm)",
            min_value=0.0, value=2.0, step=0.5, format="%.1f",
            help="Prevents false branches between vessels that pass close to each other. "
                 "If two vessel endpoints are farther apart than this distance, they will NOT "
                 "be connected as a branch. A good starting value is 2x your nozzle diameter. "
                 "Use 0 to disable (all endpoints connect, which may create unwanted branches).",
        )
        reorder_passes = st.toggle(
            "Reorder passes for minimal travel", value=False,
            help="Reorder print passes using nearest-neighbor to minimize nozzle travel distance between passes. "
                 "Off by default to preserve original pass ordering.",
        )
        gap_extension_size = st.number_input(
            "Auto gap extension (mm)",
            min_value=0.0, value=0.0, step=0.1, format="%.2f",
            help="Automatically extend each pass beyond its last node by this distance, "
                 "in the direction the pass was traveling. Closes small gaps at junctions. "
                 "Typical values: 0.1-0.5 mm. Set to 0 to disable.",
        )

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
            value=_scene_val("print_speed", 1.0),
            step=0.1,
            format="%.3f",
            help="Nozzle travel speed during extrusion. Typical range: 0.5–5.0 mm/s depending on ink viscosity.",
        )
        flow = st.number_input(
            "Flow (mm^3/s)",
            min_value=0.0,
            value=_scene_val("flow", 0.1609429886081009),
            step=0.001,
            format="%.16f",
            help="Volumetric flow rate used for speed calculation mode. Also used to compute per-node print speed when 'Speed calculation' is on.",
        )
        jog_speed = st.number_input(
            "Jog speed (mm/s)",
            min_value=0.001,
            value=_scene_val("jog_speed", 5.0),
            step=0.5,
            format="%.2f",
            help="Speed for rapid non-printing travel moves between passes.",
        )
        jog_speed_lift = st.number_input(
            "Jog speed lift (mm/s)",
            min_value=0.001,
            value=_scene_val("jog_speed_lift", 0.25),
            step=0.01,
            format="%.2f",
            help="Speed for the gentle vertical lift at the end of each pass before rapid retraction.",
        )
        initial_lift = st.number_input(
            "Initial lift (mm)",
            min_value=0.0,
            value=_scene_val("initial_lift", 0.5),
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
            automation1 = st.toggle(
                "Automation1 Aerotech",
                value=_scene_val("automation1", False),
                help="Wrap G-code in Automation1 program structure with variable-relative coordinates, "
                     "VelocityBlending/CornerRounding, and DriveBrakeOn/Off functions for pressure dispensing.",
            )
        else:
            dwell_start = 0.08
            dwell_end = 0.08
            automation1 = False

    # -- Geometry --
    with st.expander("Geometry"):
        container_x = st.number_input(
            "Container X (mm)", min_value=0.0, value=_scene_val("container_x", 50.0), step=1.0, format="%.1f",
            help="Width of the print container (mm). Used to calculate centering instructions for the operator.",
        )
        container_y = st.number_input(
            "Container Y (mm)", min_value=0.0, value=_scene_val("container_y", 50.0), step=1.0, format="%.1f",
            help="Depth of the print container (mm). Used to calculate centering instructions for the operator.",
        )
        convert_factor = st.number_input(
            "Unit conversion factor", min_value=0.001, value=_scene_val("convert_factor", 1.0), step=0.1, format="%.3f",
            help="Multiplier for input coordinate units. Use 1.0 if input is in mm (default). "
                 "Use 10.0 if input is in cm.",
        )
        scale_factor = st.number_input(
            "Scale factor", min_value=0.001, value=_scene_val("scale_factor", 1.0), step=0.1, format="%.3f",
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
        if printer_type == PrinterType.POSITIVE_INK:
            printhead_1 = st.text_input(
                "Printhead 1 name", value="Aa",
                help="Extrusion axis designation for the arterial printhead in G-code commands (e.g. 'Aa').",
            )
            printhead_2 = st.text_input(
                "Printhead 2 name", value="Ab",
                help="Extrusion axis designation for the venous printhead in G-code commands (e.g. 'Ab').",
            )
        elif printer_type == PrinterType.AEROTECH:
            printhead_1 = st.text_input(
                "Dispensing axis 1 name", value="Aa",
                help="Aerotech axis name for arterial pressure dispensing (used in Enable/BRAKE commands).",
            )
            printhead_2 = st.text_input(
                "Dispensing axis 2 name", value="Ab",
                help="Aerotech axis name for venous pressure dispensing (used in Enable/BRAKE commands).",
            )
        else:
            printhead_1 = "Aa"
            printhead_2 = "Ab"
        axis_1 = st.text_input(
            "Axis 1 name", value="A",
            help="Z-axis letter for the arterial side (e.g. 'A'). Must match the motion controller configuration.",
        )
        axis_2 = st.text_input(
            "Axis 2 name", value="B",
            help="Z-axis letter for the venous side (e.g. 'B'). Must match the motion controller configuration.",
        )
        jog_translation = st.number_input(
            "Jog translation speed (mm/s)",
            min_value=0.001,
            value=10.0,
            step=1.0,
            format="%.1f",
            help="Speed for rapid travel moves between nozzles during multimaterial printhead switching.",
        )
        if printer_type in (PrinterType.PRESSURE, PrinterType.AEROTECH):
            resting_pressure = st.number_input(
                "Resting pressure (psi)", min_value=0.0, value=0.0, step=0.5, format="%.1f",
                help="Pneumatic pressure (psi) applied to the inactive nozzle during multimaterial printing.",
            )
            active_pressure = st.number_input(
                "Active pressure (psi)", min_value=0.0, value=5.0, step=0.5, format="%.1f",
                help="Pneumatic pressure (psi) applied to the active nozzle during extrusion.",
            )
        else:
            resting_pressure = 0.0
            active_pressure = 5.0

    # -- Positive Ink Displacement (only shown for Positive Ink printer) --
    if printer_type == PrinterType.POSITIVE_INK:
      with st.expander("Positive Ink Displacement"):
        positive_ink_radii = st.toggle(
            "Use radii", value=False, key="pi_radii",
            help="When enabled, uses per-node vessel radii from SimVascular data instead of a fixed diameter for extrusion calculations. The nozzle diameter will not be used, as print speed remains constant.",
        )
        if not positive_ink_radii:
            positive_ink_diam = st.number_input(
                "Diameter", min_value=0.001, value=1.0, step=0.1, format="%.3f",
                key="pi_diam",
                help="Fixed vessel diameter (mm) used for extrusion calculations when 'Use radii' is off.",
            )
        else:
            positive_ink_diam = 1.0
        positive_ink_syringe_diam = st.number_input(
            "Syringe diameter", min_value=0.001, value=1.0, step=0.1, format="%.3f",
            key="pi_syr_diam",
            help="Inner diameter (mm) of the syringe barrel. Used to compute plunger displacement from vessel geometry.",
        )
        _default_factor = st.session_state.get("pdp_cal_factor", 1.0)
        _default_shift = st.session_state.get("pdp_cal_shift", 0.0)
        positive_ink_factor = st.number_input(
            "Factor (f)", min_value=0.0, value=_default_factor, step=0.1, format="%.6f",
            key="pi_factor",
            help="Scaling multiplier for extrusion. Auto-filled from the Extrusion Calibration tab, or enter your own value directly.",
        )
        positive_ink_shift = st.number_input(
            "Shift (s, mm)", value=_default_shift, step=0.001, format="%.6f",
            key="pi_shift",
            help="Radius shift (mm) to compensate for systematic error. Auto-filled from the Extrusion Calibration tab, or enter your own value directly.",
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
    else:
        # Defaults when not using Positive Ink printer
        positive_ink_radii = False
        positive_ink_diam = 1.0
        positive_ink_syringe_diam = 1.0
        positive_ink_factor = 1.0
        positive_ink_shift = 0.0
        positive_ink_start = 0.0
        positive_ink_end = 0.0
        positive_ink_start_arterial = 0.0
        positive_ink_start_venous = 0.0
        positive_ink_end_arterial = 0.0
        positive_ink_end_venous = 0.0
        separate_artven = False


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
        speed_unit=speed_unit,
        automation1=automation1,
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
        convert_factor=convert_factor,
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
        positive_ink_shift=positive_ink_shift,
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
        branchpoint_distance_threshold=branchpoint_distance_threshold,
        reorder_passes=reorder_passes,
        gap_extension_size=gap_extension_size,
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
tab_names.append("Print Instructions")
if printer_type in (PrinterType.PRESSURE, PrinterType.AEROTECH):
    tab_names.append("Pressure Calibration")
if printer_type == PrinterType.POSITIVE_INK:
    tab_names.append("Extrusion Calibration")

tabs = st.tabs(tab_names)
idx = 0
main_tab = tabs[idx]; idx += 1
cg_tab = tabs[idx] if custom_gcode else None; idx += (1 if custom_gcode else 0)
instr_tab = tabs[idx]; idx += 1
cal_tab = tabs[idx] if printer_type in (PrinterType.PRESSURE, PrinterType.AEROTECH) else None
if printer_type in (PrinterType.PRESSURE, PrinterType.AEROTECH):
    idx += 1
pdp_cal_tab = tabs[idx] if printer_type == PrinterType.POSITIVE_INK else None

if cg_tab is not None:
    with cg_tab:
        st.subheader("Custom G-code Templates")
        st.caption(
            "Paste your printer-specific G-code snippets below, or upload "
            ".txt files directly. These replace the default commands for "
            "header, extrusion start/stop, pressure control, and dwell "
            "sections in the final output file."
        )

        with st.expander("Upload G-code files"):
            st.markdown(
                "Upload `.txt` files to populate the corresponding fields below. "
                "Each file's contents will replace the current text in its field."
            )
            _upload_cols = st.columns(2)
            _field_items = list(_CUSTOM_GCODE_FIELDS.items())
            for col_idx, col in enumerate(_upload_cols):
                with col:
                    for key, meta in _field_items[col_idx::2]:
                        uploaded = st.file_uploader(
                            meta["label"],
                            type=["txt"],
                            key=f"upload_{key}",
                        )
                        if uploaded is not None:
                            st.session_state[key] = uploaded.getvalue().decode("utf-8")

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
        # Warnings
        # --------------------------------------------------------------
        for w in result.get("warnings", []):
            st.warning(w)

        # --------------------------------------------------------------
        # Visualization
        # --------------------------------------------------------------
        st.divider()
        st.subheader("3D Visualization")

        if config_saved.generate_plots:
            from xcavate.viz.plotting import create_network_plot, create_original_network_plot

            # Original network plot
            if result.get("points_original") is not None and result.get("coord_num_dict_original") is not None:
                st.markdown("**Original Network**")
                fig_orig = create_original_network_plot(
                    result["points_original"],
                    result["coord_num_dict_original"],
                    title="Original Network",
                )
                st.plotly_chart(fig_orig, use_container_width=True)
                st.download_button(
                    label="Download Original Network (HTML)",
                    data=fig_orig.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8"),
                    file_name="original_network.html",
                    mime="text/html",
                    key="dl_plot_orig",
                )

            # Single-material plot
            if result.get("print_passes_sm") is not None and result.get("points") is not None:
                st.markdown("**Single Material Print Passes**")
                fig_sm = create_network_plot(
                    result["print_passes_sm"],
                    result["points"],
                    title="Single Material",
                )
                st.plotly_chart(fig_sm, use_container_width=True)
                st.download_button(
                    label="Download SM Print Passes (HTML)",
                    data=fig_sm.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8"),
                    file_name="print_passes_SM.html",
                    mime="text/html",
                    key="dl_plot_sm",
                )

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
                st.download_button(
                    label="Download MM Print Passes (HTML)",
                    data=fig_mm.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8"),
                    file_name="print_passes_MM.html",
                    mime="text/html",
                    key="dl_plot_mm",
                )
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

    def _coord_diagram(orientation: int):
        """Create a 3D coordinate system diagram.
        orientation=1: +x right, +y backwards, +z up
        orientation=2: +x left, +y forwards, +z up
        """
        import plotly.graph_objects as go
        fig = go.Figure()
        L = 1.0  # axis length
        # Axis arrows
        colors = {"X": "red", "Y": "green", "Z": "blue"}
        for axis, vec, color in [
            ("X", [L, 0, 0], colors["X"]),
            ("Y", [0, L, 0], colors["Y"]),
            ("Z", [0, 0, L], colors["Z"]),
        ]:
            fig.add_trace(go.Scatter3d(
                x=[0, vec[0]], y=[0, vec[1]], z=[0, vec[2]],
                mode="lines+text",
                line=dict(color=color, width=6),
                text=["", f"+{axis}"],
                textposition="top center",
                textfont=dict(size=14, color=color),
                showlegend=False,
            ))
        # Container outline (wireframe box)
        cx, cy, cz = 1.2, 1.2, 0.8
        edges = [
            ([0,cx],[0,0],[0,0]), ([0,cx],[cy,cy],[0,0]), ([0,cx],[0,0],[cz,cz]), ([0,cx],[cy,cy],[cz,cz]),
            ([0,0],[0,cy],[0,0]), ([cx,cx],[0,cy],[0,0]), ([0,0],[0,cy],[cz,cz]), ([cx,cx],[0,cy],[cz,cz]),
            ([0,0],[0,0],[0,cz]), ([cx,cx],[0,0],[0,cz]), ([0,0],[cy,cy],[0,cz]), ([cx,cx],[cy,cy],[0,cz]),
        ]
        for ex, ey, ez in edges:
            fig.add_trace(go.Scatter3d(
                x=ex, y=ey, z=ez, mode="lines",
                line=dict(color="gray", width=2), showlegend=False,
            ))
        # Labels
        if orientation == 1:
            labels = [
                (cx/2, -0.3, -0.15, "Right (+x)"),
                (-0.15, cy/2, -0.15, "Away from observer (+y)"),
                (cx + 0.1, -0.15, 0, "Nozzle start (left-front corner)"),
            ]
            title = "+x right, +y backwards, +z up"
            # Nozzle marker at left-front corner
            fig.add_trace(go.Scatter3d(
                x=[0], y=[0], z=[cz + 0.1], mode="markers",
                marker=dict(size=8, color="black", symbol="diamond"),
                showlegend=False,
            ))
            obs_y, obs_label = -0.4, "Observer"
        else:
            labels = [
                (cx/2, -0.3, -0.15, "Left (+x)"),
                (-0.15, cy/2, -0.15, "Towards observer (+y)"),
                (-0.1, cy + 0.15, 0, "Nozzle start (right-back corner)"),
            ]
            title = "+x left, +y forwards, +z up"
            fig.add_trace(go.Scatter3d(
                x=[cx], y=[cy], z=[cz + 0.1], mode="markers",
                marker=dict(size=8, color="black", symbol="diamond"),
                showlegend=False,
            ))
            obs_y, obs_label = -0.4, "Observer"
        # Observer marker
        fig.add_trace(go.Scatter3d(
            x=[cx/2], y=[obs_y], z=[0], mode="markers+text",
            marker=dict(size=6, color="orange"),
            text=[obs_label], textposition="bottom center",
            textfont=dict(size=11, color="orange"),
            showlegend=False,
        ))
        fig.update_layout(
            scene=dict(
                aspectmode="data",
                xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False),
            ),
            title=dict(text=title, font=dict(size=13)),
            margin=dict(l=0, r=0, t=30, b=0),
            height=300,
        )
        return fig

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

            # Coordinate system diagrams
            with st.expander("Coordinate System Reference", expanded=False):
                st.markdown(
                    "The diagrams below show the two possible coordinate system "
                    "orientations. The **black diamond** marks where the nozzle "
                    "should be positioned before starting. The **orange dot** "
                    "marks the observer's position."
                )
                diag_cols = st.columns(2)
                with diag_cols[0]:
                    st.plotly_chart(_coord_diagram(1), use_container_width=True)
                with diag_cols[1]:
                    st.plotly_chart(_coord_diagram(2), use_container_width=True)

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
# Pressure Calibration tab (Pressure / Aerotech only)
# ---------------------------------------------------------------------------

if cal_tab is not None:
    with cal_tab:

        # --- Compute Q section -----------------------------------------------
        st.subheader("Compute Volumetric Flow Rate (Q)")

        q_csv_upload = st.file_uploader(
            "Upload measured diameters CSV",
            type=["csv"],
            help="CSV file with a 'Length' column containing measured filament diameters in microns.",
            key="q_csv_upload",
        )

        q_print_speeds_str = st.text_input(
            "Print speeds used during calibration (comma-separated, mm/s)",
            value="1.0",
            help="Comma-separated list of print speeds in mm/s, one per target diameter group (same order). "
                 "Pressure is held constant; speed is varied for each calibration filament.",
            key="q_print_speeds_str",
        )

        q_measurements_per = st.number_input(
            "Measurements per speed",
            value=3,
            min_value=1,
            step=1,
            help="Number of rows in the CSV to average for each print speed group.",
            key="q_measurements_per",
        )

        q_run = st.button("Compute Q", disabled=(q_csv_upload is None))

        if q_run and q_csv_upload is not None:
            try:
                q_print_speeds = [float(x.strip()) for x in q_print_speeds_str.split(",")]
                q_csv_bytes = q_csv_upload.getvalue()

                from xcavate.core.calibration import compute_flow_rate

                q_result = compute_flow_rate(
                    measured_csv_bytes=q_csv_bytes,
                    print_speeds=q_print_speeds,
                    measurements_per_target=q_measurements_per,
                )

                st.session_state.q_result = q_result
            except Exception as exc:
                st.error(f"Q computation failed: {exc}")
                st.exception(exc)

        if "q_result" in st.session_state and st.session_state.q_result is not None:
            q_result = st.session_state.q_result

            st.metric("Computed Q (mm\u00b3/s)", f"{q_result['q_value']:.6f}")
            st.plotly_chart(q_result["figure"], use_container_width=True)

            q_dl_cols = st.columns(2)
            with q_dl_cols[0]:
                st.download_button(
                    label="Download Q_pressure.txt",
                    data=q_result["q_txt_bytes"],
                    file_name="Q_pressure.txt",
                    mime="text/plain",
                    key="dl_q_txt",
                )
            with q_dl_cols[1]:
                st.download_button(
                    label="Download radii_pressure.html",
                    data=q_result["html_bytes"],
                    file_name="radii_pressure.html",
                    mime="text/html",
                    key="dl_q_html",
                )

        st.divider()

        # --- Validation section ----------------------------------------------
        st.subheader("Calibration Validation")
        st.caption(
            "Compare target filament diameters against measured values from a CSV. "
            "The CSV must have a column named **Length** with measurements in microns."
        )

        cal_csv_upload = st.file_uploader(
            "Upload measured diameters CSV",
            type=["csv"],
            help="CSV file with a 'Length' column containing measured filament diameters in microns.",
            key="cal_csv_upload",
        )

        cal_targets_str = st.text_input(
            "Target diameters (comma-separated, mm)",
            value="0.4, 0.375, 0.35, 0.325, 0.3, 0.275, 0.25, 0.225, 0.2, 0.175, 0.15, 0.125, 0.1, 0.075",
            help="Comma-separated list of expected filament diameters in mm, in the same order as the measurements.",
            key="cal_targets_str",
        )

        cal_measurements_per = st.number_input(
            "Measurements per target",
            value=3,
            min_value=1,
            step=1,
            help="Number of rows in the CSV to average for each target diameter.",
            key="cal_measurements_per",
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

# ---------------------------------------------------------------------------
# Extrusion Calibration tab (Positive Ink only)
# ---------------------------------------------------------------------------

if pdp_cal_tab is not None:
    with pdp_cal_tab:
        st.subheader("Extrusion Calibration")
        st.markdown(
            "Fit the scaling factor **f** and radius shift **s** for the "
            "positive ink displacement formula:"
        )
        st.latex(r"E = f \times N \left(\frac{L_r + s}{S_r}\right)^2")
        st.markdown(
            "| Symbol | Meaning |\n"
            "|--------|---------|\n"
            "| $E$ | Linear displacement of the plunger |\n"
            "| $N$ | Length of printed line |\n"
            "| $L_r$ | Radius of the line being printed |\n"
            "| $S_r$ | Radius of the syringe |\n"
            "| $f$ | Scaling factor |\n"
            "| $s$ | Radius shift to account for error |"
        )

        st.divider()
        st.markdown(
            "**Print test lines at known intended radii, measure the "
            "actual radii, then fit *f* and *s*.** Enter comma-separated "
            "values below (in \u00b5m)."
        )

        pdp_intended_str = st.text_input(
            "Intended radii (\u00b5m)",
            value="200, 400, 600, 800, 1000",
            key="pdp_cal_intended",
        )
        pdp_measured_str = st.text_input(
            "Measured radii (\u00b5m)",
            value="",
            key="pdp_cal_measured",
            help="Enter measured radii in the same order as intended.",
        )

        pdp_cal_run = st.button("Fit Calibration", key="pdp_cal_run")

        if pdp_cal_run and pdp_measured_str.strip():
            try:
                import numpy as np

                intended = np.array([float(x) for x in pdp_intended_str.split(",")])
                measured = np.array([float(x) for x in pdp_measured_str.split(",")])
                if len(intended) != len(measured):
                    st.error("Intended and measured lists must have the same length.")
                elif len(intended) < 2:
                    st.error("Need at least 2 data points.")
                else:
                    coeffs = np.polyfit(intended, measured, 1)
                    a, b = float(coeffs[0]), float(coeffs[1])
                    fitted = np.polyval(coeffs, intended)
                    r_squared = 1.0 - np.sum((measured - fitted) ** 2) / np.sum((measured - np.mean(measured)) ** 2)

                    # Inverse correction: f = 1/a², s = -b (µm → mm)
                    f_cal = 1.0 / (a ** 2)
                    s_cal = -b / 1000.0

                    st.session_state.pdp_cal_factor = round(f_cal, 6)
                    st.session_state.pdp_cal_shift = round(s_cal, 6)
                    st.session_state.pdp_source = "fitted"
                    # Store fit results for display after rerun
                    st.session_state.pdp_fit_result = {
                        "f": f_cal, "s": s_cal, "r2": r_squared,
                        "intended": intended.tolist(),
                        "measured": measured.tolist(),
                        "fitted": fitted.tolist(),
                    }
                    st.rerun()
            except Exception as exc:
                st.error(f"Calibration failed: {exc}")

        # Show stored fit results (persists across reruns)
        if "pdp_fit_result" in st.session_state:
            res = st.session_state.pdp_fit_result
            st.success(f"**f** = {res['f']:.4f},  **s** = {res['s']:.4f} mm  (R\u00b2 = {res['r2']:.4f})")

            import plotly.graph_objects as go
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=res["intended"], y=res["measured"], mode="markers",
                name="Measured", marker=dict(size=10),
            ))
            fig.add_trace(go.Scatter(
                x=res["intended"], y=res["fitted"], mode="lines",
                name=f"Fit (f={res['f']:.3f}, s={res['s']:.4f} mm)",
            ))
            fig.update_layout(
                xaxis_title="Intended radius (\u00b5m)",
                yaxis_title="Measured radius (\u00b5m)",
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown(
                "| Intended (\u00b5m) | Measured (\u00b5m) | Predicted (\u00b5m) | Error (\u00b5m) |\n"
                "|:---:|:---:|:---:|:---:|\n"
                + "\n".join(
                    f"| {i:.0f} | {m:.1f} | {p:.1f} | {m - p:+.1f} |"
                    for i, m, p in zip(res["intended"], res["measured"], res["fitted"])
                )
            )

        st.divider()

        pdp_use_manual = st.toggle(
            "Enter f and s manually", value=False, key="pdp_use_manual",
        )
        if pdp_use_manual:
            pdp_manual_cols = st.columns(2)
            with pdp_manual_cols[0]:
                pdp_manual_f = st.number_input(
                    "Factor (f)", min_value=0.0, value=1.0,
                    step=0.01, format="%.6f", key="pdp_manual_f",
                )
            with pdp_manual_cols[1]:
                pdp_manual_s = st.number_input(
                    "Shift (s, mm)", value=0.0,
                    step=0.001, format="%.6f", key="pdp_manual_s",
                )
            if st.button("Apply", key="pdp_apply_manual"):
                st.session_state.pdp_cal_factor = pdp_manual_f
                st.session_state.pdp_cal_shift = pdp_manual_s
                st.session_state.pdp_source = "manual"
                st.rerun()

        # --- Status banner showing active values ---
        st.divider()
        _active_f = st.session_state.get("pdp_cal_factor", 1.0)
        _active_s = st.session_state.get("pdp_cal_shift", 0.0)
        _source = st.session_state.get("pdp_source", "default")
        if _source == "fitted":
            st.success(
                f"Using **fitted** values:  f = {_active_f:.6f},  s = {_active_s:.6f} mm"
            )
        elif _source == "manual":
            st.info(
                f"Using **manual** values:  f = {_active_f:.6f},  s = {_active_s:.6f} mm"
            )
        else:
            st.warning(
                f"Using **default** values:  f = {_active_f:.6f},  s = {_active_s:.6f} mm  "
                "(no calibration or manual entry performed)"
            )
