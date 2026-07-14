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


def test_workflow_command_is_host_orchestrated_human_gated():
    body = _read(os.path.join(".claude", "commands", "solomon-workflow.md")).lower()
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


# --- Episodic work graph wired into the commands (ADR-0018) ------------------


def test_commands_wire_worked_on_and_produced_edges():
    """The stages that write sessions and handoffs must also write the graph:
    issues=[...] on save_session (the worked_on edge) and
    link_session_handoff (the produced edge), in both hosts' command files."""
    for name in ("start", "review", "release", "bug", "issue"):
        body = _read(os.path.join(".claude", "commands", f"solomon-{name}.md"))
        assert "link_session_handoff" in body, name
        assert "issues=[" in body, name
        # The tool must be callable, not just mentioned: it is allowlisted.
        frontmatter = body.split("---")[1]
        assert "mcp__solomon-memory__link_session_handoff" in frontmatter, name
        assert "mcp__solomon-memory__save_session" in frontmatter, name


def test_gemini_mirrors_carry_the_edge_wiring():
    for name in ("start", "review", "release", "bug", "issue"):
        body = _read(os.path.join(".gemini", "commands", f"solomon-{name}.toml"))
        assert "link_session_handoff" in body, name
        assert "issues=[" in body, name


# --- Merge-to-Done transition owned by review, not release (#172, ADR-0020) --


def test_review_command_owns_the_merge_on_approval():
    body = _read(os.path.join(".claude", "commands", "solomon-review.md"))
    assert "solomon_harness.github merge" in body
    assert "ADR-0020" in body
    # The old contradiction ("do not merge here") must be gone.
    assert "do not push, merge" not in body.lower()
    # AskUserQuestion must actually be callable for the interactive confirm step.
    frontmatter = body.split("---")[1]
    assert "AskUserQuestion" in frontmatter


def test_release_command_never_merges_individual_prs():
    body = _read(os.path.join(".claude", "commands", "solomon-release.md"))
    assert "ADR-0020" in body
    assert "never merges an individual pr" in body.lower()
    # The old ambiguous claim must be gone.
    assert "now happens in `/solomon-review` close-out, not here" not in body


def test_gemini_mirrors_match_the_merge_ownership_decision():
    review = _read(os.path.join(".gemini", "commands", "solomon-review.toml"))
    assert "solomon_harness.github merge" in review
    assert "ADR-0020" in review
    assert "do not push, merge" not in review.lower()

    release = _read(os.path.join(".gemini", "commands", "solomon-release.toml"))
    assert "ADR-0020" in release
    assert "never merges an individual pr" in release.lower()


def test_workflow_doc_documents_the_merge_owner():
    doc = _read(os.path.join("docs", "solomon-workflow.md"))
    assert "The merge-to-Done transition" in doc
    assert "ADR-0020" in doc


# --- Socratic elicitation gate in /solomon-issue (#222, ADR-0025) -------------

ELICITATION_CRITERIA = (
    "problem",
    "persona",
    "outcome",
    "boundary",
    "single reading",
    "job behind the solution",
)


def test_issue_command_wires_the_elicitation_gate():
    body = _read(os.path.join(".claude", "commands", "solomon-issue.md"))
    low = body.lower()
    assert "elicitation gate" in low
    for criterion in ELICITATION_CRITERIA:
        assert criterion in low, criterion
    # Bounds: questioning is bounded and targets only what is missing.
    assert "at most 3 rounds" in low
    assert "at most 4 questions" in low
    assert "only for failed criteria" in low
    # Trace lines and the decline/headless paths, pinned verbatim.
    assert "Elicitation: skipped — all 6 readiness criteria met" in body
    assert "Elicitation: skipped (non-interactive)" in body
    assert "Assumptions (unelicited)" in body
    # The gate must not weaken the outward-action gate (#222 R1).
    assert "confirm before creating" in low


def test_workflow_doc_defines_the_elicitation_gate():
    doc = _read(os.path.join("docs", "solomon-workflow.md"))
    low = doc.lower()
    assert "elicitation gate" in low
    for criterion in ELICITATION_CRITERIA:
        assert criterion in low, criterion
    assert "at most 3 rounds" in low
    assert "at most 4 questions" in low


def test_gemini_mirror_carries_the_elicitation_gate():
    body = _read(os.path.join(".gemini", "commands", "solomon-issue.toml"))
    assert "elicitation gate" in body.lower()
    assert "Elicitation: skipped (non-interactive)" in body


def test_product_owner_has_the_socratic_elicitation_skill():
    skill = _read(
        os.path.join("agents", "product_owner", "skills", "socratic_elicitation.md")
    )
    low = skill.lower()
    assert "at most 3 rounds" in low
    assert "definition of done" in low
    profile = _read(
        os.path.join("agents", "product_owner", "agents", "product_owner.md")
    )
    assert "socratic_elicitation" in profile
