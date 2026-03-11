# X-CAVATE Protocol: G-Code Generation from Vascular Network Geometry

**Stage II of the vascular network 3D bioprinting workflow.**

This protocol describes how to use X-CAVATE to convert SimVascular b-spline output into collision-free 3D printer G-code. X-CAVATE can be run in three modes: a **web GUI** (recommended for new users), a **command-line interface**, or via **Docker**. The steps below cover all three.

---

## Part A: Installation (5 minutes)

### Option 1: Conda (Recommended)

1. Open a terminal (Mac: Terminal.app; Windows: Anaconda Prompt or PowerShell).

2. Confirm conda is installed:
   ```
   conda --version
   ```
   If not installed, download Anaconda or Miniconda from [https://docs.conda.io/en/latest/miniconda.html](https://docs.conda.io/en/latest/miniconda.html).

3. Navigate to the folder where you want to store X-CAVATE and clone the repository:
   ```
   git clone https://github.com/skylarscottlab/X-CAVATE.git
   cd X-CAVATE
   ```
   Alternatively, download and unzip the repository from the GitHub page (green "Code" button > "Download ZIP").

4. Create and activate the conda environment (installs Python 3.11, all dependencies, and the X-CAVATE package):
   ```
   conda env create -f environment.yml
   conda activate xcavate-gui
   ```

5. Verify the installation:
   ```
   xcavate --help
   ```
   You should see the full list of command-line parameters.

### Option 2: pip install

1. Open a terminal (Mac: Terminal.app; Windows: Anaconda Prompt or PowerShell).

2. Confirm Python 3.9+ is installed:
   ```
   python3 --version
   ```

3. Navigate to the folder where you want to store X-CAVATE and clone the repository:
   ```
   git clone https://github.com/skylarscottlab/X-CAVATE.git
   cd X-CAVATE
   ```
   Alternatively, download and unzip the repository from the GitHub page (green "Code" button > "Download ZIP").

4. Install X-CAVATE with GUI support (includes all required libraries: numpy, scipy, pandas, plotly, matplotlib, streamlit):
   ```
   pip install ".[gui]"
   ```
   If you only need the CLI (no web interface):
   ```
   pip install .
   ```

5. Verify the installation:
   ```
   xcavate --help
   ```
   You should see the full list of command-line parameters.

### Option 3: Docker (no Python required)

1. Install Docker Desktop from [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop).

2. Open a terminal and navigate to the X-CAVATE folder:
   ```
   cd X-CAVATE
   ```

3. Build the Docker image:
   ```
   docker build -t xcavate .
   ```

4. Run the container:
   ```
   docker run -p 8501:8501 xcavate
   ```

5. Open your browser to **http://localhost:8501**. The X-CAVATE web interface should appear.

---

## Part B: Prepare Input Files (5 minutes)

X-CAVATE requires two input files from your SimVascular workflow.

### B.1 Network File (b-splines)

This file contains the vessel centerline coordinates exported from SimVascular. Each vessel has a header line followed by coordinate data rows.

**Format:**
```
Vessel: 0, Number of Points: 100
33.4878, 0.0000, 53.5303, 0.0200
33.4115, -0.5285, 52.7311, 0.0200
...
Vessel: 1, Number of Points: 100
15.0600, -37.3300, 11.6600, 0.0190
...
```

- **Columns 1-3** (required): x, y, z coordinates in centimeters.
- **Column 4** (optional): vessel radius, needed if using speed calculation.
- **Column 5** (optional): arterial/venous flag (0 = venous, nonzero = arterial), needed for multimaterial printing.

> **CAUTION:** Coordinates must be in centimeters. X-CAVATE internally converts to millimeters.

> **CAUTION:** Limit each vessel to no more than 100 coordinates to avoid long runtimes.

### B.2 Inlet/Outlet File

This file identifies which network locations are inlets (where printing begins) and outlets.

**Format:**
```
inlet
21.97, -15.43, 50.00
11.81, 0.00, 21.34
outlet
36.05, -27.19, 50.00
50.00, 0.00, 26.54
```

Each section begins with the keyword `inlet` or `outlet` on its own line, followed by one or more (x, y, z) coordinate triplets. You can have any number of inlets and outlets.

> **Note:** Inlet/outlet coordinates are matched to the nearest network point automatically. They do not need to exactly match a coordinate in the network file.

### B.3 File Placement

- **GUI or Docker mode:** Files are uploaded through the web interface. No file placement needed.
- **CLI mode:** Transfer both files into the `inputs/` folder inside the X-CAVATE directory.

---

## Part C: Custom G-Code Templates (5 minutes, optional)

Custom G-code templates adapt X-CAVATE's output to your specific printer hardware and software. Each template file contains a G-code snippet that is automatically inserted at the appropriate location in the final G-code output.

The `inputs/custom/` folder contains 12 template files with placeholder text. Replace the placeholder text with your own G-code for each section relevant to your printer.

### C.1 Header

| Step | File to Edit | Instructions |
|------|-------------|--------------|
| 1 | `header_code.txt` | Replace the placeholder text with your custom G-code for the header section of the final G-code output. Include any code required for the functioning of your printer, such as establishing connections between external pressure boxes and syringes. |

### C.2 Single Material Extrusion

Skip this section if printing multimaterial; proceed to C.3.

| Step | File to Edit | Instructions |
|------|-------------|--------------|
| 2 | `start_extrusion_code.txt` | Replace the placeholder text with your custom G-code for starting extrusion. |
| 3 | `stop_extrusion_code.txt` | Replace the placeholder text with your custom G-code for stopping extrusion. |

### C.3 Multimaterial Extrusion

Skip this section if printing single material; proceed to C.4.

| Step | File to Edit | Instructions |
|------|-------------|--------------|
| 4 | `start_extrusion_code_printhead1.txt` | Replace with your G-code for starting extrusion of Printhead 1 (arterial). |
| 5 | `start_extrusion_code_printhead2.txt` | Replace with your G-code for starting extrusion of Printhead 2 (venous). |
| 6 | `stop_extrusion_code_printhead1.txt` | Replace with your G-code for stopping extrusion of Printhead 1 (arterial). |
| 7 | `stop_extrusion_code_printhead2.txt` | Replace with your G-code for stopping extrusion of Printhead 2 (venous). |
| 8 | `active_pressure_printhead1.txt` | Replace with your G-code for setting the ink extrusion pressure of Printhead 1 when it is the **active** printhead. |
| 9 | `active_pressure_printhead2.txt` | Replace with your G-code for setting the ink extrusion pressure of Printhead 2 when it is the **active** printhead. |
| 10 | `rest_pressure_printhead1.txt` | Replace with your G-code for setting the ink extrusion pressure of Printhead 1 when it is the **inactive** printhead. |
| 11 | `rest_pressure_printhead2.txt` | Replace with your G-code for setting the ink extrusion pressure of Printhead 2 when it is the **inactive** printhead. |

### C.4 Dwell (Optional)

Incorporating time delays ("dwells") at the first and last node of each print pass deposits additional ink at each junction, improving the connection via a process similar to "spot welding."

| Step | File to Edit | Instructions |
|------|-------------|--------------|
| 12 | `dwell_code.txt` | Replace with your G-code for creating a time delay at the start and end of each print pass (e.g., `G4 P80` for an 80 ms dwell). |

### How to provide custom G-code in each mode

| Mode | How to provide custom G-code |
|------|------------------------------|
| **GUI** | Enable the "Custom G-code" toggle in the sidebar's Advanced section. A tabbed editor (Header, Single Material, Multimaterial, Dwell) appears in the main area. Paste your G-code into the text areas. |
| **CLI** | Edit the `.txt` files in `inputs/custom/` directly with a text editor (e.g., `nano`, TextEdit, Sublime Text), then run with `--custom 1`. |
| **Docker** | *Option A:* Use the GUI editor in the browser (no file mounting needed). *Option B:* Mount your local `inputs/custom/` folder into the container: `docker run -p 8501:8501 -v $(pwd)/inputs/custom:/app/inputs/custom xcavate`, then enable "Custom G-code" in the GUI. |

---

## Part D: Execute X-CAVATE (5 minutes)

### Mode 1: Web GUI

1. Activate the environment and start the server:
   ```
   conda activate xcavate-gui
   streamlit run xcavate/gui/app.py
   ```
   A browser window opens at **http://localhost:8501**.

2. In the **sidebar**, upload your Network file and Inlet/Outlet file.

3. Set the **Required Parameters**:
   - **Nozzle diameter** (mm): Outer diameter of the print nozzle.
   - **Container height** (mm): Height of the print container.
   - **Decimal places**: Number of decimal places for output rounding.
   - **Amount up** (mm): Distance to raise the nozzle above the container between passes.

4. Select a **Printer type**: Pressure, Positive Ink, or Aerotech.

5. (Optional) Toggle **Multimaterial** if printing with two inks.

6. (Optional) Expand the optional parameter sections to adjust:
   - Tolerancing
   - Print settings (speed, flow, jog speeds, dwell times)
   - Geometry (container dimensions, scale factor, padding)
   - Downsampling
   - Multimaterial settings (printhead offsets, names, pressures)
   - Positive ink displacement settings
   - Advanced (custom G-code, pathfinding algorithm, overlap nodes, plots)

7. If using custom G-code, enable the toggle in the Advanced section and fill in the template editor tabs (see Part C).

8. Click **Run X-CAVATE**.

9. The progress bar tracks the pipeline through 7 steps:
   1. Reading network and inlet/outlet files
   2. Interpolating network to nozzle resolution
   3. Building adjacency graph and detecting branchpoints
   4. Generating collision-free print passes
   5. Post-processing: subdivision, gap closure, overlap
   6. Processing multimaterial passes
   7. Writing output files and G-code

10. When complete, the main area displays:
    - An interactive 3D plot of the print passes (rotatable, zoomable).
    - Download buttons for G-code files, coordinate files, and the changelog.

11. Click the download buttons to save output files to your computer.

### Mode 2: Command-Line Interface

1. Open a terminal, activate the environment, and navigate to the X-CAVATE directory:
   ```
   conda activate xcavate-gui
   cd X-CAVATE
   ```

2. (If using custom G-code) Edit the template files in `inputs/custom/` with your G-code (see Part C), then include `--custom 1` in the command below.

3. Run X-CAVATE with your parameters. Example for a single-material pressure print:
   ```
   xcavate \
     --network_file inputs/VesselNetwork.txt \
     --inletoutlet_file inputs/InletsOutlets.txt \
     --nozzle_diameter 0.65 \
     --container_height 50.0 \
     --num_decimals 5 \
     --amount_up 10.0 \
     --printer_type 0 \
     --multimaterial 0 \
     --tolerance_flag 0 \
     --speed_calc 1 \
     --plots 1 \
     --downsample 0 \
     --custom 1 \
     --flow 0.127
   ```
   Or equivalently:
   ```
   python -m xcavate [same arguments]
   ```

4. As the program executes, the terminal outputs progress through each pipeline step:
   1. Network importation
   2. Interpolation of network coordinates
   3. Graph generation and branchpoint detection
   4. DFS algorithm to generate print passes
   5. Subdivision and gap closure
   6. (If multimaterial) Multimaterial pass generation
   7. (If speed_calc) Print speed calculation
   8. Output file generation

5. When complete, output files are written to the `outputs/` directory (or the path specified by `--output_dir`):
   ```
   outputs/
   ├── graph/          # Coordinate files, adjacency graph, special nodes
   ├── gcode/          # G-code text files (SM and/or MM)
   ├── plots/          # Interactive 3D HTML plots
   └── changelog.txt   # Gap closure log
   ```

**Required CLI parameters:**

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--network_file` | Path to network coordinates file | `inputs/VesselNetwork.txt` |
| `--inletoutlet_file` | Path to inlet/outlet coordinates file | `inputs/InletsOutlets.txt` |
| `--nozzle_diameter` | Nozzle outer diameter (mm) | `0.65` |
| `--container_height` | Container height (mm) | `50` |
| `--num_decimals` | Decimal places for rounding | `5` |
| `--amount_up` | Z-raise between passes (mm) | `10` |
| `--printer_type` | 0 = Pressure, 1 = Positive Ink, 2 = Aerotech | `0` |
| `--multimaterial` | 0 = single, 1 = multimaterial | `0` |
| `--tolerance_flag` | 0 = off, 1 = on | `0` |
| `--speed_calc` | 0 = off, 1 = on | `1` |
| `--plots` | 0 = off, 1 = on | `1` |
| `--downsample` | 0 = off, 1 = on | `0` |
| `--custom` | 0 = off, 1 = on | `1` |

**Commonly used optional parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--algorithm` | `dfs` | Pathfinding algorithm: `dfs` |
| `--output_dir` | `outputs` | Output directory |
| `--flow` | `0.127` | Volumetric flow rate (mm^3/s) |
| `--print_speed` | `1.0` | Print speed (mm/s) |
| `--tolerance` | `0` | Tolerance amount (mm) |
| `--scale_factor` | `1.0` | Network scale multiplier |
| `--num_overlap` | `0` | Overlap nodes for gap closure |

See the README for the complete list of 35+ optional parameters.

### Mode 3: Docker

1. Build and start the container (if not already running):
   ```
   docker build -t xcavate .
   docker run -p 8501:8501 -v $(pwd)/outputs:/app/outputs xcavate
   ```

2. Open **http://localhost:8501** in your browser.

3. Follow the same steps as **Mode 1 (Web GUI)** above. All functionality is identical.

4. To use pre-written custom G-code template files, mount the `inputs/custom/` folder:
   ```
   docker run -p 8501:8501 \
     -v $(pwd)/inputs/custom:/app/inputs/custom \
     -v $(pwd)/outputs:/app/outputs \
     xcavate
   ```

5. Output files are accessible in the mounted `outputs/` directory on your host machine, or via the download buttons in the GUI.

---

## Part E: Inspect Output Files

After execution completes, X-CAVATE produces the following outputs:

### E.1 G-Code Files

Located in `outputs/gcode/`:

| File | Description |
|------|-------------|
| `gcode_SM_pressure.txt` | Single-material G-code (for pressure printer) |
| `gcode_MM_pressure.txt` | Multimaterial G-code (if multimaterial enabled) |

The filename suffix matches your selected printer type (`pressure`, `positive_ink`, or `aerotech`).

### E.2 Coordinate Files

Located in `outputs/graph/`:

| File | Description |
|------|-------------|
| `SM_x_coords.txt` | Single-material x-coordinates per print pass |
| `SM_y_coords.txt` | Single-material y-coordinates per print pass |
| `SM_z_coords.txt` | Single-material z-coordinates per print pass |
| `SM_combined.txt` | Combined x, y, z per print pass |
| `MM_*.txt` | Multimaterial equivalents (if enabled) |
| `graph.txt` | Full adjacency graph |
| `special_nodes.txt` | Branchpoints, endpoints, inlets, outlets |

### E.3 Visualizations

Located in `outputs/plots/`:

| File | Description |
|------|-------------|
| `network_SM.html` | Interactive 3D plot of single-material passes |
| `network_MM.html` | Interactive 3D plot of multimaterial passes |

Open the `.html` files in any web browser to rotate, zoom, and inspect the print paths.

### E.4 Changelog

| File | Description |
|------|-------------|
| `outputs/changelog.txt` | Log of all gap closure operations performed |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Runtime instance already exists` (GUI) | A stale Streamlit process is running. Kill it: `pkill -f streamlit`, then restart. |
| Inlet/outlet matching warnings | The inlet/outlet coordinates in your file are approximate. X-CAVATE matches to the nearest network point and logs the distance. Verify the matches are reasonable. |
| Pipeline hangs on large networks | Reduce the number of coordinates per vessel to 100 or fewer, or enable downsampling. |
| `ModuleNotFoundError` | Run `pip install ".[gui]"` to install all dependencies. |
| Docker container won't start | Ensure Docker Desktop is running and port 8501 is not in use. |

---

## Quick Reference: Mode Comparison

| Feature | GUI | CLI | Docker |
|---------|-----|-----|--------|
| Python installation required | Yes (via conda or pip) | Yes (via conda or pip) | No |
| Custom G-code via file editing | No (use GUI editor) | Yes (`inputs/custom/`) | Optional (mount or use GUI editor) |
| Custom G-code via GUI editor | Yes | No | Yes |
| Interactive 3D plots | In-browser | Open `.html` files | In-browser |
| File download | Download buttons | Files in `outputs/` | Download buttons + mounted volume |
| Best for | New users, quick runs | Scripting, automation, batch processing | Reproducible environments, sharing |
