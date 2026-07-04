import json
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, create_autospec, patch

from solomon_harness import github
from solomon_harness.tools.database_client import DatabaseClient


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestGhWrapper(unittest.TestCase):
    def test_gh_missing_is_handled(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            res = github._gh(["repo", "view"])
        self.assertFalse(res["ok"])
        self.assertIn("gh CLI not found", res["error"])

    def test_gh_nonzero_returns_error(self):
        with patch("subprocess.run", return_value=_Proc(1, "", "boom")):
            res = github._gh(["repo", "view"])
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "boom")

    def test_gh_parses_json(self):
        with patch("subprocess.run", return_value=_Proc(0, '{"a": 1}')):
            res = github._gh(["x"], parse_json=True)
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"], {"a": 1})

    def test_gh_bounds_every_call_with_a_timeout(self):
        """Every gh invocation passes a timeout so a hung gh cannot block a caller."""
        captured = {}

        def fake_run(cmd, **kwargs):
            captured.update(kwargs)
            return _Proc(0, "{}")

        with patch("subprocess.run", side_effect=fake_run):
            github._gh(["repo", "view"], parse_json=True)
        self.assertEqual(captured.get("timeout"), github.GH_TIMEOUT_SECONDS)

    def test_gh_timeout_is_handled_as_a_failed_call(self):
        """A gh subprocess that exceeds the timeout is treated as a failed call:
        _gh returns the ok:False shape and never raises."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["gh"], timeout=15),
        ):
            res = github._gh(["issue", "view", "7"])
        self.assertFalse(res["ok"])
        self.assertIn("error", res)


class TestGhRetry(unittest.TestCase):
    """_gh retries once on a transient failure (a non-zero exit or a timeout) and
    heals a credential blip on the retry by injecting a freshly resolved token. A
    deterministic failure (gh missing, or a JSON parse error after a success) is
    never retried."""

    def test_transient_nonzero_then_success_retries_and_succeeds(self):
        """A first call that exits non-zero is retried once; a succeeding retry makes
        _gh return ok. With a token already in the env the heal injection is skipped,
        so exactly two subprocess.run calls occur (no `gh auth token`)."""
        results = [_Proc(1, "", "Bad credentials"), _Proc(0, "ok")]

        def fake_run(cmd, **kwargs):
            return results.pop(0)

        with patch.dict("os.environ", {"GH_TOKEN": "preset"}, clear=False):
            with patch("subprocess.run", side_effect=fake_run) as run:
                res = github._gh(["project", "item-edit"])
        self.assertTrue(res["ok"])
        self.assertEqual(res["stdout"], "ok")
        self.assertEqual(run.call_count, 2)

    def test_retry_injects_freshly_resolved_token_when_env_has_none(self):
        """On the heal retry, with neither GITHUB_TOKEN nor GH_TOKEN in the env, _gh
        resolves a fresh token via `gh auth token` and passes it as GH_TOKEN in the
        env= of the retried gh call, healing a credential blip."""
        gh_args_envs = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["gh", "auth", "token"]:
                return _Proc(0, "healed-token-42")
            gh_args_envs.append(kwargs.get("env"))
            first_attempt = len(gh_args_envs) == 1
            return _Proc(1, "", "Bad credentials") if first_attempt else _Proc(0, "done")

        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run", side_effect=fake_run):
                res = github._gh(["project", "item-edit"])
        self.assertTrue(res["ok"])
        # The first attempt inherits the env; the retry carries the healed token.
        self.assertIsNone(gh_args_envs[0])
        self.assertIsNotNone(gh_args_envs[1])
        self.assertEqual(gh_args_envs[1].get("GH_TOKEN"), "healed-token-42")

    def test_retry_does_not_resolve_or_override_a_preset_token(self):
        """When GITHUB_TOKEN is already set, the heal retry neither calls
        `gh auth token` nor overrides the token: the retried call runs with the
        inherited env (env=None)."""
        seen = []
        results = [_Proc(1, "", "Bad credentials"), _Proc(0, "ok")]

        def fake_run(cmd, **kwargs):
            seen.append((cmd, kwargs.get("env")))
            return results.pop(0)

        with patch.dict("os.environ", {"GITHUB_TOKEN": "preset"}, clear=False):
            with patch("subprocess.run", side_effect=fake_run):
                res = github._gh(["project", "item-edit"])
        self.assertTrue(res["ok"])
        self.assertFalse(any(cmd[:3] == ["gh", "auth", "token"] for cmd, _env in seen))
        self.assertEqual(len(seen), 2)
        self.assertIsNone(seen[1][1])  # the retry inherits the env, no injection

    def test_retry_runs_without_injection_when_token_resolution_is_empty(self):
        """If `gh auth token` resolves nothing (empty output), the retry still runs as
        a plain network retry with no env override; a succeeding retry returns ok."""
        gh_args_envs = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["gh", "auth", "token"]:
                return _Proc(0, "")  # nothing resolved -> no injection
            gh_args_envs.append(kwargs.get("env"))
            first_attempt = len(gh_args_envs) == 1
            return _Proc(1, "", "Bad credentials") if first_attempt else _Proc(0, "done")

        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run", side_effect=fake_run):
                res = github._gh(["project", "item-edit"])
        self.assertTrue(res["ok"])
        self.assertIsNone(gh_args_envs[1])  # plain retry, no env override

    def test_successful_first_call_does_not_retry(self):
        """A first call that exits zero is not retried: exactly one subprocess.run."""
        with patch("subprocess.run", return_value=_Proc(0, "ok")) as run:
            res = github._gh(["repo", "view"])
        self.assertTrue(res["ok"])
        self.assertEqual(run.call_count, 1)

    def test_gh_missing_is_not_retried(self):
        """A missing gh (FileNotFoundError) is deterministic: it is not retried and
        returns the gh-not-found error after a single attempt."""
        with patch("subprocess.run", side_effect=FileNotFoundError()) as run:
            res = github._gh(["repo", "view"])
        self.assertFalse(res["ok"])
        self.assertIn("gh CLI not found", res["error"])
        self.assertEqual(run.call_count, 1)


class TestEnsureBoard(unittest.TestCase):
    def test_returns_existing_without_creating(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["gh", "repo", "view"]:
                return _Proc(0, json.dumps({"owner": {"login": "acme"}}))
            if cmd[:3] == ["gh", "project", "list"]:
                return _Proc(0, json.dumps({"projects": [{"title": "solomon", "number": 4}]}))
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_project_board()
        self.assertTrue(res["ok"])
        self.assertFalse(res["created"])
        self.assertEqual(res["project"]["number"], 4)
        self.assertFalse(any(c[:3] == ["gh", "project", "create"] for c in calls))

    def test_creates_when_absent(self):
        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["gh", "repo", "view"]:
                return _Proc(0, json.dumps({"owner": {"login": "acme"}}))
            if cmd[:3] == ["gh", "project", "list"]:
                return _Proc(0, json.dumps({"projects": []}))
            if cmd[:3] == ["gh", "project", "create"]:
                return _Proc(0, json.dumps({"number": 9, "title": "solomon"}))
            if cmd[:3] == ["gh", "project", "field-list"]:
                return _Proc(0, json.dumps({"fields": [{"name": "Status", "id": "F1", "options": [{"name": "Todo", "id": "o1"}]}]}))
            if cmd[:3] == ["gh", "api", "graphql"]:
                self._graphql_calls.append(cmd)
                return _Proc(0, "{}")
            raise AssertionError(f"unexpected gh call: {cmd}")

        self._graphql_calls = []
        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_project_board()
        self.assertTrue(res["ok"])
        self.assertTrue(res["created"])
        self.assertEqual(res["project"]["number"], 9)
        self.assertTrue(res["columns_configured"])
        # The create path must push every lifecycle column as a single-select option.
        self.assertEqual(len(self._graphql_calls), 1)
        mutation = self._graphql_calls[0][-1]
        for col in github.BOARD_COLUMNS:
            self.assertIn(f'name: "{col}"', mutation)


class TestEnsureBoardGuards(unittest.TestCase):
    """A failed or ambiguous project lookup must never mint a new board (bug #76).

    The duplicate 'solomon-harness' board was created when a transient gh failure
    made the lookup return empty and the find-or-create path treated 'could not
    list' as 'absent'. Once a duplicate exists, first-match resolution silently
    routes every transition to the newest board.
    """

    def test_listing_failure_refuses_to_create(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["gh", "auth", "token"]:
                return _Proc(0, "")
            if cmd[:3] == ["gh", "repo", "view"]:
                return _Proc(0, json.dumps({"owner": {"login": "acme"}}))
            if cmd[:3] == ["gh", "project", "list"]:
                return _Proc(1, "", "HTTP 401: Bad credentials")
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_project_board()
        self.assertFalse(res["ok"])
        self.assertIn("refusing to create", res["error"])
        self.assertFalse(any(c[:3] == ["gh", "project", "create"] for c in calls))

    def test_duplicate_titles_resolve_to_the_lowest_number(self):
        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["gh", "repo", "view"]:
                return _Proc(0, json.dumps({"owner": {"login": "acme"}}))
            if cmd[:3] == ["gh", "project", "list"]:
                # gh lists newest first; a stray duplicate must not shadow the
                # canonical (oldest) board.
                return _Proc(0, json.dumps({"projects": [
                    {"title": "solomon", "number": 16},
                    {"title": "solomon", "number": 5},
                ]}))
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_project_board()
        self.assertTrue(res["ok"])
        self.assertFalse(res["created"])
        self.assertEqual(res["project"]["number"], 5)

    def test_absent_board_without_create_does_not_create(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["gh", "repo", "view"]:
                return _Proc(0, json.dumps({"owner": {"login": "acme"}}))
            if cmd[:3] == ["gh", "project", "list"]:
                return _Proc(0, json.dumps({"projects": []}))
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_project_board(create=False)
        self.assertFalse(res["ok"])
        self.assertIn("ensure-board", res["error"])
        self.assertFalse(any(c[:3] == ["gh", "project", "create"] for c in calls))

    def test_add_issue_never_creates_a_board(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["gh", "repo", "view"]:
                return _Proc(0, json.dumps({"owner": {"login": "acme"}}))
            if cmd[:3] == ["gh", "project", "list"]:
                return _Proc(0, json.dumps({"projects": []}))
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.add_issue_to_board(7)
        self.assertFalse(res["ok"])
        self.assertFalse(any(c[:3] == ["gh", "project", "create"] for c in calls))


class TestConfigureBoardColumns(unittest.TestCase):
    def test_missing_project_number_is_handled(self):
        res = github._configure_board_columns("acme", None)
        self.assertFalse(res["ok"])

    def test_builds_mutation_with_all_columns(self):
        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["gh", "project", "field-list"]:
                return _Proc(0, json.dumps({"fields": [{"name": "Status", "id": "F1", "options": [{"name": "Todo", "id": "o1"}]}]}))
            if cmd[:3] == ["gh", "api", "graphql"]:
                return _Proc(0, "{}")
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            res = github._configure_board_columns("acme", 9)
        self.assertTrue(res["ok"])


class TestEnsureLabels(unittest.TestCase):
    def test_creates_every_standard_label(self):
        created = []

        def fake_run(cmd, **kwargs):
            self.assertEqual(cmd[:3], ["gh", "label", "create"])
            created.append(cmd[3])
            return _Proc(0, "")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_labels()
        self.assertTrue(res["ok"])
        self.assertEqual(created, [name for name, _c, _d in github.STANDARD_LABELS])

    def test_partial_failure_is_not_ok(self):
        def fake_run(cmd, **kwargs):
            if cmd[3] == "type:bug":
                return _Proc(1, "", "boom")
            return _Proc(0, "")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_labels()
        self.assertFalse(res["ok"])
        self.assertNotIn("type:bug", res["labels"])


class TestSetStatus(unittest.TestCase):
    def test_rejects_unknown_status(self):
        res = github.set_issue_status(1, "Nope")
        self.assertFalse(res["ok"])
        self.assertIn("unknown status", res["error"])

    def test_known_status_is_allowed(self):
        self.assertIn("Code Review", github.BOARD_COLUMNS)
        self.assertIn("QA", github.BOARD_COLUMNS)


class TestRecordTransition(unittest.TestCase):
    def test_appends_timeline_entry(self):
        import tempfile

        from solomon_harness.tools.database_client import DatabaseClient

        with tempfile.TemporaryDirectory() as tmp:
            with patch("os.getcwd", return_value=tmp):
                github.record_transition(7, "In Progress")
                github.record_transition(7, "Code Review")
                with DatabaseClient(harness_dir=tmp) as db:
                    raw = db.get_memory("board_history:7")
            history = json.loads(raw)
        self.assertEqual([h["column"] for h in history], ["In Progress", "Code Review"])
        self.assertTrue(all("entered_at" in h for h in history))

    def test_never_raises_on_failure(self):
        with patch("solomon_harness.tools.database_client.DatabaseClient", side_effect=RuntimeError):
            # Best-effort: a DB failure must not propagate.
            github.record_transition(1, "Done")


def _fake_db_cm(fake_db):
    """Wrap a fake DatabaseClient as the context manager record_terminal_status uses."""
    cm = MagicMock()
    cm.__enter__.return_value = fake_db
    cm.__exit__.return_value = False
    return cm


class TestRecordTerminalStatus(unittest.TestCase):
    # create_autospec(DatabaseClient) pins the real method signatures, so a drift
    # in the 5-arg log_issue contract fails these tests instead of passing silently
    # against a permissive bare MagicMock.
    def test_writes_one_closed_preserving_fields(self):
        """A non-terminal row is read then written once as closed, preserving the
        title, type, milestone and the already-captured assignee (read-modify-write
        through log_issue). An assignee already on the row is preserved without a
        fresh GitHub capture (the capture short-circuits)."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = {
            "github_id": "34",
            "title": "Deliver the thing",
            "type_": "bug",
            "status": "code_review",
            "milestone_id": "m1",
            "assignee": "alice@example.com",
        }
        with (
            patch("solomon_harness.github._gh") as gh,
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=_fake_db_cm(fake_db),
            ),
        ):
            github.record_terminal_status(34)
        fake_db.get_issue.assert_called_once_with("34")
        fake_db.log_issue.assert_called_once_with(
            "34", "Deliver the thing", "bug", "closed", "m1", assignee="alice@example.com"
        )
        gh.assert_not_called()  # an already-captured key is preserved, not re-fetched

    def test_already_terminal_row_triggers_no_write(self):
        """An already-terminal row is idempotent: no log_issue write occurs."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = {
            "github_id": "9",
            "title": "Done already",
            "type_": "feature",
            "status": "closed",
            "milestone_id": None,
        }
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            return_value=_fake_db_cm(fake_db),
        ):
            github.record_terminal_status(9)
        fake_db.log_issue.assert_not_called()

    def test_missing_row_triggers_no_write(self):
        """No memory row for the issue means nothing to repair (no row is created)."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = None
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            return_value=_fake_db_cm(fake_db),
        ):
            github.record_terminal_status(404)
        fake_db.log_issue.assert_not_called()

    def test_memory_error_is_swallowed_and_logged(self):
        """A raised memory error must never propagate out of the merge path, and the
        failure is logged at warning level (not silently swallowed). The log carries
        only the exception type, never its message, so a backend error string cannot
        leak store internals (STRIDE: information disclosure)."""
        # Constructor failure: caught, never raised, logged at warning.
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            side_effect=RuntimeError("backend down"),
        ):
            with self.assertLogs(level="WARNING") as cm:
                github.record_terminal_status(1)  # must not raise
        self.assertTrue(any("terminal write-through" in m for m in cm.output))

        # Write failure: log_issue is reached (the row is non-terminal), and its
        # error is caught, not raised, and logged at warning by exception type.
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = {
            "github_id": "2",
            "title": "T",
            "type_": "bug",
            "status": "in_progress",
            "milestone_id": None,
            "assignee": "gh:bob",
        }
        fake_db.log_issue.side_effect = RuntimeError("write failed")
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            return_value=_fake_db_cm(fake_db),
        ):
            with self.assertLogs(level="WARNING") as cm:
                github.record_terminal_status(2)  # must not raise
        fake_db.log_issue.assert_called_once()  # log_issue was reached
        joined = "\n".join(cm.output)
        self.assertIn("RuntimeError", joined)  # the exception type is logged
        self.assertNotIn("write failed", joined)  # the message is not


