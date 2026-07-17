"""Governed autonomy: the L1/L2/L3 maturity ladder, denylist, and kill-switch.

Phase 2 of the loop-engineering adaptation. The policy is the one autonomy dial,
enforced in portable Python (so it holds on both Claude Code and the Gemini CLI),
not only in a Claude-only hook. Three hard rules it can never widen:

- merge, release, and the lifecycle decision that originates Done are
  PERMANENTLY human-gated at every level — ADR-0034 permits only an idempotent
  projection repair after GitHub already reports the issue closed;
- L3 (unattended) only runs while the single-driver lock is held;
- the kill-switch halts every stage immediately, in one command.

The default level is ``human`` (no restriction), so a repository with no ``loop``
block in ``.agent/config.json`` behaves exactly as before. L1/L2/L3 are opt-in for
automation and cadence.
"""

import fnmatch
import json
import os
from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Tuple

from solomon_harness.loop_lock import resolve_common_file

LEVELS = ("human", "L1", "L2", "L3")

# Permanently human-gated stages — never autonomous, at any level.
HUMAN_GATED_STAGES = {"release"}
# L1 is report-only: it may scan and propose, never mutate.
L1_ALLOWED_STAGES = {"workflow"}
# L2/L3 may create work and draft PRs, but never the human-gated stages above.
# The scan loops draft PRs; reconcile only repairs the projection of issues that
# GitHub already reports CLOSED (ADR-0034). Neither originates a merge/release.
AUTOMATION_ALLOWED_STAGES = {
    "workflow", "loop", "idea", "issue", "bug", "refine", "start", "review",
    "scan-arch", "scan-dedup", "reconcile",
}

# Renamed stages, normalized on read so pre-rename callers and recorded state
# keep the same verdicts (`loop-auto` became `loop`).
LEGACY_STAGE_ALIASES = {"loop-auto": "loop"}

DEFAULT_DENYLIST = [
    ".git/*",
    ".agent/config.json",
    "*/.env",
    ".env",
    "*.pem",
    "*.key",
    "*.enc",
    "*secrets/*",
    "*/migrations/*",
    "*/node_modules/*",
]


class Decision(NamedTuple):
    allowed: bool
    reason: str


