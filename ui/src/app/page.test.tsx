// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Home from "./page";

const SEVEN = [
  "Ideas",
  "Backlog",
  "Ready",
  "In Progress",
  "Code Review",
  "QA",
  "Done",
];

interface Issue {
  github_id: string;
  title: string;
  type_: string;
  status: string;
}

function columns(populate: Record<string, Issue[]> = {}) {
  return SEVEN.map((name) => {
    const issues = populate[name] ?? [];
    return { name, count: issues.length, issues };
  });
}

function payload(
  projects: string[],
  selectedProject: string,
  cols: ReturnType<typeof columns>,
) {
  const total = cols.reduce((acc, c) => acc + c.count, 0);
  return {
    projects,
    selectedProject,
    board: { project: selectedProject, found: true, total, unmapped: 0, columns: cols },
  };
}

function mockFetch(body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => body,
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe("cockpit board page", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the seven board columns and the issue cards from the API", async () => {
    mockFetch(
      payload(
        ["alpha"],
        "alpha",
        columns({
          Backlog: [
            { github_id: "b1", title: "First", type_: "feature", status: "Backlog" },
            { github_id: "b2", title: "Second", type_: "bug", status: "Backlog" },
          ],
        }),
      ),
    );

    render(<Home />);

    for (const name of SEVEN) {
      expect(await screen.findByText(name)).toBeInTheDocument();
    }
    await waitFor(() =>
      expect(screen.queryAllByTestId("issue-card")).toHaveLength(2),
    );
    expect(screen.getByText("First")).toBeInTheDocument();
  });

  it("stays empty for an empty project and keeps it listed, issuing no writes", async () => {
    const fetchMock = mockFetch(payload(["empty-proj"], "empty-proj", columns()));

    render(<Home />);

    for (const name of SEVEN) {
      expect(await screen.findByText(name)).toBeInTheDocument();
    }
    // The project is still offered in the selector even with zero issues.
    expect(screen.getByText("empty-proj")).toBeInTheDocument();
    // An empty project shows no issue cards (nothing is fabricated/seeded).
    expect(screen.queryAllByTestId("issue-card")).toHaveLength(0);

    // The page is observe-only: it never issues a write request.
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    for (const call of fetchMock.mock.calls) {
      const init = call[1] as RequestInit | undefined;
      expect((init?.method ?? "GET").toUpperCase()).not.toBe("POST");
    }
  });
});
