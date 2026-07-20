"""The checked-in host registrations must launch the memory MCP server through uv.

A bare ``python3`` cannot import the ``mcp`` package (it lives in the uv venv
only), so the server dies at startup and that host runs memory-blind -- no
resume, no decisions, no handoffs. install_global already registers with the
running interpreter for the same reason; these tests pin the source checkout's
own ``.mcp.json`` (Claude) and ``.gemini/settings.json`` (AGY) to the working
uv form.
"""

import json
import os
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestMemoryServerRegistrations(unittest.TestCase):
    def _server(self, relative_path):
        with open(os.path.join(REPO_ROOT, relative_path), encoding="utf-8") as fh:
            document = json.load(fh)
        return document["mcpServers"]["solomon-memory"]

    def assert_uv_launched(self, server):
        self.assertEqual(server["command"], "uv")
        self.assertIn("solomon_harness.mcp_server", server["args"])
        self.assertNotIn("python3", [server["command"], *server["args"]])

    def test_claude_registration_launches_via_uv(self):
        self.assert_uv_launched(self._server(".mcp.json"))

    def test_gemini_registration_launches_via_uv(self):
        self.assert_uv_launched(self._server(os.path.join(".gemini", "settings.json")))


if __name__ == "__main__":
    unittest.main()
