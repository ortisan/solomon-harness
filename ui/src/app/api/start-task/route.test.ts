// @vitest-environment node
import type { ChildProcess } from "child_process";
import { spawn } from "child_process";
import fs from "fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as routeModule from "./route";

const TOKEN_HEADER = "x-solomon-token";
const TOKEN_ENV_VAR = "SOLOMON_COCKPIT_TOKEN";
const VALID_TOKEN = "correct-secret";

vi.mock("child_process", () => ({
  spawn: vi.fn(),
}));

vi.mock("fs", () => ({
  default: {
    existsSync: vi.fn().mockReturnValue(false),
    readFileSync: vi.fn().mockReturnValue(""),
    mkdirSync: vi.fn(),
    createWriteStream: vi.fn().mockReturnValue({
      pipe: vi.fn(),
      end: vi.fn(),
    }),
  },
  existsSync: vi.fn().mockReturnValue(false),
  readFileSync: vi.fn().mockReturnValue(""),
  mkdirSync: vi.fn(),
  createWriteStream: vi.fn().mockReturnValue({
    pipe: vi.fn(),
    end: vi.fn(),
  }),
}));

function authedRequest(body: unknown): Request {
  return new Request("http://localhost/api/start-task", {
    method: "POST",
    headers: { [TOKEN_HEADER]: VALID_TOKEN, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("start-task API route", () => {
  const originalToken = process.env[TOKEN_ENV_VAR];

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(spawn).mockReturnValue({
      pid: 12345,
      stdout: { pipe: vi.fn() },
      stderr: { pipe: vi.fn() },
      on: vi.fn(),
    } as unknown as ChildProcess);
    process.env[TOKEN_ENV_VAR] = VALID_TOKEN;
  });

  afterEach(() => {
    if (originalToken === undefined) {
      delete process.env[TOKEN_ENV_VAR];
    } else {
      process.env[TOKEN_ENV_VAR] = originalToken;
    }
  });

  it("returns 400 if issueId is missing in POST", async () => {
    const response = await routeModule.POST(authedRequest({}));
    const data = await response.json();

    expect(response.status).toBe(400);
    expect(data.ok).toBe(false);
    expect(data.error).toBe("Missing issueId");
  });

  it("returns 400 if engine is invalid in POST", async () => {
    const response = await routeModule.POST(
      authedRequest({ issueId: "123", engine: "invalid-engine" }),
    );
    const data = await response.json();

    expect(response.status).toBe(400);
    expect(data.ok).toBe(false);
    expect(data.error).toContain("Invalid engine");
  });

  it("spawns the child process and returns 200 on success in POST", async () => {
    const response = await routeModule.POST(authedRequest({ issueId: "123", engine: "claude" }));
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.ok).toBe(true);
    expect(data.status).toBe("running");
    expect(spawn).toHaveBeenCalled();
  });

  it("rejects a path-traversal issueId in POST without touching the filesystem", async () => {
    const response = await routeModule.POST(
      authedRequest({ issueId: "../../../../tmp/pwned", engine: "claude" }),
    );
    const data = await response.json();

    expect(response.status).toBe(400);
    expect(data.ok).toBe(false);
    expect(spawn).not.toHaveBeenCalled();
    expect(vi.mocked(fs.createWriteStream)).not.toHaveBeenCalled();
  });

  it("rejects a path-traversal issueId in GET without reading the filesystem", async () => {
    const req = new Request(
      "http://localhost/api/start-task?issueId=" + encodeURIComponent("../../../../tmp/pwned"),
    );
    const response = await routeModule.GET(req);

    expect(response.status).toBe(400);
    expect(vi.mocked(fs.readFileSync)).not.toHaveBeenCalled();
  });

  it("returns 501 when the cockpit token is not configured (fail closed)", async () => {
    delete process.env[TOKEN_ENV_VAR];
    const req = new Request("http://localhost/api/start-task", {
      method: "POST",
      body: JSON.stringify({ issueId: "123", engine: "claude" }),
    });

    const response = await routeModule.POST(req);
    const data = await response.json();

    expect(response.status).toBe(501);
    expect(data.ok).toBe(false);
    expect(spawn).not.toHaveBeenCalled();
  });

  it("returns 401 when the cockpit token is missing or incorrect", async () => {
    const req = new Request("http://localhost/api/start-task", {
      method: "POST",
      headers: { [TOKEN_HEADER]: "wrong-token" },
      body: JSON.stringify({ issueId: "123", engine: "claude" }),
    });

    const response = await routeModule.POST(req);
    const data = await response.json();

    expect(response.status).toBe(401);
    expect(data.ok).toBe(false);
    expect(spawn).not.toHaveBeenCalled();
  });
});
