// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { TOKEN_HEADER, checkCockpitAuth } from "./cockpit-auth";

const ENV_VAR = "SOLOMON_COCKPIT_TOKEN";

describe("checkCockpitAuth", () => {
  const originalToken = process.env[ENV_VAR];

  beforeEach(() => {
    delete process.env[ENV_VAR];
  });

  afterEach(() => {
    if (originalToken === undefined) {
      delete process.env[ENV_VAR];
    } else {
      process.env[ENV_VAR] = originalToken;
    }
  });

  it("fails closed with 501 when the token env var is not configured at all", () => {
    const request = new Request("http://localhost/api/start-task", {
      method: "POST",
      headers: { [TOKEN_HEADER]: "anything" },
    });

    const result = checkCockpitAuth(request);

    expect(result).not.toBeNull();
    expect(result?.status).toBe(501);
  });

  it("rejects a request with no token header when auth is configured", async () => {
    process.env[ENV_VAR] = "correct-secret";
    const request = new Request("http://localhost/api/start-task", { method: "POST" });

    const result = checkCockpitAuth(request);

    expect(result).not.toBeNull();
    expect(result?.status).toBe(401);
  });

  it("rejects a request with an incorrect token when auth is configured", () => {
    process.env[ENV_VAR] = "correct-secret";
    const request = new Request("http://localhost/api/start-task", {
      method: "POST",
      headers: { [TOKEN_HEADER]: "wrong-secret" },
    });

    const result = checkCockpitAuth(request);

    expect(result).not.toBeNull();
    expect(result?.status).toBe(401);
  });

  it("allows a request with the correct token when auth is configured", () => {
    process.env[ENV_VAR] = "correct-secret";
    const request = new Request("http://localhost/api/start-task", {
      method: "POST",
      headers: { [TOKEN_HEADER]: "correct-secret" },
    });

    const result = checkCockpitAuth(request);

    expect(result).toBeNull();
  });
});
