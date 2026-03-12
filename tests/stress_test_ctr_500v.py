#!/usr/bin/env python3
"""Stress test: CTR collision detection on a 500-vessel network.

Runs the CTR pipeline on a real 50k-point vascular network with:
- Reachability filtering
- DFS pathfinding with graph-aware CTR collision detector
- Straight-needle baseline comparison
- Detailed collision statistics
"""

import copy
import sys
import time
import logging
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

NETWORK_FILE = Path("/Users/sohams/Downloads/network_0_b_splines_500_vessels (3).txt")
if not NETWORK_FILE.exists():
    print(f"ERROR: Network file not found: {NETWORK_FILE}")
    sys.exit(1)

print("=" * 70)
print("CTR STRESS TEST — 500-vessel network")
print("=" * 70)

t0_total = time.perf_counter()

# ── 1. Read raw data ──────────────────────────────────────────────────────
raw_lines = NETWORK_FILE.read_text().splitlines()
points_list = []
coord_num_dict = {}

for line in raw_lines:
    line = line.strip()
    if not line:
        continue
    if line.startswith("Vessel:"):
        parts = line.split(",")
        current_vessel = int(parts[0].split(":")[1].strip())
        num_pts = int(parts[1].split(":")[1].strip())
        coord_num_dict[current_vessel] = num_pts
    else:
        vals = [float(x) for x in line.split(",")]
        points_list.append(vals)

points_raw = np.array(points_list)
num_columns = points_raw.shape[1]

# Convert to mm
points_mm = points_raw.copy()
points_mm[:, :3] *= 10.0
if num_columns >= 4:
    points_mm[:, 3] *= 10.0

points_xyz = points_mm[:, :3].copy()
center = points_xyz.mean(axis=0)
span = points_xyz.max(axis=0) - points_xyz.min(axis=0)

print(f"\n1. DATA: {points_raw.shape[0]:,} pts, {len(coord_num_dict)} vessels")
print(f"   Center: ({center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}) mm")
print(f"   Span: ({span[0]:.1f}, {span[1]:.1f}, {span[2]:.1f}) mm")

# ── 2. CTR Configuration ──────────────────────────────────────────────────
from xcavate.core.ctr_kinematics import (
    CTRConfig, is_reachable, batch_is_reachable, global_to_snt, compute_needle_body, _load_calibration,
)

CTR_RADIUS = 47.0
SS_LIM = 110.0       # z_span(~50) + radius(47) + margin(~13)
NTNL_LIM = 185.0     # ss_max(110) + max_arc(47*pi/2 ≈ 74) ≈ 184
NOZZLE_DIAM = 0.5
NOZZLE_RADIUS = NOZZLE_DIAM / 2.0

# CTR must be at least `radius` above the network top so the arc's axial
# component doesn't push z_ss negative for off-axis points near the top.
ctr_z = float(points_xyz[:, 2].max()) + CTR_RADIUS + 5.0
f_xr_yr, f_yr_ntnlss, x_val = _load_calibration(None, CTR_RADIUS)

ctr_config = CTRConfig(
    X=np.array([center[0], center[1], ctr_z]),
    R_hat=np.array([0.0, 0.0, -1.0]),
    n_hat=np.array([1.0, 0.0, 0.0]),
    theta_match=0.0,
    radius=CTR_RADIUS,
    f_xr_yr=f_xr_yr,
    f_yr_ntnlss=f_yr_ntnlss,
    x_val=x_val,
    ss_lim=SS_LIM,
    ntnl_lim=NTNL_LIM,
)

print(f"\n2. CTR: pos=({center[0]:.1f}, {center[1]:.1f}, {ctr_z:.1f})mm, "
      f"R=[0,0,-1], radius={CTR_RADIUS}mm")

# ── 3. Build graph ────────────────────────────────────────────────────────
print(f"\n3. GRAPH CONSTRUCTION")
t_graph = time.perf_counter()

from xcavate.core.preprocessing import interpolate_network, get_vessel_boundaries
from xcavate.core.graph import build_graph

inlet_nodes = [0]
outlet_nodes = [len(points_xyz) - 1]

points_interp = interpolate_network(points_mm, coord_num_dict, NOZZLE_RADIUS, num_columns)
boundaries = get_vessel_boundaries(points_interp, coord_num_dict)
coord_num_dict_interp = {v: info["count"] for v, info in boundaries.items()}
vessel_start_nodes_interp = [info["start"] for v, info in sorted(boundaries.items())]
points_xyz_interp = points_interp[:, :3].copy()

(graph, branch_dict, branchpoint_list,
 branchpoint_daughter_dict, endpoint_nodes,
 nodes_by_vessel, repeat_daughters,
) = build_graph(
    points_xyz_interp, coord_num_dict_interp, vessel_start_nodes_interp,
    inlet_nodes, outlet_nodes,
)

graph_full = copy.deepcopy(graph)
t_graph_elapsed = time.perf_counter() - t_graph
print(f"   {len(points_xyz):,} -> {len(points_xyz_interp):,} points (interpolated)")
print(f"   {len(graph):,} graph nodes  |  {len(branch_dict)} branchpoints  |  {t_graph_elapsed:.2f}s")

# ── 4. CTR Reachability filtering ─────────────────────────────────────────
print(f"\n4. CTR REACHABILITY FILTERING")

