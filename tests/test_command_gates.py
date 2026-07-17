"""Gate-and-honesty fitness checks for the /solomon-* command prompts and docs.

These assert that the Definition of Done is wired as a real gate (not an orphan
per-agent skill), that every issue family states its Acceptance Criteria /
Definition of Ready / Definition of Done expectation, that the board columns are
reconciled with the named lifecycle stages, and that the loop is described
honestly as host-orchestrated and human-gated rather than fully autonomous.
"""

import os
import re

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

# The criteria as they appear in the gate text itself, pinned with their
# distinctive continuations so generic words elsewhere in the files (the
# "Context" template section, the user-story persona/outcome lines) cannot
# satisfy the assertions.
COMMAND_CRITERIA = (
    "**Problem** (the pain and why now)",
    "**Persona** (a real user type",
    "**Outcome** (the observable change that means success)",
    "**Boundary** (at least one scope limit or constraint)",
    "**Single reading**",
    "**Job behind the solution**",
)

DOC_CRITERIA = (
    "**Problem** — the pain or trigger is stated",
    "**Persona** — who is affected is identifiable",
    "**Outcome** — the observable change that means success is stated",
    "**Boundary** — at least one scope limit or constraint is stated",
    "**Single reading**",
    "**Job behind the solution**",
)


def test_issue_command_wires_the_elicitation_gate():
    body = _read(os.path.join(".claude", "commands", "solomon-issue.md"))
    low = body.lower()
    assert "elicitation gate" in low
    for criterion in COMMAND_CRITERIA:
        assert criterion in body, criterion
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
    for criterion in DOC_CRITERIA:
        assert criterion in doc, criterion
    assert "at most 3 rounds" in low
    assert "at most 4 questions" in low


def test_gemini_mirror_carries_the_elicitation_gate():
    body = _read(os.path.join(".gemini", "commands", "solomon-issue.toml"))
    low = body.lower()
    assert "elicitation gate" in low
    # The mirror embeds the command prompt verbatim: the same criteria,
    # bounds, and trace lines must survive regeneration untruncated.
    for criterion in COMMAND_CRITERIA:
        assert criterion in body, criterion
    assert "at most 3 rounds" in low
    assert "at most 4 questions" in low
    assert "Elicitation: skipped — all 6 readiness criteria met" in body
    assert "Elicitation: skipped (non-interactive)" in body
    assert "Assumptions (unelicited)" in body


def test_product_owner_has_the_socratic_elicitation_skill():
    skill = _read(
        os.path.join("agents", "product_owner", "skills", "socratic_elicitation.md")
    )
    low = skill.lower()
    assert "at most 3 rounds" in low
    assert "at most 4 questions" in low
    assert "Assumptions (unelicited)" in skill
    assert "never re-ask" in low
    profile = _read(
        os.path.join("agents", "product_owner", "agents", "product_owner.md")
    )
    assert "socratic_elicitation" in profile


# --- Capability broker wiring in refine/start (#50, ADR-0008) -----------------


def test_start_and_refine_wire_the_broker_through_the_cli():
    for rel in (
        os.path.join(".claude", "commands", "solomon-start.md"),
        os.path.join(".claude", "commands", "solomon-refine.md"),
    ):
        body = _read(rel)
        low = body.lower()
        assert "capability check" in low, rel
        # The mechanism is the CLI over a JSON file, never inline Python over
        # issue-derived text (PR #213 review B1/B3).
        assert "broker route --file" in body, rel
        assert "broker apply --file" in body, rel
        assert 'python -c "from solomon_harness' not in body, rel
        # Acquisition is human-gated: headless records the gap, never applies
        # (PR #213 review B2, issue #50 AC2).
        assert "human-gated" in low, rel
        assert "fails closed" in low, rel
        # The enumerated gate must be answerable: the tool is allowlisted.
        frontmatter = body.split("---")[1]
        assert "AskUserQuestion" in frontmatter, rel


