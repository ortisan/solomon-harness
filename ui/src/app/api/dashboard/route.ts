import { execFile } from "child_process";
import path from "path";

// Read-only driving adapter over the ADR-0002 read port. The Node-to-Python
// bridge uses execFile with an argument array and no shell, so a request value
// is an inert argv element and never a shell command (closes the bug #65 RCE).
// There is no POST handler: the cockpit is observe-only in slice 1a.

const MODULE = "solomon_harness.cockpit_read";
const SUBPROCESS_TIMEOUT_MS = 10_000;
const MAX_OUTPUT_BYTES = 8 * 1024 * 1024;

function pythonBin(rootDir: string): string {
  return process.platform === "win32"
    ? path.join(rootDir, ".venv", "Scripts", "python.exe")
    : path.join(rootDir, ".venv", "bin", "python");
}

function readBridge(bin: string, args: string[], cwd: string): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(
      bin,
      args,
      {
        cwd,
        shell: false,
        timeout: SUBPROCESS_TIMEOUT_MS,
        maxBuffer: MAX_OUTPUT_BYTES,
      },
      (error, stdout) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(typeof stdout === "string" ? stdout : stdout.toString("utf8"));
      },
    );
  });
}

export async function GET(request: Request): Promise<Response> {
  try {
    const rootDir = path.resolve(process.cwd(), "..");
    const bin = pythonBin(rootDir);

    const { searchParams } = new URL(request.url);
    const requested = searchParams.get("project") ?? "";

    const projects: string[] = JSON.parse(
      await readBridge(bin, ["-m", MODULE, "projects"], rootDir),
    );
    const selectedProject = requested || projects[0] || "";

    // The requested project is passed as a single argv element. The Python
    // composer validates it against the discovered allowlist and returns
    // found:false for an unknown (or injection) value, which maps to 404 here.
    const board = JSON.parse(
      await readBridge(
        bin,
        ["-m", MODULE, "board", "--project", selectedProject],
        rootDir,
      ),
    );

    const status = board.found === false ? 404 : 200;
    return Response.json({ projects, selectedProject, board }, { status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "read failed";
    return Response.json({ ok: false, error: message }, { status: 500 });
  }
}
