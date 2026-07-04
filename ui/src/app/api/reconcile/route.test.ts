// @vitest-environment node
import { execFile } from "child_process";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as routeModule from "./route";

const TOKEN_HEADER = "x-solomon-token";
const TOKEN_ENV_VAR = "SOLOMON_COCKPIT_TOKEN";
const VALID_TOKEN = "correct-secret";

vi.mock("child_process", () => ({
  execFile: vi.fn(),
}));

function authedRequest(url = "http://localhost/api/reconcile"): Request {
  return new Request(url, {
    method: "POST",
    headers: { [TOKEN_HEADER]: VALID_TOKEN },
  });
}

describe("reconcile API route", () => {
  const originalToken = process.env[TOKEN_ENV_VAR];

  beforeEach(() => {
    vi.restoreAllMocks();
    process.env[TOKEN_ENV_VAR] = VALID_TOKEN;
  });

  afterEach(() => {
    if (originalToken === undefined) {
      delete process.env[TOKEN_ENV_VAR];
    } else {
      process.env[TOKEN_ENV_VAR] = originalToken;
    }
  });

  it("calls execFile with reconcile subcommand and returns 200 on success", async () => {
    vi.mocked(execFile).mockImplementation(((
      _file: string,
      args: string[],
      _options: unknown,
      callback: (err: Error | null, stdout: string, stderr: string) => void,
    ) => {
      expect(args).toContain("reconcile");
      callback(null, "reconcile complete", "");
      return {} as never;
    }) as never);

    const response = await routeModule.POST(authedRequest());
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.ok).toBe(true);
    expect(data.output).toBe("reconcile complete");
  });

  it("returns 500 on execFile failure", async () => {
    vi.mocked(execFile).mockImplementation(((
      _file: string,
      args: string[],
      _options: unknown,
      callback: (err: Error | null, stdout: string, stderr: string) => void,
    ) => {
      callback(new Error("reconcile failed"), "", "subprocess error");
      return {} as never;
    }) as never);

    const response = await routeModule.POST(authedRequest());
    const data = await response.json();

    expect(response.status).toBe(500);
    expect(data.ok).toBe(false);
    expect(data.error).toBe("reconcile failed");
    expect(data.detail).toBe("subprocess error");
  });

  it("defaults to a dry run when confirm=true is not provided", async () => {
    vi.mocked(execFile).mockImplementation(((
      _file: string,
      args: string[],
      _options: unknown,
      callback: (err: Error | null, stdout: string, stderr: string) => void,
    ) => {
      expect(args).toContain("--dry-run");
      callback(null, "dry run complete", "");
      return {} as never;
    }) as never);

    const response = await routeModule.POST(authedRequest());
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.ok).toBe(true);
  });

  it("performs the live write only when confirm=true is passed", async () => {
    vi.mocked(execFile).mockImplementation(((
      _file: string,
      args: string[],
      _options: unknown,
      callback: (err: Error | null, stdout: string, stderr: string) => void,
    ) => {
      expect(args).not.toContain("--dry-run");
      callback(null, "reconcile complete", "");
      return {} as never;
    }) as never);

    const response = await routeModule.POST(
      authedRequest("http://localhost/api/reconcile?confirm=true"),
    );
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.ok).toBe(true);
  });

  it("returns 501 when the cockpit token is not configured (fail closed)", async () => {
    delete process.env[TOKEN_ENV_VAR];
    const req = new Request("http://localhost/api/reconcile", { method: "POST" });

    const response = await routeModule.POST(req);
    const data = await response.json();

    expect(response.status).toBe(501);
    expect(data.ok).toBe(false);
    expect(execFile).not.toHaveBeenCalled();
  });

  it("returns 401 when the cockpit token is missing or incorrect", async () => {
    const req = new Request("http://localhost/api/reconcile", {
      method: "POST",
      headers: { [TOKEN_HEADER]: "wrong-token" },
    });

    const response = await routeModule.POST(req);
    const data = await response.json();

    expect(response.status).toBe(401);
    expect(data.ok).toBe(false);
    expect(execFile).not.toHaveBeenCalled();
  });
});
