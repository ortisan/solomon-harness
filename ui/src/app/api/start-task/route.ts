import { spawn } from "child_process";
import fs from "fs";
import path from "path";

import { checkCockpitAuth } from "../../../lib/cockpit-auth";

function pythonBin(rootDir: string): string {
  return process.platform === "win32"
    ? path.join(rootDir, ".venv", "Scripts", "python.exe")
    : path.join(rootDir, ".venv", "bin", "python");
}

// issueId travels straight from the request into a log file path, so it must
// be restricted to a strict allowlist before it ever touches path.join.
const ISSUE_ID_PATTERN = /^[A-Za-z0-9_-]+$/;

// Builds the per-issue log file path, rejecting anything that would place the
// result outside the intended `.solomon/logs` directory. The allowlist regex
// above should already block traversal sequences and separators, but the
// resolved-path containment check is kept as defense in depth in case the
// pattern is ever loosened.
function resolveLogPath(rootDir: string, issueId: string): string | null {
  if (!ISSUE_ID_PATTERN.test(issueId)) {
    return null;
  }
  const logDir = path.resolve(rootDir, ".solomon", "logs");
  const candidate = path.resolve(logDir, `issue-${issueId}-start.log`);
  const relative = path.relative(logDir, candidate);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    return null;
  }
  return candidate;
}

interface ActiveTask {
  child: import("child_process").ChildProcess;
  status: string;
  startedAt: string;
  engine: string;
}

// Keep active tasks in a global variable (persists during npm run dev session)
const activeTasks = new Map<string, ActiveTask>();

export async function GET(request: Request): Promise<Response> {
  const { searchParams } = new URL(request.url);
  const issueId = searchParams.get("issueId");
  const rootDir = path.resolve(process.cwd(), "..");

  if (issueId) {
    const logFile = resolveLogPath(rootDir, issueId);
    if (!logFile) {
      return Response.json({ ok: false, error: "Invalid issueId" }, { status: 400 });
    }

    const task = activeTasks.get(issueId);
    let logContent = "";
    if (fs.existsSync(logFile)) {
      logContent = fs.readFileSync(logFile, "utf-8");
    }

    if (task) {
      return Response.json({
        issueId,
        status: task.status,
        startedAt: task.startedAt,
        engine: task.engine,
        log: logContent,
      });
    } else {
      // If not active, but log exists, check if it ran previously
      if (fs.existsSync(logFile)) {
        const isSuccess = logContent.includes("SUCCESS:") || logContent.includes("successfully processed");
        return Response.json({
          issueId,
          status: isSuccess ? "success" : "failed",
          log: logContent,
        });
      }
      return Response.json({
        issueId,
        status: "idle",
        log: "",
      });
    }
  }

  // List all tasks
  const list = Array.from(activeTasks.entries()).map(([id, t]) => ({
    issueId: id,
    status: t.status,
    startedAt: t.startedAt,
    engine: t.engine,
  }));
  return Response.json({ tasks: list });
}

export async function POST(request: Request): Promise<Response> {
  try {
    const authError = checkCockpitAuth(request);
    if (authError) {
      return authError;
    }

    const body = await request.json();
    const { issueId, engine } = body;

    if (!issueId) {
      return Response.json({ ok: false, error: "Missing issueId" }, { status: 400 });
    }

    const selectedEngine = (engine || "claude").toLowerCase();
    if (!["claude", "agy"].includes(selectedEngine)) {
      return Response.json({ ok: false, error: "Invalid engine. Use 'claude' or 'agy'." }, { status: 400 });
    }

    const rootDir = path.resolve(process.cwd(), "..");
    const bin = pythonBin(rootDir);

    const logFile = resolveLogPath(rootDir, issueId);
    if (!logFile) {
      return Response.json({ ok: false, error: "Invalid issueId" }, { status: 400 });
    }

    // If already running, return error
    if (activeTasks.has(issueId) && activeTasks.get(issueId)?.status === "running") {
      return Response.json(
        { ok: false, error: `Task for issue #${issueId} is already running.` },
        { status: 409 },
      );
    }

    fs.mkdirSync(path.dirname(logFile), { recursive: true });
    const logStream = fs.createWriteStream(logFile, { flags: "w" });

    // Spawn Python subprocess
    const child = spawn(
      bin,
      ["-m", "solomon_harness.cli", "dev", "start", issueId],
      {
        cwd: rootDir,
        env: {
          ...process.env,
          SOLOMON_ENGINE: selectedEngine,
        },
      }
    );

    const startedAt = new Date().toISOString();
    activeTasks.set(issueId, {
      child,
      status: "running",
      startedAt,
      engine: selectedEngine,
    });

    child.stdout.pipe(logStream);
    child.stderr.pipe(logStream);

    child.on("close", (code) => {
      const task = activeTasks.get(issueId);
      if (task) {
        task.status = code === 0 ? "success" : "failed";
      }
      logStream.end();
    });

    return Response.json({
      ok: true,
      message: `Started task for issue #${issueId} in background using ${selectedEngine}.`,
      status: "running",
    });
  } catch (error) {
    console.error("Start task handler failed:", error);
    return Response.json({ ok: false, error: "Internal Server Error" }, { status: 500 });
  }
}

export async function PATCH(request: Request): Promise<Response> {
  try {
    const body = await request.json();
    const { issueId, input } = body;

    if (!issueId) {
      return Response.json({ ok: false, error: "Missing issueId" }, { status: 400 });
    }
    if (typeof input !== "string") {
      return Response.json({ ok: false, error: "Missing or invalid input" }, { status: 400 });
    }

    const task = activeTasks.get(issueId);
    if (!task || task.status !== "running" || !task.child) {
      return Response.json({ ok: false, error: "Task is not running" }, { status: 400 });
    }

    // Write input to the child process's stdin
    if (task.child.stdin && task.child.stdin.writable) {
      task.child.stdin.write(input + "\n");
      return Response.json({ ok: true, message: "Input sent successfully" });
    } else {
      return Response.json({ ok: false, error: "Stdin is not writable" }, { status: 500 });
    }
  } catch (error) {
    console.error("Failed to send input to task:", error);
    return Response.json({ ok: false, error: "Internal Server Error" }, { status: 500 });
  }
}
