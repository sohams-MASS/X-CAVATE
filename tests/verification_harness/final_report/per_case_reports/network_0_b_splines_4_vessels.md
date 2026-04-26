# Case `network_0_b_splines_4_vessels`

## Pipelines
### science — OK
- exit_code: `0`
- emitted: `gcode.txt`
- metrics: `moves=2197 g0=0 g1=1896 g4=0 path=418.709 mm mm_trans=0 t_est=620.25 s`

### x1130 — OK
- exit_code: `0`
- emitted: `gcode_SM_pressure.txt`
- metrics: `moves=2034 g0=0 g1=1896 g4=0 path=418.709 mm mm_trans=0 t_est=620.25 s`

### main — OK
- exit_code: `0`
- emitted: `gcode_SM_pressure.txt`
- metrics: `moves=2033 g0=0 g1=1896 g4=0 path=418.709 mm mm_trans=0 t_est=620.25 s`

## Pairwise diffs
### science vs x1130
- counts=(2197,2034) aligned=False max_xyz_dev=33 max_f_dev=9.821 max_e_dev=0 out_of_tol=1838 byte_equal=False
- first divergences:

```
  [  189] A: Enable Aa
        B: G91
  [  190] A: G91
        B: G1 A0.5 F0.25
  [  191] A: DWELL 0.08
        B: G90
  [  192] A: BRAKE Aa 1
        B: G1 A22.878906016426214 F10
  [  193] A: G1 A0.5 F0.25
        B: G90
  [  194] A: G90
        B: G1 X-3.482783 Y10.087774
  [  195] A: G1 A22.878906016426214 F10
        B: G90
  [  196] A: G90
        B: G1 X-3.482783 Y10.087774 A-23.687615
  [  197] A: BRAKE Aa 1
        B: G91
  [  198] A: G1 X-3.482782730688342 Y10.08777395304591
        B: G90
  [  199] A: G90
        B: G1 X-3.482783 Y10.087774 A-23.687615 F0.5316508378133167
  [  200] A: G1 X-3.482782730688342 Y10.08777395304591 A-23.68761503850749
        B: G1 X-3.670456 Y10.126698 A-23.687151 F0.5316508378133167
  [  201] A: Enable Aa
        B: G1 X-3.858129 Y10.165622 A-23.686687 F0.5316508378133167
  [  202] A: G91
        B: G1 X-4.045802 Y10.204546 A-23.686222 F0.5316508378133167
  [  203] A: BRAKE Aa 0
        B: G1 X-4.233475 Y10.24347 A-23.685758 F0.5348644299919595
  [  204] A: DWELL 0.08
        B: G1 X-4.421391 Y10.281099 A-23.684031 F0.5348644299919595
  [  205] A: G90
        B: G1 X-4.609306 Y10.318729 A-23.682304 F0.5348644299919595
  [  206] A: G1 X-3.482782730688342 Y10.08777395304591 A-23.68761503850749 F0.5316508378133167
        B: G1 X-4.797222 Y10.356358 A-23.680577 F0.5348644299919595
  [  207] A: G1 X-3.6704558208955076 Y10.126697907238732 A-23.687150789393762 F0.5316508378133167
        B: G1 X-4.985137 Y10.393988 A-23.678849 F0.5170514376017865
  [  208] A: G1 X-3.8581289111026735 Y10.165621861431555 A-23.68668654028003 F0.5316508378133167
        B: G1 X-5.173297 Y10.430286 A-23.675705 F0.5170514376017865
```

### science vs main
- counts=(2197,2033) aligned=False max_xyz_dev=33 max_f_dev=9.821 max_e_dev=0 out_of_tol=1838 byte_equal=False
- first divergences:

```
  [  189] A: Enable Aa
        B: G91
  [  190] A: G91
        B: G1 A0.5 F0.25
  [  191] A: DWELL 0.08
        B: G90
  [  192] A: BRAKE Aa 1
        B: G1 A22.878906016426214 F10
  [  193] A: G1 A0.5 F0.25
        B: G90
  [  194] A: G90
        B: G1 X-3.482783 Y10.087774
  [  195] A: G1 A22.878906016426214 F10
        B: G90
  [  196] A: G90
        B: G1 X-3.482783 Y10.087774 A-23.687615
  [  197] A: BRAKE Aa 1
        B: G91
  [  198] A: G1 X-3.482782730688342 Y10.08777395304591
        B: G90
  [  199] A: G90
        B: G1 X-3.482783 Y10.087774 A-23.687615 F0.531651
  [  200] A: G1 X-3.482782730688342 Y10.08777395304591 A-23.68761503850749
        B: G1 X-3.670456 Y10.126698 A-23.687151 F0.531651
  [  201] A: Enable Aa
        B: G1 X-3.858129 Y10.165622 A-23.686687 F0.531651
  [  202] A: G91
        B: G1 X-4.045802 Y10.204546 A-23.686222 F0.531651
  [  203] A: BRAKE Aa 0
        B: G1 X-4.233475 Y10.24347 A-23.685758 F0.534864
  [  204] A: DWELL 0.08
        B: G1 X-4.421391 Y10.281099 A-23.684031 F0.534864
  [  205] A: G90
        B: G1 X-4.609306 Y10.318729 A-23.682304 F0.534864
  [  206] A: G1 X-3.482782730688342 Y10.08777395304591 A-23.68761503850749 F0.5316508378133167
        B: G1 X-4.797222 Y10.356358 A-23.680577 F0.534864
  [  207] A: G1 X-3.6704558208955076 Y10.126697907238732 A-23.687150789393762 F0.5316508378133167
        B: G1 X-4.985137 Y10.393988 A-23.678849 F0.517051
  [  208] A: G1 X-3.8581289111026735 Y10.165621861431555 A-23.68668654028003 F0.5316508378133167
        B: G1 X-5.173297 Y10.430286 A-23.675705 F0.517051
```

### x1130 vs main
- counts=(2034,2033) aligned=True max_xyz_dev=0 max_f_dev=4.998e-07 max_e_dev=0 out_of_tol=0 byte_equal=False

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
