import ast
import os
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(WORKSPACE, "solomon_harness")
_SUBPROCESS_CALLS = {"run", "check_output", "Popen", "check_call", "call"}
_ALLOWLIST = {("curator.py", ("git", "rev-parse", "HEAD"))}


def _bare_git_calls():
    offenders = []
    for dirpath, _, files in os.walk(PKG):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                if getattr(node.func, "attr", None) not in _SUBPROCESS_CALLS:
                    continue
                arg0 = node.args[0]
                if not (isinstance(arg0, ast.List) and arg0.elts):
                    continue
                head = arg0.elts[0]
                if not (isinstance(head, ast.Constant) and head.value in ("git", "gh")):
                    continue
                if any(kw.arg == "env" for kw in node.keywords):
                    continue
                tokens = tuple(
                    e.value for e in arg0.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
                )
                if (fn, tokens) in _ALLOWLIST:
                    continue
                offenders.append(f"{os.path.relpath(path, WORKSPACE)}:{node.lineno}")
    return sorted(offenders)


class TestGitEnvSweep(unittest.TestCase):
    def test_no_bare_git_or_gh_subprocess_without_env(self):
        offenders = _bare_git_calls()
        self.assertEqual(
            offenders,
            [],
            "git/gh subprocess calls must pass env=clean_git_env() to strip GIT_*; "
            f"offenders: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
