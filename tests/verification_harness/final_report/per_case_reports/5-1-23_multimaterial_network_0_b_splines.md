# Case `5-1-23_multimaterial_network_0_b_splines`

## Pipelines
### science — OK
- exit_code: `0`
- emitted: `gcode_multimaterial.txt`, `gcode.txt`
- metrics: `moves=3110 g0=0 g1=2424 g4=0 path=7182.730 mm mm_trans=33 t_est=1522.04 s`

### x1130 — OK
- exit_code: `0`
- emitted: `gcode_MM_pressure.txt`, `gcode_SM_pressure.txt`
- metrics: `moves=2525 g0=0 g1=2457 g4=0 path=7353.539 mm mm_trans=33 t_est=1217.99 s`

### main — OK
- exit_code: `0`
- emitted: `gcode_MM_pressure.txt`, `gcode_SM_pressure.txt`
- metrics: `moves=2524 g0=0 g1=2457 g4=0 path=7353.539 mm mm_trans=33 t_est=1217.99 s`

## Pairwise diffs
### science vs x1130
- counts=(3110,2525) aligned=False max_xyz_dev=72.72 max_f_dev=9.332 max_e_dev=0 out_of_tol=2521 byte_equal=False
- first divergences:

```
  [    2] A: G91 G1 A-60 B-60 F5
        B: G91 G1 Y0.5 F5.0
  [    3] A: G90
        B: G91 G1 A-60.0 B-60.0 F5.0
  [    4] A: G92 X-10.405079990704829 Y1.7564312892943552 A-9.896561013084437 B-9.896561013084437
        B: G90
  [    5] A: Enable Ab
        B: G92 X-10.40508 Y1.756431 A-9.896561 B-9.896561
  [    6] A: Enable Aa
        B: G1 X-10.40508 Y1.756431 B-9.896561 F2.5489302641007896
  [    7] A: BRAKE Ab 0
        B: G1 X-10.434403 Y1.854763 B-9.892032 F2.548927368182767
  [    8] A: BRAKE Aa 0
        B: G1 X-10.463726 Y1.953095 B-9.887504 F2.548927368182767
  [    9] A: DWELL 0.75
        B: G1 X-10.484906 Y2.052771 B-9.87441 F2.548927714607718
  [   10] A: G1 X-10.405079990704829 Y1.7564312892943552 B-9.896561013084437 F2.5489302641007896
        B: G1 X-10.506087 Y2.152447 B-9.861316 F2.548927714607718
  [   11] A: G1 X-10.434402771636679 Y1.854763086482289 B-9.892032477480075 F2.548927368182767
        B: G1 X-10.517558 Y2.252006 B-9.838598 F2.54892815302443
  [   12] A: G1 X-10.463725552568528 Y1.953094883670223 B-9.887503941875716 F2.548927368182767
        B: G1 X-10.529028 Y2.351565 B-9.815879 F2.54892815302443
  [   13] A: G1 X-10.484906279849646 Y2.052770793112736 B-9.874410201254499 F2.548927714607718
        B: G1 X-10.529899 Y2.449037 B-9.783325 F2.548927938218316
  [   14] A: G1 X-10.506087007130763 Y2.152446702555249 B-9.861316460633283 F2.548927714607718
        B: G1 X-10.530769 Y2.546508 B-9.750772 F2.548927938218316
  [   15] A: G1 X-10.517557612832169 Y2.252006008188412 B-9.838597719685708 F2.54892815302443
        B: G1 X-10.520908 Y2.639872 B-9.708945 F2.5489279179027067
  [   16] A: G1 X-10.529028218533576 Y2.351565313821575 B-9.815878978738136 F2.54892815302443
        B: G1 X-10.511047 Y2.733237 B-9.667118 F2.5489279179027067
  [   17] A: G1 X-10.529898718271207 Y2.44903681024301 B-9.783325294321912 F2.548927938218316
        B: G1 X-10.491414 Y2.821065 B-9.617462 F2.548927973850255
  [   18] A: G1 X-10.530769218008839 Y2.546508306664445 B-9.750771609905689 F2.548927938218316
        B: G1 X-10.471781 Y2.908894 B-9.567806 F2.548927973850255
  [   19] A: G1 X-10.52090831909512 Y2.639872407849908 B-9.708944718152111 F2.5489279179027067
        B: G1 X-10.44372 Y2.990448 B-9.511913 F2.548927967873902
  [   20] A: G1 X-10.5110474201814 Y2.733236509035371 B-9.667117826398531 F2.5489279179027067
        B: G1 X-10.41566 Y3.072002 B-9.456021 F2.548927967873902
  [   21] A: G1 X-10.491414096507373 Y2.821065318456002 B-9.617461832340815 F2.548927973850255
        B: G1 X-10.380757 Y3.147297 B-9.395464 F2.548927955524282
```

