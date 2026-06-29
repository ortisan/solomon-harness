import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Two environments: jsdom for the React page tests, node for the route handler
// tests. Per-file overrides are set with a `// @vitest-environment` comment.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "node",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
