"""Pipeline registry, case discovery, and per-pipeline arg builders."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .synth_io import synthesize_inletoutlet


SCIENCE_SCRIPT = Path(
    "/Users/sohams/Downloads/Copy of Xcavate used for Science paper 2/xcavate_Science.py"
)
X1130_SCRIPT = Path(
    "/Users/sohams/X-CAVATE/.claude/worktrees/serene-proskuriakova/xcavate_11_30_25.py"
)


@dataclass
class Case:
    network: Path
    inletoutlet: Path
    multimaterial: bool
    slug: str


@dataclass
class Pipeline:
    name: str
    label: str
    invocation: list[str]
    build_args: Callable[["Case", dict], list[str]]
    locate_gcode: Callable[[Path, "Case"], list[Path]]


CANONICAL_PARAMS: dict = {
    "nozzle_diameter": 0.41,
    "container_height": 50.0,
    "container_x": 50.0,
    "container_y": 50.0,
    "container_z": 50.0,
    "print_speed": 1.0,
    "jog_speed": 5.0,
    "flow": 0.1272265034574846,
    "dwell_start": 0.08,
    "dwell_end": 0.08,
    "tolerance_flag": 0,
    "tolerance": 0.0,
    "speed_calc": 1,
    "downsample": 0,
    "plots": 0,
    "num_decimals": 6,
    "scale_factor": 1.0,
    "top_padding": 0.0,
    "amount_up": 10.0,
    "custom": 0,
    "printer_type": 0,
    "convert_factor": 10.0,
}


def _slugify(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem)
    return base.strip("_") or "case"


def _is_multimaterial(network_name: str, ioc_name: str | None) -> bool:
    return "multimaterial" in network_name.lower() or (
        ioc_name is not None and "multimaterial" in ioc_name.lower()
    )


def _find_companion_io(network_path: Path) -> Path | None:
    """Find the I/O file matching the network. Score by shared alphanumeric tokens."""
    parent = network_path.parent
    candidates: list[Path] = []
    for cand in parent.iterdir():
        if not cand.is_file() or cand == network_path:
            continue
        nl = cand.name.lower()
        if ("inlet" in nl and "outlet" in nl) or "inletoutlet" in nl:
            candidates.append(cand)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    def tokens(name: str) -> set[str]:
        return set(re.findall(r"[A-Za-z0-9]+", Path(name).stem.lower()))

    net_tokens = tokens(network_path.name)
    return max(candidates, key=lambda p: len(net_tokens & tokens(p.name)))


def discover_cases(verification_root: Path) -> list[Case]:
    """Walk the verification dir and return Case records for every network file."""
    verification_root = Path(verification_root)
    cases: list[Case] = []
    network_paths: list[Path] = []
    for p in sorted(verification_root.rglob("*.txt")):
        nl = p.name.lower()
        if "inlet" in nl and "outlet" in nl:
            continue
        if "inletoutlet" in nl:
            continue
        network_paths.append(p)

    for net in network_paths:
        ioc = _find_companion_io(net)
        if ioc is None:
            ioc = synthesize_inletoutlet(net)
        cases.append(Case(
            network=net,
            inletoutlet=ioc,
            multimaterial=_is_multimaterial(net.name, ioc.name if ioc else None),
            slug=_slugify(net.name),
        ))
    return cases


def build_args_science(case: Case, params: dict) -> list[str]:
    return [
        "--network_file", str(case.network),
        "--inletoutlet_file", str(case.inletoutlet),
        "--multimaterial", str(int(case.multimaterial)),
        "--tolerance_flag", str(params["tolerance_flag"]),
        "--tolerance", str(params["tolerance"]),
        "--nozzleOD", str(params["nozzle_diameter"]),
        "--container_x", str(params["container_x"]),
        "--container_y", str(params["container_y"]),
        "--container_z", str(params["container_z"]),
        "--numDecimalsOutput", str(params["num_decimals"]),
        "--speed_calc", str(params["speed_calc"]),
        "--plots", str(params["plots"]),
        "--downsample", str(params["downsample"]),
        "--scaleFactor", str(params["scale_factor"]),
        "--topPadding", str(params["top_padding"]),
        "--flow", str(params["flow"]),
    ]


def build_args_x1130(case: Case, params: dict) -> list[str]:
    return [
        "--network_file", str(case.network),
        "--inletoutlet_file", str(case.inletoutlet),
        "--multimaterial", str(int(case.multimaterial)),
        "--tolerance_flag", str(params["tolerance_flag"]),
        "--tolerance", str(params["tolerance"]),
        "--nozzle_diameter", str(params["nozzle_diameter"]),
        "--container_height", str(params["container_height"]),
        "--container_x", str(params["container_x"]),
        "--container_y", str(params["container_y"]),
        "--num_decimals", str(params["num_decimals"]),
        "--speed_calc", str(params["speed_calc"]),
        "--plots", str(params["plots"]),
        "--downsample", str(params["downsample"]),
        "--scale_factor", str(params["scale_factor"]),
        "--top_padding", str(params["top_padding"]),
        "--flow", str(params["flow"]),
        "--print_speed", str(params["print_speed"]),
        "--jog_speed", str(params["jog_speed"]),
        "--dwell_start", str(params["dwell_start"]),
        "--dwell_end", str(params["dwell_end"]),
        "--amount_up", str(params["amount_up"]),
        "--custom", str(params["custom"]),
        "--printer_type", str(params["printer_type"]),
    ]


def build_args_main(case: Case, params: dict) -> list[str]:
    return build_args_x1130(case, params) + [
        "--convert_factor", str(params["convert_factor"]),
        "--algorithm", "dfs",
        "--reorder_passes", "0",
        "--branchpoint_distance_threshold", "0",
        "--speed_unit", "mm/s",
        "--output_dir", "outputs",
    ]


def _locate_science(cwd: Path, case: Case) -> list[Path]:
    candidates: list[Path] = []
    for name in ("gcode.txt", "gcode_multimaterial.txt"):
        p = cwd / name
        if p.exists():
            candidates.append(p)
    return candidates


def _locate_modern(cwd: Path, case: Case) -> list[Path]:
    gcode_dir = cwd / "outputs" / "gcode"
    if not gcode_dir.exists():
        return []
    return sorted(gcode_dir.glob("gcode_*.txt"))


PIPELINES: list[Pipeline] = [
    Pipeline(
        name="science",
        label="xcavate_Science.py (Jun 2023)",
        invocation=["python", str(SCIENCE_SCRIPT)],
        build_args=build_args_science,
        locate_gcode=_locate_science,
    ),
    Pipeline(
        name="x1130",
        label="xcavate_11_30_25.py (Nov 2025)",
        invocation=["python", str(X1130_SCRIPT)],
        build_args=build_args_x1130,
        locate_gcode=_locate_modern,
    ),
    Pipeline(
        name="main",
        label="sohams-MASS/X-CAVATE main",
        invocation=["python", "-m", "xcavate"],
        build_args=build_args_main,
        locate_gcode=_locate_modern,
    ),
]
