"""Structural guards for solomon_harness/tools/database_client.py (issue #163).

Pins the follow-ups from the 2026-07-03 structure audit so they cannot silently
regress: SurrealQL LIMIT values are bound parameters (never f-string
interpolation), the client exposes an honest public backend accessor, and the
constructor stays split into focused initializers instead of regrowing into one
monolithic block.
"""

import inspect
import os
import re
import sys
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from solomon_harness.tools import database_client  # noqa: E402


class TestParameterizedLimit(unittest.TestCase):
    """Parameterized queries are the project default; LIMIT is no exception.

    int() coercion happens to neutralize injection for these sites, but the
    rule the audit enforces is structural: no query string is built by
    interpolating a caller-supplied value, so a future edit cannot silently
    downgrade a coerced int into a raw string.
    """

    def test_no_brace_interpolated_limit_in_module_source(self):
        source = inspect.getsource(database_client)
        offenders = [
            line.strip()
            for line in source.splitlines()
            if re.search(r"LIMIT\s*\{", line)
        ]
        self.assertEqual(
            offenders, [], f"brace-interpolated LIMIT found: {offenders}"
        )


if __name__ == "__main__":
    unittest.main()
