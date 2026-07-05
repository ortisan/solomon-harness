import uuid
from solomon_harness.tools.database_client import DatabaseClient

db = DatabaseClient(harness_dir='.')

# 1. Log decision
decision_id = db.log_decision(
    title="fix(workflow): check permanently human-gated stages before human autonomy early-return",
    rationale="Reviewed and verified the fix for issue 183. The reordering of stage checks in loop_policy.py correctly blocks permanently human-gated stages like release under the default human autonomy level, while preserving non-gated behavior.",
    outcome="go",
    author="qa",
    branch="bugfix/loop-policy-enforce-human-gate-default",
    commit_sha="2d927c03e4b0e26ff9fad6d5a734c4b4fb68673f"
)
print("Logged decision ID:", decision_id)

# 2. Log handoff
handoff_id = db.log_handoff(
    sender="qa",
    recipient="sre",
    contract_type="release-candidate",
    contract_path=".solomon/handoffs/issue-183-review-to-release.md",
    status="accepted",
    summary="Approved loop policy reordering stage checks to enforce human gates."
)
print("Logged handoff ID:", handoff_id)

# 3. Save session
session_id = str(uuid.uuid4())
db.save_session(
    session_id=session_id,
    agent_name="code_reviewer",
    task="Review PR #203",
    messages="Single Step: run code review workflow stage on PR #203.",
    status="completed",
    issues=["183"]
)
print("Saved session ID:", session_id)

# 4. Link session to handoff
link_id = db.link_session_handoff(session_id, handoff_id)
print("Linked session to handoff:", link_id)
