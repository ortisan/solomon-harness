import { execFile } from "child_process";
import path from "path";

import { checkCockpitAuth } from "../../../lib/cockpit-auth";

function pythonBin(rootDir: string): string {
  return process.platform === "win32"
    ? path.join(rootDir, ".venv", "Scripts", "python.exe")
    : path.join(rootDir, ".venv", "bin", "python");
}

// Reconcile repairs live memory rows, so it defaults to a dry run (matching
// the CLI's own --dry-run flag) unless the caller explicitly opts into the
// live write with confirm=true, as a query param or a JSON body field.
async function wantsLiveWrite(request: Request): Promise<boolean> {
  const { searchParams } = new URL(request.url);
  if (searchParams.get("confirm") === "true") {
    return true;
  }
  try {
    const body = await request.clone().json();
    return body?.confirm === true || body?.confirm === "true";
  } catch {
    return false;
  }
}

export async function POST(request: Request): Promise<Response> {
  try {
    const authError = checkCockpitAuth(request);
    if (authError) {
      return authError;
    }

    const rootDir = path.resolve(process.cwd(), "..");
    const bin = pythonBin(rootDir);
    const confirmed = await wantsLiveWrite(request);
    const args = ["-m", "solomon_harness.cli", "reconcile"];
    if (!confirmed) {
      args.push("--dry-run");
    }

    return new Promise((resolve) => {
      execFile(
        bin,
        args,
        {
          cwd: rootDir,
          shell: false,
          timeout: 20000,
        },
        (error, stdout, stderr) => {
          if (error) {
            console.error("Reconcile failed:", error, stderr);
            resolve(
              Response.json(
                { ok: false, error: error.message, detail: stderr },
                { status: 500 },
              ),
            );
            return;
          }
          resolve(Response.json({ ok: true, output: stdout }));
        },
      );
    });
  } catch (error) {
    console.error("Reconcile handler failed:", error);
    return Response.json(
      { ok: false, error: "Internal Server Error" },
      { status: 500 },
    );
  }
}
