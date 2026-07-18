"""Select the specialist agents a target project needs, from its detected stack.

``select_agents(workspace_root)`` inspects the project's files and dependency
manifests and returns the subset of agents to enable, instead of enabling all of
them. A core set (the delivery spine and the cross-cutting roles) is always
included; platform and domain agents are added only when their stack is present.
The result is intersected with the agents that actually exist under ``agents/``.

CLI:
    python -m solomon_harness.agent_selection [path] [--json]
"""

import argparse
import json
import os
import stat
import sys
from typing import List, Optional, Set

from solomon_harness.layout import HarnessPaths

# Always enabled: planning, build, quality, delivery and documentation roles.
CORE_AGENTS = [
    "product_owner",
    "scrum_master",
    "software_architect",
    "software_engineer",
    "qa",
    "security",
    "sre",
    "observability",
    "documenter",
    "agent_builder",
]


ML_DEPS = ("torch", "tensorflow", "scikit-learn", "sklearn", "pandas", "numpy", "keras", "xgboost")
TRADING_DEPS = ("backtrader", "ccxt", "zipline", "vectorbt", "ta-lib", "alpaca")
FRONTEND_DEPS = ("react", "next", "@angular/core", "vue", "svelte")
AUTH_DEPS = ("authlib", "python-jose", "passport", "next-auth", "@auth/core", "pyjwt", "oauthlib")

SCAN_SKIP_DIRS = frozenset({
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "agents",
    ".agent",
    ".agents",
    ".claude",
    ".codex",
    ".gemini",
    ".solomon",
    ".solomon-harness",
    "solomon_harness",
})
MANIFEST_NAMES = frozenset(
    {"package.json", "pyproject.toml", "requirements.txt", "pipfile", "go.mod"}
)
MAX_SCAN_DEPTH = 4
MAX_MANIFEST_BYTES = 512 * 1024
MAX_MANIFEST_TOTAL_BYTES = 2 * 1024 * 1024


def discover_agents(workspace_root: str) -> Set[str]:
    """Return the agents present under the resolved agents directory.

    The agents directory is resolved through ``HarnessPaths`` so a host-agnostic
    layout (``.agents/solomon/agents``) and the legacy top-level ``agents`` tree
    are both found. An agent is any directory carrying its role file.
    """
    agents_dir = os.fspath(HarnessPaths(workspace_root).resolve_agents())
    found: Set[str] = set()
    if not os.path.isdir(agents_dir):
        return found
    for item in os.listdir(agents_dir):
        if os.path.isfile(os.path.join(agents_dir, item, "agents", f"{item}.md")):
            found.add(item)
    return found


# Back-compat alias for the historical private name (now a public surface that
# capability_router and others depend on).
_discover_agents = discover_agents


def _scan(workspace_root: str, max_depth: int = MAX_SCAN_DEPTH) -> tuple:
    """Return (set of file extensions, set of basenames) up to max_depth."""
    exts: Set[str] = set()
    names: Set[str] = set()
    root_depth = workspace_root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(workspace_root):
        dirnames[:] = sorted(d for d in dirnames if d not in SCAN_SKIP_DIRS)
        if dirpath.count(os.sep) - root_depth >= max_depth:
            dirnames[:] = []
            continue
        for name in filenames:
            names.add(name.lower())
            _, ext = os.path.splitext(name)
            if ext:
                exts.add(ext.lower())
    return exts, names