# --- Vectorized (batch) filtering ---
t_filter_batch = time.perf_counter()
graph_nodes_arr = np.array(sorted(graph.keys()), dtype=np.intp)
reachable_mask = batch_is_reachable(points_xyz_interp[graph_nodes_arr], ctr_config)
unreachable_graph = set(graph_nodes_arr[~reachable_mask])
t_filter_batch_elapsed = time.perf_counter() - t_filter_batch

# --- Scalar filtering for comparison ---
t_filter_scalar = time.perf_counter()
unreachable_scalar = {n for n in graph if not is_reachable(points_xyz_interp[n], ctr_config)}
t_filter_scalar_elapsed = time.perf_counter() - t_filter_scalar
assert unreachable_graph == unreachable_scalar, "Batch and scalar results differ!"

n_before = len(graph)

for n in unreachable_graph:
    graph.pop(n, None)
for nbrs in graph.values():
    for u in unreachable_graph:
        if u in nbrs:
            nbrs.remove(u)

n_reachable = len(graph)
print(f"   Removed {len(unreachable_graph):,} unreachable -> {n_reachable:,} remaining")
print(f"   Scalar: {t_filter_scalar_elapsed:.2f}s  |  Vectorized: {t_filter_batch_elapsed:.2f}s  "
      f"({t_filter_scalar_elapsed/max(t_filter_batch_elapsed, 0.001):.0f}x speedup)")

# ── 5. DFS with graph-aware CTR collision detector ────────────────────────
print(f"\n5. CTR DFS PATHFINDING (graph-aware, with tip exclusion + neighbor exemption)")

import heapq
from xcavate.core.ctr_collision import CTRCollisionDetector
from xcavate.core.pathfinding import iterative_dfs

t_dfs = time.perf_counter()

detector = CTRCollisionDetector(
    points_xyz_interp, ctr_config, nozzle_radius=NOZZLE_RADIUS,
    graph=graph,  # graph-aware: neighbors exempt from shaft collision
    n_arc_samples=20,
)

# Mark unreachable nodes as visited
for n in range(len(points_xyz_interp)):
    if n not in graph:
        detector.mark_visited(n)

z_heap = []
for node in graph:
    heapq.heappush(z_heap, (float(points_xyz_interp[node, 2]), node))

print_passes = {}
pass_idx = 0
nodes_visited = 0

is_valid_calls = 0
is_valid_true = 0
_orig_valid = detector.is_valid
def _track(node):
    global is_valid_calls, is_valid_true
    is_valid_calls += 1
    r = _orig_valid(node)
    if r:
        is_valid_true += 1
    return r
detector.is_valid = _track

while detector.has_unvisited():
    start_node = None
    while z_heap:
        z_val, node = heapq.heappop(z_heap)
        if not detector.is_visited(node) and node in graph:
            start_node = node
            break
    if start_node is None:
        break

    pass_list = iterative_dfs(graph, start_node, detector, points_xyz_interp)
    if pass_list:
        print_passes[pass_idx] = pass_list
        nodes_visited += len(pass_list)
        pass_idx += 1

    if pass_idx % 500 == 0 and pass_idx > 0:
        elapsed = time.perf_counter() - t_dfs
        pct = 100 * nodes_visited / n_reachable
        print(f"   ... {pass_idx} passes, {nodes_visited:,} nodes ({pct:.0f}%), {elapsed:.1f}s")

t_dfs_elapsed = time.perf_counter() - t_dfs

pass_sizes = np.array([len(p) for p in print_passes.values()]) if print_passes else np.array([0])
remaining = len(detector.unvisited)

print(f"\n   CTR RESULTS:")
print(f"   Passes: {len(print_passes):,}")
print(f"   Nodes visited: {nodes_visited:,} / {n_reachable:,} ({100*nodes_visited/max(n_reachable,1):.1f}%)")
print(f"   Remaining unvisited: {remaining:,}")
print(f"   Time: {t_dfs_elapsed:.2f}s")
print(f"   is_valid() calls: {is_valid_calls:,}  |  accept: {is_valid_true:,} "
      f"({100*is_valid_true/max(is_valid_calls,1):.1f}%)  |  reject: {is_valid_calls-is_valid_true:,}")
if print_passes:
    print(f"   Pass sizes: min={pass_sizes.min()}, max={pass_sizes.max()}, "
          f"mean={pass_sizes.mean():.1f}, median={np.median(pass_sizes):.0f}")

    # Histogram
    bins = [1, 2, 5, 10, 20, 50, 100, 500, 1000, 10000]
    hist_lines = []
    for i in range(len(bins) - 1):
        count = ((pass_sizes >= bins[i]) & (pass_sizes < bins[i+1])).sum()
        if count > 0:
            hist_lines.append(f"     [{bins[i]}-{bins[i+1]}): {count}")
    count = (pass_sizes >= bins[-1]).sum()
    if count > 0:
        hist_lines.append(f"     [{bins[-1]}+): {count}")
    if hist_lines:
        print(f"   Pass size distribution:")
        for line in hist_lines:
            print(line)

if is_valid_calls > 0:
    print(f"   Throughput: {1e6*t_dfs_elapsed/is_valid_calls:.0f} us/call, "
          f"{is_valid_calls/t_dfs_elapsed:.0f} calls/sec")

# ── 6. CTR SWEPT-VOLUME ORDERING ─────────────────────────────────────────
print(f"\n6. CTR SWEPT-VOLUME ORDERING")

from xcavate.core.swept_volume import build_conflict_graph, topological_order_with_cycle_breaking

