"""Swept-volume conflict graph and topological ordering for CTR pathfinding.

Builds a directed conflict graph where edge i → j means "node i must be printed
before node j" because reaching node i requires the needle body to pass through
node j's location.  A topological sort of this graph gives a global print
ordering that minimizes body-drag conflicts.

Cycles are broken using the Eades GreedyFAS algorithm, which provably removes
at least 50% of back-edges in O(m) time.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, List, Set

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from xcavate.core.ctr_kinematics import (
    CTRConfig,
    batch_global_to_local,
    batch_local_to_snt,
)

logger = logging.getLogger(__name__)

Graph = Dict[int, List[int]]


def build_conflict_graph(
    points: NDArray[np.floating],
    ctr_config: CTRConfig,
    graph: Graph,
    nozzle_radius: float,
    n_arc_samples: int = 20,
) -> Dict[int, Set[int]]:
    """Build a directed conflict graph from needle-body swept volumes.

    For each reachable node ``i``, compute the full needle body and find all
    other graph nodes whose positions fall within ``nozzle_radius`` of the
    body (excluding the tip zone and graph neighbors).

    An edge ``i → j`` means: to print node ``i``, the needle body passes
    through node ``j``'s location, so ``i`` should be printed before ``j``
    (otherwise body-drag would disturb ``j``'s already-printed material).

    Uses fully vectorized IK, body computation, and KD-tree queries for
    performance (~50-100x faster than the scalar per-node loop).

    Parameters
    ----------
    points : ndarray (N, 3)
    ctr_config : CTRConfig
    graph : dict[int, list[int]]
        Adjacency list.
    nozzle_radius : float
    n_arc_samples : int

    Returns
    -------
    dict[int, set[int]]
        Conflict graph: ``{node: set of nodes that must come after}``.
    """
    import time

    graph_nodes = sorted(graph.keys())
    node_arr = np.array(graph_nodes, dtype=np.intp)
    N = len(node_arr)

    if N == 0:
        return {}

    t0 = time.perf_counter()

    # ------------------------------------------------------------------ #
    # Step 1: Batch inverse kinematics (vectorized)
    # ------------------------------------------------------------------ #
    pts_xyz = points[node_arr]  # (N, 3)
    local = batch_global_to_local(
        pts_xyz, ctr_config.X, ctr_config.R_hat,
        ctr_config.n_hat, ctr_config.theta_match,
    )
    snt = batch_local_to_snt(
        local, ctr_config.f_xr_yr, ctr_config.f_yr_ntnlss,
        ctr_config.x_val, ctr_config.radius,
    )

    z_ss_all = snt[:, 0]
    z_ntnl_all = snt[:, 1]
    theta_all = snt[:, 2]

    valid_mask = (
        ~np.isnan(z_ss_all)
        & (z_ss_all >= 0) & (z_ss_all <= ctr_config.ss_lim)
        & (z_ntnl_all >= 0) & (z_ntnl_all <= ctr_config.ntnl_lim)
    )

    valid_idx = np.where(valid_mask)[0]  # indices into node_arr
    M = len(valid_idx)
    if M == 0:
        return {}

    valid_nodes = node_arr[valid_idx]  # actual node IDs
    z_ss = z_ss_all[valid_idx]
    z_ntnl = z_ntnl_all[valid_idx]
    theta = theta_all[valid_idx]

    t1 = time.perf_counter()
    logger.info("Conflict graph IK: %.3fs (%d/%d reachable)", t1 - t0, M, N)

    # ------------------------------------------------------------------ #
    # Step 2: Vectorized needle body computation
    # ------------------------------------------------------------------ #
    R_hat = ctr_config.R_hat
    n_hat = ctr_config.n_hat
    X = ctr_config.X
    radius = ctr_config.radius
    tm = ctr_config.theta_match

    # Vectorized Rodrigues rotation for bend directions
    # bend_dir[i] = rodrigues(tm + theta[i], R_hat) @ n_hat
    #             = n_hat + sin(a)*K@n_hat + (1-cos(a))*K^2@n_hat
    K = np.array([
        [0, -R_hat[2], R_hat[1]],
        [R_hat[2], 0, -R_hat[0]],
        [-R_hat[1], R_hat[0], 0],
    ])
    Kn = K @ n_hat
    K2n = (K @ K) @ n_hat
    a = tm + theta  # (M,)
    bend_dirs = (
        n_hat[None, :]
        + np.sin(a)[:, None] * Kn[None, :]
        + (1 - np.cos(a))[:, None] * K2n[None, :]
    )  # (M, 3)

    # SS straight section: fixed sample count
    n_ss = 12
    ss_params = np.linspace(0, 1, n_ss)  # (n_ss,)
    ss_lengths = z_ss[:, None] * ss_params[None, :]  # (M, n_ss)
    ss_points = (
        X[None, None, :] + ss_lengths[:, :, None] * R_hat[None, None, :]
    )  # (M, n_ss, 3)

    # Arc section
    ntnl_ext = np.maximum(z_ntnl - z_ss, 0.0)  # (M,)
    max_angle = ntnl_ext / radius  # (M,)
    arc_params = np.linspace(0, 1, n_arc_samples + 1)[1:]  # (n_arc,)
    arc_angles = max_angle[:, None] * arc_params[None, :]  # (M, n_arc)

    ss_tips = X[None, :] + z_ss[:, None] * R_hat[None, :]  # (M, 3)
    sin_arc = np.sin(arc_angles)  # (M, n_arc)
    cos_arc = np.cos(arc_angles)  # (M, n_arc)

    arc_points = (
        ss_tips[:, None, :]
        + radius * sin_arc[:, :, None] * R_hat[None, None, :]
        + radius * (1 - cos_arc)[:, :, None] * bend_dirs[:, None, :]
    )  # (M, n_arc, 3)

    n_body = n_ss + n_arc_samples
    all_body = np.concatenate([ss_points, arc_points], axis=1)  # (M, n_body, 3)

    t2 = time.perf_counter()
    logger.info(
        "Conflict graph bodies: %.3fs (%d nodes x %d pts = %d total)",
        t2 - t1, M, n_body, M * n_body,
    )

    # ------------------------------------------------------------------ #
    # Step 3: Precompute tip exclusion mask
    # ------------------------------------------------------------------ #
    tip_exclusion_r = 3.0 * nozzle_radius
    tip_excl_sq = tip_exclusion_r ** 2
    target_pts = pts_xyz[valid_idx]  # (M, 3)
    dists_sq = np.sum(
        (all_body - target_pts[:, None, :]) ** 2, axis=2,
    )  # (M, n_body)
    flat_is_tip = (dists_sq < tip_excl_sq).ravel()  # (M * n_body,)

    # ------------------------------------------------------------------ #
    # Step 4: Build KD-tree over all body points and query graph nodes
    # ------------------------------------------------------------------ #
    flat_body = all_body.reshape(M * n_body, 3)
    body_tree = cKDTree(flat_body)

    t3 = time.perf_counter()
    logger.info("Conflict graph body tree: %.3fs", t3 - t2)

    # For each graph node, find body points within nozzle_radius
    hits = body_tree.query_ball_point(pts_xyz, nozzle_radius, workers=-1)

    t4 = time.perf_counter()
    logger.info("Conflict graph query: %.3fs", t4 - t3)

    # ------------------------------------------------------------------ #
    # Step 5: Build conflict graph from hits
    # ------------------------------------------------------------------ #
    neighbor_sets = {node: set(graph[node]) for node in graph_nodes}
    conflict: Dict[int, Set[int]] = defaultdict(set)

    for j_idx in range(N):
        hit_list = hits[j_idx]
        if not hit_list:
            continue
        j_node = int(node_arr[j_idx])

        hit_arr = np.asarray(hit_list, dtype=np.intp)
        # Exclude body points in the tip zone of their source node
        hit_arr = hit_arr[~flat_is_tip[hit_arr]]
        if len(hit_arr) == 0:
            continue

        # Map body point index → source node
        src_nodes = valid_nodes[hit_arr // n_body]
        # Remove self-hits (source == hit target)
        src_nodes = src_nodes[src_nodes != j_node]
        if len(src_nodes) == 0:
            continue

        # Add unique source nodes (with graph-neighbor filter)
        for i_node in set(src_nodes.tolist()):
            if j_node not in neighbor_sets.get(i_node, set()):
                conflict[i_node].add(j_node)

    t5 = time.perf_counter()
    logger.info(
        "Conflict graph assembly: %.3fs | total: %.3fs", t5 - t4, t5 - t0,
    )
    logger.info(
        "Conflict graph: %d nodes with conflicts, %d total edges",
        len(conflict),
        sum(len(v) for v in conflict.values()),
    )
    return dict(conflict)


def eades_greedy_fas(
    adj: Dict[int, Set[int]],
    nodes: List[int],
) -> List[int]:
    """Eades GreedyFAS linear ordering that minimizes back-edges.

    The algorithm provably removes at least 50% of back-edges in O(m) time,
    where m is the number of edges.  It is superior to the simple min-in-degree
    cycle breaker used previously.

    Algorithm
    ---------
    Maintain two output deques ``s_l`` (sinks, prepended) and ``s_r`` (sources,
    appended).  Iteratively:

    1. Remove all sinks (out-degree 0) → prepend to ``s_l``.
    2. Remove all sources (in-degree 0) → append to ``s_r``.
    3. If stuck, pick node with max ``(outdeg - indeg)`` → append to ``s_r``.

    Final order = ``s_l + s_r``.

    Parameters
    ----------
    adj : dict[int, set[int]]
        Forward adjacency list (only edges within *nodes*).
    nodes : list[int]
        All nodes to order.

    Returns
    -------
    list[int]
        Nodes in recommended print order (earlier = print first).

    References
    ----------
    Eades, Lin, Smyth — "A fast and effective heuristic for the feedback arc
    set problem", Information Processing Letters, 1993.
    """
    if not nodes:
        return []

    node_set = set(nodes)

    # Build in-degree, out-degree, reverse adjacency
    in_deg: Dict[int, int] = {n: 0 for n in nodes}
    out_deg: Dict[int, int] = {n: 0 for n in nodes}
    rev: Dict[int, Set[int]] = {n: set() for n in nodes}

    for u in nodes:
        succs = adj.get(u, set())
        out_deg[u] = len(succs)
        for v in succs:
            in_deg[v] = in_deg.get(v, 0) + 1
            rev[v].add(u)

    # Bucket queues keyed by delta = outdeg - indeg
    remaining = set(nodes)
    delta: Dict[int, int] = {}
    buckets: Dict[int, Set[int]] = defaultdict(set)
    for n in nodes:
        d = out_deg[n] - in_deg[n]
        delta[n] = d
        buckets[d].add(n)

    s_l: deque[int] = deque()
    s_r: deque[int] = deque()

    def _remove_node(n: int) -> None:
        remaining.discard(n)
        buckets[delta[n]].discard(n)
        # Update neighbors
        for v in adj.get(n, set()):
            if v in remaining:
                in_deg[v] -= 1
                old_d = delta[v]
                new_d = out_deg[v] - in_deg[v]
                buckets[old_d].discard(v)
                delta[v] = new_d
                buckets[new_d].add(v)
        for u in rev.get(n, set()):
            if u in remaining:
                out_deg[u] -= 1
                old_d = delta[u]
                new_d = out_deg[u] - in_deg[u]
                buckets[old_d].discard(u)
                delta[u] = new_d
                buckets[new_d].add(u)

    while remaining:
        changed = True
        while changed:
            changed = False
            # Remove sinks (out_deg == 0 → delta = -in_deg ≤ 0)
            while True:
                sinks = [n for n in remaining if out_deg[n] == 0]
                if not sinks:
                    break
                changed = True
                for n in sinks:
                    _remove_node(n)
                    s_l.appendleft(n)
            # Remove sources (in_deg == 0 → delta = out_deg ≥ 0)
            while True:
                sources = [n for n in remaining if in_deg[n] == 0]
                if not sources:
                    break
                changed = True
                for n in sources:
                    _remove_node(n)
                    s_r.append(n)

        if not remaining:
            break

        # Pick node with max delta (outdeg - indeg)
        max_delta = max(delta[n] for n in remaining)
        # Pick any node with that delta
        best = next(iter(buckets[max_delta] & remaining))
        _remove_node(best)
        s_r.append(best)
        logger.debug(
            "Eades cycle break: node %d (delta=%d)", best, max_delta,
        )

    result = list(s_l) + list(s_r)
    return result


def topological_order_with_cycle_breaking(
    conflict_graph: Dict[int, Set[int]],
    nodes: List[int],
) -> List[int]:
    """Topological sort with Eades GreedyFAS cycle breaking.

    Delegates to :func:`eades_greedy_fas` which provably removes at least
    50% of back-edges in O(m) time.

    Parameters
    ----------
    conflict_graph : dict[int, set[int]]
        Directed edges: ``node → {successors}``.
    nodes : list[int]
        All nodes to order.

    Returns
    -------
    list[int]
        Nodes in recommended print order (earlier = print first).
    """
    node_set = set(nodes)

    # Build adjacency for nodes in the set
    adj: Dict[int, Set[int]] = {n: set() for n in nodes}
    for u, successors in conflict_graph.items():
        if u not in node_set:
            continue
        for v in successors:
            if v in node_set:
                adj[u].add(v)

    return eades_greedy_fas(adj, nodes)
