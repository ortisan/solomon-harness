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

function zeroColumns() {
  return SEVEN.map((name) => ({ name, count: 0, issues: [] }));
}

// Drive the mocked subprocess for the no-project portfolio path: the `portfolio`
// subcommand returns the composed aggregate JSON the Python composer would print.
function wirePortfolio(portfolio: unknown) {
  vi.mocked(execFile).mockImplementation(((
    _file: string,
    args: string[],
    _options: unknown,
    callback: (err: Error | null, stdout: string, stderr: string) => void,
  ) => {
    if (args.includes("portfolio")) {
      callback(null, JSON.stringify(portfolio), "");
    } else {
      callback(new Error(`unexpected args: ${args.join(" ")}`), "", "");
    }
    return {} as never;
  }) as never);
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

describe("dashboard portfolio route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("bridges to the portfolio subcommand and returns 200 when all OK", async () => {
    wirePortfolio({
      swimlanes: [
        { project: "alpha", status: "OK", total: 2, unmapped: 0, columns: zeroColumns() },
        { project: "beta", status: "OK", total: 1, unmapped: 0, columns: zeroColumns() },
      ],
      columns: zeroColumns().map(({ name, count }) => ({ name, count })),
      total: 3,
      unmapped: 0,
      aggregateStatus: 200,
      overflow: 0,
      notice: null,
    });

    const res = await get();

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.swimlanes.map((s: { project: string }) => s.project)).toEqual([
      "alpha",
      "beta",
    ]);
    expect(body.total).toBe(3);

    // The bridge used the portfolio subcommand as an argv array with shell:false.
    const call = vi.mocked(execFile).mock.calls[0];
    expect((call[1] as string[]).includes("portfolio")).toBe(true);
    expect(Array.isArray(call[1])).toBe(true);
    expect((call[2] as { shell?: boolean }).shell).toBe(false);
    expect(execSync).not.toHaveBeenCalled();
  });

  it("maps a degraded aggregate to 207 and keeps the FORBIDDEN tenant's rows out", async () => {
    const forbiddenTitle = "forbidden-tenant-secret-issue";
    wirePortfolio({
      swimlanes: [
        {
          project: "alpha",
          status: "OK",
          total: 1,
          unmapped: 0,
          columns: SEVEN.map((name) =>
            name === "Backlog"
              ? {
                  name,
                  count: 1,
                  issues: [
                    { github_id: "a1", title: "visible", type_: "feature", status: "Backlog" },
                  ],
                }
              : { name, count: 0, issues: [] },
          ),
        },
        { project: "beta", status: "UNREACHABLE", total: 0, unmapped: 0, columns: zeroColumns() },
        {
          project: "gamma",
          status: "FORBIDDEN",
          httpStatus: 403,
          total: 0,
          unmapped: 0,
          // A regressed composer that leaked the FORBIDDEN tenant's rows: the
          // route must strip them at the boundary so they never reach the wire.
          columns: SEVEN.map((name) =>
            name === "Backlog"
              ? {
                  name,
                  count: 1,
                  issues: [
                    { github_id: "g1", title: forbiddenTitle, type_: "feature", status: "Backlog" },
                  ],
                }
              : { name, count: 0, issues: [] },
          ),
        },
      ],
      columns: zeroColumns().map(({ name, count }) => ({ name, count })),
      total: 1,
      unmapped: 0,
      aggregateStatus: 207,
      overflow: 0,
      notice: null,
    });

    const res = await get();

    // Any degraded tenant lifts the aggregate to 207 Multi-Status.
    expect(res.status).toBe(207);
    const body = await res.json();

    const gamma = body.swimlanes.find(
      (s: { project: string }) => s.project === "gamma",
    );
    expect(gamma.status).toBe("FORBIDDEN");
    expect(gamma.httpStatus).toBe(403);

    // No row of the FORBIDDEN tenant's data appears anywhere in the payload.
    const gammaIssues = gamma.columns.flatMap(
      (c: { issues: unknown[] }) => c.issues,
    );
    expect(gammaIssues).toEqual([]);
    expect(JSON.stringify(body)).not.toContain(forbiddenTitle);

    // Every bridge call is execFile with an argv array and shell disabled.
    for (const call of vi.mocked(execFile).mock.calls) {
      expect(Array.isArray(call[1])).toBe(true);
      expect((call[2] as { shell?: boolean }).shell).toBe(false);
    }
    expect(execSync).not.toHaveBeenCalled();
  });
});

describe("dashboard route tracing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
  });
});
