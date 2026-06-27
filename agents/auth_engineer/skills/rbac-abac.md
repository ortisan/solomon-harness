# Authorization Models: RBAC, ABAC, ReBAC

Purpose: choose and implement the right authorization model, enforce it deny-by-default at every endpoint, and close the IDOR/BOLA class of bugs that tops the OWASP API risk list. This skill is for the auth_engineer building the decision layer; pair it with the OAuth/OIDC and session/token skills, which produce the authenticated principal this layer consumes.

Hard rule the whole skill serves: authentication tells you who the caller is; authorization decides what they may do. Never conflate them. A valid token is not a permission.

## When this applies

Every endpoint, every RPC, every message handler, every data-layer read and write that touches tenant or user data. Design the model before the first handler exists; enforce on every path including non-GET verbs, admin routes, batch/list endpoints, GraphQL resolvers, and service-to-service calls. UI gating (hiding a button) is never an authorization control.

## Pick the model before writing policy

The three models are not exclusive; real systems compose them. Pick the primary axis by what your rules actually depend on.

- RBAC (role-based, ANSI/INCITS 359, the NIST RBAC model): permission is a function of the subject's role(s). Use when access maps cleanly to job functions and the resource set is coarse (admin, editor, viewer over a whole tenant). Cheapest to reason about and audit.
- ABAC (attribute-based, NIST SP 800-162): permission is a function of attributes of subject, resource, action, and environment evaluated against policy. Use when decisions depend on context: department match, data classification, time of day, IP/geo, MFA level, ownership fields. RBAC is a degenerate ABAC where the only attribute is `role`.
- ReBAC (relationship-based, Google Zanzibar model): permission is derived from a graph of relationships between subjects and objects ("viewer of a folder inherits viewer on its documents"). Use for hierarchical, shared, nested resources: documents/folders, orgs/teams/repos, parent/child tenancy.

Decision thresholds that signal you have outgrown the current model:

- You are minting roles that encode a resource instance (`editor_project_42`, `owner_doc_991`). That is role explosion. Past a few hundred roles, or any role naming a specific object, move ownership/sharing to ReBAC and keep RBAC for coarse function-level roles.
- Your `if` conditions in policy read more resource fields than roles. That is ABAC; stop forcing it into role tables.
- Permissions cascade through a hierarchy ("can edit doc if can edit its folder if member of its team"). That is ReBAC; an RBAC/ABAC engine will make you recompute the transitive closure by hand and you will get it wrong.

A common, correct composition: RBAC for function-level gates (who can call the admin API at all), ReBAC for object-level sharing (which records this user reaches), ABAC for contextual constraints (only from a managed device, only during market hours).

## Deny-by-default and least privilege (non-negotiable)

- Deny-by-default: the decision function returns deny unless a rule explicitly permits. No rule matched means deny. An error, timeout, or unreachable PDP means deny (fail closed). OWASP ASVS 5.0 V8 requires access controls to fail securely by denying.
- Least privilege: grant the minimum scope, for the minimum time, over the minimum data. No standing admin. Prefer just-in-time elevation with an expiry over a permanent role. Default new roles to empty and add permissions deliberately; never start from "allow all" and subtract.
- Explicit-deny precedence: when the engine supports both allow and deny rules (Cedar `forbid`, XACML deny-overrides), a deny always wins over any permit. Use forbid rules for hard guardrails (suspended account, legal hold) that no grant can override.
- Separation of duties: the subject who requests an action and the one who approves it must be distinguishable in policy for sensitive operations.

## Architecture: decouple the decision from the enforcement

Use the XACML/NIST vocabulary; it keeps roles clean:

- PEP (Policy Enforcement Point): the code at the endpoint that intercepts the request, calls the PDP, and enforces the verdict. Thin. One per protected boundary.
- PDP (Policy Decision Point): evaluates policy against the request context and returns permit/deny. The engine (OPA, Cedar, OpenFGA, etc.).
- PIP (Policy Information Point): supplies attributes/relationships the PDP needs (user dept, resource owner, relationship tuples).
- PAP (Policy Administration Point): where policy is authored, version-controlled, and deployed.

Keep policy out of business logic. The handler should not contain `if user.role == "admin" or ...`. It should call `decide(subject, action, resource, context)` and act on the boolean. This is enforceable in review: scattered inline role checks are a finding.

