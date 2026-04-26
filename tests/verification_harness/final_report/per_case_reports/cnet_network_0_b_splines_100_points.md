# Case `cnet_network_0_b_splines_100_points`

## Pipelines
### science — OK
- exit_code: `0`
- emitted: `gcode.txt`
- metrics: `moves=20940 g0=0 g1=16128 g4=0 path=4936.942 mm mm_trans=0 t_est=4076.24 s`

### x1130 — OK
- exit_code: `0`
- emitted: `gcode_SM_pressure.txt`
- metrics: `moves=18348 g0=0 g1=16128 g4=0 path=4936.942 mm mm_trans=0 t_est=4076.24 s`

### main — OK
- exit_code: `0`
- emitted: `gcode_SM_pressure.txt`
- metrics: `moves=18347 g0=0 g1=16128 g4=0 path=4936.942 mm mm_trans=0 t_est=4076.24 s`

## Pairwise diffs
### science vs x1130
- counts=(20940,18348) aligned=False max_xyz_dev=32.47 max_f_dev=9.955 max_e_dev=0 out_of_tol=18159 byte_equal=False
- first divergences:

```
  [   45] A: Enable Aa
        B: G91
  [   46] A: G91
        B: G1 A0.5 F0.25
  [   47] A: DWELL 0.08
        B: G90
  [   48] A: BRAKE Aa 1
        B: G1 A17.043445151000583 F10
  [   49] A: G1 A0.5 F0.25
        B: G90
  [   50] A: G90
        B: G1 X15.594251 Y13.404555
  [   51] A: G1 A17.043445151000583 F10
        B: G90
  [   52] A: G90
        B: G1 X15.594251 Y13.404555 A-17.110545
  [   53] A: BRAKE Aa 1
        B: G91
  [   54] A: G1 X15.594251249055942 Y13.404555265911425
        B: G90
  [   55] A: G90
        B: G1 X15.594251 Y13.404555 A-17.110545 F0.9640890164385006
  [   56] A: G1 X15.594251249055942 Y13.404555265911425 A-17.110544853697636
        B: G1 X15.602553 Y13.523412 A-17.089739 F0.9640886618159613
  [   57] A: Enable Aa
        B: G1 X15.591446 Y13.634747 A-17.044352 F0.9640827416508073
  [   58] A: G91
        B: G1 X15.563189 Y13.732752 A-16.979055 F0.9640925873288495
  [   59] A: BRAKE Aa 0
        B: G1 X15.522231 Y13.81482 A-16.900656 F0.9641211337021148
  [   60] A: DWELL 0.08
        B: G1 X15.472581 Y13.883643 A-16.813926 F0.9641081233061453
  [   61] A: G90
        B: G1 X15.417978 Y13.942489 A-16.723106 F0.963996166011991
  [   62] A: G1 X15.594251249055942 Y13.404555265911425 A-17.110544853697636 F0.9640890164385006
        B: G1 X15.36017 Y13.99334 A-16.630056 F0.9638365798406026
  [   63] A: G1 X15.602553311984195 Y13.523411712160009 A-17.08973873939619 F0.9640886618159613
        B: G1 X15.299801 Y14.03746 A-16.535316 F0.9637408542447039
  [   64] A: G1 X15.5914463735163 Y13.634746506156139 A-17.04435212718464 F0.9640827416508073
        B: G1 X15.237502 Y14.076107 A-16.43941 F0.9638210687364491
```

### science vs main
- counts=(20940,18347) aligned=False max_xyz_dev=32.47 max_f_dev=9.955 max_e_dev=0 out_of_tol=18159 byte_equal=False
- first divergences:

