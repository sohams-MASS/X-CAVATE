# Case `network_0_b_splines_14_vessels`

## Pipelines
### science — OK
- exit_code: `0`
- emitted: `gcode.txt`
- metrics: `moves=5084 g0=0 g1=4367 g4=0 path=1140.626 mm mm_trans=0 t_est=1667.00 s`

### x1130 — OK
- exit_code: `0`
- emitted: `gcode_SM_pressure.txt`
- metrics: `moves=4697 g0=0 g1=4367 g4=0 path=1140.626 mm mm_trans=0 t_est=1667.00 s`

### main — OK
- exit_code: `0`
- emitted: `gcode_SM_pressure.txt`
- metrics: `moves=4696 g0=0 g1=4367 g4=0 path=1140.626 mm mm_trans=0 t_est=1667.00 s`

## Pairwise diffs
### science vs x1130
- counts=(5084,4697) aligned=False max_xyz_dev=35.17 max_f_dev=9.914 max_e_dev=0 out_of_tol=4531 byte_equal=False
- first divergences:

```
  [  153] A: Enable Aa
        B: G91
  [  154] A: G91
        B: G1 A0.5 F0.25
  [  155] A: DWELL 0.08
        B: G90
  [  156] A: BRAKE Aa 1
        B: G1 A24.963496470633185 F10
  [  157] A: G1 A0.5 F0.25
        B: G90
  [  158] A: G90
        B: G1 X6.588714 Y-4.147611
  [  159] A: G1 A24.963496470633185 F10
        B: G90
  [  160] A: G90
        B: G1 X6.588714 Y-4.147611 A-22.199824
  [  161] A: BRAKE Aa 1
        B: G91
  [  162] A: G1 X6.588714409145773 Y-4.14761051794545
        B: G90
  [  163] A: G90
        B: G1 X6.588714 Y-4.147611 A-22.199824 F0.5814029554403893
  [  164] A: G1 X6.588714409145773 Y-4.14761051794545 A-22.19982445928311
        B: G1 X6.552107 Y-4.337306 A-22.198942 F0.5814029554403893
  [  165] A: Enable Aa
        B: G1 X6.515499 Y-4.527001 A-22.19806 F0.5814029554403893
  [  166] A: G91
        B: G1 X6.478891 Y-4.716696 A-22.197178 F0.5814029554403893
  [  167] A: BRAKE Aa 0
        B: G1 X6.442284 Y-4.906391 A-22.196296 F0.5814069596283921
  [  168] A: DWELL 0.08
        B: G1 X6.401304 Y-5.095021 A-22.188354 F0.5814069596283921
  [  169] A: G90
        B: G1 X6.360324 Y-5.283651 A-22.180412 F0.5814069596283921
  [  170] A: G1 X6.588714409145773 Y-4.14761051794545 A-22.19982445928311 F0.5814029554403893
        B: G1 X6.319344 Y-5.472282 A-22.172471 F0.5814069596283921
  [  171] A: G1 X6.552106699685743 Y-4.337305520689096 A-22.198942359872497 F0.5814029554403893
        B: G1 X6.278364 Y-5.660912 A-22.164529 F0.5814293979115278
  [  172] A: G1 X6.515498990225714 Y-4.527000523432741 A-22.19806026046188 F0.5814029554403893
        B: G1 X6.234229 Y-5.848537 A-22.151418 F0.5814293979115278
```

### science vs main
- counts=(5084,4696) aligned=False max_xyz_dev=35.17 max_f_dev=9.914 max_e_dev=0 out_of_tol=4531 byte_equal=False
- first divergences:

```
  [  153] A: Enable Aa
        B: G91
  [  154] A: G91
        B: G1 A0.5 F0.25
  [  155] A: DWELL 0.08
        B: G90
  [  156] A: BRAKE Aa 1
        B: G1 A24.963496470633185 F10
  [  157] A: G1 A0.5 F0.25
        B: G90
  [  158] A: G90
        B: G1 X6.588714 Y-4.147611
  [  159] A: G1 A24.963496470633185 F10
        B: G90
  [  160] A: G90
        B: G1 X6.588714 Y-4.147611 A-22.199824
  [  161] A: BRAKE Aa 1
        B: G91
  [  162] A: G1 X6.588714409145773 Y-4.14761051794545
        B: G90
  [  163] A: G90
        B: G1 X6.588714 Y-4.147611 A-22.199824 F0.581403
  [  164] A: G1 X6.588714409145773 Y-4.14761051794545 A-22.19982445928311
        B: G1 X6.552107 Y-4.337306 A-22.198942 F0.581403
  [  165] A: Enable Aa
        B: G1 X6.515499 Y-4.527001 A-22.19806 F0.581403
  [  166] A: G91
        B: G1 X6.478891 Y-4.716696 A-22.197178 F0.581403
  [  167] A: BRAKE Aa 0
        B: G1 X6.442284 Y-4.906391 A-22.196296 F0.581407
  [  168] A: DWELL 0.08
        B: G1 X6.401304 Y-5.095021 A-22.188354 F0.581407
  [  169] A: G90
        B: G1 X6.360324 Y-5.283651 A-22.180412 F0.581407
  [  170] A: G1 X6.588714409145773 Y-4.14761051794545 A-22.19982445928311 F0.5814029554403893
        B: G1 X6.319344 Y-5.472282 A-22.172471 F0.581407
  [  171] A: G1 X6.552106699685743 Y-4.337305520689096 A-22.198942359872497 F0.5814029554403893
        B: G1 X6.278364 Y-5.660912 A-22.164529 F0.581429
  [  172] A: G1 X6.515498990225714 Y-4.527000523432741 A-22.19806026046188 F0.5814029554403893
        B: G1 X6.234229 Y-5.848537 A-22.151418 F0.581429
```

### x1130 vs main
- counts=(4697,4696) aligned=True max_xyz_dev=0 max_f_dev=4.998e-07 max_e_dev=0 out_of_tol=0 byte_equal=False

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

### Branchpoint daughter-selection ties resolved differently across pipelines
`id: branchpoint-tiebreak-large-network`

On dense vasculature (e.g., the 500-vessel network with 63,904 interpolated points), some vessel endpoints have two or more candidate "daughter" nodes at *exactly equal* distance. Each pipeline uses a different tiebreaker:
  • main → `scipy.cKDTree.query(point, k=N)` (binary tree)
  • x1130 → nested-loop brute force with strict-less comparison
  • science → nested-loop brute force with slightly different loop ordering than x1130
When ties occur, the three implementations pick different daughter nodes. On the 4/9/14-vessel networks ties are rare, so the graphs match exactly (`x1130 ↔ main = 0` mm). On the 500-vessel network ~38 adjacency-list entries differ between main and x1130 — different branchpoint daughter pairs cascade through DFS into a different pass order, producing the ~70 mm `max_xyz_dev` between every pair (sci↔x1130 = 71.16, sci↔main = 69.94, x1130↔main = 70.19). All three pipelines still print the same vessels with the same total path; only the visit order differs.

To force byte-equivalence we'd need to add an explicit secondary tiebreaker (e.g., "on equal distance, pick smaller node index") and apply it identically to all three implementations. None of the three is currently "correct" — they're all valid choices for the same geometric configuration.