Standardize the PEP-PDP wire format with OpenID AuthZEN Authorization API 1.0 (Final Specification, OpenID Foundation, 2026). It is a JSON `POST /access/v1/evaluation` of `{subject, action, resource, context}` returning `{"decision": true|false}`. Using it lets you swap PDP vendors without rewriting every PEP. OPA, Cedar, and the commercial engines are converging on it.

```json
// AuthZEN evaluation request a PEP sends to any conformant PDP
{
  "subject":  { "type": "user", "id": "alice@example.com" },
  "action":   { "name": "can_edit" },
  "resource": { "type": "document", "id": "doc-991" },
  "context":  { "mfa": true, "ip": "203.0.113.7", "time": "2026-06-27T14:00:00Z" }
}
```

## RBAC done right

Model the relations, not strings. The NIST core RBAC set is: users, roles, permissions (operation+object), user-role assignment, permission-role assignment, and sessions that activate a subset of a user's roles. Hierarchical RBAC adds role inheritance; constrained RBAC adds separation-of-duty constraints.

- Permissions attach to roles, users attach to roles, never permissions directly to users (that is the path to an unauditable mess).
- Support multi-tenancy with role-per-domain (Casbin's `g, alice, admin, tenant1`) so a user can be admin in one tenant and viewer in another.
- Do not bake fine-grained, per-object permissions into the JWT. Put coarse roles or a stable `sub` in the token (short-lived, 5-15 min access tokens), and resolve fine-grained authorization at request time against current data. Baking permissions into a token freezes them until expiry and leaks the model.

Common failure: encoding object identity into roles. If you need "owner of this specific document," that is a relationship, not a role.

## ABAC done right

A rule is a boolean over attributes of (subject, action, resource, environment). Make the attribute sources explicit (the PIP) and validate them; an ABAC decision is only as trustworthy as its inputs.

- Source subject attributes from the verified token claims and a trusted directory, not from request body fields the caller controls.
- Source resource attributes (owner, classification, tenant) from the system of record at decision time, not from the client.
- Keep environment attributes (time, IP, device posture, MFA level) in the request context the PEP assembles, signed/derived server-side.
- Watch combinatorial blow-up: ABAC is expressive but hard to audit ("who can reach this record?" has no static answer). Mitigate with policy tests that enumerate representative subject/resource pairs and with reverse-query tooling where the engine offers it.

## ReBAC and the Zanzibar model

Store `object#relation@subject` tuples and answer two questions: Check ("does user U have relation R on object O?") and reverse lookups (ListObjects: "which objects can U read?"; Expand: "who can read O?"). Relationships compose through the schema, so "viewer of folder implies viewer of its documents" is one rule, not per-object data.

Google's Zanzibar (2019 paper) runs Drive/YouTube/Calendar at >10M QPS, 99.999% availability, using zookies/snapshot tokens to bound staleness. The open implementations bring that model in-house. Use ReBAC when sharing and hierarchy dominate; it is the right answer to per-object access that RBAC cannot express without role explosion.

The hard part is consistency: a permission check may read a stale replica and allow access just revoked ("new enemy" problem). Both OpenFGA and SpiceDB give you consistency tokens to bound this; use them on revocation-sensitive checks (see tool sections).

## Tool: Open Policy Agent (OPA) + Rego

Status: CNCF graduated. Current line OPA 1.17.x (2026); OPA 1.0 shipped December 2024 and changed Rego defaults. General-purpose PDP for RBAC/ABAC and policy-as-code across APIs, Kubernetes, and gateways. Excellent for attribute logic; it is not a relationship store, so for deep ReBAC graphs pair it with a Zanzibar engine or feed relationships in as data.

Rego v1 (mandatory since 1.0): rules use `if`, multi-value rules use `contains`, `in`/`every` need no import. `import rego.v1` is now a no-op (it was the migration shim). Run `opa fmt --rego-v1` and `opa check` to migrate older policies, and lint with Regal.

Deny-by-default RBAC + ABAC, written for OPA 1.x:

```rego
package authz

# Default deny. Nothing below it can be reached without an explicit allow.
default allow := false

# Function-level RBAC: role grants the action.
allow if {
    some role in input.subject.roles
    grant := role_grants[role][_]
    grant.action == input.action
    grant.resource_type == input.resource.type
}

# Object-level ABAC: owner can always edit their own record,
# but only from an MFA-verified session.
allow if {
    input.action == "edit"
    input.resource.owner == input.subject.id
    input.context.mfa == true
}

role_grants := {
    "viewer": [{"action": "read",  "resource_type": "document"}],
    "editor": [{"action": "read",  "resource_type": "document"},
               {"action": "edit",  "resource_type": "document"}],
    "admin":  [{"action": "read",  "resource_type": "document"},
               {"action": "edit",  "resource_type": "document"},
               {"action": "delete","resource_type": "document"}],
}
```

Deployment and hardening:

- Run OPA as a sidecar or library, not a single shared network PDP you can DDoS or partition yourself away from. If remote, the PEP must fail closed on timeout.
- Never put data fetching or HTTP calls inside Rego (`http.send` in a hot policy is a footgun and a security hole). Push the data in as `input` or via bundles. Keep policy logic pure.
- Use bundles for signed, versioned policy distribution; enable bundle signature verification. Restrict the OPA API (it exposes data and policy); do not expose the diagnostic/management ports publicly. See the CNCF "OPA best practices for a secure deployment" guidance.
- For list/index endpoints, do not call OPA per row. Use partial evaluation (`opa eval --partial`) to compile the policy into a query filter you push to the database, so the data layer returns only authorized rows.
- Test with `opa test` (table-driven cases), covering allow and the deny boundary.

```rego
# policy_test.rego
package authz
test_viewer_cannot_edit if {
    not allow with input as {
        "subject": {"id": "u1", "roles": ["viewer"]},
        "action": "edit",
        "resource": {"type": "document", "owner": "u2"},
        "context": {"mfa": true},
    }
}
```

## Tool: OpenFGA (Zanzibar ReBAC)

Status: CNCF Incubating since October 2025; current 1.17.x (June 2026). Originated at Auth0/Okta. Authorization-model DSL plus Check / ListObjects / ListUsers / Expand APIs. The easiest Zanzibar on-ramp, broad SDK coverage.

Model the schema, then write relationship tuples as data:

```dsl
model
  schema 1.1

type user

type folder
  relations
    define owner: [user]
    define viewer: [user] or owner

type document
  relations
    define parent: [folder]
    # viewer of a document = direct viewer OR viewer of its parent folder
    define viewer: [user] or viewer from parent
    define editor: [user] or owner from parent
```

```python
# PEP: check at the endpoint, fail closed on error.
from openfga_sdk.client import OpenFgaClient
from openfga_sdk.client.models import ClientCheckRequest

async def can(user_id: str, relation: str, obj: str, fga: OpenFgaClient) -> bool:
    try:
        resp = await fga.check(ClientCheckRequest(
            user=f"user:{user_id}", relation=relation, object=obj,
        ))
        return bool(resp.allowed)
    except Exception:
        return False  # deny on PDP failure
```

- For list endpoints use `ListObjects` (returns the objects the user can access) instead of fetching all and filtering; this is the ReBAC answer to the N+1 BOLA pattern.
- Consistency: revocation-sensitive checks should request higher consistency. OpenFGA supports a `HIGHER_CONSISTENCY` option to avoid reading a stale model/tuple after a grant change; default `MINIMIZE_LATENCY` is fine for most reads.
- Keep the authorization model in version control and deploy it like code; tuples are runtime data written when sharing/membership changes.

## Tool: SpiceDB (Zanzibar ReBAC)

Status: by AuthZed; current 1.53.x (June 2026). The most Zanzibar-faithful open implementation: schema language close to the paper, a Watch API for cache invalidation, and explicit consistency controls.

```zed
definition user {}

definition folder {
    relation owner: user
    relation viewer: user
    permission view = viewer + owner
}

definition document {
    relation parent: folder
    relation viewer: user
    relation editor: user
    permission view = viewer + parent->view
    permission edit = editor + parent->owner
}
```

```text
CheckPermission(resource=document:991, permission=view, subject=user:alice,
                consistency=at_least_as_fresh(<zedtoken>))
```

- Consistency knobs you must choose deliberately: `minimize_latency` (fast, may be stale), `at_least_as_fresh(zedtoken)` (read your writes; pass the zedtoken returned by the write that changed the grant), `fully_consistent` (strongest, slowest). For "user was just removed, must not see the doc," use a zedtoken or full consistency. Defaulting everything to fully_consistent throws away SpiceDB's performance; defaulting everything to minimize_latency reopens revocation races.
- Use `LookupResources` for authorized-list endpoints and the Watch API to invalidate downstream caches when relationships change.

## Tool: AWS Cedar / Amazon Verified Permissions

Status: Cedar is AWS's open-source policy language (Rust); current major is Cedar 4.x. Cedar 4 added the `is` type operator and entity tags; Amazon Verified Permissions (AVP), the managed PDP, runs Cedar 4.5 as of 2026. Cedar is a typed ABAC engine that also expresses RBAC and supports formal/static analysis of policies, which is its real differentiator over Rego for high-assurance use.

```cedar
// RBAC: admins may do anything to documents.
permit (
    principal in Role::"admin",
    action,
    resource is Document
);

// ABAC: owners may edit their own documents, MFA required.
permit (
    principal,
    action == Action::"edit",
    resource is Document
)
when { resource.owner == principal && context.mfa == true };

// Hard guardrail: suspended principals are denied everything.
// forbid always overrides any permit.
forbid (principal, action, resource)
when { principal.status == "suspended" };
```

Semantics that matter: default deny (no matching `permit` means deny), and `forbid` takes precedence over `permit`. Define a schema so policies are type-checked and you can run policy analysis (detect contradictions, prove a resource is unreachable). Use AVP when you want a managed, audited PDP on AWS and value validation/analysis; self-host the Cedar engine where you need it in-process. Cedar evaluates in microseconds and AWS benchmarks it well ahead of equivalent Rego, though raw speed rarely decides this; expressiveness, analysis, and operational fit do.

## Tool: Apache Casbin

Status: Apache (incubating); embeddable library across Go, Java, Python (`pycasbin`), Node, Rust, .NET, and more. Built on the PERM metamodel (Policy, Effect, Request, Matchers) defined in a `model.conf`, with policy rows in CSV or a DB adapter. Good when you want authorization in-process with no extra service and a model you can reshape via config.

```ini
# model.conf — RBAC with resource roles, deny-by-default via the matcher
[request_definition]
r = sub, obj, act
[policy_definition]
p = sub, obj, act
[role_definition]
g = _, _
[policy_effect]
e = some(where (p.eft == allow))
[matchers]
m = g(r.sub, p.sub) && r.obj == p.obj && r.act == p.act
```

```csv
p, admin, /documents/*, (GET|POST|PUT|DELETE)
p, viewer, /documents/*, GET
g, alice, admin
g, bob, viewer
```

- The effect `some(where (p.eft == allow))` is implicit deny: no matching allow row means deny. For explicit deny add `!some(where (p.eft == deny))` and deny rows.
- Persist policy in a DB adapter for multi-instance deployments and call `e.LoadPolicy()`/watcher to sync changes; an in-memory CSV diverges across replicas.
- Casbin can express ABAC (`r.obj.Owner == r.sub`) and ReBAC-ish patterns, but for deep graphs a Zanzibar engine is the better tool.

## Tool: Oso / Polar

Status: the embeddable open-source `oso` library is deprecated; current product is Oso Cloud with the Polar policy language. Polar is a declarative logic language that expresses RBAC, ReBAC, and ABAC together, evaluating over facts stored in Oso Cloud and/or your database. Strength: one policy spanning roles, relationships, and attributes, with data-filtering ("list" authorization) built in so list endpoints return only authorized rows.

```polar
actor User {}
resource Document {
  permissions = ["read", "edit"];
  roles = ["viewer", "editor"];
  relations = { folder: Folder };

  "read" if "viewer";
  "edit" if "editor";
  "viewer" if "editor";
  # ReBAC: inherit viewer from the parent folder
  "viewer" if "viewer" on "folder";
}
```

Use Oso when you want managed ReBAC+ABAC with strong list-filtering and you accept a hosted PDP. If you were on the deprecated OSS `oso` crate/package, plan a migration; do not start new work on it.

## Framework-native enforcement (still deny-by-default)

When a dedicated PDP is overkill, enforce in the framework, but keep the same discipline.

- Spring Security: method security with `@PreAuthorize("hasRole('ADMIN') and @owns.check(#id, authentication)")`; configure `authorizeHttpRequests` with `.anyRequest().denyAll()` as the terminal rule so an unmatched route is denied, not permitted. Object-level checks belong in `@PostAuthorize`/`@PreAuthorize` calling an ownership bean, not in the controller body.
- Node/Express, Django, Rails, etc.: a single authorization middleware/decorator on every protected route, with the default route handler denying. Django object permissions, Rails Pundit/CanCanCan policies. The rule is the same: no route reaches a handler without passing an explicit check, and the framework default is deny.

## Closing IDOR / BOLA, BOPLA, BFLA

These are the OWASP API Security Top 10 (2023) authorization failures. API1:2023 BOLA is the #1 risk and accounts for a large share of real API breaches.

- BOLA / IDOR (API1): the caller swaps an object ID (`/documents/991` -> `/documents/992`) and reaches another tenant's data. Fix: derive the subject from the authenticated token, never from request input, and authorize the specific object on every request that names an ID. Make ownership/tenancy part of the query, not a post-fetch check: `SELECT ... WHERE id = :id AND tenant_id = :ctx_tenant`. If the row is not owned, the query returns nothing and you 404 (do not 403 with detail that confirms existence). Re-check on every call in a session, not once.
- Unpredictable IDs (UUIDv4/ULID) are defense-in-depth, not a control. An exposed or leaked ID must still fail the ownership check.
- BOPLA (API3): mass assignment and excessive data exposure at the property level. Bind requests through an explicit allowlist DTO, never the raw model; serialize responses through an allowlist of fields. A user updating their profile must not be able to set `role` or `is_admin` by adding it to the JSON body.
- BFLA (API5): the caller invokes a function their role may not, often a different HTTP verb or an admin route (`DELETE /users/1`, `/admin/...`). Fix: enforce function-level role on every method and route, especially non-GET and administrative ones. Do not rely on a WAF or API gateway alone; it lacks the context to know the verb is unauthorized for that role. Enumerate every route and assert each has an explicit authorization decision; a route with no check is the bug.
- Log every authorization denial with subject, action, resource, and decision reason for anomaly detection. A spike of denials walking sequential IDs is an active BOLA probe.

## Testing authorization (TDD applies)

- Write the failing test first: the denied case before the fix. For every new permission, add a positive test (authorized subject allowed) and a negative test (unauthorized subject, wrong tenant, missing MFA denied). The negative tests are the ones that catch regressions.
- Test the boundary, not just the happy path: cross-tenant access, expired elevation, revoked-then-checked (the ReBAC consistency case), missing attribute (must fail closed), and the unmatched-route default (must deny).
- Mock the PDP and PIP in unit tests so they are deterministic; run a contract/integration test against the real engine (OPA `opa test`, OpenFGA model assertions, Cedar policy tests, SpiceDB `zed validate` with an assertions file) so the policy itself is covered.
- Add an automated route-coverage check that fails the build if any endpoint lacks an authorization decision. Unenforced endpoints are how BOLA ships.

## Common pitfalls to reject in review

- Authorization only in the UI or API gateway while services and the data layer trust each other implicitly.
- Trusting an object ID, tenant, or role taken from the request body/query for the authorization decision instead of from the verified token and the system of record.
- Fail-open: PDP timeout, missing attribute, or unmatched route resulting in allow. It must be deny.
- Role explosion: roles naming specific object instances; a sign you need ReBAC.
- Fine-grained permissions baked into a long-lived JWT, frozen until expiry and impossible to revoke promptly.
- `http.send`/data fetching inside Rego; business logic and data calls leaking into policy.
- List endpoints fetching all rows then filtering in app code (N+1 BOLA), instead of partial evaluation / `ListObjects` / `LookupResources` / data filtering.
- ReBAC checks defaulting to minimize-latency on revocation-sensitive reads, leaving a stale-allow window.
- Inline `if role ==` checks scattered through handlers instead of a single decide() call against a versioned policy.
- New work on the deprecated `oso` OSS library, or unmigrated pre-1.0 Rego (no `if`/`contains`).

## Definition of done

- [ ] Model chosen and justified (RBAC / ABAC / ReBAC or a stated composition); decision recorded in PLAN.md and project memory via `save_decision`, with the role-explosion / attribute-heavy / hierarchy signals that drove it.
- [ ] Policy is deny-by-default: no matching rule denies, and PDP error/timeout/unreachable fails closed; verified by test.
- [ ] Least privilege enforced: new roles start empty, no standing admin, elevation is time-bounded; explicit `forbid`/deny guardrails override grants where required.
- [ ] Decision decoupled from enforcement (PDP/PEP/PIP separated); no inline role checks in handlers; PEP wire format aligned to AuthZEN where a remote PDP is used.
- [ ] Every endpoint, verb, and service-to-service call has an explicit authorization decision; an automated route-coverage check fails the build on any unguarded endpoint.
- [ ] Object-level authorization on every request that names an ID; ownership/tenancy is part of the data query; non-owned access returns 404, not a revealing 403.
- [ ] Property-level controls in place: input bound through allowlist DTOs (no mass assignment of `role`/`is_admin`), responses serialized through an output allowlist.
- [ ] Function-level (BFLA) checks on all verbs and admin routes; not relying on WAF/gateway for context-dependent decisions.
- [ ] List/index endpoints return only authorized rows via partial evaluation / `ListObjects` / `LookupResources` / data filtering, not fetch-then-filter.
- [ ] ReBAC consistency chosen per check: revocation-sensitive reads use `HIGHER_CONSISTENCY` / `at_least_as_fresh` (zedtoken) / `fully_consistent`; rationale documented.
- [ ] Engine pinned to a current version (OPA 1.17.x / OpenFGA 1.17.x / SpiceDB 1.53.x / Cedar 4.x as applicable); policy in version control and deployed like code; OPA bundles signed, management ports not public.
- [ ] Tests cover positive and negative cases, cross-tenant, missing-attribute, revoked-then-checked, and unmatched-route default; PDP/PIP mocked in unit tests; policy covered by the engine's own test tool (TDD: denied case written first).
- [ ] Authorization denials logged with subject/action/resource/reason for anomaly detection.
- [ ] Aligned with OWASP ASVS 5.0 V8 and the OWASP API Security Top 10 2023 (API1 BOLA, API3 BOPLA, API5 BFLA); handed to the security specialist for review.

## References

- OWASP API Security Top 10 (2023), API1 BOLA: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP API3:2023 BOPLA: https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
- OWASP API5:2023 BFLA: https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/
- OWASP ASVS 5.0 V8 Authorization: https://github.com/OWASP/ASVS/blob/master/5.0/en/0x17-V8-Authorization.md
- NIST SP 800-162 (ABAC): https://nvlpubs.nist.gov/nistpubs/specialpublications/nist.sp.800-162.pdf
- NIST SP 800-178 (comparison of the XACML and NGAC ABAC standards): https://nvlpubs.nist.gov/nistpubs/specialpublications/nist.sp.800-178.pdf
- OPA docs and OPA 1.0 notes: https://www.openpolicyagent.org/docs ; https://blog.openpolicyagent.org/opa-1-0-is-coming-heres-what-you-need-to-know-c8fb0d258368
- Rego style guide and Regal linter: https://www.openpolicyagent.org/docs/style-guide
- OpenFGA (Zanzibar ReBAC): https://openfga.dev/docs/authorization-concepts
- SpiceDB / AuthZed and Zanzibar: https://authzed.com/docs/spicedb/concepts/zanzibar
- Cedar policy language: https://docs.cedarpolicy.com/ ; Amazon Verified Permissions Cedar 4.5: https://aws.amazon.com/about-aws/whats-new/2025/08/amazon-verified-permissions-cedar-4-5/
- Apache Casbin: https://casbin.org/
- Oso / Polar: https://www.osohq.com/docs/develop/policies/rbac
- OpenID AuthZEN Authorization API 1.0: https://openid.net/specs/authorization-api-1_0.html
- CNCF OPA secure deployment best practices: https://www.cncf.io/blog/2025/03/18/open-policy-agent-best-practices-for-a-secure-deployment/
