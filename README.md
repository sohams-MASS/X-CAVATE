# X-CAVATE

Convert vascular network geometries (e.g. from SimVascular) into collision-free 3D printer toolhead pathways and G-code. 

### Core Developer and Original Author: Jessica Herrmann

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Input Files](#input-files)
- [Running X-CAVATE](#running-x-cavate)
  - [Mode 1: Streamlit GUI](#mode-1-streamlit-gui-recommended-for-new-users)
  - [Mode 2: Command-Line Interface](#mode-2-command-line-interface)
  - [Mode 3: Docker](#mode-3-docker)
- [Python API](#python-api)
- [Parameters Reference](#parameters-reference)
- [Output Files](#output-files)
- [Project Structure](#project-structure)
- [Development](#development)
- [License](#license)

---

## Overview

X-CAVATE accepts an input list of coordinates (in cm) specifying the b-splines constituting a vascular network. It reorders the coordinates such that they can be printed, from start to finish, to fabricate the network without collisions between the printhead nozzle and deposited ink.

The pipeline performs seven steps:

| Step | Description |
|------|-------------|
| 1 | Read and preprocess network geometry |
| 2 | Interpolate to nozzle-radius resolution |
| 3 | Build the vascular adjacency graph |
| 4 | Generate collision-free print passes (DFS or Sweep Line) |
| 5 | Subdivide, gap-close, downsample, overlap, and reorder passes |
| 6 | (Optional) Multimaterial arterial/venous splitting |
| 7 | Write coordinate outputs, plots, and G-code |

**Key improvements over the original monolithic script:**
- KD-tree spatial indexing for collision detection (100-1000x speedup)
- Batch interpolation (10-50x speedup)
- Modular codebase (~1,300 lines across focused modules vs. ~11,200 lines)
- Multiple pathfinding algorithms (DFS + Sweep Line)
- Web GUI for non-technical users
- pip installable + Docker deployable

---

## Installation

**Requirements:** Python 3.9+

### Option A: Conda (Recommended)

The easiest way to set up a fully isolated environment with all dependencies (including the GUI):

```bash
# Clone the repository
git clone https://github.com/sohams-MASS/X-CAVATE.git
cd X-CAVATE

# Create and activate the conda environment
conda env create -f environment.yml
conda activate xcavate-gui

# Verify
xcavate --help
```

This installs Python 3.11, all core and GUI dependencies, and the `xcavate` package itself in one step. To remove the environment later: `conda env remove -n xcavate-gui`.

### Option B: pip install

```bash
# Clone the repository
git clone https://github.com/sohams-MASS/X-CAVATE.git
cd X-CAVATE

# Install core package (CLI only)
pip install .

# Install with GUI support (adds Streamlit)
pip install ".[gui]"

# Install with development tools (adds pytest, ruff)
pip install ".[dev]"

# Install everything
pip install ".[all]"
```

### Option C: Development mode

```bash
pip install -e ".[all]"
```

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| numpy | >= 1.21 | Array operations |
| pandas | >= 1.3 | Data handling |
| scipy | >= 1.7 | KD-tree spatial indexing, interpolation |
| plotly | >= 5.0 | Interactive 3D visualization |
| matplotlib | >= 3.5 | Static plots |
| prompt_toolkit | — | Interactive prompts |
| streamlit | >= 1.20 | Web GUI *(optional with pip; included in conda env)* |

---

## Input Files

X-CAVATE requires two input text files. Both support whitespace-separated, comma-separated, or mixed delimiter formats.

### 1. Network File

Contains vessel coordinates exported from SimVascular. Each vessel has a header line followed by coordinate rows.

```
Vessel: 0, Number of Points: 100
33.4878, 0.0000, 53.5303, 0.0200
33.4115, -0.5285, 52.7311, 0.0200
...
Vessel: 1, Number of Points: 100
15.0600, -37.3300, 11.6600, 0.0190
...
```

**Columns:**

| Column | Required | Description |
|--------|----------|-------------|
| 1-3 | Yes | x, y, z coordinates (in cm) |
| 4 | No | Vessel radius (for speed calculation) |
| 5 | No | Arterial/venous flag: 0 = venous, any other number = arterial |

**Constraints:**
- Bifurcation points ("branchpoints") must exist ON the vessel from which they branch
- Recommended: limit to 100 coordinates/vessel to avoid long runtimes
- Coordinates should be in centimeters (X-CAVATE converts to mm internally)

### 2. Inlet/Outlet File

Specifies which network locations are inlets (where printing starts) and outlets. Each section starts with the keyword `inlet` or `outlet` on its own line, followed by one or more coordinate triplets.

```
inlet
21.97, -15.43, 50.00
11.81, 0.00, 21.34
outlet
36.05, -27.19, 50.00
50.00, 0.00, 26.54
```

You can have any number of inlets and outlets. Coordinates are matched to the nearest network point automatically (approximate matching is supported).

### 3. Custom G-code Template Files (Optional)

Custom G-code templates let you adapt X-CAVATE's output to your specific printer hardware and software. Each template file contains a G-code snippet that is inserted at a specific point in the final output. The template files are located in `inputs/custom/` and ship with placeholder text that you replace with your own G-code.

There are 12 template files organized into four categories:

**Header** (applies to all prints):

| File | Purpose |
|------|---------|
| `header_code.txt` | G-code header: printer initialization, establishing connections between external pressure boxes and syringes, homing, etc. |

**Single Material** (used when `--multimaterial 0`):

| File | Purpose |
|------|---------|
| `start_extrusion_code.txt` | G-code to start extrusion at the beginning of each print pass |
| `stop_extrusion_code.txt` | G-code to stop extrusion at the end of each print pass |

**Multimaterial** (used when `--multimaterial 1`):

| File | Purpose |
|------|---------|
| `start_extrusion_code_printhead1.txt` | Start extrusion for Printhead 1 (arterial) |
| `start_extrusion_code_printhead2.txt` | Start extrusion for Printhead 2 (venous) |
| `stop_extrusion_code_printhead1.txt` | Stop extrusion for Printhead 1 (arterial) |
| `stop_extrusion_code_printhead2.txt` | Stop extrusion for Printhead 2 (venous) |
| `active_pressure_printhead1.txt` | Set ink extrusion pressure when Printhead 1 is the **active** printhead |
| `active_pressure_printhead2.txt` | Set ink extrusion pressure when Printhead 2 is the **active** printhead |
| `rest_pressure_printhead1.txt` | Set ink extrusion pressure when Printhead 1 is the **inactive** printhead |
| `rest_pressure_printhead2.txt` | Set ink extrusion pressure when Printhead 2 is the **inactive** printhead |

**Dwell** (optional, applies to all prints):

| File | Purpose |
|------|---------|
| `dwell_code.txt` | Time delay ("dwell") at the start and end of each print pass. Deposits extra ink at junctions, improving connections via a process similar to "spot welding." |

**Example template content** (`start_extrusion_code.txt`):

```gcode
; Begin extrusion
M42 P0 S255     ; Open valve
G4 P80          ; Dwell 80ms for pressure build-up
```

> Each file can contain multiple lines. Any file that does not exist or is empty is simply skipped.

### 4. Gap Extension Files (Optional)

For manual gap closure, place in `inputs/extension/`:
- `pass_to_extend_SM.txt` / `pass_to_extend_MM.txt` — pass indices to extend
- `deltas_to_extend_SM.txt` / `deltas_to_extend_MM.txt` — delta x, y, z per pass (mm)

---

## Running X-CAVATE

### Mode 1: Streamlit GUI (Recommended for New Users)

The web-based GUI is the easiest way to run X-CAVATE. No coding required.

**Start the server:**

```bash
# If using conda:
conda activate xcavate-gui
streamlit run xcavate/gui/app.py

# If using pip:
streamlit run xcavate/gui/app.py
```

This opens a browser at **http://localhost:8501** with:

- **Sidebar** — File upload widgets and all configurable parameters in expandable sections
- **Main area** — Top-level tabs:
  - **Pipeline** — Run button, progress bar (7 steps), 3D visualizations (original network, SM, and MM plots), download buttons
  - **Custom G-code** *(appears only when the toggle is on)* — Tabbed template editor for header, extrusion, pressure, and dwell snippets
  - **Print Instructions** — Step-by-step printing instructions for SM and MM modes
  - **Calibration Validation** — Upload calibration data to validate print accuracy

**Steps:**

1. Upload your **Network file** and **Inlet/Outlet file** in the sidebar
2. Set **Required Parameters**: nozzle diameter, container height, decimal places, amount up
3. Choose a **Printer type** (Pressure, Positive Ink, or Aerotech)
4. (Optional) Expand optional sections to fine-tune: tolerancing, print speeds, geometry, downsampling, multimaterial, positive ink displacement, advanced
5. (Optional) Enable **Custom G-code** in the Advanced section to reveal the Custom G-code tab (see below)
6. Click **Run X-CAVATE** in the Pipeline tab
7. Watch the progress bar as the pipeline runs through all 7 steps
8. View the interactive 3D plots: original network, single-material passes, and multimaterial passes (if enabled)
9. Download G-code, coordinate files, and changelog
10. Check the **Print Instructions** tab for step-by-step printing guidance

**Custom G-code in the GUI:**

When you enable the "Custom G-code" toggle in the sidebar's Advanced section, a **Custom G-code** tab appears between the Pipeline and Print Instructions tabs. It contains four sub-tabs:

| Tab | What to paste |
|-----|---------------|
| **Header** | Printer initialization code (pressure box connections, homing, etc.) |
| **Single Material** | Start/stop extrusion code for single-nozzle prints |
| **Multimaterial** | Start/stop extrusion + active/resting pressure for each printhead (8 fields in a 2-column layout) |
| **Dwell** | Optional time-delay code for "spot welding" at pass junctions |

Paste your printer-specific G-code into each text area. The snippets are saved automatically and persist across page re-runs (even when the toggle is turned off). When you click **Run X-CAVATE**, they are injected into the appropriate sections of the final G-code output.

**Troubleshooting:**
- If you see `Runtime instance already exists`, kill stale processes: `pkill -f streamlit` then restart
- If download buttons disappear after clicking, update to the latest version (this has been fixed)

---

### Mode 2: Command-Line Interface

After installation (via `conda activate xcavate-gui` or `pip install .`), the `xcavate` command is available. You can also use `python -m xcavate`.

**Minimal example:**

```bash
xcavate \
  --network_file inputs/network.txt \
  --inletoutlet_file inputs/inletoutlet.txt \
  --nozzle_diameter 0.5 \
  --container_height 10.0 \
  --num_decimals 3 \
  --amount_up 10.0 \
  --printer_type 0 \
  --multimaterial 0 \
  --tolerance_flag 0 \
  --speed_calc 0 \
  --plots 1 \
  --downsample 0 \
  --custom 0
```

**Or equivalently:**

```bash
python -m xcavate \
  --network_file inputs/network.txt \
  --inletoutlet_file inputs/inletoutlet.txt \
  --nozzle_diameter 0.5 \
  --container_height 10.0 \
  --num_decimals 3 \
  --amount_up 10.0 \
  --printer_type 0 \
  --multimaterial 0 \
  --tolerance_flag 0 \
  --speed_calc 0 \
  --plots 1 \
  --downsample 0 \
  --custom 0
```

**Custom G-code in CLI mode:**

When using `--custom 1`, the CLI reads template files from the `inputs/custom/` directory (relative to where you run the command). Set up the templates before running:

```bash
# 1. Edit the template files with your printer-specific G-code
nano inputs/custom/header_code.txt
nano inputs/custom/start_extrusion_code.txt
nano inputs/custom/stop_extrusion_code.txt

# 2. For multimaterial, also edit:
nano inputs/custom/start_extrusion_code_printhead1.txt
nano inputs/custom/start_extrusion_code_printhead2.txt
nano inputs/custom/stop_extrusion_code_printhead1.txt
nano inputs/custom/stop_extrusion_code_printhead2.txt
nano inputs/custom/active_pressure_printhead1.txt
nano inputs/custom/active_pressure_printhead2.txt
nano inputs/custom/rest_pressure_printhead1.txt
nano inputs/custom/rest_pressure_printhead2.txt

# 3. Optional: dwell code for "spot welding" at junctions
nano inputs/custom/dwell_code.txt

# 4. Run with --custom 1
xcavate \
  --network_file inputs/network.txt \
  --inletoutlet_file inputs/inletoutlet.txt \
  --nozzle_diameter 0.5 \
  --container_height 10.0 \
  --num_decimals 3 \
  --amount_up 10.0 \
  --printer_type 0 \
  --multimaterial 0 \
  --tolerance_flag 0 \
  --speed_calc 0 \
  --plots 1 \
  --downsample 0 \
  --custom 1
```

Any template file that does not exist or is empty is simply skipped. See [Custom G-code Template Files](#3-custom-g-code-template-files-optional) for the full file list and what each one does.

**Full example with all optional flags:**

```bash
xcavate \
  --network_file inputs/new_splines.txt \
  --inletoutlet_file inputs/inletoutlet.txt \
  --nozzle_diameter 0.5 \
  --container_height 10.0 \
  --num_decimals 5 \
  --amount_up 10.0 \
  --printer_type 0 \
  --multimaterial 1 \
  --tolerance_flag 0 \
  --speed_calc 1 \
  --plots 1 \
  --downsample 0 \
  --custom 1 \
  --algorithm sweep_line \
  --output_dir my_output \
  --scale_factor 1.0 \
  --print_speed 2.0 \
  --flow 0.127 \
  --jog_speed 5.0 \
  --jog_speed_lift 0.25 \
  --initial_lift 0.5 \
  --dwell_start 0.08 \
  --dwell_end 0.08 \
  --container_x 50.0 \
  --container_y 50.0 \
  --top_padding 0.0 \
  --num_overlap 2 \
  --offset_x 103.0 \
  --offset_y 0.5 \
  --front_nozzle 1 \
  --resting_pressure 0.0 \
  --active_pressure 5.0
```

---

### Mode 3: Docker

Run X-CAVATE in a Docker container with the Streamlit GUI — no Python installation needed on the host machine.

**Build the image:**

```bash
docker build -t xcavate .
```

**Run the container:**

```bash
docker run -p 8501:8501 xcavate
```

Then open **http://localhost:8501** in your browser.

**Mount a local directory** to access output files on your host machine:

```bash
docker run -p 8501:8501 -v $(pwd)/outputs:/app/outputs xcavate
```

**Custom G-code in Docker:**

You have two options for custom G-code in Docker:

*Option A: Use the GUI editor* — Enable the "Custom G-code" toggle in the web interface and paste your snippets directly into the text areas. No volume mounting needed.

*Option B: Mount pre-written template files* — If you already have your template files on the host, mount them into the container:

```bash
docker run -p 8501:8501 \
  -v $(pwd)/inputs/custom:/app/inputs/custom \
  -v $(pwd)/outputs:/app/outputs \
  xcavate
```

Then enable "Custom G-code" in the GUI. The pipeline will read the mounted files. This is useful for sharing a consistent set of templates across your team.

**Health check:**

The container includes a health check endpoint at `http://localhost:8501/_stcore/health`.

---

## Python API

You can use X-CAVATE as a Python library in your own scripts or notebooks:

**Basic usage:**

```python
from xcavate.config import XcavateConfig, PrinterType, PathfindingAlgorithm
from xcavate.pipeline import run_xcavate

config = XcavateConfig(
    network_file="inputs/network.txt",
    inletoutlet_file="inputs/inletoutlet.txt",
    nozzle_diameter=0.5,
    container_height=10.0,
    num_decimals=3,
    printer_type=PrinterType.PRESSURE,
    algorithm=PathfindingAlgorithm.DFS,
)

# Optional: track progress
def on_progress(step, description):
    print(f"Step {step}/7: {description}")

result = run_xcavate(config, progress_cb=on_progress)

# Access results
print(f"Generated {len(result['print_passes_sm'])} single-material passes")

# result keys:
#   "print_passes_sm"          - Single-material print passes (dict)
#   "print_passes_mm"          - Multimaterial passes (dict or None)
#   "points"                   - Interpolated coordinate array (ndarray)
#   "points_original"          - Pre-interpolation coordinates (ndarray)
#   "coord_num_dict_original"  - Vessel index -> point count (dict)
#   "changelog"                - Gap closure changelog (list of strings)
#   "speed_map_sm"             - Speed map for SM (dict or None)
#   "speed_map_mm"             - Speed map for MM (dict or None)
#   "material_map"             - Material classification (dict or None)
#   "instructions"             - Printing instructions (dict)
```

**With custom G-code templates:**

```python
from pathlib import Path
from xcavate.config import XcavateConfig, PrinterType
from xcavate.pipeline import run_xcavate

config = XcavateConfig(
    network_file="inputs/network.txt",
    inletoutlet_file="inputs/inletoutlet.txt",
    nozzle_diameter=0.5,
    container_height=10.0,
    num_decimals=3,
    printer_type=PrinterType.PRESSURE,
    # Enable custom G-code and point to the template directory
    custom_gcode=True,
    custom_gcode_dir=Path("inputs/custom"),
)

result = run_xcavate(config)
```

The pipeline loads all `.txt` template files from `custom_gcode_dir`. Any missing file is silently skipped (its section in the output will use the printer's default commands instead).

---

## Parameters Reference

### Required Parameters

| Parameter | CLI Flag | Description |
|-----------|----------|-------------|
| `network_file` | `--network_file` | Path to network coordinates .txt file |
| `inletoutlet_file` | `--inletoutlet_file` | Path to inlet/outlet coordinates .txt file |
| `nozzle_diameter` | `--nozzle_diameter` | Nozzle outer diameter in mm |
| `container_height` | `--container_height` | Print container height in mm |
| `num_decimals` | `--num_decimals` | Decimal places for output rounding |
| `amount_up` | `--amount_up` | Z-raise above container between passes (mm). Default: 10 |
| `printer_type` | `--printer_type` | 0 = Pressure, 1 = Positive Ink, 2 = Aerotech |
| `multimaterial` | `--multimaterial` | 0 = off, 1 = on |
| `tolerance_flag` | `--tolerance_flag` | 0 = off, 1 = on |
| `speed_calc` | `--speed_calc` | Compute varying print speeds? 0 = off, 1 = on |
| `plots` | `--plots` | Generate 3D plots? 0 = off, 1 = on |
| `downsample` | `--downsample` | Downsample interpolated network? 0 = off, 1 = on |
| `custom` | `--custom` | Use custom G-code templates? 0 = off, 1 = on |

### Optional Parameters

| Parameter | CLI Flag | Default | Description |
|-----------|----------|---------|-------------|
| `algorithm` | `--algorithm` | `dfs` | Pathfinding: `dfs` or `sweep_line` |
| `output_dir` | `--output_dir` | `outputs` | Output directory path |
| `tolerance` | `--tolerance` | 0 | Tolerance amount (mm) |
| `scale_factor` | `--scale_factor` | 1.0 | Network scale multiplier |
| `container_x` | `--container_x` | 50.0 | Container x-dimension (mm) |
| `container_y` | `--container_y` | 50.0 | Container y-dimension (mm) |
| `top_padding` | `--top_padding` | 0.0 | Padding above max z (mm) |
| `downsample_factor` | `--downsample_factor` | 1 | Downsample factor (integer) |
| `flow` | `--flow` | 0.127 | Volumetric flow rate (mm^3/s) |
| `print_speed` | `--print_speed` | 1.0 | Print speed / feed rate (mm/s) |
| `jog_speed` | `--jog_speed` | 5.0 | Jog speed (mm/s) |
| `jog_speed_lift` | `--jog_speed_lift` | 0.25 | Z-lift jog speed (mm/s) |
| `jog_translation` | `--jog_translation` | 10.0 | Nozzle-to-nozzle jog speed (mm/s) |
| `initial_lift` | `--initial_lift` | 0.5 | Initial lift distance (mm) |
| `dwell_start` | `--dwell_start` | 0.08 | Dwell at pass start (s) |
| `dwell_end` | `--dwell_end` | 0.08 | Dwell at pass end (s) |
| `num_overlap` | `--num_overlap` | 0 | Overlap nodes for gap closure |
| `close_sm` | `--close_sm` | 0 | Gap extension file for SM? 0/1 |
| `close_mm` | `--close_mm` | 0 | Gap extension file for MM? 0/1 |

### Multimaterial Parameters

| Parameter | CLI Flag | Default | Description |
|-----------|----------|---------|-------------|
| `offset_x` | `--offset_x` | 103.0 | Printhead X offset (mm) |
| `offset_y` | `--offset_y` | 0.5 | Printhead Y offset (mm) |
| `front_nozzle` | `--front_nozzle` | 1 | 1 = venous in front, 2 = behind |
| `printhead_1` | `--printhead_1` | Aa | Arterial printhead name |
| `printhead_2` | `--printhead_2` | Ab | Venous printhead name |
| `axis_1` | `--axis_1` | A | Arterial z-axis name |
| `axis_2` | `--axis_2` | B | Venous z-axis name |
| `resting_pressure` | `--resting_pressure` | 0.0 | Inactive nozzle pressure (psi) |
| `active_pressure` | `--active_pressure` | 5.0 | Active nozzle pressure (psi) |

### Positive Ink Displacement Parameters

| Parameter | CLI Flag | Default | Description |
|-----------|----------|---------|-------------|
| `positiveInk_start` | `--positiveInk_start` | 0.0 | Extrusion start value |
| `positiveInk_end` | `--positiveInk_end` | 0.0 | Extrusion stop value |
| `positiveInk_radii` | `--positiveInk_radii` | 0 | Use vessel radii? 0/1 |
| `positiveInk_diam` | `--positiveInk_diam` | 1.0 | Vessel diameter (mm) |
| `positiveInk_syringe_diam` | `--positiveInk_syringe_diam` | 1.0 | Syringe diameter (mm) |
| `positiveInk_factor` | `--positiveInk_factor` | 1.0 | Extrusion multiplier |
| `positiveInk_start_arterial` | `--positiveInk_start_arterial` | 0.0 | Arterial start value |
| `positiveInk_start_venous` | `--positiveInk_start_venous` | 0.0 | Venous start value |
| `positiveInk_end_arterial` | `--positiveInk_end_arterial` | 0.0 | Arterial end value |
| `positiveInk_end_venous` | `--positiveInk_end_venous` | 0.0 | Venous end value |

### Printer Types

| Value | Name | Description |
|-------|------|-------------|
| 0 | Pressure | Standard pressure-based extrusion |
| 1 | Positive Ink | Positive ink displacement |
| 2 | Aerotech | Aerotech 6-axis motion controller |

### Pathfinding Algorithms

| Name | CLI Value | Description |
|------|-----------|-------------|
| DFS | `dfs` | Depth-first search from lowest unvisited node with KD-tree collision detection. Default. |
| Sweep Line | `sweep_line` | Sort by z, trace upward. Naturally collision-free for upward printing. May produce fewer, longer passes. |

---

## Output Files

All output is written to the output directory (default: `outputs/`):

```
outputs/
├── graph/
│   ├── graph.txt               # Adjacency graph
│   ├── special_nodes.txt       # Branchpoints, endpoints, inlets, outlets
│   ├── SM_x_coords.txt         # Single-material x coordinates per pass
│   ├── SM_y_coords.txt         # Single-material y coordinates per pass
│   ├── SM_z_coords.txt         # Single-material z coordinates per pass
│   ├── SM_combined.txt         # Combined xyz per pass
│   ├── MM_*.txt                # Multimaterial equivalents (if enabled)
│   └── ...
├── gcode/
│   ├── gcode_SM_pressure.txt   # Single-material G-code
│   └── gcode_MM_pressure.txt   # Multimaterial G-code (if enabled)
├── plots/
│   ├── network_original.html   # Interactive 3D plot (original network)
│   ├── network_SM.html         # Interactive 3D plot (single material)
│   └── network_MM.html         # Interactive 3D plot (multimaterial)
└── changelog.txt               # Gap closure operations log
```

---

## Project Structure

```
X-CAVATE/
├── xcavate/
│   ├── __init__.py
│   ├── __main__.py              # python -m xcavate entry point
│   ├── cli.py                   # Command-line argument parsing
│   ├── config.py                # XcavateConfig dataclass + enums
│   ├── pipeline.py              # 7-step pipeline orchestrator
│   │
│   ├── core/                    # Core algorithms
│   │   ├── preprocessing.py     # Batch interpolation (O(n) vs original O(n^2))
│   │   ├── graph.py             # Graph construction + KD-tree branchpoint detection
│   │   ├── pathfinding.py       # DFS + Sweep Line with KD-tree collision detection
│   │   ├── gap_closure.py       # Unified gap closure pipeline
│   │   ├── postprocessing.py    # Subdivision, downsampling, overlap, reordering
│   │   └── multimaterial.py     # Arterial/venous classification
│   │
│   ├── io/                      # Input/output
│   │   ├── reader.py            # Network + inlet/outlet file parsing
│   │   ├── writer.py            # Coordinate output files
│   │   └── gcode/               # G-code generation
│   │       ├── base.py          # Abstract writer + custom code templates
│   │       ├── pressure.py      # Pressure printer G-code
│   │       ├── positive_ink.py  # Positive ink displacement G-code
│   │       └── aerotech.py      # Aerotech 6-axis G-code
│   │
│   ├── spatial/
│   │   └── index.py             # KD-tree spatial indexing wrapper
│   │
│   ├── viz/
│   │   └── plotting.py          # Plotly 3D visualization
│   │
│   ├── gui/
│   │   └── app.py               # Streamlit web interface
│   │
│   └── calibration/
│       └── __init__.py          # Calibration utilities (reuses core modules)
│
├── tests/
│   ├── conftest.py              # Shared test fixtures (Y-shaped network)
│   ├── test_preprocessing.py    # Interpolation + boundary detection tests
│   ├── test_graph.py            # Graph construction + branchpoint tests
│   ├── test_pathfinding.py      # DFS + collision detection tests
│   ├── test_gap_closure.py      # Gap closure pipeline tests
│   └── test_gcode.py            # G-code writer tests
│
├── inputs/
│   ├── custom/                  # Custom G-code templates (12 .txt files)
│   │   ├── header_code.txt
│   │   ├── start_extrusion_code.txt
│   │   ├── stop_extrusion_code.txt
│   │   ├── start_extrusion_code_printhead1.txt
│   │   ├── start_extrusion_code_printhead2.txt
│   │   ├── stop_extrusion_code_printhead1.txt
│   │   ├── stop_extrusion_code_printhead2.txt
│   │   ├── active_pressure_printhead1.txt
│   │   ├── active_pressure_printhead2.txt
│   │   ├── rest_pressure_printhead1.txt
│   │   ├── rest_pressure_printhead2.txt
│   │   └── dwell_code.txt
│   └── extension/               # Gap extension files (optional)
│
├── pyproject.toml               # Package metadata and dependencies
├── environment.yml              # Conda environment (xcavate-gui)
├── Dockerfile                   # Docker container for GUI deployment
└── README.md
```

---

## Development

### Running Tests

```bash
# With conda (dev tools already installed):
conda activate xcavate-gui
pytest tests/ -v

# With pip:
pip install ".[dev]"
pytest tests/ -v
```

### Code Style

```bash
ruff check xcavate/
```

### Building the Docker Image

```bash
docker build -t xcavate .
docker run -p 8501:8501 xcavate
```

---

## Volumetric Flow Rate

The volumetric flow rate `Q` of the ink through the printhead nozzle varies with the ink, syringe, and nozzle. It can be experimentally determined using the calibration module. This value is necessary when printing vessels of varying radii. If not specified, X-CAVATE defaults to 0.127 mm^3/s.

## Tolerancing

Branchpoints are sites prone to nozzle collisions because they contain many closely-spaced coordinates. The tolerance value overrides the nozzle outer diameter for collision detection at these sites: any neighboring coordinate within the tolerance distance will be included in the same print pass, even if it would normally be flagged as a collision. Default: 0 (no tolerance).

## Gap Closure

X-CAVATE has two features for optimizing closure of gaps at print pass junctions:

**1. Nodal Overlap** (`--num_overlap`): Overlap the end of a print pass with the previously-printed pass it connects to by N nodes. If fewer than N nodes exist in the existing pass, X-CAVATE retraces the entire pass.

**2. Segment Extension** (via extension files): Manually specify which passes to extend and by how much (delta x, y, z in mm). See `inputs/extension/` for file format.

---

## License

Copyright (c) Stanford University, The Regents of the University of California, and others.

All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject
to the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER
OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
