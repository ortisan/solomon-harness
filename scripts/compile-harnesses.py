#!/usr/bin/env python3
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.abspath(os.path.join(script_dir, ".."))
sys.path.insert(0, workspace_root)

from solomon_harness.compiler import compile_harnesses  # noqa: E402

if __name__ == "__main__":
    compile_harnesses(workspace_root)
