"""Source hashes shared by the harness and the comparator.

The harness records them with each run; the comparator recomputes them and
refuses to compare artifacts produced from different sources.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files whose contents determine the pipeline outputs.
SOURCE_GLOBS = (
    "src/energy_budget/baseline.py",
    "src/energy_budget/bills.py",
    "src/energy_budget/budget_options.py",
    "src/energy_budget/config.py",
    "src/energy_budget/reforms/**/*.py",
    "validation/run_certified_pair.py",
    "validation/_provenance.py",
)


def source_hashes():
    files = sorted({p for g in SOURCE_GLOBS for p in ROOT.glob(g) if p.is_file()})
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
    }


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def sources_dirty():
    """True if any source file differs from the committed version. Generated
    outputs (``src/data``, ``validation/out_*``) do not count."""
    return bool(git("status", "--porcelain", "--", *SOURCE_GLOBS))
