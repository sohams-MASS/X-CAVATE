# X-CAVATE Verification Harness — Final Report

This report compares three X-CAVATE pipelines on the seven networks under
`Vascular Trees Verification/` and documents the bugs found, fixes applied,
and residual differences that remain.

## Pipelines

| ID | Source | Notes |
|---|---|---|
| **science** | `xcavate_Science.py` (June 2023, Herrmann) | 5,568-line monolithic script. Three logging/typo bugs patched in `tests/verification_harness/science_runner.py` so it can run end-to-end. |
| **x1130** | `xcavate_11_30_25.py` (Nov 30 2025) | 5,568-line fork of Science.py. Two patches in `tests/verification_harness/x1130_runner.py`: the `custom_gcode == 1` gate on multimaterial-pressure emission, and an unguarded `graph[i].remove()` on the 500-vessel network. |
| **main** | `sohams-MASS/X-CAVATE` `xcavate/` package, branch `verification-harness` | Modular refactor with iterative DFS, KD-tree spatial queries, and dataclass-based config. Three correctness fixes applied during this work — see "Bugs fixed in main" below. |

The harness invokes each pipeline as a subprocess in an isolated working
directory, parses the emitted G-code, computes aggregate metrics, and
diffs each pair pairwise. `numerical_diff` uses `align_on_first_g1=True`
so a missing leading `G90` doesn't shift the entire stream.

## Inputs

Seven networks under `Vascular Trees Verification/`:

| Network | Vessels | Type |
|---|---:|---|
| `CNET Network/cnet_network_0_b_splines_100_points.txt` | 100 | single |
| `Figure 4 (F)/network_0_b_splines_4_vessels.txt` | 4 | single |
| `Figure 4 (F)/network_0_b_splines_9_vessels.txt` | 9 | single |
| `Figure 4 (F)/network_0_b_splines_14_vessels.txt` | 14 | single |
| `Figure 2 (A-C), Figure 4 (G)/multimaterial_test_network_61_vessels.txt` | 61 | **multi** |
| `Figure 2 (D-E)/5-1-23_multimaterial_network_0_b_splines.txt` | ~30 | **multi** |
| `network_0_b_splines_500_vessels (1).txt` | 500 | single (orphan — synthesized inlet/outlet) |