class TestCaptureIssueAssignee(unittest.TestCase):
    """capture_issue_assignee maps the first GitHub assignee to the person key and
    is best-effort: it never raises on the write-through path."""

    def test_capture_never_raises_on_gh_failure(self):
        """A failing gh call yields None (the unassigned key) and never raises, so a
        slow or failing GitHub never breaks the merge/write-through path."""
        with patch(
            "solomon_harness.github._gh",
            return_value={"ok": False, "error": "gh exploded"},
        ):
            self.assertIsNone(github.capture_issue_assignee(7))

    def test_capture_survives_a_gh_timeout(self):
        """A hung gh (TimeoutExpired) on the capture path yields None (unassigned)
        and never raises, so a slow GitHub cannot block the merge/write-through path.
        The timeout is absorbed by _gh as a failed call, so no warning is logged."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["gh"], timeout=15),
        ):
            self.assertIsNone(github.capture_issue_assignee(7))  # must not raise

    def test_malformed_assignee_warns_type_only_and_does_not_raise(self):
        """A failure while normalizing a malformed assignee is caught: capture
        returns None, logs a warning carrying the exception type only (never
        str(exc), which can leak internals), and never raises (STRIDE: information
        disclosure)."""
        gh_res = {"ok": True, "data": {"assignees": [{"login": "bob"}]}}
        with (
            patch("solomon_harness.github._gh", return_value=gh_res),
            patch(
                "solomon_harness.github.normalize_person_key",
                side_effect=RuntimeError("backend internals"),
            ),
        ):
            with self.assertLogs(level="WARNING") as cm:
                captured = github.capture_issue_assignee(7)  # must not raise
        self.assertIsNone(captured)
        joined = "\n".join(cm.output)
        self.assertIn("RuntimeError", joined)  # the exception type is logged
        self.assertNotIn("backend internals", joined)  # the message is not


class TestSyncCapturesAssignee(unittest.TestCase):
    """The terminal write-through captures the GitHub assignee fresh when the memory
    row has none, normalizing it on write into log_issue."""

    def _row(self, **overrides):
        row = {
            "github_id": "34",
            "title": "T",
            "type_": "bug",
            "status": "code_review",
            "milestone_id": "m1",
            "assignee": None,
        }
        row.update(overrides)
        return row

    def _record(self, issue_number, gh_res, fake_db):
        with (
            patch("solomon_harness.github._gh", return_value=gh_res),
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=_fake_db_cm(fake_db),
            ),
        ):
            github.record_terminal_status(issue_number)

    def test_sync_captures_email_assignee(self):
        """An email assignee is captured and the normalized email key is passed."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = self._row(github_id="34")
        gh_res = {
            "ok": True,
            "data": {"assignees": [{"login": "alice", "email": "Alice@Example.com"}]},
        }
        self._record(34, gh_res, fake_db)
        fake_db.log_issue.assert_called_once_with(
            "34", "T", "bug", "closed", "m1", assignee="alice@example.com"
        )

    def test_sync_unassigned_passes_null(self):
        """An empty assignees list passes assignee=None through log_issue."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = self._row(github_id="8", milestone_id=None)
        gh_res = {"ok": True, "data": {"assignees": []}}
        self._record(8, gh_res, fake_db)
        fake_db.log_issue.assert_called_once_with(
            "8", "T", "bug", "closed", None, assignee=None
        )

    def test_sync_captures_handle_only_assignee(self):
        """A handle-only assignee (email absent or private) becomes gh:<login>."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = self._row(github_id="9", milestone_id=None)
        gh_res = {"ok": True, "data": {"assignees": [{"login": "Bob"}]}}
        self._record(9, gh_res, fake_db)
        fake_db.log_issue.assert_called_once_with(
            "9", "T", "bug", "closed", None, assignee="gh:bob"
        )

    def test_only_person_key_persisted_not_profile(self):
        """Only the normalized key reaches log_issue: no name, avatar, or other
        profile field from the GitHub assignee is passed or stored (PII)."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = self._row(github_id="5", milestone_id=None)
        gh_res = {
            "ok": True,
            "data": {
                "assignees": [
                    {
                        "login": "alice",
                        "email": "alice@example.com",
                        "name": "Alice Anderson",
                        "avatarUrl": "https://example.com/a.png",
                    }
                ]
            },
        }
        self._record(5, gh_res, fake_db)
        args, kwargs = fake_db.log_issue.call_args
        self.assertEqual(kwargs.get("assignee"), "alice@example.com")
        # No profile field crosses into the store: only the key is passed.
        passed = repr(args) + repr(kwargs)
        self.assertNotIn("Alice Anderson", passed)
        self.assertNotIn("avatarUrl", passed)
        self.assertNotIn("example.com/a.png", passed)


class TestRecordTerminalStatusRealStore(unittest.TestCase):
    def test_persists_closed_against_a_real_store(self):
        """A real DatabaseClient (not a wholesale mock) is opened and exercises real
        backend selection: record_terminal_status reads the seeded row and persists
        status=closed, preserving the title, type and milestone. The seeded row has
        no assignee and GitHub returns none, so it stays unassigned. _gh is stubbed
        so the capture stays hermetic (no real subprocess)."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch("os.getcwd", return_value=tmp):
                with DatabaseClient(harness_dir=tmp) as db:
                    milestone_id = db.create_milestone(
                        "M1", "goals", "2026-07-01", "active"
                    )
                    db.log_issue(
                        "77", "Deliver feature", "feature", "code_review", milestone_id
                    )
                with patch(
                    "solomon_harness.github._gh",
                    return_value={"ok": True, "data": {"assignees": []}},
                ):
                    github.record_terminal_status(77)
                with DatabaseClient(harness_dir=tmp) as db:
                    row = db.get_issue("77")
                    open_ids = {i["github_id"] for i in db.get_open_issues()}
        self.assertEqual(row["status"], "closed")
        self.assertEqual(row["title"], "Deliver feature")
        self.assertEqual(row["type_"], "feature")
        self.assertEqual(str(row["milestone_id"]), str(milestone_id))
        self.assertIsNone(row["assignee"])
        self.assertNotIn("77", open_ids)


