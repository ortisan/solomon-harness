import { execFile } from "child_process";
import path from "path";
import type { Span } from "@opentelemetry/api";
import { isSpanContextValid, SpanStatusCode, trace } from "@opentelemetry/api";

// Read-only driving adapter over the ADR-0002 read port. The Node-to-Python
// bridge uses execFile with an argument array and no shell, so a request value
// is an inert argv element and never a shell command (closes the bug #65 RCE).
// There is no POST handler: the cockpit is observe-only in slice 1a. The GET is
// wrapped in an OpenTelemetry span so the read path is traced across both the
// Next route and the Python composer (ADR-0003).

const MODULE = "solomon_harness.cockpit_read";
const SUBPROCESS_TIMEOUT_MS = 10_000;
const MAX_OUTPUT_BYTES = 8 * 1024 * 1024;

// Aggregate HTTP statuses mirrored from the Python composer: 200 when every
// tenant read cleanly, 207 Multi-Status when any tenant is degraded.
const HTTP_OK = 200;
const HTTP_MULTI_STATUS = 207;
const HTTP_NOT_FOUND = 404;

// Per-project read outcome carried inside the 207 envelope; only OK lanes hold
// issue rows. Mirrors the Python composer's STATUS_OK.
const STATUS_OK = "OK";

interface DegradableColumn {
  issues: unknown[];
  [key: string]: unknown;
}

interface PortfolioSwimlane {
  status: string;
  columns: DegradableColumn[];
  [key: string]: unknown;
}

interface AggregatePortfolio {
  aggregateStatus: number;
  swimlanes: PortfolioSwimlane[];
  [key: string]: unknown;
}

// Defense in depth at the transport boundary: a degraded (non-OK) swimlane must
// carry no issue rows, even if the upstream composer regressed and sent some, so
// a FORBIDDEN or UNREACHABLE tenant's data never reaches the wire (information
// disclosure). OK lanes pass through untouched.
function withoutDegradedRows(portfolio: AggregatePortfolio): AggregatePortfolio {
  const swimlanes = portfolio.swimlanes.map((lane) =>
    lane.status === STATUS_OK
      ? lane
      : {
          ...lane,
          columns: lane.columns.map((column) => ({ ...column, issues: [] })),
        },
  );
  return { ...portfolio, swimlanes };
}

const tracer = trace.getTracer("solomon_harness.cockpit_dashboard_route");

function pythonBin(rootDir: string): string {
  return process.platform === "win32"
    ? path.join(rootDir, ".venv", "Scripts", "python.exe")
    : path.join(rootDir, ".venv", "bin", "python");
}

// Build a W3C traceparent for the span and add it to the subprocess env, so the
// Python read path can join the same trace. Reads the span context directly
// (no ContextManager is required) and returns the env unchanged when the span
// context is invalid (e.g. when no tracer provider is registered in production).
function withTraceparent(env: NodeJS.ProcessEnv, span: Span): NodeJS.ProcessEnv {
  const ctx = span.spanContext();
  if (!isSpanContextValid(ctx)) {
    return env;
  }
  const flags = (ctx.traceFlags ?? 0).toString(16).padStart(2, "0");
  return { ...env, traceparent: `00-${ctx.traceId}-${ctx.spanId}-${flags}` };
}

function readBridge(
  bin: string,
  args: string[],
  cwd: string,
  env: NodeJS.ProcessEnv,
): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(
      bin,
      args,
      {
        cwd,
        env,
        shell: false,
        timeout: SUBPROCESS_TIMEOUT_MS,
        maxBuffer: MAX_OUTPUT_BYTES,
      },
      (error, stdout) => {
        if (error) {
          reject(error);
          return;
        }
        // execFile with the default encoding resolves stdout as a string.
        resolve(stdout);
      },
    );
  });
}

// Portfolio path (no ?project=): bridge to the cross-tenant `portfolio`
// subcommand and map the composer's aggregateStatus straight to the HTTP status
// (200 all-OK, else 207). The per-project 403/UNREACHABLE semantics travel inside
// the 207 envelope as each swimlane's status, so no degraded tenant's rows leak.
async function portfolioResponse(
  bin: string,
  rootDir: string,
  env: NodeJS.ProcessEnv,
  user: string,
  span: Span,
): Promise<Response> {
  // The user filter is applied server-side by the composer, so a non-matching
  // tenant's rows never reach the wire. The value travels as one inert argv
  // element (shell:false), so an injection value runs as nothing (bug #65).
  const args = user
    ? ["-m", MODULE, "portfolio", "--user", user]
    : ["-m", MODULE, "portfolio"];
  const portfolio: AggregatePortfolio = JSON.parse(
    await readBridge(bin, args, rootDir, env),
  );
  span.setAttribute("cockpit.aggregate_status", portfolio.aggregateStatus);
  const status =
    portfolio.aggregateStatus === HTTP_MULTI_STATUS ? HTTP_MULTI_STATUS : HTTP_OK;
  return Response.json(withoutDegradedRows(portfolio), { status });
}

// Single-project drill-down path (slice 1a): the requested project is passed as
// one argv element. The Python composer validates it against the discovered
// allowlist and returns found:false for an unknown (or injection) value, mapped
// to 404 here.
async function boardResponse(
  bin: string,
  rootDir: string,
  env: NodeJS.ProcessEnv,
  requested: string,
  span: Span,
): Promise<Response> {
  const board = JSON.parse(
    await readBridge(bin, ["-m", MODULE, "board", "--project", requested], rootDir, env),
  );
  const projects: string[] = board.projects;
  const selectedProject: string = board.selectedProject;
  span.setAttribute("cockpit.project", selectedProject);
  const status = board.found === false ? HTTP_NOT_FOUND : HTTP_OK;
  return Response.json({ projects, selectedProject, board }, { status });
}

export async function GET(request: Request): Promise<Response> {
  return tracer.startActiveSpan("cockpit.dashboard_route", async (span) => {
    try {
      const rootDir = path.resolve(process.cwd(), "..");
      const bin = pythonBin(rootDir);

      const { searchParams } = new URL(request.url);
      const requested = searchParams.get("project") ?? "";
      const user = searchParams.get("user") ?? "";
      span.setAttribute("cockpit.project", requested);

      // Propagate the active trace to the Python read path via the subprocess env.
      const env = withTraceparent(process.env, span);

      // No project selected renders the cross-tenant portfolio (optionally
      // narrowed to one person); a selected project drills down into that one
      // tenant's board.
      if (!requested) {
        return await portfolioResponse(bin, rootDir, env, user, span);
      }
      return await boardResponse(bin, rootDir, env, requested, span);
    } catch (error) {
      // Record the failure on the span and log the detail server-side; the
      // client receives a generic message so internal paths and errors never
      // leak to the wire (information disclosure).
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: "dashboard read failed" });
      console.error("dashboard read failed", error);
      return Response.json(
        { ok: false, error: "Internal Server Error" },
        { status: 500 },
      );
    } finally {
      span.end();
    }
  });
}