# Rebuild the graph (it was mutated during DFS section above is fine — the
# graph dict still has all reachable nodes; mark_visited doesn't remove keys)
# We need a fresh graph copy for swept-volume since we popped unreachable
# nodes earlier.  With 0 unreachable, graph == graph_full.
sv_graph = copy.deepcopy(graph_full)

# Remove unreachable nodes (same as step 4 — with 100% reachable this is a no-op)
for n in range(len(points_xyz_interp)):
    if n not in graph_full:
        sv_graph.pop(n, None)

# 6a. Build conflict graph
t_conflict = time.perf_counter()
conflict_graph = build_conflict_graph(
    points_xyz_interp, ctr_config, sv_graph, NOZZLE_RADIUS, n_arc_samples=20,
)
t_conflict_elapsed = time.perf_counter() - t_conflict

n_conflict_nodes = len(conflict_graph)
n_conflict_edges = sum(len(v) for v in conflict_graph.values())
print(f"   Conflict graph: {n_conflict_nodes:,} nodes with conflicts, "
      f"{n_conflict_edges:,} edges  ({t_conflict_elapsed:.2f}s)")

# 6b. Topological sort
t_topo = time.perf_counter()
sv_nodes = sorted(sv_graph.keys())
topo_order = topological_order_with_cycle_breaking(conflict_graph, sv_nodes)
priority = {node: idx for idx, node in enumerate(topo_order)}
t_topo_elapsed = time.perf_counter() - t_topo
print(f"   Topological sort: {len(topo_order):,} nodes  ({t_topo_elapsed:.2f}s)")

# 6c. DFS with swept-volume priority ordering
t_sv_dfs = time.perf_counter()

sv_detector = CTRCollisionDetector(
    points_xyz_interp, ctr_config, nozzle_radius=NOZZLE_RADIUS,
    graph=sv_graph, n_arc_samples=20,
)

# Mark non-graph nodes as visited
for n in range(len(points_xyz_interp)):
    if n not in sv_graph:
        sv_detector.mark_visited(n)

# Build priority heap using topo order
sv_heap = []
for node in sv_graph:
    heapq.heappush(sv_heap, (priority.get(node, len(topo_order)), node))

sv_passes = {}
sv_idx = 0
sv_visited = 0

sv_valid_calls = 0
sv_valid_true = 0
_sv_orig_valid = sv_detector.is_valid
def _sv_track(node):
    global sv_valid_calls, sv_valid_true
    sv_valid_calls += 1
    r = _sv_orig_valid(node)
    if r:
        sv_valid_true += 1
    return r
sv_detector.is_valid = _sv_track

while sv_detector.has_unvisited():
    start_node = None
    while sv_heap:
        prio_val, node = heapq.heappop(sv_heap)
        if not sv_detector.is_visited(node) and node in sv_graph:
            start_node = node
            break
    if start_node is None:
        break

    pass_list = iterative_dfs(sv_graph, start_node, sv_detector, points_xyz_interp)
    if pass_list:
        sv_passes[sv_idx] = pass_list
        sv_visited += len(pass_list)
        sv_idx += 1

    if sv_idx % 500 == 0 and sv_idx > 0:
        elapsed = time.perf_counter() - t_sv_dfs
        pct = 100 * sv_visited / n_reachable
        print(f"   ... {sv_idx} passes, {sv_visited:,} nodes ({pct:.0f}%), {elapsed:.1f}s")

t_sv_dfs_elapsed = time.perf_counter() - t_sv_dfs
sv_sizes = np.array([len(p) for p in sv_passes.values()]) if sv_passes else np.array([0])
sv_remaining = len(sv_detector.unvisited)

print(f"\n   SWEPT-VOLUME RESULTS:")
print(f"   Passes: {len(sv_passes):,}")
print(f"   Nodes visited: {sv_visited:,} / {n_reachable:,} ({100*sv_visited/max(n_reachable,1):.1f}%)")
print(f"   Remaining unvisited: {sv_remaining:,}")
print(f"   Time: {t_conflict_elapsed:.2f}s (conflict) + {t_topo_elapsed:.2f}s (topo) + {t_sv_dfs_elapsed:.2f}s (DFS) = {t_conflict_elapsed+t_topo_elapsed+t_sv_dfs_elapsed:.2f}s total")
print(f"   is_valid() calls: {sv_valid_calls:,}  |  accept: {sv_valid_true:,} "
      f"({100*sv_valid_true/max(sv_valid_calls,1):.1f}%)  |  reject: {sv_valid_calls-sv_valid_true:,}")
if sv_passes:
    print(f"   Pass sizes: min={sv_sizes.min()}, max={sv_sizes.max()}, "
          f"mean={sv_sizes.mean():.1f}, median={np.median(sv_sizes):.0f}")

# ── 7. Straight-needle baseline ───────────────────────────────────────────
print(f"\n7. STRAIGHT-NEEDLE BASELINE")

from xcavate.core.pathfinding import CollisionDetector

t_straight = time.perf_counter()
straight_det = CollisionDetector(
    points_xyz_interp, NOZZLE_RADIUS, tolerance=0.0, tolerance_flag=False,
)

z_heap2 = []
for node in range(len(points_xyz_interp)):
    heapq.heappush(z_heap2, (float(points_xyz_interp[node, 2]), node))

straight_passes = {}
sp_idx = 0
straight_visited = 0

