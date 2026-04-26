"""Run xcavate_Science.py with in-memory patches for known typo-class bugs.

The 2023-vintage Science.py crashes with `KeyError` on every verification
network. The errors are not in the algorithm itself — they're in the
diagnostic-logging branches that copy-pasted dict references and forgot
to rename them. This runner applies the minimum patches needed to get the
script past those crashes so the harness can produce a real Science vs
modern-pipeline comparison.

Each patch is a one-character fix that mirrors a correct analogous line a
few rows above. The original file at SCIENCE_SCRIPT is not modified.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCIENCE_SCRIPT = Path(
    "/Users/sohams/Downloads/Copy of Xcavate used for Science paper 2/xcavate_Science.py"
)


# Each tuple is (anchor_old, anchor_new). The anchor must be unique in the
# source so we can replace it without ambiguity.
_PATCHES = [
    # Line ~1781 in Branchpoint Condition #1 logging — uses
    # `append_first_branch[i]` inside a loop iterating `append_last_branch`.
    # When `i` exists in append_last_branch but not append_first_branch,
    # raises KeyError. The actual list mutation just above is correct;
    # only the log message is wrong.
    (
        'f.write(f\'\\nAppending node {append_first_branch[i]} to end of pass {i}.\')',
        'f.write(f\'\\nAppending node {append_last_branch[i]} to end of pass {i}.\')',
    ),
    # Line ~2127 in Branchpoint Condition #2 — comma INSIDE the filename
    # string rather than between filename and mode. Python implicit string
    # concatenation produces 'changelog.txt,a' (a single 14-char filename
    # with an embedded comma), then `open(...)` fails with FileNotFoundError.
    (
        "with open('changelog.txt,' 'a') as f:",
        "with open('changelog.txt', 'a') as f:",
    ),
]


def main() -> int:
    src = SCIENCE_SCRIPT.read_text()
    for old, new in _PATCHES:
        if old not in src:
            sys.stderr.write(
                f"science_runner: patch anchor not found:\n  {old!r}\n"
                "Upstream may have changed; verify the patch list.\n"
            )
            return 2
        src = src.replace(old, new, 1)
    sys.argv[0] = str(SCIENCE_SCRIPT)
    exec(compile(src, str(SCIENCE_SCRIPT), "exec"),
         {"__name__": "__main__", "__file__": str(SCIENCE_SCRIPT)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
