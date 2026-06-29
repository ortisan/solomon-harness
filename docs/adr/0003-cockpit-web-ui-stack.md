# ADR-0003: Web UI stack for the delivery cockpit

- Status: superseded by ADR-0005
- Date: 2026-06-28
- Deciders: frontend with software_architect (UX: ux_designer); ratified by the maintainer
- Issue: #44 (gates all slices including #53)

## Context and problem statement

The cockpit (#44) needs a web surface, but the project has none today and is a
Python CLI/harness. The surface is read-only with charts (burndown, #57) and no
real-time updates (out of scope per the epic). Hexagonal is the project default, so
the UI must be a driving adapter over the cockpit read port defined in ADR-0002
(`UI -> read API -> read port -> per-tenant DatabaseClients`). The existing
`frontend` agent owns React/Angular and the new `ux_designer` owns a DTCG
design-token design system, so the stack must be a viable handoff target for both.
Non-functional requirements: OpenTelemetry instrumentation and secure-by-default
(read-only enforced at the port; the per-project 403 path is AC-COCKPIT-01.6). The
choice gates slice 1 (D-02, R-02).

## Decision drivers

- A real product surface a design system (ux_designer) and the frontend agent can
  own and grow, not a throwaway.
- Clean hexagonal boundary: the Python read API is the driving adapter over the
  ADR-0002 read port; the SPA consumes JSON.
- Richest fit for a DTCG-token-driven design system and component model.
- Observability and secure-by-default at the API boundary.

## Considered options

- (a) Python-native server-rendered: FastAPI + Jinja templates + HTMX, JSON
  endpoint for charts. Smallest new toolchain; lowest slice-1a cost.
- (b) Separate React/Angular SPA + Python read API (FastAPI JSON): the frontend
  agent's stack; richest interactivity and design-system component fit; introduces a
  full JS build/test/deploy toolchain.
- (c) Lightweight Python dashboarding (Streamlit/Dash/Panel): fastest to charts,
  weakest hexagonal and design-system fit.

## Decision outcome

Chosen: **(b) a React/Angular SPA backed by a Python (FastAPI) read API.** The
software_architect's recommendation was (a) on cost grounds, but the maintainer
ratified (b) deliberately: the cockpit is a long-lived product surface that the new
`ux_designer` is building a DTCG design system for and that the `frontend` agent
owns in React/Angular, so the richest design-system and component fit is worth the
larger toolchain. The hexagonal boundary is preserved — the FastAPI JSON read API
is the driving adapter over the ADR-0002 read port, and the SPA is a second adapter
consuming it. The specific framework (React vs Angular) is a follow-up for the
frontend agent and ux_designer to confirm at slice 1a; both are within the frontend
agent's remit. Option (c) is rejected: the framework owns the app structure and
event loop, breaking the thin-adapter boundary, fighting a token-driven design
system, and weakening OpenTelemetry/deploy/auth control.

### Consequences

- Positive: the frontend agent works in its native stack; the ux_designer's DTCG
  tokens map to a full component library, the best design-system handoff; the read
  API cleanly enforces read-only and the per-project 207/403 partial-render
  contract at the HTTP boundary; the surface scales to richer interactivity later
  without rework.
- Negative: a full JS build/test/deploy toolchain and two deployable artifacts
  (SPA + API) with CSP/CORS to manage; higher slice-1a cost than (a) — the walking
  skeleton must scaffold both the SPA and the read API before anything renders;
  OpenTelemetry spans two artifacts.
- Follow-ups: React chosen as the SPA framework (2026-06-28, maintainer-ratified) for
  its dashboard/charting ecosystem and clean DTCG-token component mapping; ux_designer
  confirms the token-to-component build; set CSP/CORS and the OTel trace context across
  SPA and API; size slice 1a against the heavier scaffold.

## Effect on the slice-1 (#53) split

Under (b), the 1a/1b split still applies but 1a is heavier: **1a** scaffolds the SPA
shell + the FastAPI read API + single-project render + the project-discovery
function (validating A-02); **1b** carries the cross-tenant aggregation read port
(ADR-0002), the 207/403 partial-render contract, bounded-concurrency reads with
per-project timeout, and the p95 < 2s assertion. Re-estimate 1a against the SPA+API
scaffold; if it exceeds 8 SP, split the SPA shell and the read API into separate
increments.

## More information

Composes with ADR-0002 (the read API sits on that read port). Recorded in project
memory via `save_decision`. Backs RAID R-02, D-02, D-03 on #44.

## Amendment (2026-06-28): Next.js full-stack instead of SPA + FastAPI

A pre-existing React/Next cockpit on `feat/ui-dashboard` is being adopted as the
frontend starting point for slice 1a (the "salvage the UI, rebuild the data path"
decision). This changes the realized stack from "React SPA + a separate Python
FastAPI read API" to a Next.js full-stack app: a React UI with Next.js API route
handlers that reach the Python read port. The hexagonal intent is unchanged — the
Next route is the driving adapter over the ADR-0002 read port — but there is no
separate FastAPI artifact, so there is one deployable instead of two.

The existing implementation violated the constraints below (see bug #65); the
rebuild MUST honor them:

- The Node-to-Python bridge MUST NOT pass request input through a shell (no
  `execSync` on a built command string). Use an argument-array subprocess call with
  no shell, or an in-process read path. Shell injection is forbidden.
- Read-only: the route handlers and the Python read path call only ADR-0002
  read-port methods; zero writes, no auto-seed, no editable write-back.
- OpenTelemetry on the Node route and the Python read path; the per-project
  207/403 contract is enforced at the Next route + read port (no FastAPI layer).

A future separate SPA + API split remains possible but is not built now.

This amendment is superseded by ADR-0005, which now carries the realized
decision (the Next.js full-stack app with a non-shell bridge over the ADR-0002
read port). This file is retained for history; see ADR-0005 for the live decision.