### science vs main
- counts=(3110,2524) aligned=False max_xyz_dev=72.72 max_f_dev=9.332 max_e_dev=0 out_of_tol=2521 byte_equal=False
- first divergences:

```
  [    2] A: G91 G1 A-60 B-60 F5
        B: G91 G1 Y0.5 F5.0
  [    3] A: G90
        B: G91 G1 A-60.0 B-60.0 F5.0
  [    4] A: G92 X-10.405079990704829 Y1.7564312892943552 A-9.896561013084437 B-9.896561013084437
        B: G90
  [    5] A: Enable Ab
        B: G92 X-10.40508 Y1.756431 A-9.896561 B-9.896561
  [    6] A: Enable Aa
        B: G1 X-10.40508 Y1.756431 B-9.896561 F2.54893
  [    7] A: BRAKE Ab 0
        B: G1 X-10.434403 Y1.854763 B-9.892032 F2.548927
  [    8] A: BRAKE Aa 0
        B: G1 X-10.463726 Y1.953095 B-9.887504 F2.548927
  [    9] A: DWELL 0.75
        B: G1 X-10.484906 Y2.052771 B-9.87441 F2.548928
  [   10] A: G1 X-10.405079990704829 Y1.7564312892943552 B-9.896561013084437 F2.5489302641007896
        B: G1 X-10.506087 Y2.152447 B-9.861316 F2.548928
  [   11] A: G1 X-10.434402771636679 Y1.854763086482289 B-9.892032477480075 F2.548927368182767
        B: G1 X-10.517558 Y2.252006 B-9.838598 F2.548928
  [   12] A: G1 X-10.463725552568528 Y1.953094883670223 B-9.887503941875716 F2.548927368182767
        B: G1 X-10.529028 Y2.351565 B-9.815879 F2.548928
  [   13] A: G1 X-10.484906279849646 Y2.052770793112736 B-9.874410201254499 F2.548927714607718
        B: G1 X-10.529899 Y2.449037 B-9.783325 F2.548928
  [   14] A: G1 X-10.506087007130763 Y2.152446702555249 B-9.861316460633283 F2.548927714607718
        B: G1 X-10.530769 Y2.546508 B-9.750772 F2.548928
  [   15] A: G1 X-10.517557612832169 Y2.252006008188412 B-9.838597719685708 F2.54892815302443
        B: G1 X-10.520908 Y2.639872 B-9.708945 F2.548928
  [   16] A: G1 X-10.529028218533576 Y2.351565313821575 B-9.815878978738136 F2.54892815302443
        B: G1 X-10.511047 Y2.733237 B-9.667118 F2.548928
  [   17] A: G1 X-10.529898718271207 Y2.44903681024301 B-9.783325294321912 F2.548927938218316
        B: G1 X-10.491414 Y2.821065 B-9.617462 F2.548928
  [   18] A: G1 X-10.530769218008839 Y2.546508306664445 B-9.750771609905689 F2.548927938218316
        B: G1 X-10.471781 Y2.908894 B-9.567806 F2.548928
  [   19] A: G1 X-10.52090831909512 Y2.639872407849908 B-9.708944718152111 F2.5489279179027067
        B: G1 X-10.44372 Y2.990448 B-9.511913 F2.548928
  [   20] A: G1 X-10.5110474201814 Y2.733236509035371 B-9.667117826398531 F2.5489279179027067
        B: G1 X-10.41566 Y3.072002 B-9.456021 F2.548928
  [   21] A: G1 X-10.491414096507373 Y2.821065318456002 B-9.617461832340815 F2.548927973850255
        B: G1 X-10.380757 Y3.147297 B-9.395464 F2.548928
```

### x1130 vs main
- counts=(2525,2524) aligned=True max_xyz_dev=4.915e-07 max_f_dev=4.994e-07 max_e_dev=0 out_of_tol=0 byte_equal=False

## Known residual deltas

These are documented, characterized differences between the pipelines — not bugs in the harness. Each is either intrinsic to the pipeline implementation or already mitigated by the harness.

