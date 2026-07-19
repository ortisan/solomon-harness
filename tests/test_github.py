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

    def test_gh_preserves_explicit_context_across_a_healed_retry(self):
        """Repository-scoped callers keep their cwd and scrubbed environment on
        both attempts, including when the retry injects a healed token."""
        safe_env = {"PATH": "/usr/bin", "GIT_TERMINAL_PROMPT": "0"}
        gh_calls = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["gh", "auth", "token"]:
                self.assertEqual(kwargs.get("cwd"), "/safe/worktree")
                self.assertEqual(kwargs.get("env"), safe_env)
                return _Proc(0, "healed-token-42")
            gh_calls.append(kwargs)
            if len(gh_calls) == 1:
                return _Proc(1, "", "Bad credentials")
            return _Proc(0, "done")

        with patch.dict(
            "os.environ",
            {"GIT_DIR": "/wrong/repo", "GH_REPO": "attacker/other"},
            clear=True,
        ):
            with patch("subprocess.run", side_effect=fake_run):
                result = github._gh(
                    ["issue", "edit", "99"],
                    cwd="/safe/worktree",
                    env=safe_env,
                )

        self.assertTrue(result["ok"])
        self.assertEqual(len(gh_calls), 2)
        self.assertEqual(gh_calls[0]["cwd"], "/safe/worktree")
        self.assertEqual(gh_calls[0]["env"], safe_env)
        self.assertEqual(gh_calls[1]["cwd"], "/safe/worktree")
        self.assertEqual(gh_calls[1]["env"]["GH_TOKEN"], "healed-token-42")
        self.assertNotIn("GIT_DIR", gh_calls[1]["env"])
        self.assertNotIn("GH_REPO", gh_calls[1]["env"])

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
        # The first attempt runs with the scrubbed default env (no token); the
        # retry carries the healed token.
        self.assertNotIn("GH_TOKEN", gh_args_envs[0])
        self.assertEqual(gh_args_envs[1].get("GH_TOKEN"), "healed-token-42")

    def test_retry_does_not_resolve_or_override_a_preset_token(self):
        """When GITHUB_TOKEN is already set, the heal retry neither calls
        `gh auth token` nor overrides the token: the retried call keeps the preset
        token in the scrubbed env, with no GH_TOKEN injection."""
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
        self.assertEqual(seen[1][1].get("GITHUB_TOKEN"), "preset")
        self.assertNotIn("GH_TOKEN", seen[1][1])

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
        self.assertNotIn("GH_TOKEN", gh_args_envs[1])  # plain retry, no injection

    def test_gh_call_strips_git_env(self):
        """Every gh call runs with GIT_* stripped so a leaked GIT_DIR/GIT_WORK_TREE
        cannot redirect gh to an enclosing repository (Refs #251)."""
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["env"] = kwargs.get("env")
            return _Proc(0, "ok")

        with patch.dict(
            "os.environ",
            {"GIT_DIR": "/enclosing/.git", "GIT_WORK_TREE": "/enclosing"},
            clear=False,
        ):
            with patch("subprocess.run", side_effect=fake_run):
                github._gh(["repo", "view"])
        self.assertIsNotNone(seen["env"])
        self.assertNotIn("GIT_DIR", seen["env"])
        self.assertNotIn("GIT_WORK_TREE", seen["env"])

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
        self.assertTrue(any("status write-through" in m for m in cm.output))

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


