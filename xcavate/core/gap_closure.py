# -*- coding: utf-8 -*-
"""Gap closure pipeline for print pass post-processing.

Replaces ~2000 lines of duplicated changelog blocks and gap closure conditions
from the original xcavate.py with a compact, parameterized implementation.

The pipeline identifies disconnected endpoints in print passes and closes gaps
through a sequence of conditions:
  - Condition 0: Close gaps within existing vessels (numerical neighbors)
  - Branchpoint Condition 1: Daughter-to-parent, checking backwards
  - Branchpoint Condition 2: Daughter-to-parent, checking forwards
  - Branchpoint Condition 3: Parent-to-non-daughter neighbor
  - Final gap closure: Close any remaining disconnects
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DisconnectInfo:
    """Results from a single disconnect-finding pass.

    Attributes:
        final_true_disconnect: Mapping of node -> [pass_number] for truly
            disconnected nodes.
        neighbor_locs: Mapping of node -> [pass_of_neighbor] indicating which
            pass the neighbor to connect resides in.
        neighbor_to_connect: Mapping of node -> [neighbor_node] identifying the
            graph neighbor that should be joined.
        neighbor_index: Mapping of node -> [index_in_neighbor_pass] giving the
            index of the neighbor within its pass.
    """
    final_true_disconnect: Dict[int, List[int]] = field(default_factory=dict)
    neighbor_locs: Dict[int, List[int]] = field(default_factory=dict)
    neighbor_to_connect: Dict[int, List[int]] = field(default_factory=dict)
    neighbor_index: Dict[int, List[int]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core disconnect detection  (replaces all 6 changelog blocks)
# ---------------------------------------------------------------------------

def find_disconnects(
    print_passes: Dict[int, List[int]],
    graph: Dict[int, List[int]],
    endpoint_nodes: List[int],
    inlet_nodes: Optional[List[int]] = None,
    outlet_nodes: Optional[List[int]] = None,
) -> DisconnectInfo:
    """Identify truly disconnected pass endpoints and their graph neighbors.

    This single function replaces the six nearly-identical "changelog" blocks in
    the original code.  The algorithm:

    1. Collect all pass endpoints (first/last node; single-node passes counted
       once).
    2. Find endpoints appearing only once = "potentially disconnected".
    3. Exclude original vessel endpoints (unless they are the sole node in their
       pass).
    4. For each potentially disconnected node, check whether it appears in
       multiple passes (not truly disconnected).
    5. For truly disconnected nodes locate their graph neighbors in other passes
       or in the same pass (only if not already adjacent).
    6. Remove false positives (nodes that are actually adjacent to their
       supposed disconnect target).
    7. Handle reciprocal first/last connections (only connect last -> first, not
       first -> last).

    Parameters
    ----------
    print_passes : dict[int, list[int]]
        Current print passes keyed by sequential integer index.
    graph : dict[int, list[int]]
        Adjacency list representation of the vessel graph.
    endpoint_nodes : list[int]
        Endpoint nodes of the original vessels (includes inlets/outlets).
    inlet_nodes : list[int], optional
        Inlet nodes (currently unused separately; included for API symmetry).
    outlet_nodes : list[int], optional
        Outlet nodes (currently unused separately; included for API symmetry).

    Returns
    -------
    DisconnectInfo
        Dataclass holding the four result dictionaries.
    """
    changelog_lines: List[str] = []

    # ------------------------------------------------------------------
    # Step 1: Collect pass endpoints
    # ------------------------------------------------------------------
    processed_endpoints: List[int] = []
    single_node_in_pass: List[int] = []

    for i in print_passes:
        if len(print_passes[i]) == 1:
            processed_endpoints.append(print_passes[i][0])
            single_node_in_pass.append(print_passes[i][0])
        else:
            processed_endpoints.append(print_passes[i][0])
            processed_endpoints.append(print_passes[i][-1])

    # ------------------------------------------------------------------
    # Step 2: Potentially disconnected = endpoints appearing exactly once
    # ------------------------------------------------------------------
    disconnected: List[int] = []
    for node in processed_endpoints:
        if processed_endpoints.count(node) == 1:
            disconnected.append(node)

    logger.debug("Potentially disconnected: %s", disconnected)

    # ------------------------------------------------------------------
    # Step 3: Exclude original vessel endpoints (unless sole node in pass)
    # ------------------------------------------------------------------
    to_remove = [
        node for node in disconnected
        if (node in endpoint_nodes) and (node not in single_node_in_pass)
    ]
    for node in to_remove:
        disconnected.remove(node)

    # ------------------------------------------------------------------
    # Step 4: Check which passes each potentially disconnected node appears in
    # ------------------------------------------------------------------
    potential_disconnect: Dict[int, List[int]] = {node: [] for node in disconnected}

    for pass_idx in print_passes:
        for node in disconnected:
            if node in print_passes[pass_idx]:
                for m in range(len(print_passes)):
                    if node in print_passes[m]:
                        potential_disconnect[node].append(m)

    # Remove duplicates
    for node in potential_disconnect:
        potential_disconnect[node] = list(set(potential_disconnect[node]))

    # True disconnects: node appears in only one pass
    final_true_disconnect: Dict[int, List[int]] = {
        node: passes
        for node, passes in potential_disconnect.items()
        if len(passes) == 1
    }

    # ------------------------------------------------------------------
    # Step 5: Locate graph neighbors of disconnected nodes
    # ------------------------------------------------------------------
    neighbor_locs: Dict[int, List[int]] = {}
    neighbor_index: Dict[int, List[int]] = {}
    neighbor_to_connect: Dict[int, List[int]] = {}

    for node in final_true_disconnect:
        graph_neighbors = graph[node]
        neighbor_locs[node] = []
        neighbor_index[node] = []
        neighbor_to_connect[node] = []

        pass_of_node = final_true_disconnect[node][0]

        for nbr in graph_neighbors:
            if nbr == node:
                continue

            for pass_num in print_passes:
                # Case 1: neighbor in a DIFFERENT pass
                if nbr in print_passes[pass_num] and pass_num != pass_of_node:
                    neighbor_locs[node].append(pass_num)
                    neighbor_index[node].append(print_passes[pass_num].index(nbr))
                    neighbor_to_connect[node].append(nbr)

                # Case 2: neighbor in the SAME pass
                if nbr in print_passes[pass_num] and pass_num == pass_of_node:
                    idx = print_passes[pass_num].index(node)
                    pass_len = len(print_passes[pass_num])

                    # 2A: node is LAST in its pass
                    if idx == pass_len - 1 and pass_len > 1:
                        node_left = print_passes[pass_num][idx - 1]
                        if node_left != nbr:
                            neighbor_locs[node].append(pass_num)
                            neighbor_index[node].append(
                                print_passes[pass_num].index(nbr)
                            )
                            neighbor_to_connect[node].append(nbr)

                    # 2B: node is FIRST in its pass
                    if idx == 0 and pass_len > 1:
                        node_right = print_passes[pass_of_node][idx + 1]
                        if node_right != nbr:
                            neighbor_locs[node].append(pass_num)
                            neighbor_index[node].append(
                                print_passes[pass_num].index(nbr)
                            )
                            neighbor_to_connect[node].append(nbr)

    # ------------------------------------------------------------------
    # Step 6: Remove false positives (already adjacent)
    # ------------------------------------------------------------------
    to_pop: Dict[int, List[int]] = {}

    for node in list(neighbor_locs.keys()):
        if node not in final_true_disconnect:
            continue
        if not neighbor_to_connect.get(node):
            continue

        pass_num = final_true_disconnect[node][0]
        idx = print_passes[pass_num].index(node)
        pass_len = len(print_passes[pass_num])

        if pass_len == 1:
            continue

        # First node: check right neighbor
        if idx == 0 and pass_len > 0:
            right_idx = idx + 1
            if print_passes[pass_num][right_idx] == neighbor_to_connect[node][0]:
                to_pop[node] = [node]

        # Last node: check left neighbor
        if (idx + 1 == pass_len) and pass_len > 0:
            left_idx = idx - 1
            if print_passes[pass_num][left_idx] == neighbor_to_connect[node][0]:
                to_pop[node] = [node]

    # ------------------------------------------------------------------
    # Step 7: Handle reciprocal first/last connections
    # ------------------------------------------------------------------
    still_check: Dict[int, List[int]] = {}
    tracker = 0

    for node in final_true_disconnect:
        if node in to_pop:
            continue
        pass_to_check = final_true_disconnect[node][0]
        if final_true_disconnect[node] == neighbor_locs.get(node, []):
            if tracker % 2 == 0:
                still_check[pass_to_check] = [node]
                tracker = len(still_check[pass_to_check])
            elif tracker % 2 == 1:
                still_check.setdefault(pass_to_check, [])
                still_check[pass_to_check].append(node)
                tracker = len(still_check[pass_to_check])

    for pass_idx in still_check:
        if len(still_check[pass_idx]) == 2:
            node_a = still_check[pass_idx][0]
            node_b = still_check[pass_idx][1]
            if node_b in graph.get(node_a, []):
                if neighbor_to_connect.get(node_a, [None])[0] == node_b:
                    if (node_a == print_passes[pass_idx][0]
                            and node_b == print_passes[pass_idx][-1]):
                        logger.debug(
                            "Pass %d: not appending %d to %d at start "
                            "(will append %d to last node %d instead)",
                            pass_idx, node_b, node_a, node_a, node_b,
                        )
                        to_pop[node_a] = [node_a]

    # Apply removals
    for node in to_pop:
        final_true_disconnect.pop(node, None)
        neighbor_locs.pop(node, None)
        neighbor_to_connect.pop(node, None)
        neighbor_index.pop(node, None)

    # Logging summary
    logger.debug("Disconnect summary (%d remaining):", len(final_true_disconnect))
    for node in neighbor_locs:
        if neighbor_locs[node] and neighbor_to_connect[node]:
            logger.debug(
                "  Node %d in pass %d -> connect to %d (pass %d, index %d)",
                node,
                final_true_disconnect[node][0],
                neighbor_to_connect[node][0],
                neighbor_locs[node][0],
                neighbor_index[node][0],
            )

    return DisconnectInfo(
        final_true_disconnect=final_true_disconnect,
        neighbor_locs=neighbor_locs,
        neighbor_to_connect=neighbor_to_connect,
        neighbor_index=neighbor_index,
    )


# ---------------------------------------------------------------------------
# Condition 0: Gaps within existing vessels
# ---------------------------------------------------------------------------

def close_gaps_condition0(
    print_passes: Dict[int, List[int]],
    graph: Dict[int, List[int]],
    branch_dict: Dict[int, List[int]],
    branchpoint_list: List[int],
    branchpoint_list_keys: List[int],
    endpoint_nodes: List[int],
    arbitrary_val: int,
) -> Dict[int, List[int]]:
    """Close gaps within existing vessels by appending numerical neighbors.

    For each pass (starting from the second), check whether the numerical
    neighbors (node +/- 1) of the first and last nodes are also graph
    neighbors.  If such a neighbor exists in a PREVIOUS pass and the current
    endpoint is not a parent branchpoint or original vessel endpoint, append
    the neighbor.

    For daughter nodes the partner ordering is respected to avoid incorrect
    connections.  Single-node passes only get one append (start OR end, not
    both).

    After appending, single-node passes that now appear in another pass are
    marked for removal (replaced with ``[arbitrary_val, arbitrary_val]``).

    Parameters
    ----------
    print_passes : dict[int, list[int]]
        Mutable print passes dict (modified in place and returned).
    graph : dict[int, list[int]]
        Vessel graph adjacency list.
    branch_dict : dict[int, list[int]]
        Parent branchpoint -> [daughter1, daughter2].
    branchpoint_list : list[int]
        Flat list of all daughter nodes.
    branchpoint_list_keys : list[int]
        List of parent branchpoint nodes.
    endpoint_nodes : list[int]
        Original vessel endpoint nodes.
    arbitrary_val : int
        Placeholder value for marking passes for removal.

    Returns
    -------
    dict[int, list[int]]
        The modified print passes.
    """
    start_append: Dict[int, List[int]] = {}
    end_append: Dict[int, List[int]] = {}

    for i in range(1, len(print_passes)):
        first_node = print_passes[i][0]
        last_node = print_passes[i][-1]
        is_single = (first_node == last_node)

        # Compute numerical neighbors that are also graph neighbors
        left_of_first = first_node - 1 if (first_node - 1) in graph[first_node] else arbitrary_val
        right_of_first = first_node + 1 if (first_node + 1) in graph[first_node] else arbitrary_val
        left_of_last = last_node - 1 if (last_node - 1) in graph[last_node] else arbitrary_val
        right_of_last = last_node + 1 if (last_node + 1) in graph[last_node] else arbitrary_val

        for j in range(0, i):
            for k in print_passes[j]:
                already_added_to_single = 0

                # --- Handle FIRST NODE ---
                if ((k == left_of_first or k == right_of_first)
                        and first_node not in branchpoint_list_keys
                        and first_node not in endpoint_nodes):

                    if k in branchpoint_list:
                        # k is a daughter node; find its partner
                        partner = _find_daughter_partner(k, branch_dict, branchpoint_list)
                        if partner != first_node:
                            start_append[i] = [k]
                            already_added_to_single = 1 if is_single else 0
                        # If partner == first_node, do NOT append (ordering issue)
                    else:
                        start_append[i] = [k]
                        already_added_to_single = 1 if is_single else 0

                # --- Handle LAST NODE ---
                if ((k == left_of_last or k == right_of_last)
                        and last_node not in branchpoint_list_keys
                        and last_node not in endpoint_nodes):

                    if k in branchpoint_list:
                        partner = _find_daughter_partner(k, branch_dict, branchpoint_list)
                        if partner != last_node:
                            if already_added_to_single == 0:
                                end_append[i] = [k]
                    else:
                        if already_added_to_single == 0:
                            end_append[i] = [k]

    # Apply appends
    for i in start_append:
        print_passes[i].insert(0, start_append[i][0])
        logger.debug("Condition 0: appending %d to start of pass %d", start_append[i][0], i)
    for i in end_append:
        print_passes[i].append(end_append[i][0])
        logger.debug("Condition 0: appending %d to end of pass %d", end_append[i][0], i)

    logger.info("Condition 0 completed.")
    return print_passes


# ---------------------------------------------------------------------------
# Branchpoint gap closure (conditions 1, 2, 3)
# ---------------------------------------------------------------------------

def close_gaps_branchpoint(
    print_passes: Dict[int, List[int]],
    branch_dict: Dict[int, List[int]],
    branchpoint_list: List[int],
    branchpoint_list_keys: List[int],
    branchpoint_daughter_dict: Dict[int, int],
    repeat_daughters: set,
    direction: str,
    graph: Optional[Dict[int, List[int]]] = None,
) -> Dict[int, List[int]]:
    """Close branchpoint gaps using a parameterized direction.

    Parameters
    ----------
    print_passes : dict[int, list[int]]
        Mutable print passes dict (modified in place and returned).
    branch_dict : dict[int, list[int]]
        Parent branchpoint -> [daughter1, daughter2].
    branchpoint_list : list[int]
        Flat list of all daughter nodes.
    branchpoint_list_keys : list[int]
        List of parent branchpoint nodes.
    branchpoint_daughter_dict : dict[int, int]
        Daughter -> parent branchpoint mapping.
    repeat_daughters : set
        Daughters that appear under more than one parent.
    direction : str
        One of ``"backwards"``, ``"forwards"``, or ``"parent_to_neighbor"``.

        - **"backwards"** (Condition 1): For each pass check if first/last
          node is a daughter.  If parent branchpoint exists in a PREVIOUS pass,
          append parent to the daughter endpoint.
        - **"forwards"** (Condition 2): Same but check LATER passes.
        - **"parent_to_neighbor"** (Condition 3): If first node is a parent
          branchpoint, find its non-daughter neighbor.  If that neighbor is the
          last (or first) node of a previous pass, append the parent to that
          previous pass.  Requires *graph* parameter.
    graph : dict[int, list[int]], optional
        Vessel graph adjacency list.  Required when ``direction`` is
        ``"parent_to_neighbor"``.

    Returns
    -------
    dict[int, list[int]]
        The modified print passes.
    """
    if direction == "parent_to_neighbor":
        if graph is None:
            raise ValueError(
                "graph is required when direction='parent_to_neighbor'"
            )
        return _close_gaps_parent_to_neighbor_with_graph(
            print_passes, graph, branch_dict,
        )

    # "backwards" or "forwards"
    append_first: Dict[int, int] = {}
    append_last: Dict[int, int] = {}

    if direction == "backwards":
        pass_range = range(1, len(print_passes))
    else:
        pass_range = range(len(print_passes))

    for i in pass_range:
        first_point = print_passes[i][0]
        last_point = print_passes[i][-1]
        is_single = (first_point == last_point)

        second_point = print_passes[i][1] if len(print_passes[i]) > 1 else None
        second_to_last = print_passes[i][-2] if len(print_passes[i]) > 1 else None

        # --- FIRST NODE: check if daughter ---
        if first_point in branchpoint_list:
            associated_branch = _find_parent_branch(
                first_point, branch_dict, branchpoint_list, repeat_daughters,
            )
            if associated_branch is not None:
                search_range = (
                    range(0, i) if direction == "backwards"
                    else range(i + 1, len(print_passes))
                )
                for j in search_range:
                    for k in print_passes[j]:
                        if int(associated_branch) == k:
                            if second_point is not None and second_point != int(associated_branch):
                                append_first[i] = k
                            elif second_point is None:
                                append_first[i] = k

        # --- LAST NODE: check if daughter ---
        if last_point in branchpoint_list:
            associated_branch = _find_parent_branch(
                last_point, branch_dict, branchpoint_list, repeat_daughters,
            )
            if associated_branch is not None:
                search_range = (
                    range(0, i) if direction == "backwards"
                    else range(i + 1, len(print_passes))
                )
                for j in search_range:
                    for k in print_passes[j]:
                        if int(associated_branch) == k and not is_single:
                            if second_to_last is not None and second_to_last != int(associated_branch):
                                append_last[i] = k

    # Apply appends
    label = "backwards" if direction == "backwards" else "forwards"
    for i in append_first:
        print_passes[i].insert(0, append_first[i])
        logger.debug("Branchpoint %s: appending %d to start of pass %d", label, append_first[i], i)
    for i in append_last:
        print_passes[i].append(append_last[i])
        logger.debug("Branchpoint %s: appending %d to end of pass %d", label, append_last[i], i)

    logger.info("Branchpoint condition (%s) completed.", label)
    return print_passes


def _close_gaps_parent_to_neighbor_with_graph(
    print_passes: Dict[int, List[int]],
    graph: Dict[int, List[int]],
    branch_dict: Dict[int, List[int]],
) -> Dict[int, List[int]]:
    """Condition 3 implementation with full graph access.

    If the first node of a pass is a parent branchpoint, find its non-daughter
    graph neighbor.  If that neighbor is the last (or first) node of a previous
    pass, append/prepend the parent to that previous pass.
    """
    append_end: Dict[int, List[int]] = {}
    append_start: Dict[int, List[int]] = {}

    for i in range(1, len(print_passes)):
        first_point_curr = print_passes[i][0]

        if first_point_curr not in branch_dict:
            continue

        first_point_neighbors = graph[first_point_curr]
        first_point_daughters = branch_dict[first_point_curr]

        # Non-daughter neighbors = graph neighbors minus daughters minus self
        overlap = list(set(first_point_neighbors).intersection(first_point_daughters))
        removed = [x for x in first_point_neighbors if x not in overlap and x != first_point_curr]
        if not removed:
            continue
        non_daughter_neighbor = removed[0]

        for j in range(0, i):
            last_point_prev = print_passes[j][-1]
            first_point_prev = print_passes[j][0]

            if non_daughter_neighbor == last_point_prev:
                append_end[j] = [first_point_curr]
            elif non_daughter_neighbor == first_point_prev:
                append_start[j] = [first_point_curr]

    # Apply appends
    for i in append_start:
        print_passes[i].insert(0, append_start[i][0])
        logger.debug(
            "Branchpoint parent_to_neighbor: appending %d to start of pass %d",
            append_start[i][0], i,
        )
    for i in append_end:
        print_passes[i].append(append_end[i][0])
        logger.debug(
            "Branchpoint parent_to_neighbor: appending %d to end of pass %d",
            append_end[i][0], i,
        )

    logger.info("Branchpoint condition (parent_to_neighbor) completed.")
    return print_passes


# ---------------------------------------------------------------------------
# Final gap closure
# ---------------------------------------------------------------------------

def close_gaps_final(
    print_passes: Dict[int, List[int]],
    final_true_disconnect: Dict[int, List[int]],
    neighbor_to_connect: Dict[int, List[int]],
) -> Dict[int, List[int]]:
    """Close remaining gaps identified by the most recent find_disconnects.

    For first-node disconnects: prepend the neighbor to the pass.
    For last-node disconnects: append the neighbor to the pass.
    Single-node passes: prepend only (to start).

    Parameters
    ----------
    print_passes : dict[int, list[int]]
        Mutable print passes dict.
    final_true_disconnect : dict[int, list[int]]
        Node -> [pass_number] from :func:`find_disconnects`.
    neighbor_to_connect : dict[int, list[int]]
        Node -> [neighbor_node] from :func:`find_disconnects`.

    Returns
    -------
    dict[int, list[int]]
        The modified print passes.
    """
    start_append: Dict[int, List[int]] = {}
    end_append: Dict[int, List[int]] = {}

    for node in final_true_disconnect:
        if not neighbor_to_connect.get(node):
            continue
        passnum = final_true_disconnect[node][0]
        idx = print_passes[passnum].index(node)
        pass_len = len(print_passes[passnum])
        nbr = neighbor_to_connect[node][0]

        # First node
        if idx == 0:
            if pass_len > 1:
                if print_passes[passnum][idx + 1] != nbr:
                    start_append[passnum] = [nbr]
            else:
                # Single node or empty pass: prepend
                start_append[passnum] = [nbr]

        # Last node (for single-node passes idx==0 is both first and last;
        # single-node passes use start_append only to avoid duplication)
        if idx == pass_len - 1:
            if pass_len > 1:
                if print_passes[passnum][idx - 1] != nbr:
                    end_append[passnum] = [nbr]
            elif pass_len == 1:
                # Single node: use start only (already handled above)
                start_append.setdefault(passnum, [nbr])
            elif pass_len == 0:
                end_append[passnum] = [nbr]

    # Apply appends
    for i in start_append:
        print_passes[i].insert(0, start_append[i][0])
        logger.debug("Final gap closure: appending %d to start of pass %d", start_append[i][0], i)
    for i in end_append:
        print_passes[i].append(end_append[i][0])
        logger.debug("Final gap closure: appending %d to end of pass %d", end_append[i][0], i)

    return print_passes


# ---------------------------------------------------------------------------
# Artifact removal
# ---------------------------------------------------------------------------

def remove_artifact_passes(
    print_passes: Dict[int, List[int]],
    arbitrary_val: int,
) -> Dict[int, List[int]]:
    """Remove passes whose first node equals *arbitrary_val* and re-index.

    These artifact passes were marked for removal during condition 0 (single-
    node passes that became redundant after appending).

    Parameters
    ----------
    print_passes : dict[int, list[int]]
        Print passes dict (not modified in place; a new dict is returned).
    arbitrary_val : int
        The sentinel value used to mark passes for removal.

    Returns
    -------
    dict[int, list[int]]
        New print passes dict with artifact passes removed and keys
        re-indexed sequentially from 0.
    """
    to_remove = [
        i for i in print_passes
        if print_passes[i][0] == arbitrary_val
    ]
    for i in to_remove:
        logger.debug("Removing artifact pass %d", i)

    remaining = {
        i: print_passes[i]
        for i in print_passes
        if i not in to_remove
    }

    # Re-index sequentially
    result: Dict[int, List[int]] = {}
    for counter, key in enumerate(remaining):
        result[counter] = remaining[key]

    return result


# ---------------------------------------------------------------------------
# Redundant single-node pass removal (post Condition 0)
# ---------------------------------------------------------------------------

def _remove_redundant_single_node_passes(
    print_passes: Dict[int, List[int]],
    arbitrary_val: int,
) -> Dict[int, List[int]]:
    """Mark single-node passes as artifacts if their node appears elsewhere.

    After condition 0 appending, a single-node pass may now have its node
    printed in a different pass.  Mark such passes with
    ``[arbitrary_val, arbitrary_val]`` for later removal.
    """
    for i in print_passes:
        if len(print_passes[i]) == 1:
            node = print_passes[i][0]
            # Check previous passes
            for j in range(0, i):
                if node in print_passes[j]:
                    print_passes[i] = [arbitrary_val, arbitrary_val]
                    break
            # Check subsequent passes (only if not already marked)
            if print_passes[i][0] != arbitrary_val:
                for k in range(i + 1, len(print_passes)):
                    if node in print_passes[k]:
                        print_passes[i] = [arbitrary_val, arbitrary_val]
                        break

    return print_passes


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_full_gap_closure_pipeline(
    print_passes: Dict[int, List[int]],
    graph: Dict[int, List[int]],
    branch_dict: Dict[int, List[int]],
    branchpoint_list: List[int],
    branchpoint_list_keys: List[int],
    branchpoint_daughter_dict: Dict[int, int],
    endpoint_nodes: List[int],
    inlet_nodes: List[int],
    outlet_nodes: List[int],
    repeat_daughters: set,
    arbitrary_val: int,
) -> Tuple[Dict[int, List[int]], List[str]]:
    """Orchestrate the complete gap closure pipeline.

    Sequence:
      1. find_disconnects  (changelog 0)
      2. close_gaps_condition0
      3. find_disconnects  (changelog 1) + remove redundant single-node passes
      4. close_gaps_branchpoint("backwards")   -- condition 1
      5. find_disconnects  (changelog 2)
      6. close_gaps_branchpoint("forwards")    -- condition 2
      7. find_disconnects  (changelog 3)
      8. close_gaps_branchpoint("parent_to_neighbor")  -- condition 3
      9. find_disconnects  (changelog 4)
     10. close_gaps_final
     11. find_disconnects  (changelog 5)
     12. remove_artifact_passes

    Parameters
    ----------
    print_passes : dict[int, list[int]]
        Initial print passes (will be modified in place through the pipeline).
    graph, branch_dict, branchpoint_list, branchpoint_list_keys,
    branchpoint_daughter_dict, endpoint_nodes, inlet_nodes, outlet_nodes,
    repeat_daughters, arbitrary_val :
        See individual function docstrings for descriptions.

    Returns
    -------
    tuple[dict[int, list[int]], list[str]]
        ``(final_print_passes, changelog_lines)`` where *changelog_lines* is a
        list of human-readable log strings summarizing each stage.
    """
    changelog: List[str] = []

    def _log_disconnects(info: DisconnectInfo, label: str) -> None:
        """Append a summary of disconnects to the changelog."""
        changelog.append(f"\n--- {label} ---")
        changelog.append(f"Number of disconnects: {len(info.final_true_disconnect)}")
        for node in info.neighbor_locs:
            if info.neighbor_locs[node] and info.neighbor_to_connect[node]:
                changelog.append(
                    f"Node {node} in pass {info.final_true_disconnect[node][0]} "
                    f"-> connect to {info.neighbor_to_connect[node][0]} "
                    f"(pass {info.neighbor_locs[node][0]}, "
                    f"index {info.neighbor_index[node][0]})"
                )

    def _log_passes(label: str) -> None:
        """Log current state of passes."""
        changelog.append(f"\n{label}")
        changelog.append("Current list of print passes:")
        for p in print_passes:
            changelog.append(f"  Pass {p}: {print_passes[p]}")

    # Step 1: Changelog 0
    logger.info("Running Changelog 0 (initial disconnect check).")
    info0 = find_disconnects(print_passes, graph, endpoint_nodes, inlet_nodes, outlet_nodes)
    _log_disconnects(info0, "Changelog 0")

    # Step 2: Condition 0
    logger.info("Running Condition 0.")
    changelog.append("\nNow running Condition 0.")
    print_passes = close_gaps_condition0(
        print_passes, graph, branch_dict, branchpoint_list,
        branchpoint_list_keys, endpoint_nodes, arbitrary_val,
    )
    _log_passes("Condition 0 completed.")

    # Step 3: Changelog 1 + redundant single-node removal
    logger.info("Running Changelog 1 (post Condition 0).")
    info1 = find_disconnects(print_passes, graph, endpoint_nodes, inlet_nodes, outlet_nodes)
    _log_disconnects(info1, "Changelog 1")
    print_passes = _remove_redundant_single_node_passes(print_passes, arbitrary_val)

    # Step 4: Branchpoint Condition 1 (backwards)
    logger.info("Running Branchpoint Condition 1 (backwards).")
    changelog.append("\nNow running Branchpoint Condition #1.")
    print_passes = close_gaps_branchpoint(
        print_passes, branch_dict, branchpoint_list,
        branchpoint_list_keys, branchpoint_daughter_dict,
        repeat_daughters, direction="backwards",
    )
    _log_passes("Branchpoint Condition #1 completed.")

    # Step 5: Changelog 2
    logger.info("Running Changelog 2 (post Branchpoint Condition 1).")
    info2 = find_disconnects(print_passes, graph, endpoint_nodes, inlet_nodes, outlet_nodes)
    _log_disconnects(info2, "Changelog 2")

    # Step 6: Branchpoint Condition 2 (forwards)
    logger.info("Running Branchpoint Condition 2 (forwards).")
    changelog.append("\nNow running Branchpoint Condition #2.")
    print_passes = close_gaps_branchpoint(
        print_passes, branch_dict, branchpoint_list,
        branchpoint_list_keys, branchpoint_daughter_dict,
        repeat_daughters, direction="forwards",
    )
    _log_passes("Branchpoint Condition #2 completed.")

    # Step 7: Changelog 3
    logger.info("Running Changelog 3 (post Branchpoint Condition 2).")
    info3 = find_disconnects(print_passes, graph, endpoint_nodes, inlet_nodes, outlet_nodes)
    _log_disconnects(info3, "Changelog 3")

    # Step 8: Branchpoint Condition 3 (parent_to_neighbor)
    logger.info("Running Branchpoint Condition 3 (parent_to_neighbor).")
    changelog.append("\nNow running Branchpoint Condition #3.")
    print_passes = close_gaps_branchpoint(
        print_passes, branch_dict, branchpoint_list,
        branchpoint_list_keys, branchpoint_daughter_dict,
        repeat_daughters, direction="parent_to_neighbor", graph=graph,
    )
    _log_passes("Branchpoint Condition #3 completed.")

    # Step 9: Changelog 4
    logger.info("Running Changelog 4 (post Branchpoint Condition 3).")
    info4 = find_disconnects(print_passes, graph, endpoint_nodes, inlet_nodes, outlet_nodes)
    _log_disconnects(info4, "Changelog 4")

    # Step 10: Final gap closure
    logger.info("Running Final Gap Closure.")
    changelog.append("\nNow running Final Gap Closure.")
    print_passes = close_gaps_final(
        print_passes,
        info4.final_true_disconnect,
        info4.neighbor_to_connect,
    )

    # Step 11: Changelog 5
    logger.info("Running Changelog 5 (post Final Gap Closure).")
    info5 = find_disconnects(print_passes, graph, endpoint_nodes, inlet_nodes, outlet_nodes)
    _log_disconnects(info5, "Changelog 5")

    # Step 12: Remove artifact passes
    logger.info("Removing artifact passes.")
    print_passes = remove_artifact_passes(print_passes, arbitrary_val)
    _log_passes("After artifact removal.")

    return print_passes, changelog


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _find_daughter_partner(
    daughter: int,
    branch_dict: Dict[int, List[int]],
    branchpoint_list: List[int],
) -> int:
    """Find the partner daughter of *daughter* under the same parent.

    The branchpoint_list is a flat list where consecutive pairs share a parent
    (``branchpoint_list[2*k]`` and ``branchpoint_list[2*k+1]`` are daughters of
    ``list(branch_dict.keys())[k]``).

    Returns the partner node.
    """
    list_index = int(branchpoint_list.index(daughter))
    list_index = int(np.trunc(list_index / 2))
    associated_branch = list(branch_dict.keys())[list_index]
    pair = branch_dict[associated_branch]
    partner = [pt for pt in pair if pt != daughter][0]
    return partner


def _find_parent_branch(
    daughter: int,
    branch_dict: Dict[int, List[int]],
    branchpoint_list: List[int],
    repeat_daughters: set,
) -> Optional[int]:
    """Find the parent branchpoint of *daughter*.

    Handles repeat daughters (daughters that appear under more than one parent)
    by iterating through all occurrences and returning the last-found parent.
    For non-repeat daughters the standard pair-index lookup is used.

    Returns the parent branchpoint node, or ``None`` if lookup fails.
    """
    associated_branch = None

    if daughter not in repeat_daughters:
        list_index = int(branchpoint_list.index(daughter))
        list_index = int(np.trunc(list_index / 2))
        associated_branch = list(branch_dict.keys())[list_index]
    else:
        for index, item in enumerate(branchpoint_list):
            if item == daughter:
                list_index = int(np.trunc(index / 2))
                associated_branch = list(branch_dict.keys())[list_index]

    return associated_branch