class TestSetStatusWriteThroughGate(unittest.TestCase):
    def test_done_transition_triggers_write_through(self):
        """The CLI set-status dispatch fires the terminal write-through only on Done,
        alongside the existing record_transition."""
        with (
            patch("solomon_harness.github.set_issue_status", return_value={"ok": True}),
            patch("solomon_harness.github.record_transition") as rt,
            patch("solomon_harness.github.record_terminal_status") as rts,
        ):
            rc = github.main(["set-status", "--issue", "5", "--status", "Done"])
        self.assertEqual(rc, 0)
        rt.assert_called_once_with(5, "Done")
        rts.assert_called_once_with(5)

    def test_non_done_transition_does_not_trigger_write_through(self):
        """A non-Done transition records the transition but never the terminal write."""
        with (
            patch("solomon_harness.github.set_issue_status", return_value={"ok": True}),
            patch("solomon_harness.github.record_transition") as rt,
            patch("solomon_harness.github.record_terminal_status") as rts,
        ):
            rc = github.main(["set-status", "--issue", "5", "--status", "Code Review"])
        self.assertEqual(rc, 0)
        rt.assert_called_once_with(5, "Code Review")
        rts.assert_not_called()


class TestBoardTitleAndLink(unittest.TestCase):
    def test_board_title_is_the_repo_name(self):
        def fake_run(cmd, **kwargs):
            if cmd[:4] == ["gh", "repo", "view", "--json"] and cmd[4] == "name":
                return _Proc(0, json.dumps({"name": "widget"}))
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            self.assertEqual(github.board_title(), "widget")

    def test_board_title_falls_back_when_repo_unknown(self):
        with patch("subprocess.run", return_value=_Proc(1, "", "no repo")):
            self.assertEqual(github.board_title(), "solomon")

    def test_create_links_board_to_repo(self):
        links = []

        def fake_run(cmd, **kwargs):
            if cmd[:4] == ["gh", "repo", "view", "--json"]:
                field = cmd[4]
                data = {
                    "owner": {"owner": {"login": "acme"}},
                    "name": {"name": "widget"},
                    "nameWithOwner": {"nameWithOwner": "acme/widget"},
                }[field]
                return _Proc(0, json.dumps(data))
            if cmd[:3] == ["gh", "project", "list"]:
                return _Proc(0, json.dumps({"projects": []}))
            if cmd[:3] == ["gh", "project", "create"]:
                return _Proc(0, json.dumps({"number": 9, "title": "widget"}))
            if cmd[:3] == ["gh", "project", "field-list"]:
                return _Proc(0, json.dumps({"fields": [{"name": "Status", "id": "F1", "options": [{"name": "Todo", "id": "o1"}]}]}))
            if cmd[:3] == ["gh", "api", "graphql"]:
                return _Proc(0, "{}")
            if cmd[:3] == ["gh", "project", "link"]:
                links.append(cmd)
                return _Proc(0, "")
            raise AssertionError(f"unexpected gh call: {cmd}")

        with patch("subprocess.run", side_effect=fake_run):
            res = github.ensure_project_board()
        self.assertTrue(res["created"])
        self.assertTrue(res["linked_to_repo"])
        # The board is titled after the repo and linked to it.
        self.assertEqual(res["project"]["title"], "widget")
        self.assertEqual(len(links), 1)
        self.assertIn("acme/widget", links[0])


if __name__ == "__main__":
    unittest.main()