def test_gemini_mirrors_carry_the_broker_wiring():
    for name in ("start", "refine"):
        body = _read(os.path.join(".gemini", "commands", f"solomon-{name}.toml"))
        assert "broker route --file" in body, name
        assert "broker apply --file" in body, name
        assert 'python -c "from solomon_harness' not in body, name


def test_workflow_doc_defines_the_capability_check():
    doc = _read(os.path.join("docs", "solomon-workflow.md"))
    low = doc.lower()
    assert "capability check" in low
    assert "broker route --file" in doc
    assert "broker apply --file" in doc
    assert "human-gated" in low
    assert "ADR-0008" in doc


def test_loop_documents_gap_surfacing_as_human_gated():
    body = _read(os.path.join(".claude", "commands", "solomon-loop.md"))
    low = body.lower()
    assert "capability gap" in low
    assert "human-gated" in low
    assert "never attempt the acquisition" in low


# --- Spec-driven issue documents (#221 S1, #233) -------------------------------


def test_ci_runs_spec_lint_beside_the_other_validators():
    ci = _read(os.path.join(".github", "workflows", "ci.yml"))
    assert "scripts/spec-lint.py" in ci


def test_issue_command_generates_the_spec_document():
    body = _read(os.path.join(".claude", "commands", "solomon-issue.md"))
    assert "docs/specs/0000-spec-template.md" in body
    assert "docs/specs/<n>-<slug>.md" in body.lower()
    assert "spec-lint.py" in body
    # The fill mapping covers every template section, Design Constraints
    # included — a skipped section would ship raw template text forever.
    for section in (
        "Context", "Problem", "Requirements", "Acceptance Criteria",
        "Design Constraints", "Out of Scope", "Traceability",
    ):
        assert section in body, section
    # The spec ships with the implementation PR, never straight to main.
    assert "never push" in body.lower() or "never pushed" in body.lower()


def test_workflow_doc_defines_the_spec_generation():
    doc = _read(os.path.join("docs", "solomon-workflow.md"))
    low = doc.lower()
    assert "spec generation" in low
    assert "docs/specs/0000-spec-template.md" in doc
    assert "spec-lint.py" in doc
    assert "TBD (refine)" in doc


def test_gemini_mirror_carries_the_spec_generation_step():
    body = _read(os.path.join(".gemini", "commands", "solomon-issue.toml"))
    assert "docs/specs/0000-spec-template.md" in body
    assert "spec-lint.py" in body
    assert "Design Constraints" in body


# --- Implementation-ready spec bar + discovered-problem protocol (#280) --------


def test_spec_template_and_lint_carry_the_implementation_ready_sections():
    template = _read(os.path.join("docs", "specs", "0000-spec-template.md"))
    assert "## Implementation Pointers" in template
    assert "## Verification" in template
    lint = _read(os.path.join("scripts", "spec-lint.py"))
    # Both sections are required by the validator...
    assert '"## Implementation Pointers"' in lint
    assert '"## Verification"' in lint
    # ...and a Ready spec may not keep an unresolved placeholder.
    assert "COMPLETION_GATED_STATUSES" in lint


def test_issue_and_refine_author_the_implementation_ready_sections():
    for rel in (
        os.path.join(".claude", "commands", "solomon-issue.md"),
        os.path.join(".claude", "commands", "solomon-refine.md"),
    ):
        body = _read(rel)
        assert "Implementation Pointers" in body, rel
        assert "Verification" in body, rel
    # Refine is the Ready gate: it resolves placeholders and re-lints.
    refine = _read(os.path.join(".claude", "commands", "solomon-refine.md"))
    assert "spec-lint.py" in refine
    assert "Status: ready" in refine or "Status` to" in refine


