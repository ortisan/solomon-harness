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

export async function GET(request: Request): Promise<Response> {
  return tracer.startActiveSpan("cockpit.dashboard_route", async (span) => {
    try {
      const rootDir = path.resolve(process.cwd(), "..");
      const bin = pythonBin(rootDir);

      const { searchParams } = new URL(request.url);
      const requested = searchParams.get("project") ?? "";
      span.setAttribute("cockpit.project", requested);

      // Propagate the active trace to the Python read path via the subprocess env.
      const env = withTraceparent(process.env, span);

      const projects: string[] = JSON.parse(
        await readBridge(bin, ["-m", MODULE, "projects"], rootDir, env),
      );
      const selectedProject = requested || projects[0] || "";
      span.setAttribute("cockpit.project", selectedProject);

      // The requested project is passed as a single argv element. The Python
      // composer validates it against the discovered allowlist and returns
      // found:false for an unknown (or injection) value, which maps to 404 here.
      const board = JSON.parse(
        await readBridge(
          bin,
          ["-m", MODULE, "board", "--project", selectedProject],
          rootDir,
          env,
        ),
      );

      const status = board.found === false ? 404 : 200;
      return Response.json({ projects, selectedProject, board }, { status });
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
