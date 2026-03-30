"""Graph construction and branchpoint detection for vascular networks.

This module refactors the monolithic graph-building logic from xcavate.py
(lines 517-906) into structured functions with algorithmic improvements:

- Endpoint and vessel-range identification post-interpolation
- Branchpoint detection via nearest-neighbor search using cKDTree
- Adjacency graph construction with O(n) vessel-interior wiring
- Daughter-pair validation via parametric line equations
- Repeated-daughter resolution (daughters shared by multiple parents)

The central entry point is :func:`build_graph`, which returns all data
structures consumed by downstream pathfinding and G-code generation.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Set, Tuple

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
Graph = Dict[int, List[int]]
BranchDict = Dict[int, List[int]]
DaughterDict = Dict[int, int]
NodesByVessel = Dict[int, List[int]]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_graph(
    points: NDArray[np.floating],
    coord_num_dict_interp: Dict[int, int],
    vessel_start_nodes: List[int],
    inlet_nodes: List[int],
    outlet_nodes: List[int],
    branchpoint_distance_threshold: float = 0.0,
) -> Tuple[
    Graph,
    BranchDict,
    List[int],
    DaughterDict,
    List[int],
    NodesByVessel,
    Set[int],
]:
    """Construct the vascular adjacency graph with branchpoint connections.

    This is the main entry point that orchestrates endpoint detection,
    branchpoint identification, and graph wiring.

    Parameters
    ----------
    points : ndarray of shape (N, 3)
        Interpolated 3-D coordinates for every node in the network.
    coord_num_dict_interp : dict[int, int]
        Mapping from vessel index to the number of nodes in that vessel
        (post-interpolation).
    vessel_start_nodes : list[int]
        Starting node index for each vessel in ``points`` (sorted by vessel
        index, i.e. ``vessel_start_nodes[v]`` is the first node of vessel
        *v*).
    inlet_nodes : list[int]
        Node indices that are physiological inlets (true endpoints).
    outlet_nodes : list[int]
        Node indices that are physiological outlets (true endpoints).
    branchpoint_distance_threshold : float
        Maximum distance for an endpoint to be connected as a branchpoint.
        Endpoints farther than this from the nearest node in another vessel
        are treated as leaf nodes.  0.0 disables the threshold (legacy).

    Returns
    -------
    graph : dict[int, list[int]]
        Adjacency list. ``graph[n]`` is a *sorted* list of neighbour
        indices for node *n*, including a self-loop.
    branch_dict : dict[int, list[int]]
        Parent-to-daughter mapping.
        ``branch_dict[parent] = [daughter1, daughter2]``.
    branchpoint_list : list[int]
        Flat list of all daughter node indices (may contain duplicates
        when a daughter is claimed by multiple parents).
    branchpoint_daughter_dict : dict[int, int]
        Daughter-to-parent mapping (inverse of *branch_dict*).
    endpoint_nodes : list[int]
        Start and end node index for every vessel, ordered as
        ``[v0_start, v0_end, v1_start, v1_end, ...]``.
    nodes_by_vessel : dict[int, list[int]]
        ``nodes_by_vessel[v]`` is the list of node indices belonging to
        vessel *v*, in path order.
    repeat_daughters : set[int]
        Daughter nodes that appear in more than one parent's daughter pair.

    Raises
    ------
    ValueError
        If *points* has fewer than 2 rows or an unexpected shape.
    """
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(
            f"Expected points with shape (N, 3), got {points.shape}"
        )

    num_vessels = len(coord_num_dict_interp)

    # Step 1 -- identify endpoints and per-vessel node ranges
    endpoint_nodes, nodes_by_vessel, num_prev_array = _find_endpoints(
        points, coord_num_dict_interp, num_vessels
    )

    # Step 2 -- detect branchpoints using KD-tree accelerated search
    branch_dict = _find_branchpoints(
        points,
        num_vessels,
        endpoint_nodes,
        num_prev_array,
        nodes_by_vessel,
        inlet_nodes,
        outlet_nodes,
        branchpoint_distance_threshold=branchpoint_distance_threshold,
    )

    # Step 3 -- build daughter-centric lookups and detect repeated daughters
    branchpoint_list, branchpoint_daughter_dict, repeat_daughters = (
        _compile_daughter_structures(branch_dict)
    )

    # Step 4 -- assemble the adjacency graph
    graph = _build_adjacency(
        points,
        endpoint_nodes,
        nodes_by_vessel,
        branch_dict,
        branchpoint_daughter_dict,
        repeat_daughters,
    )

    logger.info(
        "Graph constructed: %d nodes, %d vessels, %d branchpoints",
        points.shape[0],
        num_vessels,
        len(branch_dict),
    )
    return (
        graph,
        branch_dict,
        branchpoint_list,
        branchpoint_daughter_dict,
        endpoint_nodes,
        nodes_by_vessel,
        repeat_daughters,
    )


# ---------------------------------------------------------------------------
# Step 1 -- Endpoint and vessel-range identification
# ---------------------------------------------------------------------------

def _find_endpoints(
    points: NDArray[np.floating],
    coord_num_dict_interp: Dict[int, int],
    num_vessels: int,
) -> Tuple[List[int], NodesByVessel, List[int]]:
    """Identify the two endpoint node indices for each vessel.

    Parameters
    ----------
    points : ndarray of shape (N, 3)
    coord_num_dict_interp : dict[int, int]
        Number of nodes per vessel.
    num_vessels : int

    Returns
    -------
    endpoint_nodes : list[int]
        Flat list ``[v0_start, v0_end, v1_start, v1_end, ...]``.
    nodes_by_vessel : dict[int, list[int]]
        Per-vessel node index lists.
    num_prev_array : list[int]
        Cumulative node count *before* each vessel (used by branchpoint
        detection to exclude intra-vessel nodes).
    """
    endpoint_nodes: List[int] = []
    nodes_by_vessel: NodesByVessel = {}
    num_prev_array: List[int] = []

    cumulative = 0
    for v in range(num_vessels):
        num_prev_array.append(cumulative)
        vessel_len = coord_num_dict_interp[v]
        start_index = cumulative
        end_index = cumulative + vessel_len - 1
        cumulative += vessel_len

        endpoint_nodes.append(start_index)
        endpoint_nodes.append(end_index)

        nodes_by_vessel[v] = list(range(start_index, end_index + 1))

    return endpoint_nodes, nodes_by_vessel, num_prev_array


# ---------------------------------------------------------------------------
# Step 2 -- Branchpoint detection (KD-tree accelerated)
# ---------------------------------------------------------------------------

def _find_branchpoints(
    points: NDArray[np.floating],
    num_vessels: int,
    endpoint_nodes: List[int],
    num_prev_array: List[int],
    nodes_by_vessel: NodesByVessel,
    inlet_nodes: List[int],
    outlet_nodes: List[int],
    branchpoint_distance_threshold: float = 0.0,
) -> BranchDict:
    """Detect branchpoints where vessel endpoints meet other vessels.

    For each vessel endpoint that is *not* a true inlet/outlet, find the
    two nearest nodes in other vessels.  These two nearest nodes become the
    "daughter" pair and the endpoint becomes the "parent branchpoint".

    Uses :class:`scipy.spatial.cKDTree` for O(k log N) nearest-neighbour
    queries instead of the original O(N * num_endpoints) nested loop.

    Parameters
    ----------
    points : ndarray of shape (N, 3)
    num_vessels : int
    endpoint_nodes : list[int]
    num_prev_array : list[int]
    nodes_by_vessel : dict[int, list[int]]
    inlet_nodes, outlet_nodes : list[int]
        True endpoints to exclude from branchpoint detection.
    branchpoint_distance_threshold : float
        Maximum distance (in coordinate units) between an endpoint and the
        nearest node in another vessel for the connection to be considered a
        real branchpoint.  Endpoints farther than this are treated as leaf
        nodes and skipped.  A value of 0.0 disables the threshold (legacy
        behaviour: all endpoints connect).

    Returns
    -------
    branch_dict : dict[int, list[int]]
        ``{parent_node: [daughter1, daughter2]}``, with inlets/outlets
        removed and daughter pairs validated.
    """
    true_endpoints = set(inlet_nodes) | set(outlet_nodes)
    n_points = points.shape[0]

    # Build a full KD-tree over all points
    tree = cKDTree(points)

    branch_dict: BranchDict = {}
    counter = 0

    for v in range(num_vessels):
        ep1_idx = counter       # index into endpoint_nodes
        ep2_idx = counter + 1
        counter += 2

        # Compute set of node indices belonging to OTHER vessels
        vessel_nodes_set = set(nodes_by_vessel[v])

        for ep_pos in (ep1_idx, ep2_idx):
            endpoint = endpoint_nodes[ep_pos]

            # Skip true inlets/outlets immediately
            if endpoint in true_endpoints:
                continue

            # Query enough neighbours to guarantee 2 from other vessels.
            # In the worst case every closer point is in the same vessel,
            # so we query a generous number and filter.
            k_query = min(n_points, len(vessel_nodes_set) + 10)
            dists, indices = tree.query(points[endpoint], k=k_query)

            # Filter to nodes NOT in the same vessel (and not self)
            other_dists: List[float] = []
            other_indices: List[int] = []
            for d, idx in zip(dists, indices):
                if idx not in vessel_nodes_set:
                    other_dists.append(d)
                    other_indices.append(idx)
                    if len(other_indices) >= 2:
                        break

            if len(other_indices) < 2:
                # Fallback: brute force for this endpoint (should be rare)
                other_dists, other_indices = _brute_force_nearest(
                    points, endpoint, vessel_nodes_set, k=2
                )

            # Skip if the nearest other-vessel node is beyond the threshold
            if branchpoint_distance_threshold > 0 and other_dists[0] > branchpoint_distance_threshold:
                logger.debug(
                    "Endpoint %d skipped: nearest other-vessel node %d is %.2f mm away (threshold %.2f)",
                    endpoint, other_indices[0], other_dists[0], branchpoint_distance_threshold,
                )
                continue

            lowest = other_indices[0]
            second_lowest = other_indices[1]

            # Handle non-consecutive daughters (SimVascular sampling artifact)
            if abs(lowest - second_lowest) != 1:
                lowest, second_lowest = _resolve_nonconsecutive(
                    points, endpoint, lowest
                )

            branch_dict[endpoint] = [lowest, second_lowest]

    # Validate daughter pairs: confirm same-vessel membership + line check
    _validate_daughter_pairs(points, branch_dict, nodes_by_vessel)

    return branch_dict


def _brute_force_nearest(
    points: NDArray[np.floating],
    endpoint: int,
    exclude_set: set,
    k: int = 2,
) -> Tuple[List[float], List[int]]:
    """Fallback brute-force nearest-neighbour search.

    Used only when the KD-tree query does not return enough non-vessel
    neighbours (e.g. very small networks).

    Parameters
    ----------
    points : ndarray of shape (N, 3)
    endpoint : int
        Index of the query point.
    exclude_set : set of int
        Node indices to skip (same-vessel nodes).
    k : int
        Number of nearest neighbours to return.

    Returns
    -------
    dists : list[float]
    indices : list[int]
    """
    ep_coord = points[endpoint]
    diffs = points - ep_coord
    sq_dists = np.einsum("ij,ij->i", diffs, diffs)

    # Mask out excluded nodes with infinity
    mask = np.zeros(len(points), dtype=bool)
    for idx in exclude_set:
        mask[idx] = True
    mask[endpoint] = True
    sq_dists[mask] = np.inf

    order = np.argsort(sq_dists)[:k]
    return [float(np.sqrt(sq_dists[i])) for i in order], order.tolist()


def _resolve_nonconsecutive(
    points: NDArray[np.floating],
    endpoint: int,
    closest_node: int,
) -> Tuple[int, int]:
    """Resolve non-consecutive daughter indices.

    When the two nearest nodes in another vessel are not sequential
    (``abs(d1 - d2) != 1``), this function picks the closest of the pair
    as *daughter1* and checks its two immediate neighbours
    (``closest_node +/- 1``) to find the true second daughter.

    Parameters
    ----------
    points : ndarray of shape (N, 3)
    endpoint : int
        Parent branchpoint node index.
    closest_node : int
        The nearest node found in another vessel.

    Returns
    -------
    (daughter1, daughter2) : tuple[int, int]
        A consecutive pair where ``abs(daughter1 - daughter2) == 1``.
    """
    daughter1 = closest_node
    ep_coord = points[endpoint]

    candidates = []
    for offset in (-1, 1):
        candidate = closest_node + offset
        if 0 <= candidate < points.shape[0]:
            diff = points[candidate] - ep_coord
            dist = float(np.sqrt(np.dot(diff, diff)))
            candidates.append((dist, candidate))

    if not candidates:
        # Edge case: only one valid candidate exists
        return daughter1, closest_node + 1 if closest_node + 1 < points.shape[0] else closest_node - 1

    candidates.sort()
    daughter2 = candidates[0][1]
    return daughter1, daughter2


# ---------------------------------------------------------------------------
# Step 2b -- Daughter-pair validation
# ---------------------------------------------------------------------------

def _validate_daughter_pairs(
    points: NDArray[np.floating],
    branch_dict: BranchDict,
    nodes_by_vessel: NodesByVessel,
) -> None:
    """Confirm both daughters belong to the same vessel; re-pair if not.

    For each parent whose daughters are in different vessels, re-search
    each vessel independently for the two closest nodes and use a
    parametric line test to select the correct pairing.

    Modifies *branch_dict* in place.

    Parameters
    ----------
    points : ndarray of shape (N, 3)
    branch_dict : dict[int, list[int]]
    nodes_by_vessel : dict[int, list[int]]
    """
    # Build reverse lookup: node -> vessel index
    node_to_vessel: Dict[int, int] = {}
    for v, nodes in nodes_by_vessel.items():
        for n in nodes:
            node_to_vessel[n] = v

    parents_to_fix = []
    for parent, daughters in branch_dict.items():
        if len(daughters) != 2:
            continue
        d1, d2 = daughters
        v1 = node_to_vessel.get(d1)
        v2 = node_to_vessel.get(d2)
        if v1 is None or v2 is None:
            continue
        if abs(d1 - d2) != 1:
            parents_to_fix.append(parent)

    for parent in parents_to_fix:
        d1, d2 = branch_dict[parent]
        v1 = node_to_vessel[d1]
        v2 = node_to_vessel[d2]

        parent_coord = points[parent]

        # Find top-2 closest nodes in each daughter's vessel
        pair_v1 = _closest_pair_in_vessel(
            points, parent_coord, nodes_by_vessel[v1]
        )
        pair_v2 = _closest_pair_in_vessel(
            points, parent_coord, nodes_by_vessel[v2]
        )

        # Use parametric line test to select the correct pairing
        selected = _select_pair_by_line_test(
            points, parent_coord, pair_v1, pair_v2
        )
        if selected is not None:
            branch_dict[parent] = list(selected)


def _closest_pair_in_vessel(
    points: NDArray[np.floating],
    parent_coord: NDArray[np.floating],
    vessel_nodes: List[int],
) -> Tuple[int, int]:
    """Find the two closest nodes to *parent_coord* within a vessel.

    Parameters
    ----------
    points : ndarray of shape (N, 3)
    parent_coord : ndarray of shape (3,)
    vessel_nodes : list[int]

    Returns
    -------
    (node1, node2) : tuple[int, int]
        The two closest node indices sorted by distance.
    """
    vessel_points = points[vessel_nodes]
    diffs = vessel_points - parent_coord
    sq_dists = np.einsum("ij,ij->i", diffs, diffs)

    # argpartition is O(n) for k smallest
    if len(sq_dists) < 2:
        return (vessel_nodes[0], vessel_nodes[0])
    idx = np.argpartition(sq_dists, 2)[:2]
    # Sort the two by distance
    if sq_dists[idx[0]] > sq_dists[idx[1]]:
        idx = idx[::-1]
    return vessel_nodes[idx[0]], vessel_nodes[idx[1]]


def _select_pair_by_line_test(
    points: NDArray[np.floating],
    parent_coord: NDArray[np.floating],
    pair1: Tuple[int, int],
    pair2: Tuple[int, int],
) -> Tuple[int, int] | None:
    """Select the daughter pair whose connecting line passes through the parent.

    Uses the parametric line equation:
        t_x = (P_x - A_x) / (B_x - A_x)
    for each axis.  If all three parametric values are approximately equal,
    the parent lies on the line between A and B.

    Parameters
    ----------
    points : ndarray of shape (N, 3)
    parent_coord : ndarray of shape (3,)
    pair1, pair2 : tuple[int, int]
        Candidate daughter pairs (node indices).

    Returns
    -------
    The pair that passes the line test, or *None* if neither does.
    """
    for pair in (pair1, pair2):
        n1, n2 = pair
        a = points[n1]
        b = points[n2]
        diff = b - a

        # Guard against division by zero on any axis
        if np.any(np.abs(diff) < 1e-12):
            # Degenerate axis -- check if parent matches on that axis
            # and compute t from the remaining axes
            valid_axes = np.abs(diff) >= 1e-12
            if not np.any(valid_axes):
                continue  # A == B, skip
            t_values = (parent_coord[valid_axes] - a[valid_axes]) / diff[valid_axes]
            # Check degenerate axes: parent should match A on those
            degen_ok = np.allclose(
                parent_coord[~valid_axes], a[~valid_axes], atol=1e-4
            )
            if degen_ok and np.allclose(
                t_values, t_values[0], atol=1e-4
            ):
                return pair
        else:
            t = np.round((parent_coord - a) / diff, 5)
            if np.allclose(t, t[0], atol=1e-4):
                return pair

    return None


# ---------------------------------------------------------------------------
# Step 3 -- Daughter structures and repeated-daughter detection
# ---------------------------------------------------------------------------

def _compile_daughter_structures(
    branch_dict: BranchDict,
) -> Tuple[List[int], DaughterDict, Set[int]]:
    """Derive daughter-centric data structures from the parent-centric dict.

    Parameters
    ----------
    branch_dict : dict[int, list[int]]
        Parent -> [daughter1, daughter2].

    Returns
    -------
    branchpoint_list : list[int]
        Flat list of all daughter nodes (may contain duplicates).
    branchpoint_daughter_dict : dict[int, int]
        daughter -> parent.  For repeated daughters the *last* parent
        encountered wins (resolved later by distance in graph wiring).
    repeat_daughters : set[int]
        Daughters that appear in more than one parent's pair.
    """
    branchpoint_list: List[int] = []
    for daughters in branch_dict.values():
        branchpoint_list.extend(daughters)

    # Detect repeated daughters (appear > 1 time)
    from collections import Counter
    counts = Counter(branchpoint_list)
    repeat_daughters = {node for node, cnt in counts.items() if cnt > 1}

    # Build daughter -> parent mapping
    branchpoint_daughter_dict: DaughterDict = {}
    for parent, daughters in branch_dict.items():
        for d in daughters:
            branchpoint_daughter_dict[d] = parent

    if repeat_daughters:
        logger.info(
            "Found %d repeated daughter node(s): %s",
            len(repeat_daughters),
            repeat_daughters,
        )

    return branchpoint_list, branchpoint_daughter_dict, repeat_daughters


# ---------------------------------------------------------------------------
# Step 4 -- Adjacency graph construction
# ---------------------------------------------------------------------------

def _build_adjacency(
    points: NDArray[np.floating],
    endpoint_nodes: List[int],
    nodes_by_vessel: NodesByVessel,
    branch_dict: BranchDict,
    branchpoint_daughter_dict: DaughterDict,
    repeat_daughters: Set[int],
) -> Graph:
    """Assemble the adjacency graph for the vascular network.

    Wiring rules
    -------------
    1. **Intra-vessel edges** -- each node connects to its sequential
       predecessor and successor within the same vessel (O(N) total).
       Two endpoints from different vessels are never connected this way,
       unless they share a vessel of length 2.
    2. **Branchpoint edges** -- parent branchpoints connect to their
       two daughters; each daughter connects back to its parent but
       *not* to the other daughter in the pair.
    3. **Self-loop** -- every node includes itself in its neighbour list.
    4. **Repeated daughters** -- when a daughter has multiple parents,
       all parent edges are initially added, then the *farthest* parent
       is removed, retaining only the closest.

    Parameters
    ----------
    points : ndarray of shape (N, 3)
    endpoint_nodes : list[int]
    nodes_by_vessel : dict[int, list[int]]
    branch_dict : dict[int, list[int]]
    branchpoint_daughter_dict : dict[int, int]
    repeat_daughters : set[int]

    Returns
    -------
    graph : dict[int, list[int]]
        Sorted adjacency list with self-loops.
    """
    n_nodes = points.shape[0]
    endpoint_set = set(endpoint_nodes)

    # Pre-allocate neighbour sets for efficient building
    neighbours: Dict[int, set] = {i: set() for i in range(n_nodes)}

    # 1. Intra-vessel edges (O(N) total across all vessels)
    for v, nodes in nodes_by_vessel.items():
        vessel_len = len(nodes)
        for pos in range(vessel_len - 1):
            n_cur = nodes[pos]
            n_nxt = nodes[pos + 1]

            # Skip edge if both are endpoints from *different* vessels
            # and vessel length > 2 (original code quirk for 2-node vessels)
            if n_cur in endpoint_set and n_nxt in endpoint_set:
                if vessel_len == 2:
                    neighbours[n_cur].add(n_nxt)
                    neighbours[n_nxt].add(n_cur)
                # else: skip -- these are endpoints of adjacent vessels
                # that happen to have consecutive global indices
                continue

            neighbours[n_cur].add(n_nxt)
            neighbours[n_nxt].add(n_cur)

    # 2. Branchpoint edges: parent -> daughters
    for parent, daughters in branch_dict.items():
        for d in daughters:
            neighbours[parent].add(d)

    # 3. Daughter -> parent edges
    for daughter, parent in branchpoint_daughter_dict.items():
        if daughter not in repeat_daughters:
            neighbours[daughter].add(parent)
        else:
            # For repeated daughters, add ALL parents initially
            for p, d_pair in branch_dict.items():
                if daughter in d_pair:
                    neighbours[daughter].add(p)

    # 4. Self-loops
    for i in range(n_nodes):
        neighbours[i].add(i)

    # Convert to sorted lists
    graph: Graph = {i: sorted(neighbours[i]) for i in range(n_nodes)}

    # 5. Remove daughter-to-daughter edges
    _remove_daughter_cross_edges(graph, branch_dict, branchpoint_daughter_dict)

    # 6. Handle repeated daughters: keep only the closest parent
    _resolve_repeated_daughters(graph, points, repeat_daughters)

    return graph


def _remove_daughter_cross_edges(
    graph: Graph,
    branch_dict: BranchDict,
    branchpoint_daughter_dict: DaughterDict,
) -> None:
    """Remove edges between daughter nodes of the same parent.

    Daughters should connect to their parent branchpoint but not to the
    other daughter in the same pair.  Modifies *graph* in place.

    Parameters
    ----------
    graph : dict[int, list[int]]
    branch_dict : dict[int, list[int]]
    branchpoint_daughter_dict : dict[int, int]
    """
    for daughter in branchpoint_daughter_dict:
        parent = branchpoint_daughter_dict[daughter]
        if parent not in branch_dict:
            continue
        daughters = branch_dict[parent]
        for other_d in daughters:
            if other_d != daughter and other_d in graph[daughter]:
                graph[daughter].remove(other_d)


def _resolve_repeated_daughters(
    graph: Graph,
    points: NDArray[np.floating],
    repeat_daughters: Set[int],
) -> None:
    """For daughters with multiple parents, keep only the closest parent.

    Computes the Euclidean distance from the daughter to each of its
    neighbour nodes and removes the *farthest* neighbour.  This matches
    the original algorithm which removes the single most distant neighbour.

    Modifies *graph* in place.

    Parameters
    ----------
    graph : dict[int, list[int]]
    points : ndarray of shape (N, 3)
    repeat_daughters : set[int]
    """
    for daughter in repeat_daughters:
        nbrs = graph[daughter]
        if len(nbrs) <= 1:
            continue

        d_coord = points[daughter]
        dists = []
        for nbr in nbrs:
            diff = points[nbr] - d_coord
            dists.append(float(np.dot(diff, diff)))

        # Remove the neighbour at maximum distance
        max_idx = int(np.argmax(dists))
        node_to_remove = nbrs[max_idx]
        graph[daughter].remove(node_to_remove)


# ---------------------------------------------------------------------------
# Utility: Write special_nodes.txt (optional diagnostic output)
# ---------------------------------------------------------------------------

def write_special_nodes(
    output_path: str,
    branch_dict: BranchDict,
    branchpoint_list: List[int],
    endpoint_nodes: List[int],
    inlet_nodes: List[int],
    outlet_nodes: List[int],
    branchpoint_daughter_dict: DaughterDict,
    repeat_daughters: Set[int],
) -> None:
    """Write a diagnostic file listing all special node categories.

    Replicates the ``outputs/graph/special_nodes.txt`` output from the
    original monolithic script.

    Parameters
    ----------
    output_path : str
        File path for the output text file.
    branch_dict : dict[int, list[int]]
    branchpoint_list : list[int]
    endpoint_nodes : list[int]
    inlet_nodes, outlet_nodes : list[int]
    branchpoint_daughter_dict : dict[int, int]
    repeat_daughters : set[int]
    """
    branchpoint_list_keys = list(branch_dict.keys())

    with open(output_path, "w") as f:
        f.write("Daughter nodes:")
        f.write(str(branchpoint_list))

        f.write("\n\nParent branchpoints:")
        f.write(str(branchpoint_list_keys))

        f.write("\n\nEndpoint nodes:")
        f.write(str(endpoint_nodes))

        f.write("\n\nInlet nodes:")
        f.write(str(inlet_nodes))

        f.write("\n\nOutlet nodes:")
        f.write(str(outlet_nodes))

        f.write("\n\nBranchpoint daughter dictionary:")
        f.write(str(branchpoint_daughter_dict))

        if not repeat_daughters:
            f.write(
                "\n\nNo daughter nodes belong to >1 parent branchpoint.\n"
            )
        else:
            f.write(
                "\n\nDaughter nodes with >1 parent branchpoint "
                "(xcavate will limit to one daughter): \n"
            )
            f.write(str(repeat_daughters))

    logger.debug("Special nodes written to %s", output_path)


def write_graph(output_path: str, graph: Graph) -> None:
    """Write the adjacency list to a text file for diagnostics.

    Replicates the ``outputs/graph/graph.txt`` output from the original
    monolithic script.

    Parameters
    ----------
    output_path : str
        File path for the output text file.
    graph : dict[int, list[int]]
    """
    with open(output_path, "w") as f:
        f.write("Graph edges:\n\n")
        for i in range(len(graph)):
            f.write(f"{i}: {graph[i]}\n")

    logger.debug("Graph written to %s", output_path)
