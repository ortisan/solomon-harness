// @vitest-environment node
import { execFile, execSync } from "child_process";
import { SpanStatusCode, trace } from "@opentelemetry/api";
import {
  BasicTracerProvider,
  InMemorySpanExporter,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as routeModule from "./route";

vi.mock("child_process", () => ({
  execFile: vi.fn(),
  execSync: vi.fn(),
}));

// Capture the route spans in memory so the tracing assertions can read them.
const spanExporter = new InMemorySpanExporter();
trace.setGlobalTracerProvider(
  new BasicTracerProvider({
    spanProcessors: [new SimpleSpanProcessor(spanExporter)],
  }),
);

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

// Drive the mocked subprocess: `board` returns a board containing `projects` and `selectedProject`.
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
      const project = args.includes("--project") ? args[args.indexOf("--project") + 1] : KNOWN_TENANTS[0];
      const found = KNOWN_TENANTS.includes(project);
      callback(
        null,
        JSON.stringify({
          project,
          found,
          columns: emptyColumns(),
          total: 0,
          unmapped: 0,
          projects: KNOWN_TENANTS,
          selectedProject: project,
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
    routeModule.cache.clear();
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

  it("caches board responses for 5 seconds to prevent DoS", async () => {
    const project = "caching-test";
    KNOWN_TENANTS.push(project);
    try {
      const res1 = await get(project);
      expect(res1.status).toBe(200);
      
      const res2 = await get(project);
      expect(res2.status).toBe(200);
      
      const boardCalls = vi
        .mocked(execFile)
        .mock.calls.filter((c) => (c[1] as string[]).includes("board") && (c[1] as string[]).includes(project));
      expect(boardCalls.length).toBe(1);
    } finally {
      KNOWN_TENANTS.pop();
    }
  });

  it("writes subprocess stderr to process.stderr to prevent trace discard", async () => {
    const stderrSpy = vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    
    vi.mocked(execFile).mockImplementationOnce(((
      _file: string,
      args: string[],
      _options: unknown,
      callback: (err: Error | null, stdout: string, stderr: string) => void,
    ) => {
      callback(
        null,
        JSON.stringify({
          project: "alpha",
          found: true,
          columns: emptyColumns(),
          total: 0,
          unmapped: 0,
          projects: KNOWN_TENANTS,
          selectedProject: "alpha",
        }),
        "mock trace span logs to stderr",
      );
      return {} as never;
    }) as never);

    await get("alpha");
    expect(stderrSpy).toHaveBeenCalledWith("mock trace span logs to stderr");
    stderrSpy.mockRestore();
  });
});

describe("dashboard route tracing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routeModule.cache.clear();
    spanExporter.reset();
    wireBridge();
  });

  function routeSpan() {
    return spanExporter
      .getFinishedSpans()
      .find((s) => s.name === "cockpit.dashboard_route");
  }

  it("records a cockpit.dashboard_route span carrying the project", async () => {
    await get("alpha");

    const span = routeSpan();
    expect(span).toBeDefined();
    expect(span!.attributes["cockpit.project"]).toBe("alpha");
  });

  it("injects a W3C traceparent into the bridge subprocess env", async () => {
    await get("alpha");

    // The active trace is propagated to the Python read path via the env, so
    // both artifacts can be correlated; the value is a valid W3C traceparent.
    const call = vi.mocked(execFile).mock.calls[0];
    const env = (call[2] as { env?: Record<string, string> }).env;
    expect(env?.traceparent).toMatch(
      /^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$/,
    );
  });

  it("records the exception, sets ERROR, and returns a generic 500 on failure", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const secret = "ENOENT spawn /opt/secret/python";
    vi.mocked(execFile).mockImplementation(((
      _file: string,
      _args: string[],
      _options: unknown,
      callback: (err: Error | null, stdout: string, stderr: string) => void,
    ) => {
      callback(new Error(secret), "", "");
      return {} as never;
    }) as never);

    const res = await get("alpha");

    // The client gets a generic body; the internal detail never leaks.
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error).toBe("Internal Server Error");
    expect(JSON.stringify(body)).not.toContain(secret);

    // The span records the failure for the audit trace.
    const span = routeSpan();
    expect(span).toBeDefined();
    expect(span!.status.code).toBe(SpanStatusCode.ERROR);
    expect(span!.events.some((e) => e.name === "exception")).toBe(true);
    errorSpy.mockRestore();
  });
});
