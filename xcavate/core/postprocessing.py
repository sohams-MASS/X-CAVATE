"""Post-processing: subdivision of DFS passes, downsampling, overlap, and pass reordering.

Replaces xcavate.py lines 997-1106 (subdivision), 3218-3248 (downsampling),
3729-3806 (overlap SM), 3880-3955 (overlap MM).
"""

import numpy as np
from typing import Dict, List, Set


def subdivide_passes(
    print_passes: Dict[int, List[int]],
    graph: Dict[int, List[int]],
    points: np.ndarray,
) -> Dict[int, List[int]]:
    """Break DFS passes at backtrack points where successive nodes are not neighbors.

    DFS can backtrack, creating non-consecutive node sequences within a single
    pass. This function splits passes at those discontinuities and ensures each
    resulting segment starts with the lower-z node (bottom-up print order).

    Args:
        print_passes: Raw DFS passes {pass_idx: [node_indices]}.
        graph: Adjacency dict {node: [neighbors]}.
        points: Coordinate array (N, 3+).

    Returns:
        Subdivided passes, re-indexed sequentially.
    """
    # Find break points in each pass
    break_points = {}
    for i in print_passes:
        breaks = []
        for idx in range(len(print_passes[i]) - 1):
            current_node = print_passes[i][idx]
            next_node = print_passes[i][idx + 1]
            if next_node not in graph[current_node]:
                breaks.append(next_node)
        break_points[i] = breaks

    # Split passes at break points
    new_matrix = {}
    for i in break_points:
        if not break_points[i]:
            continue
        new_passes = {}
        start = 0
        for counter, bp in enumerate(break_points[i]):
            end = print_passes[i].index(bp)
            new_passes[counter] = print_passes[i][start:end]
            start = end
        # Last segment
        new_passes[len(break_points[i])] = print_passes[i][start:]
        new_matrix[i] = new_passes

    # Compute total number of passes
    num_new = sum(len(v) for v in new_matrix.values()) - len(new_matrix)
    num_total = len(print_passes) + num_new

    # Assemble subdivided passes
    result = {}
    counter = 0
    counter_old = 0
    while counter < num_total:
        if counter_old in new_matrix:
            for sub_idx in range(len(new_matrix[counter_old])):
                result[counter] = new_matrix[counter_old][sub_idx]
                counter += 1
            counter_old += 1
        else:
            result[counter] = print_passes[counter_old]
            counter += 1
            counter_old += 1

    # Ensure each segment starts with the lower-z node
    for i in result:
        if len(result[i]) < 2:
            continue
        first_z = points[result[i][0], 2]
        last_z = points[result[i][-1], 2]
        if first_z > last_z:
            result[i].reverse()

    return result


def downsample_passes(
    print_passes: Dict[int, List[int]],
    points: np.ndarray,
    downsample_factor: int,
    branchpoint_list: List[int],
    branchpoint_list_keys: List[int],
    endpoint_nodes: List[int],
) -> Dict[int, List[int]]:
    """Reduce point density while preserving structural nodes.

    First/last nodes, branchpoints (parents + daughters), and vessel endpoints
    are always kept. Other nodes are kept every `downsample_factor` indices.

    Args:
        print_passes: Current passes.
        points: Coordinate array.
        downsample_factor: Keep every Nth non-structural node.
        branchpoint_list: Daughter node indices.
        branchpoint_list_keys: Parent branchpoint indices.
        endpoint_nodes: Vessel endpoint indices.

    Returns:
        Downsampled passes.
    """
    structural = set(branchpoint_list) | set(branchpoint_list_keys) | set(endpoint_nodes)
    result = {}

    for i in print_passes:
        nodes = print_passes[i]
        if len(nodes) <= 3:
            result[i] = list(nodes)
            continue

        downsampled = []
        for j, node in enumerate(nodes):
            # Always keep first, last, and structural nodes
            if j == 0 or j == len(nodes) - 1 or node in structural:
                downsampled.append(node)
            elif j % downsample_factor == 0:
                downsampled.append(node)
        result[i] = downsampled

    return result


def add_overlap(
    print_passes: Dict[int, List[int]],
    num_overlap: int,
    graph: Dict[int, List[int]],
) -> Dict[int, List[int]]:
    """Add nodal overlap between connected passes for gap closure.

    For each pair of consecutive passes where the last node of pass i is a
    graph neighbor of the first node of pass i+1, extend pass i+1 by prepending
    up to `num_overlap` nodes from the end of pass i (and vice versa).

    Args:
        print_passes: Current passes.
        num_overlap: Number of overlap nodes to add.
        graph: Adjacency dict.

    Returns:
        Passes with overlapping endpoints.
    """
    if num_overlap <= 0:
        return print_passes

    result = {i: list(v) for i, v in print_passes.items()}
    pass_indices = sorted(result.keys())

    for idx in range(len(pass_indices) - 1):
        curr_key = pass_indices[idx]
        next_key = pass_indices[idx + 1]
        curr_pass = result[curr_key]
        next_pass = result[next_key]

        if not curr_pass or not next_pass:
            continue

        last_of_curr = curr_pass[-1]
        first_of_next = next_pass[0]

        # If last node of current pass neighbors first node of next pass
        if first_of_next in graph.get(last_of_curr, []):
            # Prepend overlap nodes from end of current pass to start of next
            overlap = curr_pass[-min(num_overlap, len(curr_pass)) :]
            result[next_key] = overlap + next_pass

        last_of_next = next_pass[-1] if next_pass else None
        first_of_curr_next = (
            result[pass_indices[idx + 1]][0]
            if idx + 1 < len(pass_indices)
            else None
        )

    return result


def reorder_passes_nearest_neighbor(
    print_passes: Dict[int, List[int]],
    points: np.ndarray,
) -> Dict[int, List[int]]:
    """Reorder passes to minimize total nozzle travel between pass endpoints.

    Uses a greedy nearest-neighbor heuristic: starting from pass 0, always
    pick the unvisited pass whose start point is closest to the current
    pass's end point.

    Args:
        print_passes: Current passes.
        points: Coordinate array.

    Returns:
        Reordered passes with sequential indices.
    """
    if len(print_passes) <= 1:
        return print_passes

    # Compute start/end coordinates for each pass
    pass_keys = sorted(print_passes.keys())
    start_coords = {}
    end_coords = {}
    for k in pass_keys:
        nodes = print_passes[k]
        start_coords[k] = points[nodes[0], :3]
        end_coords[k] = points[nodes[-1], :3]

    # Greedy nearest-neighbor ordering
    ordered = [pass_keys[0]]
    remaining = set(pass_keys[1:])

    while remaining:
        current_end = end_coords[ordered[-1]]
        best_key = None
        best_dist = float("inf")
        for k in remaining:
            dist = np.linalg.norm(start_coords[k] - current_end)
            if dist < best_dist:
                best_dist = dist
                best_key = k
        ordered.append(best_key)
        remaining.remove(best_key)

    return {i: print_passes[k] for i, k in enumerate(ordered)}
