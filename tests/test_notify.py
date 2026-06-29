"""Tests for outbound-only notification egress (Phase 3)."""

import io
import json
import os
import tempfile
import unittest

from solomon_harness import notify
from solomon_harness.notify import ConsoleNotifier, WebhookNotifier


class TestAdapters(unittest.TestCase):
    def test_console_notifier_formats(self):
        buf = io.StringIO()
        ConsoleNotifier(stream=buf).send("stage:start", "issue 42 advanced")
        self.assertEqual(buf.getvalue().strip(), "[solomon:stage:start] issue 42 advanced")

    def test_webhook_notifier_posts_json(self):
        captured = {}

        def fake_opener(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            captured["method"] = req.get_method()

        WebhookNotifier("https://hooks.example/abc", opener=fake_opener).send("pr", "PR 31 awaiting review")
        self.assertEqual(captured["url"], "https://hooks.example/abc")
        self.assertEqual(captured["method"], "POST")
        self.assertIn("PR 31 awaiting review", captured["body"]["text"])

    def test_webhook_send_rejects_non_http_scheme(self):
        opened = []
        n = WebhookNotifier("file:///etc/passwd", opener=lambda req, timeout=None: opened.append(req))
        with self.assertRaises(ValueError):
            n.send("e", "m")
        self.assertEqual(opened, [])  # never opened the non-http URL


class TestSelection(unittest.TestCase):
    def _root(self, notify_block=None):
        root = tempfile.mkdtemp()
        if notify_block is not None:
            os.makedirs(os.path.join(root, ".agent"))
            with open(os.path.join(root, ".agent", "config.json"), "w", encoding="utf-8") as f:
                json.dump({"notify": notify_block}, f)
        return root

    def test_default_is_noop(self):
        self.assertIsNone(notify.get_notifier(self._root(), env={}))

    def test_get_notifier_rejects_non_http_url(self):
        self.assertIsNone(notify.get_notifier(self._root(), env={"SOLOMON_NOTIFY_WEBHOOK": "file:///etc/passwd"}))

    def test_webhook_from_env(self):
        n = notify.get_notifier(self._root(), env={"SOLOMON_NOTIFY_WEBHOOK": "https://h/x"})
        self.assertIsInstance(n, WebhookNotifier)

    def test_console_from_config(self):
        n = notify.get_notifier(self._root({"mode": "console"}), env={})
        self.assertIsInstance(n, ConsoleNotifier)

    def test_disabled_config_is_noop(self):
        root = self._root({"enabled": False})
        self.assertIsNone(notify.get_notifier(root, env={"SOLOMON_NOTIFY_WEBHOOK": "https://h/x"}))

    def test_send_is_best_effort(self):
        root = self._root()
        self.assertFalse(notify.send(root, "e", "m", env={}))  # no notifier -> False, no raise

        class _Boom:
            def send(self, event, message):
                raise RuntimeError("network down")

        from unittest import mock

        with mock.patch.object(notify, "get_notifier", return_value=_Boom()):
            self.assertFalse(notify.send(root, "e", "m"))  # a failing notifier is swallowed


if __name__ == "__main__":
    unittest.main()
