"""Run xcavate_11_30_25.py with one in-memory patch.

The Nov 30 2025 script gates its multimaterial-pressure G-code emission on
`custom_gcode == 1`, so without a `--custom 1` flag (and the auxiliary
`inputs/custom/*.txt` template files it then reads) it silently skips the
multimaterial writer and only emits ``gcode_SM_pressure.txt``. Result: the
verification harness saw zero printhead transitions on multimaterial inputs.

This wrapper rewrites the gating line to drop the ``custom_gcode == 1``
requirement and execs the patched source as ``__main__``. The original
file at ``X1130_SCRIPT`` is left untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

X1130_SCRIPT = Path(
    "/Users/sohams/X-CAVATE/.claude/worktrees/serene-proskuriakova/xcavate_11_30_25.py"
)

_OLD = "if multimaterial == 1 and custom_gcode == 1 and printer_type == 0:"
_NEW = "if multimaterial == 1 and printer_type == 0:"


def main() -> int:
    src = X1130_SCRIPT.read_text()
    if _OLD not in src:
        sys.stderr.write(
            f"x1130_runner: patch anchor not found in {X1130_SCRIPT}\n"
            "The upstream script may have been updated; verify the patch.\n"
        )
        return 2
    patched = src.replace(_OLD, _NEW, 1)
    # Drop our own argv[0]; the patched script reads sys.argv[1:] via argparse.
    sys.argv[0] = str(X1130_SCRIPT)
    exec(compile(patched, str(X1130_SCRIPT), "exec"),
         {"__name__": "__main__", "__file__": str(X1130_SCRIPT)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
