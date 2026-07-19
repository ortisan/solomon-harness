"""Fitness checks for the epic-#341 compozy-adoption batch (issue #353).

Each package's skill file, its wiring into the command surfaces, and its
generated mirrors are pinned here so a rewrite that drops a load-bearing rule
fails visibly.
"""

import os

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel_path):
    # The canonical workflow bodies live in the neutral catalog; the Claude
    # commands under .claude/commands are thin bridges pointing at them.
    parts = rel_path.split(os.sep)
    if parts[:2] == [".claude", "commands"] and parts[-1].startswith("solomon-"):
        rel_path = os.path.join(
            "solomon_harness", "catalog", "workflows", parts[-1]
        )
    with open(os.path.join(WORKSPACE, rel_path), "r", encoding="utf-8") as f:
        return f.read()


def _flat(rel_path):
    return " ".join(_read(rel_path).split()).lower()


def _skill(agent, name):
    return _read(os.path.join("agents", agent, "skills", f"{name}.md"))


def _profile(agent):
    return _read(os.path.join("agents", agent, "agents", f"{agent}.md"))


# --- pkg 3: AI test-hygiene scan ---------------------------------------------


def test_ai_test_hygiene_scan_skill_and_review_wiring():
    skill = _skill("qa", "ai_test_hygiene_scan").lower()
    for token in ("rf-1", "rf-2", "rf-3", "rf-4"):
        assert token in skill, token
    assert "flake" in skill
    assert "ai_test_hygiene_scan" in _profile("qa")
    review = _flat(os.path.join(".claude", "commands", "solomon-review.md"))
    assert "ai_test_hygiene_scan" in review
    assert "rf-1" in review and "rf-3" in review


def test_rtm_gains_covers_weak_missing():
    rtm = _skill("qa", "test_planning_and_traceability").lower()
    assert "covers" in rtm and "weak" in rtm and "missing" in rtm


# --- pkg 6: persona-driven exploratory testing + honesty rule ----------------


def test_persona_exploratory_skill_and_qa_tree():
    skill = _skill("qa", "persona_driven_exploratory_testing").lower()
    assert "charter" in skill and "journey" in skill and "persona" in skill
    assert "persona_driven_exploratory_testing" in _profile("qa")
    assert os.path.isfile(os.path.join(WORKSPACE, "docs", "qa", "state.csv"))
    header = _read(os.path.join("docs", "qa", "state.csv")).splitlines()[0]
    for col in ("qa_status", "fix_status", "retest_status"):
        assert col in header, col


def test_honesty_rule_wired_into_start_and_scans():
    for rel in (
        os.path.join(".claude", "commands", "solomon-start.md"),
        os.path.join(".claude", "commands", "solomon-scan-arch.md"),
        os.path.join(".claude", "commands", "solomon-scan-dedup.md"),
    ):
        low = _flat(rel)
        assert "state.csv" in low, rel
        assert "untested" in low, rel


# --- pkg 7: memory promotion gate + compaction -------------------------------


def test_memory_skill_has_promotion_gate_and_compaction():
    low = _skill("software_engineer", "harness_memory_and_handoff").lower()
    assert "promotion gate and compaction" in low
    assert "supersede_decision" in low


# --- pkg 8: skill authoring craft --------------------------------------------


def test_skill_authoring_craft_exists():
    low = _skill("agent_builder", "skill_authoring_craft").lower()
    assert "wrangle determinism out of a stochastic system" in low
    assert "skill_authoring_craft" in _profile("agent_builder")


# --- pkg 9: no-workarounds + debugging tripwire ------------------------------


def test_no_workarounds_skill_and_debugging_tripwire():
    low = _skill("software_engineer", "no_workarounds_and_the_escape_valve").lower()
    assert "fix the source, not the signal" in low
    assert "# workaround:" in low
    assert "no_workarounds_and_the_escape_valve" in _profile("software_engineer")
    dbg = _skill("software_engineer", "debugging_method").lower()
    assert "when three fixes fail, question the architecture" in dbg


# --- pkg 10: ADR reconciliation gate -----------------------------------------


def test_adr_reconciliation_gate():
    gate = _skill("software_architect", "architecture_review_gate").lower()
    assert "adr reconciliation" in gate
    assert "matches-as-designed" in gate
    scan = _skill("software_architect", "architecture_scan_loop").lower()
    assert "reconciliation" in scan
    readme = _read(os.path.join("docs", "adrs", "README.md")).lower()
    assert "reconciliation" in readme
    review = _flat(os.path.join(".claude", "commands", "solomon-review.md"))
    assert "adr-reconciliation" in review or "adr reconciliation" in review


# --- pkg 11: vertical-slice sizing doctrine ----------------------------------