def test_start_and_loop_wire_the_discovered_problem_protocol():
    for rel in (
        os.path.join(".claude", "commands", "solomon-start.md"),
        os.path.join(".claude", "commands", "solomon-loop.md"),
    ):
        body = _read(rel)
        low = body.lower()
        assert "discovered-problem protocol" in low, rel
        # A discovery is a new linked issue, never a comment on the parent.
        assert "Refs #" in body, rel
        assert "never" in low and "comment" in low, rel


def test_bug_command_and_template_carry_suspected_location_and_verification():
    cmd = _read(os.path.join(".claude", "commands", "solomon-bug.md"))
    low = cmd.lower()
    assert "suspected location" in low
    assert "verification" in low
    tmpl = _read(os.path.join(".github", "ISSUE_TEMPLATE", "bug_report.md"))
    assert "## Suspected Location" in tmpl
    assert "## Verification" in tmpl


def test_feature_template_carries_implementation_pointers_and_verification():
    tmpl = _read(os.path.join(".github", "ISSUE_TEMPLATE", "feature_conception.md"))
    assert "## Implementation Pointers" in tmpl
    assert "Verification command" in tmpl


def test_workflow_doc_defines_the_discovered_problem_protocol():
    doc = _read(os.path.join("docs", "solomon-workflow.md"))
    low = doc.lower()
    assert "discovered-problem protocol" in low
    assert "implementation pointers" in low
    assert "refs #<parent>" in low


def test_gemini_mirrors_carry_the_new_wiring():
    refine = _read(os.path.join(".gemini", "commands", "solomon-refine.toml"))
    assert "Implementation Pointers" in refine
    assert "spec-lint.py" in refine
    start = _read(os.path.join(".gemini", "commands", "solomon-start.toml"))
    assert "iscovered-problem protocol" in start


# --- Automatic ADR capture gate (#221 S2b, #235) -------------------------------


def test_dedicated_workflow_enforces_the_adr_gate_and_stays_fresh_on_edits():
    gate = _read(os.path.join(".github", "workflows", "adr-gate.yml"))
    assert "scripts/check-adr-gate.py" in gate
    # Body-only edits must re-run the gate (a stale green would let an
    # edited-away ADR line through) — hence the explicit types list...
    assert "types: [opened, synchronize, reopened, edited]" in gate
    # ...the body travels as an env var, never shell-interpolated...
    assert "PR_BODY: ${{ github.event.pull_request.body }}" in gate
    # ...and the workflow stays least-privilege.
    assert "contents: read" in gate
    # Single owner: the heavy CI workflow does not duplicate the gate.
    ci = _read(os.path.join(".github", "workflows", "ci.yml"))
    assert "check-adr-gate" not in ci


def test_workflow_doc_defines_the_adr_gate():
    doc = _read(os.path.join("docs", "solomon-workflow.md"))
    assert "ADR: docs/adrs/NNNN-<slug>.md" in doc
    assert "ADR: not warranted — <reason>" in doc
    assert "check-adr-gate.py" in doc


def test_scan_loops_write_the_canonical_adr_line():
    for name in ("scan-arch", "scan-dedup"):
        body = _read(os.path.join(".claude", "commands", f"solomon-{name}.md"))
        assert "ADR: not warranted — <reason>" in body, name


def test_standing_reconcile_commands_use_the_locked_cli_projection():
    for rel in (
        os.path.join(".claude", "commands", "solomon-reconcile.md"),
        os.path.join(".gemini", "commands", "solomon-reconcile.toml"),
    ):
        body = _read(rel)
        assert "python -m solomon_harness.cli reconcile" in body, rel
        assert "already reports CLOSED" in body, rel
        assert "Never merge" in body, rel


def test_start_release_and_review_carry_the_canonical_adr_line():
    canonical_link = "ADR: docs/adrs/NNNN-<slug>.md"
    canonical_skip = "ADR: not warranted — <reason>"
    for name in ("start", "release"):
        body = _read(os.path.join(".claude", "commands", f"solomon-{name}.md"))
        assert canonical_link in body, name
        assert canonical_skip in body, name
    review = _read(os.path.join(".claude", "commands", "solomon-review.md"))
    assert "check-adr-gate.py" in review


