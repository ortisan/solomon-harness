"""Gate-and-honesty fitness checks for the /solomon-* command prompts and docs.

These assert that the Definition of Done is wired as a real gate (not an orphan
per-agent skill), that every issue family states its Acceptance Criteria /
Definition of Ready / Definition of Done expectation, that the board columns are
reconciled with the named lifecycle stages, and that the loop is described
honestly as host-orchestrated and human-gated rather than fully autonomous.
"""

import os

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel_path):
    with open(os.path.join(WORKSPACE, rel_path), "r", encoding="utf-8") as f:
        return f.read()


# --- Definition of Done wired as a gate -------------------------------------


def test_review_command_wires_definition_of_done_gate():
    body = _read(os.path.join(".claude", "commands", "solomon-review.md"))
    low = body.lower()
    # DoD is named and tied to the verdict, not just mentioned in passing.
    assert "Definition of Done" in body
    assert "acceptance criterion" in low or "acceptance criteria" in low
    assert "blocker" in low


def test_release_command_wires_definition_of_done_gate():
    body = _read(os.path.join(".claude", "commands", "solomon-release.md"))
    assert "Definition of Done" in body


def test_release_command_generates_release_wiki_page():
    body = _read(os.path.join(".claude", "commands", "solomon-release.md"))
    # Exact command another workstream implements; referenced here only.
    assert "uv run python -m solomon_harness.release wiki-page --release" in body


# --- AC / DoR / DoD across the issue families -------------------------------


def test_issue_commands_require_ac_dor_dod():
    for rel in (
        os.path.join(".claude", "commands", "solomon-bug.md"),
        os.path.join(".claude", "commands", "solomon-issue.md"),
        os.path.join(".claude", "commands", "solomon-refine.md"),
    ):
        body = _read(rel)
        low = body.lower()
        assert "acceptance criteria" in low, rel
        assert "Definition of Ready" in body, rel
        assert "Definition of Done" in body, rel


def test_idea_command_graduates_to_dor_dod_at_refinement():
    body = _read(os.path.join(".claude", "commands", "solomon-idea.md"))
    low = body.lower()
    # Ideas are pre-DoR discovery; they graduate to DoR/DoD at refinement.
    assert "definition of ready" in low
    assert "definition of done" in low
    assert "graduat" in low


def test_bug_template_requires_ac_dor_dod():
    body = _read(os.path.join(".github", "ISSUE_TEMPLATE", "bug_report.md"))
    low = body.lower()
    assert "acceptance criteria" in low
    assert "definition of ready" in low
    assert "definition of done" in low


def test_feature_template_requires_ac_dor_dod():
    body = _read(os.path.join(".github", "ISSUE_TEMPLATE", "feature_conception.md"))
    low = body.lower()
    assert "acceptance criteria" in low
    assert "definition of ready" in low
    assert "definition of done" in low


def test_idea_template_graduates_to_dor_dod():
    body = _read(os.path.join(".github", "ISSUE_TEMPLATE", "future_ideas.md"))
    low = body.lower()
    assert "definition of ready" in low
    assert "definition of done" in low
    assert "graduat" in low


# --- Board columns reconciled with the named lifecycle stages ---------------


def test_workflow_doc_maps_board_columns_to_lifecycle_stages():
    doc = _read(os.path.join("docs", "solomon-workflow.md"))
    assert "Board columns mapped to lifecycle stages" in doc
    for column in ("Ideas", "Backlog", "Ready", "In Progress", "Code Review", "QA", "Done"):
        assert column in doc, column
    for stage in ("Refinement", "Implementation", "Tests", "Review", "Release", "Milestone"):
        assert stage in doc, stage


# --- Honest framing: host-orchestrated, human-gated -------------------------


def test_loop_command_is_host_orchestrated_human_gated():
    body = _read(os.path.join(".claude", "commands", "solomon-loop.md")).lower()
    assert "host-orchestrated" in body
    assert "human-gated" in body


def test_docs_reframe_loop_as_host_orchestrated_human_gated():
    for rel in (
        os.path.join("docs", "loop-engineering.md"),
        os.path.join("docs", "solomon-workflow.md"),
        "README.md",
    ):
        low = _read(rel).lower()
        assert "host-orchestrated" in low, rel
        assert "human-gated" in low, rel