while straight_det.has_unvisited():
    start_node = None
    while z_heap2:
        z_val, node = heapq.heappop(z_heap2)
        if not straight_det.is_visited(node):
            start_node = node
            break
    if start_node is None:
        break
    pass_list = iterative_dfs(graph_full, start_node, straight_det, points_xyz_interp)
    if pass_list:
        straight_passes[sp_idx] = pass_list
        straight_visited += len(pass_list)
        sp_idx += 1

t_straight_elapsed = time.perf_counter() - t_straight
straight_sizes = np.array([len(p) for p in straight_passes.values()]) if straight_passes else np.array([0])

print(f"   Passes: {len(straight_passes):,}")
print(f"   Nodes visited: {straight_visited:,} / {len(points_xyz_interp):,}")
print(f"   Time: {t_straight_elapsed:.2f}s")
print(f"   Pass sizes: min={straight_sizes.min()}, max={straight_sizes.max()}, "
      f"mean={straight_sizes.mean():.1f}, median={np.median(straight_sizes):.0f}")

# ── 8. Angular Sector Strategy ───────────────────────────────────────────
print(f"\n8. CTR ANGULAR SECTOR STRATEGY")

from xcavate.core.pathfinding import AngularSectorStrategy, iterative_dfs_greedy
from xcavate.core.swept_volume import eades_greedy_fas
from xcavate.core.ctr_kinematics import batch_global_to_local, batch_local_to_snt

as_graph = copy.deepcopy(graph_full)
for n in range(len(points_xyz_interp)):
    if n not in graph_full:
        as_graph.pop(n, None)

t_as = time.perf_counter()

# Step 1: compute theta for all nodes
as_nodes = sorted(as_graph.keys())
as_node_arr = np.array(as_nodes, dtype=np.intp)
as_local = batch_global_to_local(
    points_xyz_interp[as_node_arr], ctr_config.X, ctr_config.R_hat,
    ctr_config.n_hat, ctr_config.theta_match,
)
as_snt = batch_local_to_snt(
    as_local, ctr_config.f_xr_yr, ctr_config.f_yr_ntnlss,
    ctr_config.x_val, ctr_config.radius,
)
as_theta = as_snt[:, 2]

NUM_SECTORS = 8

# Step 2: partition
sector_width = 2.0 * np.pi / NUM_SECTORS
as_sectors = {k: [] for k in range(NUM_SECTORS)}
as_no_theta = []
as_node_theta = {}
for i, node in enumerate(as_nodes):
    t = as_theta[i]
    if not np.isnan(t):
        as_node_theta[node] = float(t)
        k = int(np.clip((t + np.pi) / sector_width, 0, NUM_SECTORS - 1))
        as_sectors[k].append(node)
    else:
        as_no_theta.append(node)

print(f"   {NUM_SECTORS} sectors, {sum(len(v) for v in as_sectors.values()):,} nodes with theta")
for k in range(NUM_SECTORS):
    if as_sectors[k]:
        lo = -np.pi + k * sector_width
        hi = lo + sector_width
        print(f"     Sector {k}: [{np.degrees(lo):.0f}, {np.degrees(hi):.0f}) deg  ->  {len(as_sectors[k]):,} nodes")

# Step 3: build conflict graph (reuse from section 6 if available)
t_as_conflict = time.perf_counter()
as_conflict = build_conflict_graph(
    points_xyz_interp, ctr_config, as_graph, NOZZLE_RADIUS, n_arc_samples=20,
)
t_as_conflict_elapsed = time.perf_counter() - t_as_conflict

# Precompute conflict outdegree
as_conflict_outdegree = {node: len(as_conflict.get(node, set())) for node in as_nodes}

# Step 4: create detector
as_detector = CTRCollisionDetector(
    points_xyz_interp, ctr_config, nozzle_radius=NOZZLE_RADIUS,
    graph=as_graph, n_arc_samples=20,
)
for n in range(len(points_xyz_interp)):
    if n not in as_graph:
        as_detector.mark_visited(n)

as_valid_calls = 0
as_valid_true = 0
_as_orig_valid = as_detector.is_valid
def _as_track(node):
    global as_valid_calls, as_valid_true
    as_valid_calls += 1
    r = _as_orig_valid(node)
    if r:
        as_valid_true += 1
    return r
as_detector.is_valid = _as_track

as_passes = {}
as_idx = 0
as_visited = 0
as_node_set = set(as_nodes)

t_as_dfs = time.perf_counter()

for sector_idx in range(NUM_SECTORS):
    sector_nodes = as_sectors[sector_idx]
    if not sector_nodes:
        continue

    # Extract intra-sector conflict subgraph
    sector_set = set(sector_nodes)
    sector_adj = {n: set() for n in sector_nodes}
    for u in sector_nodes:
        for v in as_conflict.get(u, set()):
            if v in sector_set:
                sector_adj[u].add(v)

    # Eades ordering within sector
    sector_order = eades_greedy_fas(sector_adj, sector_nodes)
    sector_priority = {node: idx for idx, node in enumerate(sector_order)}

    sector_heap = []
    for node in sector_order:
        heapq.heappush(sector_heap, (sector_priority[node], node))

    while sector_heap:
        start_node = None
        while sector_heap:
            prio_val, node = heapq.heappop(sector_heap)
            if not as_detector.is_visited(node) and node in as_node_set:
                start_node = node
                break
        if start_node is None:
            break

        pass_list = iterative_dfs_greedy(
            as_graph, start_node, as_detector, points_xyz_interp,
            conflict_outdegree=as_conflict_outdegree,
        )
        if pass_list:
            as_passes[as_idx] = pass_list
            as_visited += len(pass_list)
            as_idx += 1