def test_vertical_slice_sizing_doctrine():
    for agent, name in (("product_owner", "scope_boundaries"), ("scrum_master", "backlog_management")):
        low = _skill(agent, name).lower()
        assert "vertical-slice sizing" in low
        assert "never a split reason" in low
    refine = _flat(os.path.join(".claude", "commands", "solomon-refine.md"))
    assert "vertical-slice sizing" in refine


# --- pkg 12: loop outcome integrity ------------------------------------------


def test_loop_outcome_integrity_skill():
    low = _skill("loop_engineer", "loop_outcome_integrity_and_reward_hacking").lower()
    assert "reward-hacking" in low or "reward hacking" in low
    assert "trajectory" in low and "outcome" in low
    assert "loop_outcome_integrity_and_reward_hacking" in _profile("loop_engineer")


# --- pkg 13: scoped subagent dispatch ----------------------------------------


def test_scoped_subagent_dispatch_skill():
    low = _skill("loop_engineer", "scoped_subagent_dispatch").lower()
    assert "scout" in low
    assert "non-overlapping" in low
    assert "fabricate" in low
    assert "scoped_subagent_dispatch" in _profile("loop_engineer")


# --- pkg 14: opt-in council debate -------------------------------------------


def test_council_debate_skill_and_opt_in_wiring():
    low = _skill("product_owner", "council_debate").lower()
    assert "unresolved tensions" in low
    assert "dissenting view" in low
    assert "the-thinker" in low  # named only to forbid inventing it
    assert "council_debate" in _profile("product_owner")
    idea = _flat(os.path.join(".claude", "commands", "solomon-idea.md"))
    # Pin the council opt-in in the same clause (askuserquestion pre-existed for
    # the unrelated enumerable-decisions convention) — #356 review.
    assert "council_debate" in idea or "opt-in council debate" in idea
    refine = _flat(os.path.join(".claude", "commands", "solomon-refine.md"))
    assert "council" in refine


# --- generated mirrors stay in lockstep --------------------------------------


def test_gemini_mirrors_carry_the_new_command_wiring():
    review = _flat(os.path.join(".gemini", "commands", "solomon-review.toml"))
    assert "ai_test_hygiene_scan" in review
    start = _flat(os.path.join(".gemini", "commands", "solomon-start.md")) if os.path.isfile(
        os.path.join(WORKSPACE, ".gemini", "commands", "solomon-start.md")
    ) else _flat(os.path.join(".gemini", "commands", "solomon-start.toml"))
    assert "state.csv" in start


# --- pkg 5: bounded remediation rounds ---------------------------------------


def test_remediation_cap_helper_and_doc_wiring():
    from solomon_harness import loop_log

    assert hasattr(loop_log, "consecutive_runs_for_target")
    assert hasattr(loop_log, "remediation_limit_reached")
    doc = _flat(os.path.join("docs", "solomon-workflow.md"))
    assert "remediation_limit_reached" in doc
    assert "consecutive-round cap" in doc
    # The cap is a code-enforced gate in run_stage, not doc-only guidance
    # (#356 review blocker): run_stage must call it and return 3 at the cap.
    wf = _read(os.path.join("solomon_harness", "workflows.py"))
    assert "remediation_limit_reached" in wf


# --- pkg 15: cross-round finding dedup ---------------------------------------


def test_review_carries_cross_round_dedup():
    low = _flat(os.path.join(".claude", "commands", "solomon-review.md"))
    assert "dedup_key" in low
    assert "cross-round finding dedup" in low
    # Pin the distinctive lifecycle sentence, not the bare words (a pre-existing
    # "unresolved" substring made "resolved" hollow) — #356 review.
    assert "pending` → `valid`/`invalid` → `resolved`" in _read(
        os.path.join(".claude", "commands", "solomon-review.md")
    )
    # A real, tested code artifact backs the contract, not prose alone.
    from solomon_harness import review_dedup

    assert callable(review_dedup.finding_dedup_key)
    assert review_dedup.LIFECYCLE_STATES == ("pending", "valid", "invalid", "resolved")


# --- pkg 16: blocked-issue skip + refine exploration -------------------------


def test_blocked_issue_skip_wired_into_selection():
    doc = _flat(os.path.join("docs", "solomon-workflow.md"))
    assert "issues_blocked_by" in doc
    assert "skips any candidate" in doc
    # The selection code actually consults issues_blocked_by (#356 review):
    # the digest ready-issue scan filters blocked candidates.
    dg = _read(os.path.join("solomon_harness", "digest.py"))
    assert "_blocked_ready_ids" in dg
    assert "issues_blocked_by" in dg


def test_refine_cites_an_exploration_pass():
    low = _flat(os.path.join(".claude", "commands", "solomon-refine.md"))
    assert "read-only exploration pass" in low
    assert "scoped_subagent_dispatch" in low