def test_gemini_mirrors_carry_the_canonical_adr_line():
    for name in ("start", "release"):
        body = _read(os.path.join(".gemini", "commands", f"solomon-{name}.toml"))
        assert "ADR: docs/adrs/NNNN-<slug>.md" in body, name
        assert "ADR: not warranted — <reason>" in body, name
    review = _read(os.path.join(".gemini", "commands", "solomon-review.toml"))
    assert "check-adr-gate.py" in review


# --- log_handoff summary required (issue #295) ------------------------------


def test_command_files_pass_log_handoff_summary():
    # summary is the documented mitigation for handoff contract files dying
    # with worktree teardown (docs/solomon-workflow.md, "Handoff contracts"):
    # a resume reads get_latest_activity, and a caller that omits summary
    # leaves that field empty alongside a contract_path that no longer
    # resolves. Every command file that instructs a log_handoff call must
    # carry a concrete summary= argument -- the full glob, not a sample.
    cmd_dir = os.path.join(WORKSPACE, ".claude", "commands")
    offenders = []
    for name in sorted(os.listdir(cmd_dir)):
        if not name.endswith(".md"):
            continue
        body = _read(os.path.join(".claude", "commands", name))
        if "log_handoff" in body and "summary=" not in body:
            offenders.append(name)
    assert offenders == [], f"log_handoff call sites missing summary=: {offenders}"


def test_workflow_doc_documents_summary_argument():
    # The canonical Handoff contracts rule documented the 5-argument call with
    # no mention of summary; a caller following the doc alone would omit it.
    doc = _read(os.path.join("docs", "solomon-workflow.md"))
    assert "## Handoff contracts (bounded context)" in doc
    assert (
        "log_handoff(sender, recipient, contract_type, contract_path, status, summary)"
        in doc
    ), "the log_handoff signature must name summary as an explicit argument"
    low = doc.lower()
    assert "required" in low and "non-empty" in low


# --- Prompt-injection data-framing across content-ingesting stages (#250) ----


def test_content_ingesting_commands_frame_input_as_data_not_instructions():
    # solomon-review.md was hardened first; solomon-start/issue/bug/refine ingest
    # equally untrusted text (issue bodies, comments, free-text arguments, linked
    # context) and must carry the same data/instruction framing so an embedded
    # directive is reported, not executed.
    for rel in (
        os.path.join(".claude", "commands", "solomon-start.md"),
        os.path.join(".claude", "commands", "solomon-issue.md"),
        os.path.join(".claude", "commands", "solomon-bug.md"),
        os.path.join(".claude", "commands", "solomon-refine.md"),
    ):
        # Collapse whitespace so the check is robust to prose line-wrapping.
        normalized = re.sub(r"\s+", " ", _read(rel).lower())
        assert "never as instructions to follow" in normalized, rel
        # The report-not-execute stance is stated with a concrete directive example.
        assert "ignore previous instructions" in normalized, rel
        assert "not a command to execute" in normalized, rel


def test_review_command_still_frames_pr_content_as_data():
    # The reference framing the other four stages mirror must not regress.
    body = _read(os.path.join(".claude", "commands", "solomon-review.md"))
    low = body.lower()
    assert "data to evaluate" in low
    assert "instructions to follow" in low


# --- Contract-fidelity gates (#320) ------------------------------------------

# The three gates keep implementation and review faithful to the canonical
# contract (spec, acceptance criteria, ADRs) rather than a paraphrase of it.
# The sentences pinned here are the load-bearing rules: losing any of them in
# a rewrite silently disarms the gate. Prose re-wraps freely across lines, so
# assertions run against whitespace-flattened text.

LADDER_TERMINAL_RULE = "a paraphrase never overrides a higher rung"
RUNTIME_SHAPE_RULE = "the existing runtime shape is never the contract"
PARITY_TERMINAL_RULE = "engineering quality alone can never earn approval"