# Cleanup sweep
cleanup_nodes = sorted([n for n in as_nodes if not as_detector.is_visited(n)])
cleanup_nodes = sorted(set(cleanup_nodes) | set(n for n in as_no_theta if not as_detector.is_visited(n)))
if cleanup_nodes:
    cleanup_heap = []
    for node in cleanup_nodes:
        heapq.heappush(cleanup_heap, (float(points_xyz_interp[node, 2]), node))
    while cleanup_heap:
        start_node = None
        while cleanup_heap:
            z_val, node = heapq.heappop(cleanup_heap)
            if not as_detector.is_visited(node) and node in as_node_set:
                start_node = node
                break
        if start_node is None:
            break
        pass_list = iterative_dfs_greedy(
            as_graph, start_node, as_detector, points_xyz_interp,
            conflict_outdegree=as_conflict_outdegree,
        )
        if pass_list:
            as_passes[as_idx] = pass_list
            as_visited += len(pass_list)
            as_idx += 1

t_as_dfs_elapsed = time.perf_counter() - t_as_dfs
t_as_elapsed = time.perf_counter() - t_as
as_remaining = len(as_detector.unvisited)
as_sizes = np.array([len(p) for p in as_passes.values()]) if as_passes else np.array([0])

print(f"\n   ANGULAR SECTOR RESULTS:")
print(f"   Passes: {len(as_passes):,}")
print(f"   Nodes visited: {as_visited:,} / {n_reachable:,} ({100*as_visited/max(n_reachable,1):.1f}%)")
print(f"   Remaining unvisited: {as_remaining:,}")
print(f"   Time: {t_as_conflict_elapsed:.2f}s (conflict) + {t_as_dfs_elapsed:.2f}s (DFS) = {t_as_elapsed:.2f}s total")
print(f"   is_valid() calls: {as_valid_calls:,}  |  accept: {as_valid_true:,} "
      f"({100*as_valid_true/max(as_valid_calls,1):.1f}%)  |  reject: {as_valid_calls-as_valid_true:,}")
if as_passes:
    print(f"   Pass sizes: min={as_sizes.min()}, max={as_sizes.max()}, "
          f"mean={as_sizes.mean():.1f}, median={np.median(as_sizes):.0f}")


# ── 9. Oracle (no body-drag) ────────────────────────────────────────────
print(f"\n9. ORACLE (no body-drag check)")

from xcavate.core.oracle import OracleDetector, run_oracle

t_oracle = time.perf_counter()

oracle_graph = copy.deepcopy(graph_full)
for n in range(len(points_xyz_interp)):
    if n not in graph_full:
        oracle_graph.pop(n, None)

oracle_passes = run_oracle(
    oracle_graph, points_xyz_interp, ctr_config,
    nozzle_radius=NOZZLE_RADIUS, n_arc_samples=20,
)
oracle_visited = sum(len(p) for p in oracle_passes.values())
t_oracle_elapsed = time.perf_counter() - t_oracle
oracle_sizes = np.array([len(p) for p in oracle_passes.values()]) if oracle_passes else np.array([0])

print(f"   Passes: {len(oracle_passes):,}")
print(f"   Nodes visited: {oracle_visited:,} / {n_reachable:,} ({100*oracle_visited/max(n_reachable,1):.1f}%)")
print(f"   Time: {t_oracle_elapsed:.2f}s")
if oracle_passes:
    print(f"   Pass sizes: min={oracle_sizes.min()}, max={oracle_sizes.max()}, "
          f"mean={oracle_sizes.mean():.1f}, median={np.median(oracle_sizes):.0f}")


# ── 10. Gimbal Oracle (no body-drag) cone sweep ────────────────────────
print(f"\n10. GIMBAL ORACLE (no body-drag) — cone angle sweep")

from xcavate.core.oracle import run_gimbal_oracle, run_gimbal_realistic

GIMBAL_CONE_ANGLES = [5.0, 10.0, 15.0, 20.0]
gimbal_oracle_results = {}  # {angle: (passes, visited, time)}

for cone_deg in GIMBAL_CONE_ANGLES:
    go_graph = copy.deepcopy(graph_full)
    for n in range(len(points_xyz_interp)):
        if n not in graph_full:
            go_graph.pop(n, None)

    t_go = time.perf_counter()
    go_passes = run_gimbal_oracle(
        go_graph, points_xyz_interp, ctr_config,
        nozzle_radius=NOZZLE_RADIUS, n_arc_samples=20,
        cone_angle_deg=cone_deg, n_tilt=3, n_azimuth=8,
    )
    t_go_elapsed = time.perf_counter() - t_go
    go_visited = sum(len(p) for p in go_passes.values())
    gimbal_oracle_results[cone_deg] = (len(go_passes), go_visited, t_go_elapsed)
    pct = 100 * go_visited / max(n_reachable, 1)
    print(f"   cone={cone_deg:5.1f}°  |  visited={go_visited:>6,}/{n_reachable:,} ({pct:5.1f}%)  |  "
          f"passes={len(go_passes):>5,}  |  {t_go_elapsed:.1f}s")

# ── 11. Gimbal Realistic (with body-drag) cone sweep ──────────────────
print(f"\n11. GIMBAL REALISTIC (with body-drag) — cone angle sweep")

gimbal_realistic_results = {}

