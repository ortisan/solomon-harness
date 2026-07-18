import ast
import os
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(WORKSPACE, "solomon_harness")
_SUBPROCESS_CALLS = {"run", "check_output", "Popen", "check_call", "call"}
_CLEAN_ENV = {"clean_git_env", "clean_gh_env"}
# Out-of-scope env handling exempted with an explicit reason, per #251's review:
#   curator.py  -- apply_proposal's git/gh env, tracked as #103.
#   github.py   -- _gh centralizes gh calls behind a retry/token-heal env; stripping
#                  GIT_* there is a follow-up (Refs #251), not this issue's scope.
_ALLOWLISTED_FILES = {"curator.py", "github.py"}


def _callee_name(node):
    func = getattr(node, "func", None)
    return getattr(func, "id", None) or getattr(func, "attr", None)


def _is_clean_env_expr(node, clean_env_vars):
    if isinstance(node, ast.Call):
        return _callee_name(node) in _CLEAN_ENV
    if isinstance(node, ast.Name):
        return node.id in clean_env_vars
    return False


def _first_str(elts):
    if elts and isinstance(elts[0], ast.Constant) and isinstance(elts[0].value, str):
        return elts[0].value
    return None


def _scan_function(func_node, path, offenders):
    git_cmd_vars = set()
    clean_env_vars = set()
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if isinstance(node.value, ast.List) and _first_str(node.value.elts) in ("git", "gh"):
                git_cmd_vars.add(name)
            elif isinstance(node.value, ast.Call) and _callee_name(node.value) in _CLEAN_ENV:
                clean_env_vars.add(name)
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if _callee_name(node) not in _SUBPROCESS_CALLS:
            continue
        arg0 = node.args[0]
        is_git = (
            (isinstance(arg0, ast.List) and _first_str(arg0.elts) in ("git", "gh"))
            or (isinstance(arg0, ast.Name) and arg0.id in git_cmd_vars)
        )
        if not is_git:
            continue
        env_kw = next((kw.value for kw in node.keywords if kw.arg == "env"), None)
        if not _is_clean_env_expr(env_kw, clean_env_vars):
            offenders.append(f"{os.path.relpath(path, WORKSPACE)}:{node.lineno}")


def _dirty_git_calls():
    offenders = []
    for dirpath, _, files in os.walk(PKG):
        for fn in files:
            if not fn.endswith(".py") or fn in _ALLOWLISTED_FILES:
                continue
            path = os.path.join(dirpath, fn)
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _scan_function(node, path, offenders)
    return sorted(offenders)


def _scan_source(src):
    offenders = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _scan_function(node, "x.py", offenders)
    return offenders


class TestGitEnvSweep(unittest.TestCase):
    def test_git_and_gh_subprocess_calls_pass_clean_git_env(self):
        offenders = _dirty_git_calls()
        self.assertEqual(
            offenders,
            [],
            "every git/gh subprocess call must pass env=clean_git_env()/clean_gh_env() "
            f"(directly or via a local variable) to strip GIT_*; offenders: {offenders}",
        )


class TestScannerCatchesBlindSpots(unittest.TestCase):
    def test_bare_literal_call_is_flagged(self):
        self.assertTrue(_scan_source("def f():\n subprocess.run(['git', 'push'])"))

    def test_env_present_but_not_clean_is_flagged(self):
        self.assertTrue(
            _scan_source("def f():\n e = os.environ.copy()\n subprocess.run(['git', 'push'], env=e)")
        )

    def test_command_in_a_variable_is_flagged(self):
        self.assertTrue(
            _scan_source("def f():\n c = ['gh', 'pr', 'create']\n subprocess.run(c)")
        )

    def test_clean_env_direct_passes(self):
        self.assertFalse(
            _scan_source("def f():\n subprocess.run(['git', 'push'], env=clean_git_env(r))")
        )

    def test_clean_env_via_local_variable_passes(self):
        self.assertFalse(
            _scan_source("def f():\n env = clean_git_env(d)\n subprocess.run(['git', 'init'], env=env)")
        )


if __name__ == "__main__":
    unittest.main()
