"""When must a step run again?  Rule: if an output file is missing, or any input is newer than the oldest output.

Inputs are the data files the step reads AND the code files that define it, so editing a rule rebuilds what it
produced. The rule can only err on the safe side (an extra rebuild, never a stale result). `PIPELINE_FULL=1` forces
everything to rebuild.
"""
import os
from pathlib import Path


def full_refresh() -> bool:
    return os.environ.get("PIPELINE_FULL", "") == "1"


def is_stale(outputs: list[Path], inputs: list[Path]) -> bool:
    """True when the outputs must be rebuilt."""
    if full_refresh():
        return True
    if not outputs or any(not p.exists() for p in outputs):
        return True
    missing_inputs = [p for p in inputs if not p.exists()]
    if missing_inputs:
        raise FileNotFoundError(f"missing input(s): {[p.name for p in missing_inputs]}")
    oldest_output = min(p.stat().st_mtime_ns for p in outputs)
    return any(p.stat().st_mtime_ns > oldest_output for p in inputs)