for cone_deg in GIMBAL_CONE_ANGLES:
    gr_graph = copy.deepcopy(graph_full)
    for n in range(len(points_xyz_interp)):
        if n not in graph_full:
            gr_graph.pop(n, None)

    t_gr = time.perf_counter()
    gr_passes = run_gimbal_realistic(
        gr_graph, points_xyz_interp, ctr_config,
        nozzle_radius=NOZZLE_RADIUS, n_arc_samples=20,
        cone_angle_deg=cone_deg, n_tilt=3, n_azimuth=8,
    )
    t_gr_elapsed = time.perf_counter() - t_gr
    gr_visited = sum(len(p) for p in gr_passes.values())
    gimbal_realistic_results[cone_deg] = (len(gr_passes), gr_visited, t_gr_elapsed)
    pct = 100 * gr_visited / max(n_reachable, 1)
    print(f"   cone={cone_deg:5.1f}°  |  visited={gr_visited:>6,}/{n_reachable:,} ({pct:5.1f}%)  |  "
          f"passes={len(gr_passes):>5,}  |  {t_gr_elapsed:.1f}s")

# Gimbal summary table
print(f"\n   GIMBAL SUMMARY (Oracle vs Realistic):")
print(f"   {'Cone':>6}  {'Oracle %':>10}  {'Realistic %':>12}  {'Gap':>6}")
print(f"   {'─'*6}  {'─'*10}  {'─'*12}  {'─'*6}")
print(f"   {'0.0°':>6}  {100*oracle_visited/max(n_reachable,1):>9.1f}%  "
      f"{100*nodes_visited/max(n_reachable,1):>11.1f}%  "
      f"{100*(oracle_visited-nodes_visited)/max(n_reachable,1):>5.1f}%")
for cone_deg in GIMBAL_CONE_ANGLES:
    go_n, go_v, _ = gimbal_oracle_results[cone_deg]
    gr_n, gr_v, _ = gimbal_realistic_results[cone_deg]
    print(f"   {cone_deg:5.1f}°  {100*go_v/max(n_reachable,1):>9.1f}%  "
          f"{100*gr_v/max(n_reachable,1):>11.1f}%  "
          f"{100*(go_v-gr_v)/max(n_reachable,1):>5.1f}%")

# Pick best gimbal results for comparison table
best_go_angle = max(gimbal_oracle_results, key=lambda a: gimbal_oracle_results[a][1])
best_go_passes, best_go_visited, best_go_time = gimbal_oracle_results[best_go_angle]
best_gr_angle = max(gimbal_realistic_results, key=lambda a: gimbal_realistic_results[a][1])
best_gr_passes, best_gr_visited, best_gr_time = gimbal_realistic_results[best_gr_angle]

# ── 12. Kinematic Analysis ──────────────────────────────────────────────
print(f"\n12. KINEMATIC ANALYSIS — approach direction map & singularity detection")

from xcavate.core.ctr_kinematic_analysis import (
    analyze_workspace, find_minimum_cone_angle,
    SING_ON_AXIS, SING_CAL_BOUND, SING_GIMBAL, SING_SS_LIMIT, SING_NTNL_LIMIT,
)

t_kin = time.perf_counter()
kin_nodes = np.array(sorted(graph.keys()), dtype=np.intp)
kin_result = analyze_workspace(
    points_xyz_interp, kin_nodes, ctr_config,
    cone_angle_deg=15.0, n_tilt=3, n_azimuth=8,
    nozzle_radius=NOZZLE_RADIUS,
)
t_kin_elapsed = time.perf_counter() - t_kin

ac = kin_result.approach_count
print(f"   Time: {t_kin_elapsed:.2f}s  |  {len(kin_nodes):,} nodes  |  {kin_result.total_configs} configs")
print(f"\n   APPROACH COUNT DISTRIBUTION:")
print(f"   min={ac.min()}, p5={int(np.percentile(ac, 5))}, p25={int(np.percentile(ac, 25))}, "
      f"median={int(np.median(ac))}, p75={int(np.percentile(ac, 75))}, "
      f"p95={int(np.percentile(ac, 95))}, max={ac.max()}")