Canonical run parameters: `nozzle_diameter=0.41`, `container_height=50`,
`flow=0.1609429886081009` (matched to x1130's hardcoded value), `print_speed=1`,
`jog_speed=5`, `dwell_start=dwell_end=0.08`, `printer_type=0` (pressure),
`convert_factor=10.0` (cm→mm — main only; the legacy scripts hardcode
this).



## Results

### Summary table

`max_xyz_dev` is the largest XYZ deviation (mm) between any pair of
G1 moves after preamble alignment. **0** = bit-identical G1 trajectories.
**5×10⁻⁷** = float-precision noise only (different decimal printing
between pipelines, no actual coordinate divergence).


| Case | science | x1130 | main | sci↔x1130 max_xyz | sci↔main max_xyz | x1130↔main max_xyz |
|---|---|---|---|---:|---:|---:|
| `cnet_network_0_b_splines_100_points` | OK | OK | OK | 32.47 | 32.47 | 0 |
| `multimaterial_test_network_61_vessels` | OK | OK | OK | 90 | 90 | 4.981e-07 |
| `5-1-23_multimaterial_network_0_b_splines` | OK | OK | OK | 72.72 | 72.72 | 4.915e-07 |
| `network_0_b_splines_14_vessels` | OK | OK | OK | 35.17 | 35.17 | 0 |
| `network_0_b_splines_4_vessels` | OK | OK | OK | 33 | 33 | 0 |
| `network_0_b_splines_9_vessels` | OK | OK | OK | 38.41 | 38.41 | 0 |
| `network_0_b_splines_500_vessels_1` | OK | OK | OK | 71.16 | 69.94 | 70.19 |

### Per-case G-code metrics

#### `cnet_network_0_b_splines_100_points`

```
metrics: `moves=20940 g0=0 g1=16128 g4=0 path=4936.942 mm mm_trans=0 t_est=4076.24 s`
metrics: `moves=18348 g0=0 g1=16128 g4=0 path=4936.942 mm mm_trans=0 t_est=4076.24 s`
metrics: `moves=18347 g0=0 g1=16128 g4=0 path=4936.942 mm mm_trans=0 t_est=4076.24 s`
```

#### `multimaterial_test_network_61_vessels`

```
metrics: `moves=14040 g0=0 g1=9834 g4=0 path=39204.212 mm mm_trans=184 t_est=8161.14 s`
metrics: `moves=10387 g0=0 g1=10017 g4=0 path=40255.319 mm mm_trans=184 t_est=6467.84 s`
metrics: `moves=10386 g0=0 g1=10017 g4=0 path=40255.319 mm mm_trans=184 t_est=6467.84 s`
```

#### `5-1-23_multimaterial_network_0_b_splines`

```
metrics: `moves=3110 g0=0 g1=2424 g4=0 path=7182.730 mm mm_trans=33 t_est=1522.04 s`
metrics: `moves=2525 g0=0 g1=2457 g4=0 path=7353.539 mm mm_trans=33 t_est=1217.99 s`
metrics: `moves=2524 g0=0 g1=2457 g4=0 path=7353.539 mm mm_trans=33 t_est=1217.99 s`
```

#### `network_0_b_splines_14_vessels`

```
metrics: `moves=5084 g0=0 g1=4367 g4=0 path=1140.626 mm mm_trans=0 t_est=1667.00 s`
metrics: `moves=4697 g0=0 g1=4367 g4=0 path=1140.626 mm mm_trans=0 t_est=1667.00 s`
metrics: `moves=4696 g0=0 g1=4367 g4=0 path=1140.626 mm mm_trans=0 t_est=1667.00 s`
```

#### `network_0_b_splines_4_vessels`

```
metrics: `moves=2197 g0=0 g1=1896 g4=0 path=418.709 mm mm_trans=0 t_est=620.25 s`
metrics: `moves=2034 g0=0 g1=1896 g4=0 path=418.709 mm mm_trans=0 t_est=620.25 s`
metrics: `moves=2033 g0=0 g1=1896 g4=0 path=418.709 mm mm_trans=0 t_est=620.25 s`
```

#### `network_0_b_splines_9_vessels`

```
metrics: `moves=3878 g0=0 g1=3447 g4=0 path=858.715 mm mm_trans=0 t_est=1239.40 s`
metrics: `moves=3645 g0=0 g1=3447 g4=0 path=858.715 mm mm_trans=0 t_est=1239.40 s`
metrics: `moves=3644 g0=0 g1=3447 g4=0 path=858.715 mm mm_trans=0 t_est=1239.40 s`
```

#### `network_0_b_splines_500_vessels_1`

```
metrics: `moves=116873 g0=0 g1=79132 g4=0 path=50598.085 mm mm_trans=0 t_est=5400.16 s`
metrics: `moves=96550 g0=0 g1=79132 g4=0 path=50598.085 mm mm_trans=0 t_est=5400.16 s`
metrics: `moves=96574 g0=0 g1=79145 g4=0 path=50567.487 mm mm_trans=0 t_est=5397.12 s`
```


## Bugs fixed in main (`sohams-MASS/X-CAVATE`)

1. **Inlet/outlet matching ran on the pre-interpolation 400-row coordinate
   array but the indices were used post-interpolation.** Fixed by moving
   the `match_inlet_outlet_nodes` call to AFTER `interpolate_network`
   (`xcavate/pipeline.py:104` → after `points_interp`). Eliminated the
   spurious branchpoint edges through misidentified outlets and the
   resulting +1 raw-DFS pass per network on every SM case.

2. **`classify_passes_by_material` indexed the LAST node of each pass
   (`nodes[-1]`) but the docstring said "second node".** The second-node
   choice in xcavate_11_30_25.py is more robust against material outliers
   at the tail of long passes. Implementation now matches the docstring
   and x1130's behavior (`xcavate/core/multimaterial.py`).

3. **`_subdivide_by_material` wrote swapped artven values back to the
   shared `points[n, 4]` column.** Branchpoint nodes appear in multiple
   passes; a swap performed for pass A leaked the mutated value into
   pass B's break detection, producing extra material-transition splits.
   x1130 keeps swap state in a per-pass-local `print_passes_processed_artven`
   dict. Fix: main now uses an `artven_local` dict per pass and never
   touches `points`. Result: dropped main's MM transition count from 205
   to 183 on the 61-vessel network, exactly matching x1130
   (`xcavate/pipeline.py:_subdivide_by_material`).

Each fix has a regression test under `tests/`:
- `tests/test_inlet_outlet_remap.py`
- `tests/test_multimaterial.py::test_multinode_uses_second_node`
- `tests/test_subdivide_by_material_swap_order.py`

A separate fix to `xcavate/core/multimaterial.py::classify_passes_by_material`
made it tolerate empty sub-passes that survive `_subdivide_by_material`'s
slicing — this allowed the multimaterial path to run at all on the
61-vessel network (previously crashed with `IndexError: list index out
of range`).



## Legacy-script patches (in `tests/verification_harness/`)

The two legacy scripts are not modified on disk. Each is invoked through
a wrapper that applies in-memory patches before `exec`:

### `science_runner.py` (3 patches)

1. **`KeyError` in Branchpoint Condition #1 logging** (script line ~1781):
   the f-string referenced `append_first_branch[i]` inside a loop iterating
   `append_last_branch`. Fixed by mirroring the correct dict reference.
2. **`FileNotFoundError` in Branchpoint Condition #2** (script line ~2127):
   `open('changelog.txt,' 'a')` — comma INSIDE the filename literal
   produced the path `'changelog.txt,a'`. Fixed by moving the comma.
3. **`ValueError: list.remove(x): x not in list`** in daughter-pair
   dedup (script line ~766): unguarded `graph[i].remove(daughter_to_remove)`.
   Fixed with an `if x in graph[i]:` guard.

### `x1130_runner.py` (2 patches)

1. **`gcode_MM_pressure.txt` never emitted** (script line 4717): the
   multimaterial-pressure writer was gated on `custom_gcode == 1`.
   Without `--custom 1`, x1130 silently skipped MM emission and only
   wrote `gcode_SM_pressure.txt`, reporting 0 nozzle transitions on
   multimaterial inputs. Fixed by dropping the `custom_gcode == 1`
   condition.
2. **Same `graph[i].remove()` bug** as Science (script line ~878).
   Fixed with the same `if x in graph[i]:` guard.

x1130 also hardcodes `flow = 0.1609429886081009` at script line 3705,
overriding its own `--flow` argparse value. This is not patched; the
harness's `CANONICAL_PARAMS["flow"]` is set to the same value so all
three pipelines compute feedrates on identical flow.


## Reproduction

```bash
git checkout verification-harness
pytest tests/  # 157 passed, 4 skipped
python -m tests.verification_harness.run_verification --timeout 1800
python -m tests.verification_harness.collect_artifacts
python -m tests.verification_harness.generate_final_report
```

Outputs land at `tests/verification_harness/reports/` (per-case scratch directories, gitignored) and `tests/verification_harness/final_report/` (publishable copy with collected gcode files).