```
  [   45] A: Enable Aa
        B: G91
  [   46] A: G91
        B: G1 A0.5 F0.25
  [   47] A: DWELL 0.08
        B: G90
  [   48] A: BRAKE Aa 1
        B: G1 A17.043445151000583 F10
  [   49] A: G1 A0.5 F0.25
        B: G90
  [   50] A: G90
        B: G1 X15.594251 Y13.404555
  [   51] A: G1 A17.043445151000583 F10
        B: G90
  [   52] A: G90
        B: G1 X15.594251 Y13.404555 A-17.110545
  [   53] A: BRAKE Aa 1
        B: G91
  [   54] A: G1 X15.594251249055942 Y13.404555265911425
        B: G90
  [   55] A: G90
        B: G1 X15.594251 Y13.404555 A-17.110545 F0.964089
  [   56] A: G1 X15.594251249055942 Y13.404555265911425 A-17.110544853697636
        B: G1 X15.602553 Y13.523412 A-17.089739 F0.964089
  [   57] A: Enable Aa
        B: G1 X15.591446 Y13.634747 A-17.044352 F0.964083
  [   58] A: G91
        B: G1 X15.563189 Y13.732752 A-16.979055 F0.964093
  [   59] A: BRAKE Aa 0
        B: G1 X15.522231 Y13.81482 A-16.900656 F0.964121
  [   60] A: DWELL 0.08
        B: G1 X15.472581 Y13.883643 A-16.813926 F0.964108
  [   61] A: G90
        B: G1 X15.417978 Y13.942489 A-16.723106 F0.963996
  [   62] A: G1 X15.594251249055942 Y13.404555265911425 A-17.110544853697636 F0.9640890164385006
        B: G1 X15.36017 Y13.99334 A-16.630056 F0.963837
  [   63] A: G1 X15.602553311984195 Y13.523411712160009 A-17.08973873939619 F0.9640886618159613
        B: G1 X15.299801 Y14.03746 A-16.535316 F0.963741
  [   64] A: G1 X15.5914463735163 Y13.634746506156139 A-17.04435212718464 F0.9640827416508073
        B: G1 X15.237502 Y14.076107 A-16.43941 F0.963821
```

### x1130 vs main
- counts=(18348,18347) aligned=True max_xyz_dev=0 max_f_dev=5e-07 max_e_dev=0 out_of_tol=0 byte_equal=False

## Known residual deltas

These are documented, characterized differences between the pipelines — not bugs in the harness. Each is either intrinsic to the pipeline implementation or already mitigated by the harness.

### x1130 ignores its own `--flow` argument (mitigated)
`id: x1130-flow-override`

`xcavate_11_30_25.py` line 3705 hardcodes `flow = 0.1609429886081009`, overriding the `--flow` argparse value. The harness sets `CANONICAL_PARAMS['flow'] = 0.1609429...` so all pipelines compute feedrates on the same flow constant; without this match the F values would diverge by the 0.1609/0.1272 = 1.265× ratio across every G1 move.

### x1130 emits an extra leading `G90` before its first `G92`
`id: preamble-line-shift`

x1130's preamble is `G90 / G92 .. / G90 F<feed> / ...`; main's is `G92 .. / G90 F<feed> / ...`. This shifts every subsequent line index by 1 between the two streams. The harness compensates via `align_on_first_g1=True` in `numerical_diff`, so reported deviations are post-alignment and reflect actual trajectory drift rather than the index shift.

### main's iterative DFS produces one more raw pass than x1130's recursive DFS
`id: dfs-extra-pass`

main uses an explicit-stack iterative DFS in `xcavate/core/pathfinding.py` with reversed neighbour push order; x1130 uses a recursive DFS that iterates `graph[node]` in native order. On the 4-vessel network, main produces **14 raw passes** (lengths sorted: 5, 11, 12, 13, 20, 33, 68, 97, 113, 163, 203, 227, 397, 418) while x1130 produces **13**. The extra pass is typically a 2-node bridge through a branchpoint that x1130 absorbs into an adjacent pass. Same vessels are printed; the split boundary differs.

### `run_full_gap_closure_pipeline` distributes branchpoint nodes differently
`id: gap-closure-branchpoint-distribution`

After subdivision (which is algorithmically equivalent in both pipelines), main's gap-closure prepends/appends shared branchpoint nodes to stitch passes — e.g. main pass 1 starts with `[1571, 1572, ...]` even though `subdivide_passes` returned `[1572, ...]`. Pass 2 ends with the same node it started with (`[985, 489, ..., 393, 985]`). x1130's gap closure makes the same kind of additions but distributes them across different passes, leaving one fewer net pass. Net effect: same printed segments and same vessel coverage, slightly different pass boundaries and therefore slightly different jog choreography between passes.