class LoopPolicy:
    """The autonomy policy for one workspace."""

    def __init__(
        self,
        workspace_root: str,
        *,
        level: str = "human",
        denylist: Optional[List[str]] = None,
        maker_model: Optional[str] = None,
        checker_model: Optional[str] = None,
        orchestrator_model: Optional[str] = None,
        daily_cost_ceiling: Optional[float] = None,
    ) -> None:
        self.workspace_root = workspace_root
        # Keep an invalid/typo'd level verbatim so decide_stage fails CLOSED on it
        # (a mistyped "l2" must never silently become unrestricted "human").
        self.level = level
        self.denylist = list(denylist) if denylist is not None else list(DEFAULT_DENYLIST)
        self.maker_model = maker_model
        self.checker_model = checker_model
        self.orchestrator_model = orchestrator_model
        self.daily_cost_ceiling = daily_cost_ceiling

    # -- construction -------------------------------------------------------
    @classmethod
    def from_config(cls, workspace_root: str, env: Optional[Dict[str, str]] = None) -> "LoopPolicy":
        resolved_env: Mapping[str, str] = os.environ if env is None else env
        cfg = _read_loop_config(workspace_root)
        level = resolved_env.get("SOLOMON_LOOP_AUTONOMY") or cfg.get("autonomy") or "human"
        orchestrator_model = (
            resolved_env.get("SOLOMON_ORCHESTRATOR_MODEL") or cfg.get("orchestrator_model")
        )
        return cls(
            workspace_root,
            level=str(level),
            denylist=cfg.get("denylist"),
            maker_model=cfg.get("maker_model"),
            checker_model=cfg.get("checker_model"),
            orchestrator_model=orchestrator_model,
            daily_cost_ceiling=cfg.get("daily_cost_ceiling_usd"),
        )

    # -- kill-switch --------------------------------------------------------
    def stop_path(self) -> str:
        return resolve_common_file(self.workspace_root, "solomon-loop.stop", "loop.stop")

    def is_halted(self) -> bool:
        return os.path.exists(self.stop_path())

    # -- decisions ----------------------------------------------------------
    def decide_stage(self, stage: str) -> Decision:
        """Decide whether the automation path may run ``stage`` now."""
        stage = LEGACY_STAGE_ALIASES.get(stage, stage)
        if self.is_halted():
            return Decision(False, "loop halted by kill-switch; clear with 'solomon-harness loop-stop --clear'")
        if stage in HUMAN_GATED_STAGES:
            return Decision(
                False,
                f"'{stage}' is permanently human-gated "
                "(merge/release/terminal decisions are never autonomous)",
            )
        if self.level == "human":
            return Decision(True, "")
        if self.level == "L1":
            if stage in L1_ALLOWED_STAGES:
                return Decision(True, "")
            return Decision(False, f"L1 is report-only; '{stage}' would mutate state")
        if self.level in ("L2", "L3"):
            if stage in AUTOMATION_ALLOWED_STAGES:
                return Decision(True, "")
            return Decision(False, f"'{stage}' is not permitted at {self.level}")
        return Decision(False, f"unknown autonomy level '{self.level}'")

    def requires_lock(self, stage: str) -> bool:
        """L3 may only act while the single-driver lock is held."""
        stage = LEGACY_STAGE_ALIASES.get(stage, stage)
        return self.level == "L3" and stage not in ("workflow",)

    # -- denylist -----------------------------------------------------------
    def is_denied_path(self, path: str) -> bool:
        """True when the loop is forbidden from modifying ``path``.

        An absolute path is relativized against the workspace root first, so
        slash-bearing patterns (``.agent/config.json``, ``*secrets/*``) match
        regardless of how the path was rooted — otherwise an absolute path would
        slip past them on the basename alone.
        """
        p = path.replace(os.sep, "/")
        root = (self.workspace_root or "").replace(os.sep, "/").rstrip("/")
        if root and p.startswith(root + "/"):
            p = p[len(root) + 1:]
        if p.startswith("./"):
            p = p[2:]
        base = os.path.basename(p)
        for pat in self.denylist:
            if fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(base, pat):
                return True
        return False

    # -- verifier split -----------------------------------------------------
    def checker_split_ok(self) -> bool:
        """Maker/checker must use different models so the checker is not too nice."""
        return bool(self.maker_model and self.checker_model and self.maker_model != self.checker_model)


def _read_loop_config(workspace_root: str) -> Dict[str, Any]:
    """Read the ``loop`` block from the project's .agent/config.json (best-effort)."""
    candidates = [
        os.path.join(workspace_root, ".agent", "config.json"),
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            block = data.get("loop")
            if isinstance(block, dict):
                return block
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def write_stop(workspace_root: str) -> str:
    """Engage the kill-switch; return the sentinel path."""
    path = LoopPolicy(workspace_root).stop_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("halted\n")
    return path


def clear_stop(workspace_root: str) -> bool:
    """Disengage the kill-switch; return True if a sentinel was removed."""
    path = LoopPolicy(workspace_root).stop_path()
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False


# File-modifying host tools whose target path the denylist guards.
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def denied_write_verdict(payload: Dict[str, Any], policy: "LoopPolicy") -> Tuple[bool, str]:
    """Block a file-write tool call that targets a denylisted path.

    This is the enforcement the denylist needs to be more than advisory: it stops
    an autonomous (or prompt-injected) run from editing ``.agent/config.json`` to
    widen its own autonomy level, empty the denylist, or defeat the cost ceiling.
    It runs in the PreToolUse `loop-guard` hook, so it is a Claude-side hard block;
    on the Gemini host (no PreToolUse) the denylist stays model-honored, and an
    unattended L3 cadence should pin the level with ``SOLOMON_LOOP_AUTONOMY`` so a
    config edit cannot raise it.
    """
    tool = payload.get("tool_name") or payload.get("tool") or ""
    if tool not in WRITE_TOOLS:
        return (False, "")
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path") or ""
    if path and policy.is_denied_path(str(path)):
        return (
            True,
            f"Blocked by the loop denylist: {path} may not be modified by an autonomous "
            "run (it could widen the run's own autonomy, denylist, or cost ceiling). "
            "Pin the autonomy level with SOLOMON_LOOP_AUTONOMY for unattended runs.",
        )
    return (False, "")
