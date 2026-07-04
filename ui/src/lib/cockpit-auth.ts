// Shared-secret auth guard for the cockpit's mutating write routes
// (start-task, reconcile). docs/adr/0005 makes the cockpit read-only by
// contract; these two routes are documented exceptions that mutate state, so
// they must not be reachable without a credential. There is no broader
// auth/authorization layer in ui/src, so this guard fails closed: if the
// shared secret is not configured at all, every request is rejected rather
// than treated as authenticated.

export const TOKEN_HEADER = "x-solomon-token";
export const TOKEN_ENV_VAR = "SOLOMON_COCKPIT_TOKEN";

// Returns a Response to send back immediately when the request is not
// authorized, or null when the request may proceed.
export function checkCockpitAuth(request: Request): Response | null {
  const configuredToken = process.env[TOKEN_ENV_VAR];
  if (!configuredToken) {
    return Response.json(
      { ok: false, error: "Cockpit write endpoint is not configured" },
      { status: 501 },
    );
  }

  const providedToken = request.headers.get(TOKEN_HEADER);
  if (!providedToken || providedToken !== configuredToken) {
    return Response.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  return null;
}
