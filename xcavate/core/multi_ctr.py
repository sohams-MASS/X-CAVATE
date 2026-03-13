"""Multi-CTR orchestration: node assignment, config building, and pass merging.

Provides the coordination layer for running N concurrent CTR robots on a
single vascular network.  Each robot gets a disjoint partition of graph nodes
and operates with shared collision state so body-drag checks account for
material deposited by any robot.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from numpy.typing import NDArray

from xcavate.core.ctr_collision import RobotFootprint, SharedVisitedState
from xcavate.core.ctr_kinematics import (
    CTRConfig,
    batch_is_reachable,
    compute_needle_body,
    fast_global_to_snt,
)

logger = logging.getLogger(__name__)

Graph = Dict[int, List[int]]


# ---------------------------------------------------------------------------
# Build per-robot CTRConfigs
# ---------------------------------------------------------------------------

def build_robot_configs(config) -> List[CTRConfig]:
    """Construct a list of CTRConfigs from an XcavateConfig with multi-CTR settings.

    Parameters
    ----------
    config : XcavateConfig
        Must have ``n_robots >= 1``.  When ``multi_ctr_configs`` is provided,
        each entry is merged with the shared base config via
        ``CTRConfig.from_robot_dict()``.

    Returns
    -------
    list of CTRConfig
        One per robot.
    """
    base_config = CTRConfig.from_xcavate_config(config)

    if config.n_robots == 1:
        return [base_config]

    configs: List[CTRConfig] = []
    robot_dicts = config.multi_ctr_configs or [{} for _ in range(config.n_robots)]

    if len(robot_dicts) < config.n_robots:
        # Pad with empty dicts (use base config for remaining robots)
        robot_dicts = list(robot_dicts) + [{}] * (config.n_robots - len(robot_dicts))

    for i in range(config.n_robots):
        rd = robot_dicts[i]
        if rd:
            cfg = CTRConfig.from_robot_dict(base_config, rd)
        else:
            cfg = base_config
        configs.append(cfg)

    return configs


# ---------------------------------------------------------------------------
# Node assignment — graph partitioning
# ---------------------------------------------------------------------------

def assign_nodes_to_robots(
    points: NDArray[np.floating],
    graph: Graph,
    ctr_configs: List[CTRConfig],
    gimbal_configs: Optional[List[List[CTRConfig]]] = None,
    clearance: float = 5.0,
) -> Dict[int, Set[int]]:
    """Assign graph nodes to robots based on reachability and proximity.

    Algorithm:
    1. For each robot, compute reachability mask (vectorized batch_is_reachable).
       With gimbal: union over all gimbal configs.
    2. Nodes reachable by only one robot -> assigned immediately.
    3. Contested nodes (reachable by multiple robots):
       a. Check inter-robot base exclusion: penalize nodes near other robots' bases.
       b. Among remaining candidates, assign to robot whose base is closest.
    4. Unreachable nodes -> warning, excluded from all robots.

    Parameters
    ----------
    points : ndarray (N, 3+)
        Network coordinates.
    graph : dict[int, list[int]]
        Adjacency list.
    ctr_configs : list of CTRConfig
        One per robot.
    gimbal_configs : optional list of list of CTRConfig
        Per-robot gimbal config lists.  If provided, reachability is the
        union across all gimbal configs for each robot.
    clearance : float
        Base exclusion zone radius (mm).

    Returns
    -------
    dict[int, set[int]]
        Mapping from robot_idx to the set of assigned node indices.
    """
    pts = points[:, :3]
    graph_nodes = sorted(graph.keys())
    n_robots = len(ctr_configs)

    # Step 1: Compute per-robot reachability
    reachability: List[NDArray[np.bool_]] = []
    graph_pts = pts[graph_nodes]

    for ridx in range(n_robots):
        if gimbal_configs is not None and ridx < len(gimbal_configs):
            # Union of reachability across gimbal configs
            combined = np.zeros(len(graph_nodes), dtype=np.bool_)
            for cfg in gimbal_configs[ridx]:
                combined |= batch_is_reachable(graph_pts, cfg)
            reachability.append(combined)
        else:
            reachability.append(batch_is_reachable(graph_pts, ctr_configs[ridx]))

    # Build per-robot assignment sets
    assignments: Dict[int, Set[int]] = {r: set() for r in range(n_robots)}

    # Step 2a: Assign unique nodes (reachable by exactly one robot)
    contested: List[Tuple[int, int, List[int]]] = []  # (array_idx, node, candidates)
    for i, node in enumerate(graph_nodes):
        reachable_by = [r for r in range(n_robots) if reachability[r][i]]

        if len(reachable_by) == 0:
            continue
        elif len(reachable_by) == 1:
            assignments[reachable_by[0]].add(node)
        else:
            contested.append((i, node, reachable_by))

    # Step 2b: Assign contested nodes with load balancing
    # Process most-constrained nodes first (fewest candidate robots)
    contested.sort(key=lambda x: len(x[2]))

    for _, node, reachable_by in contested:
        node_pos = pts[node]
        dists = {
            r: float(np.linalg.norm(node_pos - ctr_configs[r].X))
            for r in reachable_by
        }
        # Primary key: current assignment count (balance load)
        # Secondary key: distance to robot base (prefer closer)
        best_robot = min(
            reachable_by,
            key=lambda r: (len(assignments[r]), dists[r]),
        )
        assignments[best_robot].add(node)

    # Log statistics
    total_assigned = sum(len(s) for s in assignments.values())
    total_graph = len(graph_nodes)
    unassigned = total_graph - total_assigned
    if unassigned > 0:
        logger.warning(
            "Multi-CTR: %d/%d nodes unreachable by any robot",
            unassigned, total_graph,
        )
    for r in range(n_robots):
        logger.info(
            "Robot %d: %d nodes assigned (%.1f%%)",
            r, len(assignments[r]),
            100.0 * len(assignments[r]) / max(total_graph, 1),
        )

    return assignments


def _resolve_contested_node(
    node_pos: NDArray[np.floating],
    candidates: List[int],
    ctr_configs: List[CTRConfig],
    clearance: float,
) -> int:
    """Resolve a contested node by choosing the best robot.

    Penalizes robots whose base is too close to another robot's base/reach zone.
    Among valid candidates, selects the one whose base is closest to the node.
    """
    # Compute distances from node to each candidate robot's base
    dists = {r: float(np.linalg.norm(node_pos - ctr_configs[r].X)) for r in candidates}

    # Penalize: if node is within clearance + ss_lim of another robot's base
    valid = []
    for r in candidates:
        penalized = False
        for other_r in range(len(ctr_configs)):
            if other_r == r:
                continue
            dist_to_other = float(np.linalg.norm(node_pos - ctr_configs[other_r].X))
            if dist_to_other < clearance + ctr_configs[other_r].ss_lim:
                # Node is in another robot's danger zone — penalize this assignment
                # unless this IS that robot
                if other_r in candidates:
                    # The closer robot to the danger zone gets priority
                    if dists[other_r] < dists[r]:
                        penalized = True
                        break
        if not penalized:
            valid.append(r)

    # If all candidates are penalized, just use all
    if not valid:
        valid = candidates

    # Choose closest robot
    return min(valid, key=lambda r: dists[r])


def _base_exclusion_penalty(
    node_pos: NDArray[np.floating],
    robot_configs: List[CTRConfig],
    assigned_robot: int,
    clearance: float = 5.0,
) -> bool:
    """Check if a node is too close to another robot's base/reach zone."""
    for ridx, cfg in enumerate(robot_configs):
        if ridx == assigned_robot:
            continue
        dist = float(np.linalg.norm(node_pos - cfg.X))
        if dist < clearance + cfg.ss_lim:
            return True
    return False


