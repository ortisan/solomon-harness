# ADR-0005: Web UI stack for the delivery cockpit is a Next.js full-stack app

- Status: accepted
- Supersedes: ADR-0003
- Date: 2026-06-28
- Deciders: frontend with software_architect (UX: ux_designer); ratified by the maintainer
- Issue: #44 (gates all slices including #53); Refs #53

## Context and problem statement

ADR-0003 chose a React/Angular SPA backed by a separate Python (FastAPI) read API
as two deployable artifacts. Before that stack was built, a pre-existing React/Next
cockpit on `feat/ui-dashboard` was found and adopted as the slice-1a starting point
(the "salvage the UI, rebuild the data path" decision). That implementation reached
the data layer unsafely — it shelled out to Python and was not strictly read-only
(bug #65) — so the data path was rebuilt while the UI was kept. The realized stack
is therefore not the one ADR-0003 recorded, and the divergence must be captured as a
superseding decision rather than an in-place amendment so the decision log stays a
clean, queryable trail. The hexagonal intent from ADR-0002 is unchanged: the web
surface is a driving adapter over the cockpit read port
(`UI -> read route -> read port -> per-tenant DatabaseClients`); the surface is
read-only with charts and no real-time updates.

## Decision drivers

- A real product surface the `ux_designer` design system and the `frontend` agent
  can own and grow, with a DTCG-token-driven component model.
- Clean hexagonal boundary over the ADR-0002 read port, with read-only enforced and
  the per-project 207/403 partial-render contract honored.
- Secure-by-default at the Node-to-Python boundary: no shell injection surface.
- OpenTelemetry across the full request path, not just one tier.
- Lowest realistic slice-1a cost given a working React/Next UI already exists.

## Considered options

- (a) The ADR-0003 stack: a separate React/Angular SPA plus a standalone FastAPI
  JSON read API — two deployables, two toolchains, CSP/CORS between them, OTel
  spanning two services.
- (b) A Next.js full-stack app: the salvaged React UI with Next.js API route
  handlers that reach the Python read port over a non-shell `execFile` subprocess
  bridge. One deployable, one toolchain; the Next route is the driving adapter over
  the ADR-0002 read port, with no FastAPI layer.
- (c) Keep the salvaged implementation as-is (shell bridge, non-read-only). Rejected
  outright: bug #65 — shell injection surface and write access violate
  secure-by-default and the read-only contract.

## Decision outcome

Chosen: **(b) a Next.js full-stack app**, superseding the SPA + FastAPI decision in
ADR-0003. The React UI already exists and is the design-system handoff target the
`ux_designer` and `frontend` agent want, so the larger value is in keeping it and
fixing the data path rather than rebuilding the UI to fit a two-artifact split. The
hexagonal boundary is preserved: the Next.js API route handler is the single driving
adapter over the ADR-0002 read port, reaching the Python read path through a
subprocess bridge, so there is one deployable instead of two and no FastAPI artifact
to operate. Option (a) is no longer chosen because it duplicates a toolchain and a
deployable for a boundary a single Next route already provides; option (c) is
rejected on security grounds.

The rebuilt data path MUST honor these binding constraints (these are the
constraints the rebuild was held to, closing bug #65):

- **Non-shell bridge.** The Node-to-Python call MUST NOT pass request input through
  a shell. Use an argument-array subprocess call (`execFile` with an args array, no
  shell) or an in-process read path. `execSync` / `exec` on a built command string is
  forbidden — no shell injection surface.
- **Read-only.** The route handlers and the Python read path call only ADR-0002
  read-port methods. Zero writes, no auto-seed of any store, no editable write-back.
- **OpenTelemetry on both artifacts.** Tracing spans the Node route handler AND the
  Python read path, with trace context propagated across the subprocess boundary so a
  cockpit request is one connected trace end to end.

The per-project 207/403 partial-render contract is enforced at the Next route plus
the read port; there is no FastAPI layer to carry it.

### Consequences

- Positive: one deployable and one toolchain instead of two; no CSP/CORS surface
  between SPA and API; the existing React UI is preserved as the design-system
  handoff target; the Next route remains a thin driving adapter over the ADR-0002
  read port, so the hexagonal boundary and the read-only/partial-render contracts are
  unchanged from ADR-0003's intent; trace context is propagated across the one
  subprocess hop rather than across two network services.
- Negative: the Node-to-Python subprocess bridge is a new boundary that must be kept
  non-shell and read-only by review and test, with per-call process spawn cost and
  OTel context propagation across a process hop; the Node runtime and the Python
  harness are coupled in a single deployable, so they version and deploy together; a
  future SPA + API split would now be a migration away from this stack rather than
  the starting point.
- Follow-ups: a future separate SPA + API split (the ADR-0003 shape) remains possible
  but is not built now; keep the bridge non-shell and read-only under test; verify the
  cross-process OTel trace is continuous; size remaining slice-1 work against the
  single-deployable scaffold. ADR-0003 is set to `superseded by ADR-0005`.

## More information

Supersedes ADR-0003 (which recorded the SPA + FastAPI two-artifact stack). Composes
with ADR-0002 (the Next route is a driving adapter over that read port). Closes the
constraint violations recorded in bug #65. Recorded in project memory via
`save_decision`. Backs RAID R-02, D-02, D-03 on #44.