def _manifest_text(workspace_root: str, max_depth: int = MAX_SCAN_DEPTH) -> str:
    """Concatenate bounded dependency manifests found in a monorepo tree."""
    chunks: List[str] = []
    remaining = MAX_MANIFEST_TOTAL_BYTES
    root_depth = workspace_root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(workspace_root):
        dirnames[:] = sorted(d for d in dirnames if d not in SCAN_SKIP_DIRS)
        if dirpath.count(os.sep) - root_depth >= max_depth:
            dirnames[:] = []
            continue
        for name in sorted(filenames):
            if remaining <= 0:
                return "\n".join(chunks)
            if name.lower() not in MANIFEST_NAMES:
                continue
            path = os.path.join(dirpath, name)
            try:
                file_stat = os.stat(path, follow_symlinks=False)
                if not stat.S_ISREG(file_stat.st_mode):
                    continue
                if file_stat.st_size > MAX_MANIFEST_BYTES:
                    continue
                if file_stat.st_size > remaining:
                    return "\n".join(chunks)
                with open(path, "rb") as f:
                    content = f.read(min(file_stat.st_size + 1, remaining))
            except OSError:
                continue
            remaining -= len(content)
            if len(content) != file_stat.st_size:
                if remaining <= 0:
                    return "\n".join(chunks)
                continue
            try:
                chunks.append(content.decode("utf-8").lower())
            except UnicodeDecodeError:
                pass
            if remaining <= 0:
                return "\n".join(chunks)
    return "\n".join(chunks)


def _signals(workspace_root: str) -> Set[str]:
    exts, names = _scan(workspace_root)
    manifest = _manifest_text(workspace_root)
    sig: Set[str] = set()

    if ".dart" in exts or "pubspec.yaml" in names:
        sig.add("flutter")
    if ".swift" in exts:
        sig.add("apple")
    if (".kt" in exts or ".java" in exts) and (
        "build.gradle" in names or "build.gradle.kts" in names or "androidmanifest.xml" in names
    ):
        sig.add("android")
    if ".ts" in exts or ".tsx" in exts or ".js" in exts or ".jsx" in exts or "package.json" in names:
        sig.add("web")
        if any(dep in manifest for dep in FRONTEND_DEPS):
            sig.add("frontend")
    if ".html" in exts:
        sig.add("seo")
    if ".py" in exts or "pyproject.toml" in names or "requirements.txt" in names:
        sig.add("python")
        if any(dep in manifest for dep in ML_DEPS):
            sig.add("ml")
        if any(dep in manifest for dep in TRADING_DEPS):
            sig.add("trading")
    if ".sql" in exts or "migrations" in names or any(
        os.path.isdir(os.path.join(workspace_root, d)) for d in ("migrations", "db")
    ):
        sig.add("sql")
    if any(dep in manifest for dep in AUTH_DEPS):
        sig.add("auth")
    return sig


def select_agents(workspace_root: str) -> List[str]:
    """Return the sorted list of agents to enable for the project at workspace_root."""
    from solomon_harness.integrations import discover_agents as discover_compilable_agents

    agents_dir = os.fspath(HarnessPaths(workspace_root).resolve_agents())
    # Stack selection uses the strict "compilable agent" definition (#315): a
    # present but incomplete catalog fails closed instead of enabling a
    # half-formed agent the compiler cannot safely activate.
    available = set(discover_compilable_agents(agents_dir))
    catalog_present = bool(available) or os.path.lexists(agents_dir)
    if catalog_present and not available:
        return []

    selected: Set[str] = set(CORE_AGENTS)
    sig = _signals(workspace_root)

    rules = {
        "flutter": ["flutter"],
        "apple": ["apple"],
        "android": ["android"],
        "frontend": ["frontend", "seo"],
        "web": ["seo"],
        "ml": ["ml_engineer", "data_analyst"],
        "trading": ["quant_trader", "ml_engineer"],
        "sql": ["dba", "data_analyst"],
        "auth": ["auth_engineer"],
    }
    for signal, agents in rules.items():
        if signal in sig:
            selected.update(agents)

    # A present catalog is authoritative, even when it has no compilable agents.
    # The legacy core-and-signal fallback is reserved for projects with no agents/
    # entry at all.
    if catalog_present:
        selected &= available
    return sorted(selected)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Select the agents a project needs from its stack.")
    parser.add_argument("path", nargs="?", default=os.getcwd(), help="Project root to inspect")
    parser.add_argument("--json", action="store_true", help="Emit a JSON array")
    args = parser.parse_args(argv)

    agents = select_agents(os.path.abspath(args.path))
    if args.json:
        print(json.dumps(agents))
    else:
        for name in agents:
            print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