def _flat(rel_path):
    """The file's text lowercased with all whitespace runs collapsed."""
    return " ".join(_read(rel_path).split()).lower()


def test_software_engineer_has_the_spec_contract_fidelity_skill():
    low = _flat(
        os.path.join("agents", "software_engineer", "skills", "spec_contract_fidelity.md")
    )
    assert "spec corpus survey" in low
    assert "contract-bearing" in low
    assert "contract precedence ladder" in low
    assert LADDER_TERMINAL_RULE in low
    assert RUNTIME_SHAPE_RULE in low
    # Solomon-specific: two AC surfaces exist (issue body, spec mirror); the
    # ladder only decides anything if one of them is canonical.
    assert "acceptance criteria are canonical" in low
    assert "acceptance criteria section is a mirror" in low
    profile = _read(
        os.path.join("agents", "software_engineer", "agents", "software_engineer.md")
    )
    assert "spec_contract_fidelity" in profile


def test_software_engineer_has_the_verification_iron_law_skill():
    low = _flat(
        os.path.join("agents", "software_engineer", "skills", "verification_iron_law.md")
    )
    assert "verification iron law" in low
    # Fresh evidence: the proving command ran in the same run as the claim.
    assert "same run" in low
    assert "exit code" in low
    # Scope parity: a broad claim needs the broad command, not a subset.
    assert "claim scope" in low
    profile = _read(
        os.path.join("agents", "software_engineer", "agents", "software_engineer.md")
    )
    assert "verification_iron_law" in profile


def test_qa_has_the_spec_contract_parity_skill():
    low = _flat(os.path.join("agents", "qa", "skills", "spec_contract_parity.md"))
    assert "contract parity" in low
    assert "field by field" in low
    assert PARITY_TERMINAL_RULE in low
    assert "a parity mismatch is a blocker" in low
    # The skill owns the verdict-line format, not just the consuming surfaces.
    assert "contract parity: <artifacts" in low
    profile = _read(os.path.join("agents", "qa", "agents", "qa.md"))
    assert "spec_contract_parity" in profile


def test_start_command_wires_the_spec_corpus_survey_before_the_plan():
    low = _flat(os.path.join(".claude", "commands", "solomon-start.md"))
    assert "spec corpus survey" in low
    assert "contract-bearing" in low
    assert "contract precedence ladder" in low
    assert LADDER_TERMINAL_RULE in low
    # The survey feeds the plan, not the other way around: it must be
    # instructed before the PLAN.md authoring text.
    assert low.index("spec corpus survey") < low.index("`plan.md` at the repo root")
    # AC #1: the survey's output lands in PLAN.md — the Plan step's required
    # sections must include the artifact list, and the skill that owns
    # PLAN.md's shape must define the section (review round 1 blocker) in its
    # section list AND its Definition of done checklist (round 2: the DoD
    # bullet and frontmatter description were left unswept).
    assert "contract-bearing artifacts the plan was built from" in low
    plan_skill = _flat(
        os.path.join("agents", "software_engineer", "skills", "plan_authoring.md")
    )
    assert "contract-bearing artifacts" in plan_skill
    assert (
        "problem statement, the contract-bearing artifacts it was built from,"
        " proposed change" in plan_skill
    )
    frontmatter = plan_skill[: plan_skill.index("# authoring plan.md")]
    assert "contract-bearing artifacts" in frontmatter


def test_start_command_requires_the_verification_report_before_the_pr():
    low = _flat(os.path.join(".claude", "commands", "solomon-start.md"))
    assert "verification report" in low
    assert "exit code" in low
    # The report precedes the push/PR confirmation step.
    assert low.index("verification report") < low.index("git push -u origin")


