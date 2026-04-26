# Case `network_0_b_splines_500_vessels_1`

## Pipelines
### science — OK
- exit_code: `0`
- emitted: `gcode.txt`
- metrics: `moves=116873 g0=0 g1=79132 g4=0 path=50598.085 mm mm_trans=0 t_est=5400.16 s`

### x1130 — OK
- exit_code: `0`
- emitted: `gcode_SM_pressure.txt`
- metrics: `moves=96550 g0=0 g1=79132 g4=0 path=50598.085 mm mm_trans=0 t_est=5400.16 s`

### main — OK
- exit_code: `0`
- emitted: `gcode_SM_pressure.txt`
- metrics: `moves=96574 g0=0 g1=79145 g4=0 path=50567.487 mm mm_trans=0 t_est=5397.12 s`

## Pairwise diffs
### science vs x1130
- counts=(116873,96550) aligned=False max_xyz_dev=71.16 max_f_dev=62.9 max_e_dev=0 out_of_tol=94871 byte_equal=False
- first divergences:

```
  [   65] A: Enable Aa
        B: G91
  [   66] A: G91
        B: G1 A0.5 F0.25
  [   67] A: DWELL 0.08
        B: G90
  [   68] A: BRAKE Aa 1
        B: G1 A49.564105262501705 F10
  [   69] A: G1 A0.5 F0.25
        B: G90
  [   70] A: G90
        B: G1 X35.889242 Y35.768978
  [   71] A: G1 A49.564105262501705 F10
        B: G90
  [   72] A: G90
        B: G1 X35.889242 Y35.768978 A2.274714
  [   73] A: BRAKE Aa 1
        B: G91
  [   74] A: G1 X35.889242199537435 Y35.768977757993035
        B: G90
  [   75] A: G90
        B: G1 X35.889242 Y35.768978 A2.274714 F22.756731242858294
  [   76] A: G1 X35.889242199537435 Y35.768977757993035 A2.27471440850324
        B: G1 X35.826513 Y35.717991 A2.312792 F12.413094051272335
  [   77] A: Enable Aa
        B: G1 X35.714657 Y35.64947 A2.364329 F12.10437716371638
  [   78] A: G91
        B: G1 X35.589465 Y35.591435 A2.408415 F12.067154254216874
  [   79] A: BRAKE Aa 0
        B: G1 X35.454847 Y35.540253 A2.447692 F12.209427441401376
  [   80] A: DWELL 0.08
        B: G1 X35.314714 Y35.492289 A2.484805 F12.450012553336181
  [   81] A: G90
        B: G1 X35.172978 Y35.443912 A2.522394 F12.703924464284398
  [   82] A: G1 X35.889242199537435 Y35.768977757993035 A2.27471440850324 F22.756731242858294
        B: G1 X35.033469 Y35.391596 A2.563021 F12.878966845079269
  [   83] A: G1 X35.82651252843108 Y35.717991424089234 A2.312792428945343 F12.413094051272335
        B: G1 X34.898044 Y35.334522 A2.607198 F12.940192951664526
  [   84] A: G1 X35.71465712972674 Y35.64947028098938 A2.364328944383828 F12.10437716371638
        B: G1 X34.766491 Y35.274698 A2.653296 F12.921523994927163
```

### science vs main
- counts=(116873,96574) aligned=False max_xyz_dev=69.94 max_f_dev=62.9 max_e_dev=0 out_of_tol=94953 byte_equal=False
- first divergences:

```
  [   65] A: Enable Aa
        B: G91
  [   66] A: G91
        B: G1 A0.5 F0.25
  [   67] A: DWELL 0.08
        B: G90
  [   68] A: BRAKE Aa 1
        B: G1 A49.564105262501705 F10
  [   69] A: G1 A0.5 F0.25
        B: G90
  [   70] A: G90
        B: G1 X35.889242 Y35.768978
  [   71] A: G1 A49.564105262501705 F10
        B: G90
  [   72] A: G90
        B: G1 X35.889242 Y35.768978 A2.274714
  [   73] A: BRAKE Aa 1
        B: G91
  [   74] A: G1 X35.889242199537435 Y35.768977757993035
        B: G90
  [   75] A: G90
        B: G1 X35.889242 Y35.768978 A2.274714 F22.756731
  [   76] A: G1 X35.889242199537435 Y35.768977757993035 A2.27471440850324
        B: G1 X35.826513 Y35.717991 A2.312792 F12.413094
  [   77] A: Enable Aa
        B: G1 X35.714657 Y35.64947 A2.364329 F12.104377
  [   78] A: G91
        B: G1 X35.589465 Y35.591435 A2.408415 F12.067154
  [   79] A: BRAKE Aa 0
        B: G1 X35.454847 Y35.540253 A2.447692 F12.209427
  [   80] A: DWELL 0.08
        B: G1 X35.314714 Y35.492289 A2.484805 F12.450013
  [   81] A: G90
        B: G1 X35.172978 Y35.443912 A2.522394 F12.703924
  [   82] A: G1 X35.889242199537435 Y35.768977757993035 A2.27471440850324 F22.756731242858294
        B: G1 X35.033469 Y35.391596 A2.563021 F12.878967
  [   83] A: G1 X35.82651252843108 Y35.717991424089234 A2.312792428945343 F12.413094051272335
        B: G1 X34.898044 Y35.334522 A2.607198 F12.940193
  [   84] A: G1 X35.71465712972674 Y35.64947028098938 A2.364328944383828 F12.10437716371638
        B: G1 X34.766491 Y35.274698 A2.653296 F12.921524
```

### x1130 vs main
- counts=(96550,96574) aligned=False max_xyz_dev=70.19 max_f_dev=63.85 max_e_dev=0 out_of_tol=69748 byte_equal=False
- first divergences:

```
  [ 7304] A: G1 X40.045616 Y40.263232 A6.924149 F28.29062182150786
        B: G1 X39.917704 Y40.115127 A6.901902 F20.683359
  [21685] A: G1 X17.164225 Y41.17258 A11.046295 F38.504003623416494
        B: G91
  [21686] A: G91
        B: G1 A0.5 F0.25
  [21687] A: G1 A0.5 F0.25
        B: G90
  [21688] A: G90
        B: G1 A49.564105262501705 F10
  [21689] A: G1 A49.564105262501705 F10
        B: G90
  [21690] A: G90
        B: G1 X29.491473 Y63.210663
  [21691] A: G1 X29.491473 Y63.210663
        B: G90
  [21692] A: G90
        B: G1 X29.491473 Y63.210663 A11.013313
  [21693] A: G1 X29.491473 Y63.210663 A11.013313
        B: G91
  [21694] A: G91
        B: G90
  [21695] A: G90
        B: G1 X29.491473 Y63.210663 A11.013313 F19.82763
  [21696] A: G1 X29.491473 Y63.210663 A11.013313 F19.827629871106218
        B: G1 X29.551253 Y63.171703 A11.031261 F19.82763
  [21697] A: G1 X29.551253 Y63.171703 A11.031261 F19.827629871106218
        B: G1 X29.611272 Y63.133069 A11.049507 F19.82763
  [21698] A: G1 X29.611272 Y63.133069 A11.049507 F19.827629871106218
        B: G1 X29.671482 Y63.094694 A11.067991 F19.82763
  [21699] A: G1 X29.671482 Y63.094694 A11.067991 F19.827629871106218
        B: G1 X29.731834 Y63.056511 A11.08665 F19.82763
  [21700] A: G1 X29.731834 Y63.056511 A11.08665 F19.827629871106218
        B: G1 X29.792278 Y63.018454 A11.105425 F19.82763
  [21701] A: G1 X29.792278 Y63.018454 A11.105425 F19.827629871106218
        B: G1 X29.852766 Y62.980456 A11.124254 F19.82763
  [21702] A: G1 X29.852766 Y62.980456 A11.124254 F19.827629871106218
        B: G1 X29.913247 Y62.94245 A11.143075 F19.82763
  [21703] A: G1 X29.913247 Y62.94245 A11.143075 F19.827629871106218
        B: G1 X29.973674 Y62.904369 A11.161827 F19.82763
```

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
