// @vitest-environment node
import { execFile, execSync } from "child_process";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as routeModule from "./route";

vi.mock("child_process", () => ({
  execFile: vi.fn(),
  execSync: vi.fn(),
}));

const SEVEN = [
  "Ideas",
  "Backlog",
  "Ready",
  "In Progress",
  "Code Review",
  "QA",
  "Done",
];

const KNOWN_TENANTS = ["alpha"];

function emptyColumns() {
  return SEVEN.map((name) => ({ name, count: 0, issues: [] }));
}

// Drive the mocked subprocess: `projects` returns the known tenants; `board`
// returns a board whose `found` reflects allowlist membership of --project.
function wireBridge() {
  vi.mocked(execFile).mockImplementation(((
    _file: string,
    args: string[],
    _options: unknown,
    callback: (err: Error | null, stdout: string, stderr: string) => void,
  ) => {
    if (args.includes("projects")) {
      callback(null, JSON.stringify(KNOWN_TENANTS), "");
    } else if (args.includes("board")) {
      const project = args[args.indexOf("--project") + 1];
      const found = KNOWN_TENANTS.includes(project);
      callback(
        null,
        JSON.stringify({
          project,
          found,
          columns: emptyColumns(),
          total: 0,
          unmapped: 0,
        }),
        "",
      );
    } else {
      callback(new Error(`unexpected args: ${args.join(" ")}`), "", "");
    }
    return {} as never;
  }) as never);
}

function get(project?: string) {
  const url =
    project === undefined
      ? "http://localhost/api/dashboard"
      : `http://localhost/api/dashboard?project=${encodeURIComponent(project)}`;
  return routeModule.GET(new Request(url));
}

describe("dashboard read route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    wireBridge();
  });

  it("exports a GET handler and no POST handler", () => {
    expect(typeof routeModule.GET).toBe("function");
    expect((routeModule as Record<string, unknown>).POST).toBeUndefined();
  });

  it("passes the project as an inert argv element with shell:false", async () => {
    const injection = "alpha; rm -rf ~";
    const res = await get(injection);

    // The injection value reaches execFile as exactly one argv element; no
    // shell parses it, so the destructive command cannot run.
    const boardCall = vi
      .mocked(execFile)
      .mock.calls.find((c) => (c[1] as string[]).includes("board"));
    expect(boardCall).toBeDefined();
    const argv = boardCall![1] as string[];
    expect(argv[argv.indexOf("--project") + 1]).toBe(injection);

    // Every subprocess call uses an argument array with shell disabled.
    for (const call of vi.mocked(execFile).mock.calls) {
      expect(Array.isArray(call[1])).toBe(true);
      expect((call[2] as { shell?: boolean }).shell).toBe(false);
    }

    // No shell-string command path is ever used.
    expect(execSync).not.toHaveBeenCalled();

    // An injection value is not a known tenant, so it is rejected, not run.
    expect(res.status).toBe(404);
  });

  it("returns 404 for a project outside the discovered allowlist", async () => {
    const res = await get("ghost");
    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body.board.found).toBe(false);
    // Only read subcommands are ever bridged; no write subcommand is issued.
    for (const call of vi.mocked(execFile).mock.calls) {
      const args = call[1] as string[];
      expect(args.includes("projects") || args.includes("board")).toBe(true);
    }
  });

  it("renders a known tenant board with status 200", async () => {
    const res = await get("alpha");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.selectedProject).toBe("alpha");
    expect(body.board.found).toBe(true);
    expect(body.projects).toEqual(KNOWN_TENANTS);
  });
});
