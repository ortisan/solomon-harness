## Flaky tests


- Quarantine, do not delete, and do not paper over with auto-reruns. `pytest-rerunfailures` and `flaky` hide the symptom and let nondeterminism back into the gate. Move the test under a marker (for example `@pytest.mark.quarantine`) that the gating run excludes, open a tracking issue with the id, then fix the root cause: nondeterminism, real time, real network, order coupling, or shared state.
- A flaky test in `release/*` blocks the release until resolved or proven unrelated.
