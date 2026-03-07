"""Multimaterial processing: arterial/venous classification and speed computation.

Handles the splitting and classification of print passes by material type
(arterial vs venous) and computes per-node print speeds based on vessel radii.
"""

import numpy as np
from typing import Dict, List, Optional


def classify_passes_by_material(
    print_passes: Dict[int, List[int]],
    points: np.ndarray,
    num_columns: int,
) -> Dict[int, int]:
    """Determine arterial (1) vs venous (0) classification for each pass.

    Uses the artven column (column index 4) of the second node in each pass.
    For single-node passes, uses that node's value directly.

    Args:
        print_passes: Dict of pass_idx -> [node_indices].
        points: Coordinate array with artven in column 4.
        num_columns: Number of columns in the original input (3, 4, or 5).

    Returns:
        Dict mapping pass_idx -> 0 (venous) or 1 (arterial).
    """
    if num_columns < 5:
        return {i: 0 for i in print_passes}

    classification = {}
    for i in print_passes:
        nodes = print_passes[i]
        if len(nodes) > 1:
            # Use second node to avoid branchpoint ambiguity
            artven = points[nodes[1], 4]
        else:
            artven = points[nodes[0], 4]
        classification[i] = 0 if artven == 0 else 1
    return classification


def compute_radius_speeds(
    print_passes: Dict[int, List[int]],
    points: np.ndarray,
    flow: float,
    num_columns: int,
) -> Optional[Dict[int, float]]:
    """Compute per-node print speeds from vessel radii and flow rate.

    Speed = flow / (pi * r^2) where r is the vessel radius at each node.

    Args:
        print_passes: Dict of passes.
        points: Coordinate array with radius in column 3.
        flow: Volumetric flow rate (mm^3/s).
        num_columns: Number of columns in input.

    Returns:
        Dict mapping node_index -> speed (mm/s), or None if radii not available.
    """
    if num_columns < 4:
        return None

    speed_map = {}
    for i in print_passes:
        for node in print_passes[i]:
            r = points[node, 3]
            if r > 0:
                area = np.pi * r ** 2
                speed_map[node] = flow / area
            else:
                speed_map[node] = 1.0  # fallback
    return speed_map


def generate_multimaterial_colors(
    print_passes: Dict[int, List[int]],
    material_map: Dict[int, int],
) -> List[str]:
    """Generate color list for multimaterial visualization.

    Args:
        print_passes: Dict of passes.
        material_map: Dict mapping pass_idx -> 0 (venous/blue) or 1 (arterial/red).

    Returns:
        List of color strings indexed by pass number.
    """
    colors = []
    for i in sorted(print_passes.keys()):
        if material_map.get(i, 0) == 0:
            colors.append("blue")
        else:
            colors.append("red")
    return colors