# ---------------------------------------------------------------------------
# Subgraph extraction
# ---------------------------------------------------------------------------

def extract_robot_subgraph(
    graph: Graph,
    assigned_nodes: Set[int],
) -> Graph:
    """Extract the induced subgraph for a robot's assigned node set.

    Preserves edges between assigned nodes; drops edges to unassigned nodes.
    """
    subgraph: Graph = {}
    for node in assigned_nodes:
        if node in graph:
            subgraph[node] = [n for n in graph[node] if n in assigned_nodes]
    return subgraph


# ---------------------------------------------------------------------------
# Pass merging
# ---------------------------------------------------------------------------

def merge_robot_passes(
    per_robot_passes: Dict[int, Dict[int, List[int]]],
) -> Dict[int, List[int]]:
    """Merge per-robot pass dicts into a unified pass dict.

    Each pass key is prefixed so passes from different robots don't collide.
    Format: pass_idx = robot_idx * 10000 + local_pass_idx

    Parameters
    ----------
    per_robot_passes : dict[robot_idx, dict[pass_idx, list[node]]]

    Returns
    -------
    dict[int, list[int]]
        Unified pass dict with sequential keys starting from 0.
    """
    merged: Dict[int, List[int]] = {}
    global_idx = 0

    # Process robots in order
    for robot_idx in sorted(per_robot_passes.keys()):
        robot_passes = per_robot_passes[robot_idx]
        for local_idx in sorted(robot_passes.keys()):
            merged[global_idx] = robot_passes[local_idx]
            global_idx += 1

    return merged


def merge_robot_solutions(
    per_robot_solutions: Dict[int, Dict],
) -> Dict:
    """Merge per-robot gimbal solutions into a unified dict.

    Since node assignments are disjoint, there are no key collisions.
    """
    merged = {}
    for robot_idx in sorted(per_robot_solutions.keys()):
        merged.update(per_robot_solutions[robot_idx])
    return merged


# ---------------------------------------------------------------------------
# Multi-robot pass metadata
# ---------------------------------------------------------------------------

def build_pass_robot_map(
    per_robot_passes: Dict[int, Dict[int, List[int]]],
) -> Dict[int, int]:
    """Build a mapping from unified pass index to robot index.

    Returns
    -------
    dict[int, int]
        Maps unified pass_idx -> robot_idx.
    """
    pass_robot_map: Dict[int, int] = {}
    global_idx = 0
    for robot_idx in sorted(per_robot_passes.keys()):
        robot_passes = per_robot_passes[robot_idx]
        for local_idx in sorted(robot_passes.keys()):
            pass_robot_map[global_idx] = robot_idx
            global_idx += 1
    return pass_robot_map