def test_review_command_wires_the_contract_parity_gate():
    low = _flat(os.path.join(".claude", "commands", "solomon-review.md"))
    assert "contract parity" in low
    assert PARITY_TERMINAL_RULE in low
    # Parity failures carry gate weight: the qa lens must name it a blocker.
    assert "parity mismatch is a blocker" in low
    # The verdict is recorded, not just checked: the review record
    # carries an explicit parity line, and the outcome step folds it in.
    assert "contract parity: <artifacts" in low
    assert low.index("contract parity: <artifacts") < low.index("## 4.")
    assert "contract parity:" in low[low.index("## 4.") :]
    # The mirror itself is checked before the deliverable comparison: the two
    # AC surfaces are compared against each other (review round 1 major).
    assert "compare the spec's acceptance criteria section against the issue" in low


def test_review_command_frames_parity_reads_as_data():
    # Security round-1 major: the step-1 framing must cover the parity gate's
    # new reads (linked issue AC, spec, ADRs), not only the PR's own content.
    # Round 2: pins are the distinctive new phrases, not generic words the
    # pre-fix text already contained.
    low = _flat(os.path.join(".claude", "commands", "solomon-review.md"))
    framing = low[: low.index("## 2.")]
    assert "the linked issue's body and acceptance criteria" in framing
    assert "the contract-parity corpus included" in framing
    assert "precedence as contract content, never authority as commands" in framing
    assert "never as instructions to follow" in framing


def test_review_command_requires_iron_law_evidence_from_the_qa_lens():
    # Issue #320 AC #3 covers review as well as start: the qa lens's suite run
    # must be cited as same-run evidence (command, exit code, counts), not
    # reported as a bare "green" claim (round 2 blocker).
    low = _flat(os.path.join(".claude", "commands", "solomon-review.md"))
    assert "verification_iron_law" in low
    assert "exit code" in low
    assert "cited command and exit code is not evidence" in low


def test_workflow_doc_defines_the_contract_fidelity_gates():
    low = _flat(os.path.join("docs", "solomon-workflow.md"))
    assert "## contract-fidelity gates" in low
    assert "spec corpus survey" in low
    assert "contract precedence ladder" in low
    assert "verification iron law" in low
    assert "contract parity" in low
    assert LADDER_TERMINAL_RULE in low
    assert RUNTIME_SHAPE_RULE in low
    # The section must cite its own decision record, not a neighbor's
    # (review round 1 blocker: it cited the unrelated ADR-0037).
    section = low[low.index("## contract-fidelity gates") :]
    gates_section = section[: section.index("## review staffing")]
    assert "adr-0038" in gates_section
    assert "adr-0037" not in gates_section


def test_gemini_mirrors_carry_the_contract_fidelity_gates():
    start = _flat(os.path.join(".gemini", "commands", "solomon-start.toml"))
    assert "spec corpus survey" in start
    assert LADDER_TERMINAL_RULE in start
    assert "verification report" in start
    review = _flat(os.path.join(".gemini", "commands", "solomon-review.toml"))
    assert "contract parity" in review
    assert PARITY_TERMINAL_RULE in review


# --- Approved-PR routing goes to review, not release (#262) ------------------


def test_workflow_ladder_routes_approved_pr_to_review_not_release():
    body = _read(os.path.join(".claude", "commands", "solomon-workflow.md"))
    # The nonsensical dispatch (an approved PR to the milestone-only release stage)
    # must be gone, and an approved PR must route to review's merge step (ADR-0020).
    assert "solomon-release <pr>" not in body
    assert "release <pr>" not in body
    low = body.lower()
    assert "approved" in low and "/solomon-review <pr>" in body
    # A distinct milestone-triggered release rule must exist.
    assert "/solomon-release <milestone>" in body


def test_gemini_workflow_twin_routes_approved_pr_to_review():
    body = _read(os.path.join(".gemini", "commands", "solomon-workflow.toml"))
    assert "solomon-release <pr>" not in body
    assert "/solomon-release <milestone>" in body