class TestRecordStatusWriteThrough(unittest.TestCase):
    """Every board transition — not only Done — writes its canonical token through
    to the issue row, so code_review and qa are reachable states (ADR-0033 amending
    ADR-0006 decision point 2). record_terminal_status stays the Done-shaped alias
    the merge path (ADR-0020) calls.
    """

    def _row(self, status="in_progress"):
        return {
            "github_id": "34",
            "title": "Deliver the thing",
            "type_": "bug",
            "status": status,
            "milestone_id": "m1",
            "assignee": "alice@example.com",
        }

    def test_code_review_column_writes_canonical_token(self):
        """The Code Review display column is stored as the canonical code_review
        token, preserving title/type/milestone/assignee (AC1)."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = self._row()
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            return_value=_fake_db_cm(fake_db),
        ):
            github.record_status_write_through(34, "Code Review")
        fake_db.log_issue.assert_called_once_with(
            "34", "Deliver the thing", "bug", "code_review", "m1", assignee="alice@example.com"
        )

    def test_qa_column_writes_canonical_token(self):
        """The QA display column is stored as the canonical qa token (AC1)."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = self._row()
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            return_value=_fake_db_cm(fake_db),
        ):
            github.record_status_write_through(34, "QA")
        fake_db.log_issue.assert_called_once_with(
            "34", "Deliver the thing", "bug", "qa", "m1", assignee="alice@example.com"
        )

    def test_done_column_still_writes_closed(self):
        """The ADR-0006 Done path is unchanged: Done normalizes to closed."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = self._row(status="code_review")
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            return_value=_fake_db_cm(fake_db),
        ):
            github.record_status_write_through(34, "Done")
        fake_db.log_issue.assert_called_once_with(
            "34", "Deliver the thing", "bug", "closed", "m1", assignee="alice@example.com"
        )

    def test_non_terminal_transition_does_not_capture_missing_assignee(self):
        """Only delivery may query GitHub for a missing assignee.

        Earlier board transitions preserve a missing value without adding a new
        ``gh issue view`` call to the status write-through path (ADR-0033).
        """
        fake_db = create_autospec(DatabaseClient, instance=True)
        row = self._row()
        row["assignee"] = None
        fake_db.get_issue.return_value = row
        with (
            patch(
                "solomon_harness.tools.database_client.DatabaseClient",
                return_value=_fake_db_cm(fake_db),
            ),
            patch("solomon_harness.github.capture_issue_assignee") as capture,
        ):
            github.record_status_write_through(34, "Code Review")
        capture.assert_not_called()
        fake_db.log_issue.assert_called_once_with(
            "34", "Deliver the thing", "bug", "code_review", "m1", assignee=None
        )

    def test_terminal_row_is_never_resurrected_by_a_backwards_transition(self):
        """A delivered row stays closed even if its card is dragged back to an
        earlier column: the is_terminal short-circuit is what stops a board edit
        from un-delivering an issue in memory."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = self._row(status="closed")
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            return_value=_fake_db_cm(fake_db),
        ):
            github.record_status_write_through(34, "Code Review")
        fake_db.log_issue.assert_not_called()

    def test_unchanged_status_triggers_no_write(self):
        """Re-applying the column a row already holds writes nothing (idempotent)."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = self._row(status="code_review")
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            return_value=_fake_db_cm(fake_db),
        ):
            github.record_status_write_through(34, "Code Review")
        fake_db.log_issue.assert_not_called()

    def test_missing_row_triggers_no_write(self):
        """No memory row means nothing to update; no row is invented."""
        fake_db = create_autospec(DatabaseClient, instance=True)
        fake_db.get_issue.return_value = None
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            return_value=_fake_db_cm(fake_db),
        ):
            github.record_status_write_through(404, "QA")
        fake_db.log_issue.assert_not_called()

    def test_backend_failure_never_raises_and_logs_type_only(self):
        """Best-effort holds for every column, not just Done: a backend failure is
        caught and logged by exception type, never str(exc) (STRIDE: information
        disclosure), so a board move never fails on a memory outage."""
        with patch(
            "solomon_harness.tools.database_client.DatabaseClient",
            side_effect=RuntimeError("backend down"),
        ):
            with self.assertLogs(level="WARNING") as cm:
                github.record_status_write_through(1, "Code Review")  # must not raise
        joined = "\n".join(cm.output)
        self.assertIn("RuntimeError", joined)
        self.assertNotIn("backend down", joined)


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
    """The dispatch is the single seam every caller funnels through, so ungating it
    here (ADR-0033) is what makes code_review/qa reachable for start, review, and any
    future caller — no command markdown file needs its own log_issue call.
    """

    def test_done_transition_triggers_write_through(self):
        """The Done transition still writes through, alongside record_transition."""
        with (
            patch("solomon_harness.github.set_issue_status", return_value={"ok": True}),
            patch("solomon_harness.github.record_transition") as rt,
            patch("solomon_harness.github.record_status_write_through") as rsw,
        ):
            rc = github.main(["set-status", "--issue", "5", "--status", "Done"])
        self.assertEqual(rc, 0)
        rt.assert_called_once_with(5, "Done")
        rsw.assert_called_once_with(5, "Done")

    def test_non_done_transition_also_triggers_write_through(self):
        """Supersedes the pre-ADR-0033 assertion that a non-Done transition must NOT
        write through — that gate is exactly what made code_review/qa unreachable
        (#173). Every column now writes its canonical token to the issue row."""
        for column in ("In Progress", "Code Review", "QA"):
            with self.subTest(column=column):
                with (
                    patch("solomon_harness.github.set_issue_status", return_value={"ok": True}),
                    patch("solomon_harness.github.record_transition") as rt,
                    patch("solomon_harness.github.record_status_write_through") as rsw,
                ):
                    rc = github.main(["set-status", "--issue", "5", "--status", column])
                self.assertEqual(rc, 0)
                rt.assert_called_once_with(5, column)
                rsw.assert_called_once_with(5, column)

    def test_failed_board_move_writes_nothing_through(self):
        """Memory must not claim a transition the board rejected."""
        with (
            patch("solomon_harness.github.set_issue_status", return_value={"ok": False}),
            patch("solomon_harness.github.record_transition") as rt,
            patch("solomon_harness.github.record_status_write_through") as rsw,
        ):
            github.main(["set-status", "--issue", "5", "--status", "QA"])
        rt.assert_not_called()
        rsw.assert_not_called()


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


class TestMergePrAndClose(unittest.TestCase):
    """#172: the owning stage for the merge-to-Done transition. On a successful
    merge it must complete the Done transition in the same call (board move +
    the ADR-0006 write-through), with no separate reconcile step. On a failed
    merge it must leave board/memory untouched -- no partial state. On a merge
    that succeeds but whose board move fails, it must report the accurate
    partial state (merged, but not fully converged) rather than a blanket ok."""

    def setUp(self):
        self.claim_patcher = patch("solomon_harness.claim.release_claim")
        self.mock_release_claim = self.claim_patcher.start()

    def tearDown(self):
        self.claim_patcher.stop()

    def test_successful_merge_completes_the_done_transition(self):
        with (
            patch("solomon_harness.github._gh", return_value={"ok": True}) as gh,
            patch(
                "solomon_harness.github.set_issue_status", return_value={"ok": True}
            ) as set_status,
            patch("solomon_harness.github.record_terminal_status") as record_terminal,
            patch("solomon_harness.github.record_transition") as record_transition,
        ):
            res = github.merge_pr_and_close(42, 172)
        gh.assert_called_once_with(["pr", "merge", "42", "--squash"])
        set_status.assert_called_once_with(172, "Done")
        record_terminal.assert_called_once_with(172)
        record_transition.assert_called_once_with(172, "Done")
        self.assertTrue(res["ok"])
        self.assertEqual(res["pr"], 42)
        self.assertEqual(res["issue"], 172)
        # M14: the merge-triggered per-issue claim release must actually run,
        # not merely be patchable -- confirm it was called for this issue.
        self.mock_release_claim.assert_called_once_with(unittest.mock.ANY, 172, force=True)

    def test_merge_succeeds_but_board_move_fails_reports_partial_state(self):
        """#195 architecture-review finding: a merge that succeeds but whose
        board move fails must not be reported as ok -- the caller needs to
        know the board still needs a retry, distinct from nothing happening."""
        with (
            patch("solomon_harness.github._gh", return_value={"ok": True}),
            patch(
                "solomon_harness.github.set_issue_status",
                return_value={"ok": False, "error": "no Status field"},
            ),
            patch("solomon_harness.github.record_terminal_status") as record_terminal,
            patch("solomon_harness.github.record_transition") as record_transition,
        ):
            res = github.merge_pr_and_close(42, 172)
        self.assertFalse(res["ok"])
        self.assertTrue(res["merged"])
        self.assertEqual(res["error"], "no Status field")
        # The PR is genuinely merged (GitHub already closed the issue via the
        # Closes trailer), so memory still converges to that true state even
        # though the board column lags -- only the board needs a retry.
        record_terminal.assert_called_once_with(172)
        # The board move failed, so the timeline must not claim a Done entry:
        # column and board-history stay in lockstep.
        record_transition.assert_not_called()

    def test_failed_merge_does_not_touch_board_or_memory(self):
        with (
            patch(
                "solomon_harness.github._gh",
                return_value={"ok": False, "error": "not mergeable"},
            ),
            patch("solomon_harness.github.set_issue_status") as set_status,
            patch("solomon_harness.github.record_terminal_status") as record_terminal,
            patch("solomon_harness.github.record_transition") as record_transition,
        ):
            res = github.merge_pr_and_close(42, 172)
        set_status.assert_not_called()
        record_terminal.assert_not_called()
        record_transition.assert_not_called()
        self.assertFalse(res["ok"])
        self.assertIn("error", res)

    def test_releases_via_an_injected_fake_claim_store(self):
        # Proves the seam (issue #238 / review-215-m12): the merge path uses
        # an injected ClaimStore instead of the default GitClaimStore.
        released = []

        class FakeClaimStore:
            def release(self, issue_number, session_id=None, force=False):
                released.append((issue_number, session_id, force))
                return True

        with (
            patch("solomon_harness.github._gh", return_value={"ok": True}),
            patch(
                "solomon_harness.github.set_issue_status", return_value={"ok": True}
            ),
            patch("solomon_harness.github.record_terminal_status"),
            patch("solomon_harness.github.record_transition"),
        ):
            res = github.merge_pr_and_close(42, 172, claim_store=FakeClaimStore())

        self.assertTrue(res["ok"])
        self.assertEqual(released, [(172, None, True)])
        # The default-path patch from setUp must not have been used.
        self.mock_release_claim.assert_not_called()


class TestListOpenIssuesClaimAware(unittest.TestCase):
    """ADR-0024 item 6: the direct board-scan read path (gh issue list) must
    exclude actively-claimed issues too, not only MemoryService.get_open_issues."""

    def test_excludes_actively_claimed_issue(self):
        with (
            patch(
                "solomon_harness.github._gh",
                return_value={
                    "ok": True,
                    "data": [
                        {"number": 1, "title": "claimed by someone else"},
                        {"number": 2, "title": "unclaimed"},
                    ],
                },
            ),
            patch(
                "solomon_harness.claim.filter_unclaimed",
                return_value=[2],
            ) as filter_unclaimed,
        ):
            res = github.list_open_issues("/tmp/workspace")

        self.assertTrue(res["ok"])
        numbers = [i["number"] for i in res["issues"]]
        self.assertNotIn(1, numbers)
        self.assertIn(2, numbers)
        filter_unclaimed.assert_called_once_with("/tmp/workspace", [1, 2])

    def test_gh_failure_degrades_to_ok_false(self):
        with patch(
            "solomon_harness.github._gh",
            return_value={"ok": False, "error": "not authenticated"},
        ):
            res = github.list_open_issues("/tmp/workspace")
        self.assertFalse(res["ok"])
        self.assertIn("error", res)

    def test_excludes_via_an_injected_fake_claim_store(self):
        # Proves the seam (issue #238 / review-215-m12): an injected
        # ClaimStore is used instead of the default GitClaimStore, without
        # patching solomon_harness.claim.*.
        class FakeClaimStore:
            def filter_unclaimed(self, issue_numbers, session_id=None):
                return [n for n in issue_numbers if n != 1]

        with patch(
            "solomon_harness.github._gh",
            return_value={
                "ok": True,
                "data": [
                    {"number": 1, "title": "claimed by someone else"},
                    {"number": 2, "title": "unclaimed"},
                ],
            },
        ):
            res = github.list_open_issues("/tmp/workspace", claim_store=FakeClaimStore())

        self.assertTrue(res["ok"])
        numbers = [i["number"] for i in res["issues"]]
        self.assertNotIn(1, numbers)
        self.assertIn(2, numbers)


class TestGithubCliMerge(unittest.TestCase):
    def test_merge_subcommand_parses_and_dispatches(self):
        with patch(
            "solomon_harness.github.merge_pr_and_close",
            return_value={"ok": True, "pr": 42, "issue": 172},
        ) as merge:
            rc = github.main(["merge", "--pr", "42", "--issue", "172"])
        merge.assert_called_once_with(42, 172)
        self.assertEqual(rc, 0)

    def test_merge_subcommand_returns_nonzero_on_failure(self):
        with patch(
            "solomon_harness.github.merge_pr_and_close",
            return_value={"ok": False, "error": "not mergeable"},
        ):
            rc = github.main(["merge", "--pr", "42", "--issue", "172"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