### x1130 ignores its own `--flow` argument (mitigated)
`id: x1130-flow-override`

`xcavate_11_30_25.py` line 3705 hardcodes `flow = 0.1609429886081009`, overriding the `--flow` argparse value. The harness sets `CANONICAL_PARAMS['flow'] = 0.1609429...` so all pipelines compute feedrates on the same flow constant; without this match the F values would diverge by the 0.1609/0.1272 = 1.265× ratio across every G1 move.

### x1130 emits an extra leading `G90` before its first `G92`
`id: preamble-line-shift`

x1130's preamble is `G90 / G92 .. / G90 F<feed> / ...`; main's is `G92 .. / G90 F<feed> / ...`. This shifts every subsequent line index by 1 between the two streams. The harness compensates via `align_on_first_g1=True` in `numerical_diff`, so reported deviations are post-alignment and reflect actual trajectory drift rather than the index shift.

### x1130's multimaterial-pressure writer is gated on `custom_gcode == 1` (patched)
`id: x1130-mm-pressure-gate`

Script line 4717 reads `if multimaterial == 1 and custom_gcode == 1 and printer_type == 0:`. Without `--custom 1` (and the auxiliary `inputs/custom/*.txt` template files it would then read), x1130 silently skipped MM emission and only wrote `gcode_SM_pressure.txt` even for MM inputs — leading to `mm_trans=0` in our metrics. `x1130_runner.py` rewrites that gate in memory so the MM writer runs without requiring custom template files. After the patch, x1130 emits 184 nozzle transitions on the 61-vessel network (vs main's 206).

### main's iterative DFS produces one more raw pass than x1130's recursive DFS
`id: dfs-extra-pass`

main uses an explicit-stack iterative DFS in `xcavate/core/pathfinding.py` with reversed neighbour push order; x1130 uses a recursive DFS that iterates `graph[node]` in native order. On the 4-vessel network, main produces **14 raw passes** (lengths sorted: 5, 11, 12, 13, 20, 33, 68, 97, 113, 163, 203, 227, 397, 418) while x1130 produces **13**. The extra pass is typically a 2-node bridge through a branchpoint that x1130 absorbs into an adjacent pass. Same vessels are printed; the split boundary differs.

### `run_full_gap_closure_pipeline` distributes branchpoint nodes differently
`id: gap-closure-branchpoint-distribution`

After subdivision (which is algorithmically equivalent in both pipelines), main's gap-closure prepends/appends shared branchpoint nodes to stitch passes — e.g. main pass 1 starts with `[1571, 1572, ...]` even though `subdivide_passes` returned `[1572, ...]`. Pass 2 ends with the same node it started with (`[985, 489, ..., 393, 985]`). x1130's gap closure makes the same kind of additions but distributes them across different passes, leaving one fewer net pass. Net effect: same printed segments and same vessel coverage, slightly different pass boundaries and therefore slightly different jog choreography between passes.

### main emits more multimaterial transitions than x1130
`id: mm-transition-count-divergence`

On the 61-vessel multimaterial network main emits **205** nozzle switches while x1130 emits **183** — an ~12% surplus. The per-switch choreography is byte-identical between the two pipelines (`G91 G1 A60 B60 F5 / G91 G1 X-103 F10 / G91 G1 Y0.5 F5 / G91 G1 A-60 B-60`); only the **count** and **positions** of switches differ. Cause: main's `_subdivide_by_material` in `xcavate/pipeline.py` splits passes at material transitions more aggressively than x1130's Branchpoint-Condition analogue, producing extra arterial↔venous flips. When the harness aligns the two streams by index, at some row main is mid-shuttle (`G91 G1 X-103`) while x1130 is on a normal print move at X ≈ +103 — giving the characteristic ~206 mm `max_xyz_dev`. Functionally the same vessels are printed in both materials; main just switches between printheads more often.

Two algorithmic divergences in this path have been reconciled with x1130 (with regression tests):
  • outlier-swap order in `_subdivide_by_material` is now first → middle (cascading) → last
  • `classify_passes_by_material` now uses the **second** node of each pass, matching `xcavate_11_30_25.py:4762`
Neither fix moved the +22 transition surplus on the 61-vessel network, indicating a third difference remains (likely in the post-subdivide reclassification or in how same-material adjacent sub-passes are merged). Investigation paused; residual is documented rather than chased further.