# Histogram
ac_buckets = [(0, 0), (1, 1), (2, 5), (6, 10), (11, 15), (16, 20), (21, 25)]
print(f"\n   APPROACH COUNT HISTOGRAM:")
for lo, hi in ac_buckets:
    if lo == hi:
        count = int(np.sum(ac == lo))
        label = f"     {lo:>3}"
    else:
        count = int(np.sum((ac >= lo) & (ac <= hi)))
        label = f"     {lo:>2}-{hi:<2}"
    bar = "#" * min(count // max(len(kin_nodes) // 200, 1), 50)
    print(f"{label}: {count:>6,}  {bar}")

# Singularity flags
print(f"\n   SINGULARITY FLAGS:")
flag_names = [
    (SING_ON_AXIS, "ON_AXIS (r_perp ≈ 0)"),
    (SING_CAL_BOUND, "CAL_BOUND (near calibration edge)"),
    (SING_GIMBAL, "GIMBAL (only α=0 works)"),
    (SING_SS_LIMIT, "SS_LIMIT (z_ss near bound)"),
    (SING_NTNL_LIMIT, "NTNL_LIMIT (z_ntnl near bound)"),
]
for flag, name in flag_names:
    count = int(np.sum((kin_result.singularity_flags & flag) != 0))
    print(f"     {name:<40}: {count:>6,} nodes")

# Joint range statistics
print(f"\n   JOINT RANGE STATISTICS (across valid configs):")
dof_names = ["alpha", "phi", "z_ss", "z_ntnl", "theta"]
valid_mask = kin_result.approach_count > 0
if np.any(valid_mask):
    for j, name in enumerate(dof_names):
        ranges = kin_result.joint_ranges[valid_mask, j, 1] - kin_result.joint_ranges[valid_mask, j, 0]
        ranges = ranges[~np.isnan(ranges)]
        if len(ranges) > 0:
            print(f"     {name:<8}: mean_range={np.mean(ranges):.3f}, max_range={np.max(ranges):.3f}")

# Vulnerability distribution
vuln = kin_result.vulnerability
print(f"\n   VULNERABILITY DISTRIBUTION:")
print(f"   p50={np.percentile(vuln, 50):.3f}, p90={np.percentile(vuln, 90):.3f}, "
      f"p95={np.percentile(vuln, 95):.3f}, max={vuln.max():.3f}")

# Angular spread
spread = kin_result.angular_spread
print(f"\n   ANGULAR SPREAD:")
print(f"   mean={np.mean(spread):.3f}, min={np.min(spread):.3f}, max={np.max(spread):.3f}")


# ── 13. Approach Count vs Blocking Correlation ────────────────────────
print(f"\n13. APPROACH COUNT vs BLOCKING CORRELATION")

# Collect nodes NOT visited in the best gimbal oracle run (section 10)
# Reconstruct the visited set from the best oracle run
best_go_cone = best_go_angle
go_graph_corr = copy.deepcopy(graph_full)
for n in range(len(points_xyz_interp)):
    if n not in graph_full:
        go_graph_corr.pop(n, None)

t_corr = time.perf_counter()
go_passes_corr = run_gimbal_oracle(
    go_graph_corr, points_xyz_interp, ctr_config,
    nozzle_radius=NOZZLE_RADIUS, n_arc_samples=20,
    cone_angle_deg=best_go_cone, n_tilt=3, n_azimuth=8,
)
go_visited_set = set()
for p_list in go_passes_corr.values():
    go_visited_set.update(p_list)

go_blocked_set = set(graph.keys()) - go_visited_set

# Build correlation table: bucket nodes by approach_count → fraction blocked
print(f"\n   Correlation with Gimbal Oracle (cone={best_go_cone}°):")
print(f"   {'Approach Count':>16}  {'N_nodes':>8}  {'N_blocked':>10}  {'Blocked %':>10}")
print(f"   {'─'*16}  {'─'*8}  {'─'*10}  {'─'*10}")

# Map node indices back to approach counts
node_to_idx = {int(node): i for i, node in enumerate(kin_result.node_indices)}

corr_buckets = [(0, 0), (1, 1), (2, 5), (6, 10), (11, 15), (16, 20), (21, 25)]
for lo, hi in corr_buckets:
    if lo == hi:
        label = f"{lo}"
    else:
        label = f"{lo}-{hi}"
    bucket_nodes = []
    for node in graph:
        if node in node_to_idx:
            ac_val = kin_result.approach_count[node_to_idx[node]]
            if lo <= ac_val <= hi:
                bucket_nodes.append(node)
    n_in_bucket = len(bucket_nodes)
    if n_in_bucket == 0:
        print(f"   {label:>16}  {0:>8}  {0:>10}  {'N/A':>10}")
        continue
    n_blocked = sum(1 for n in bucket_nodes if n in go_blocked_set)
    pct = 100.0 * n_blocked / n_in_bucket
    print(f"   {label:>16}  {n_in_bucket:>8,}  {n_blocked:>10,}  {pct:>9.1f}%")

t_corr_elapsed = time.perf_counter() - t_corr
print(f"\n   Correlation analysis time: {t_corr_elapsed:.1f}s")


# ── 14. GIMBAL SOLVER — angular sector strategy with config tracking ────
print(f"\n14. GIMBAL SOLVER — angular sector strategy with config tracking")

from xcavate.core.gimbal_solver import run_gimbal_solver, GimbalNodeSolution

GIMBAL_SOLVER_CONE = 15.0

gs_graph = copy.deepcopy(graph_full)
for n in range(len(points_xyz_interp)):
    if n not in graph_full:
        gs_graph.pop(n, None)

t_gs = time.perf_counter()
gs_passes, gs_solutions = run_gimbal_solver(
    gs_graph, points_xyz_interp, ctr_config,
    nozzle_radius=NOZZLE_RADIUS, n_arc_samples=20,
    cone_angle_deg=GIMBAL_SOLVER_CONE, n_tilt=3, n_azimuth=8,
    strategy="angular_sector", n_sectors=NUM_SECTORS,
)
t_gs_elapsed = time.perf_counter() - t_gs

gs_visited = sum(len(p) for p in gs_passes.values())
gs_sizes = np.array([len(p) for p in gs_passes.values()]) if gs_passes else np.array([0])

print(f"\n   GIMBAL SOLVER RESULTS (cone={GIMBAL_SOLVER_CONE}°):")
print(f"   Passes: {len(gs_passes):,}")
print(f"   Nodes visited: {gs_visited:,} / {n_reachable:,} ({100*gs_visited/max(n_reachable,1):.1f}%)")
print(f"   Solutions recorded: {len(gs_solutions):,}")
print(f"   Time: {t_gs_elapsed:.2f}s")
if gs_passes:
    print(f"   Pass sizes: min={gs_sizes.min()}, max={gs_sizes.max()}, "
          f"mean={gs_sizes.mean():.1f}, median={np.median(gs_sizes):.0f}")

# Config continuity analysis
if gs_solutions and gs_passes:
    total_consecutive = 0
    same_config_count = 0
    transitions_per_pass = []
    for p_list in gs_passes.values():
        pass_transitions = 0
        for k in range(1, len(p_list)):
            if p_list[k] in gs_solutions and p_list[k-1] in gs_solutions:
                total_consecutive += 1
                if gs_solutions[p_list[k]].config_idx == gs_solutions[p_list[k-1]].config_idx:
                    same_config_count += 1
                else:
                    pass_transitions += 1
        transitions_per_pass.append(pass_transitions)
    continuity_pct = 100 * same_config_count / max(total_consecutive, 1)
    trans_arr = np.array(transitions_per_pass) if transitions_per_pass else np.array([0])
    print(f"\n   CONFIG CONTINUITY:")
    print(f"   Same config consecutive pairs: {same_config_count:,} / {total_consecutive:,} ({continuity_pct:.1f}%)")
    print(f"   Transitions per pass: mean={trans_arr.mean():.2f}, max={trans_arr.max()}")

    # Config usage distribution
    config_counts = {}
    for sol in gs_solutions.values():
        config_counts[sol.config_idx] = config_counts.get(sol.config_idx, 0) + 1
    print(f"\n   CONFIG USAGE (top 5):")
    for cfg_idx, count in sorted(config_counts.items(), key=lambda x: -x[1])[:5]:
        print(f"     config {cfg_idx}: {count:,} nodes ({100*count/len(gs_solutions):.1f}%)")

# Compare vs realistic baseline
best_gr_cone_15 = gimbal_realistic_results.get(15.0)
if best_gr_cone_15:
    gr_15_v = best_gr_cone_15[1]
    delta_v = gs_visited - gr_15_v
    print(f"\n   vs Gimbal Realistic (15°): {'+' if delta_v >= 0 else ''}{delta_v:,} nodes "
          f"({'+' if delta_v >= 0 else ''}{100*delta_v/max(n_reachable,1):.1f}%)")


# ── 15. Final comparison ─────────────────────────────────────────────────
t_total = time.perf_counter() - t0_total

print(f"\n{'=' * 120}")
print(f"COMPARISON")
print(f"{'=' * 120}")
print(f"   {'Metric':<25} {'Straight':>10} {'CTR Z-hp':>10} {'CTR Swpt':>10} {'CTR Angl':>10} {'Oracle':>10} {'Gmbl Orac':>10} {'Gmbl Real':>10} {'Gmbl Solv':>10}")
print(f"   {'─'*25} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*10}")
print(f"   {'Passes':<25} {len(straight_passes):>10,} {len(print_passes):>10,} {len(sv_passes):>10,} {len(as_passes):>10,} {len(oracle_passes):>10,} {best_go_passes:>10,} {best_gr_passes:>10,} {len(gs_passes):>10,}")
print(f"   {'Nodes visited':<25} {straight_visited:>10,} {nodes_visited:>10,} {sv_visited:>10,} {as_visited:>10,} {oracle_visited:>10,} {best_go_visited:>10,} {best_gr_visited:>10,} {gs_visited:>10,}")
print(f"   {'Visit rate':<25} {'100.0%':>10} {100*nodes_visited/max(n_reachable,1):>9.1f}% {100*sv_visited/max(n_reachable,1):>9.1f}% {100*as_visited/max(n_reachable,1):>9.1f}% {100*oracle_visited/max(n_reachable,1):>9.1f}% {100*best_go_visited/max(n_reachable,1):>9.1f}% {100*best_gr_visited/max(n_reachable,1):>9.1f}% {100*gs_visited/max(n_reachable,1):>9.1f}%")
print(f"   {'Unvisited':<25} {0:>10,} {n_reachable-nodes_visited:>10,} {sv_remaining:>10,} {as_remaining:>10,} {n_reachable-oracle_visited:>10,} {n_reachable-best_go_visited:>10,} {n_reachable-best_gr_visited:>10,} {n_reachable-gs_visited:>10,}")
print(f"   {'Time':<25} {t_straight_elapsed:>9.1f}s {t_dfs_elapsed:>9.1f}s {t_conflict_elapsed+t_topo_elapsed+t_sv_dfs_elapsed:>9.1f}s {t_as_elapsed:>9.1f}s {t_oracle_elapsed:>9.1f}s {best_go_time:>9.1f}s {best_gr_time:>9.1f}s {t_gs_elapsed:>9.1f}s")
print(f"   {'Best cone angle':<25} {'':>10} {'':>10} {'':>10} {'':>10} {'':>10} {best_go_angle:>9.1f}° {best_gr_angle:>9.1f}° {GIMBAL_SOLVER_CONE:>9.1f}°")
if print_passes and straight_passes and sv_passes and as_passes:
    print(f"   {'is_valid accept %':<25} {'N/A':>10} {100*is_valid_true/max(is_valid_calls,1):>9.1f}% {100*sv_valid_true/max(sv_valid_calls,1):>9.1f}% {100*as_valid_true/max(as_valid_calls,1):>9.1f}% {'N/A':>10} {'N/A':>10} {'N/A':>10} {'N/A':>10}")
print(f"\n   Total elapsed: {t_total:.1f}s")
