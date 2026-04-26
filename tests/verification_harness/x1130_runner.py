"""Run xcavate_11_30_25.py with in-memory patches for known issues.

Each patch fixes a script-level bug or limitation that prevents the
harness from getting comparable g-code output. The original file at
``X1130_SCRIPT`` is left untouched; patches are applied at exec time.
"""
from __future__ import annotations

import sys
from pathlib import Path

X1130_SCRIPT = Path(__file__).parent / "legacy_scripts" / "xcavate_11_30_25.py"

_PATCHES = [
    # Line 4717: drops the `custom_gcode == 1` requirement on the
    # multimaterial-pressure G-code writer so it actually emits
    # gcode_MM_pressure.txt under our `--custom 0` invocation.
    (
        "if multimaterial == 1 and custom_gcode == 1 and printer_type == 0:",
        "if multimaterial == 1 and printer_type == 0:",
    ),
    # Line ~878: graph-wiring step removes the "other daughter" from the
    # current daughter's neighbour list, but doesn't check whether that
    # edge actually exists. On the 500-vessel network this raises
    # `ValueError: list.remove(x): x not in list`. Guard with `if in`.
    (
        "      if j != i:\n"
        "        daughter_to_remove = j\n"
        "        graph[i].remove(daughter_to_remove)",
        "      if j != i:\n"
        "        daughter_to_remove = j\n"
        "        if daughter_to_remove in graph[i]:\n"
        "          graph[i].remove(daughter_to_remove)",
    ),
]


def main() -> int:
    src = X1130_SCRIPT.read_text()
    for old, new in _PATCHES:
        if old not in src:
            sys.stderr.write(
                f"x1130_runner: patch anchor not found:\n  {old!r}\n"
                f"in {X1130_SCRIPT}\nUpstream may have changed; verify the patch.\n"
            )
            return 2
        src = src.replace(old, new, 1)
    # Drop our own argv[0]; the patched script reads sys.argv[1:] via argparse.
    sys.argv[0] = str(X1130_SCRIPT)
    exec(compile(src, str(X1130_SCRIPT), "exec"),
         {"__name__": "__main__", "__file__": str(X1130_SCRIPT)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
