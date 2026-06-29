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

    // The page is observe-only: every request is a GET, never a write of any
    // kind (POST/PUT/PATCH/DELETE are all rejected, not just POST).
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    for (const call of fetchMock.mock.calls) {
      const init = call[1] as RequestInit | undefined;
      expect((init?.method ?? "GET").toUpperCase()).toBe("GET");
    }
  });

  it("renders a distinct project-not-found notice when found is false", async () => {
    mockFetch({
      projects: ["alpha"],
      selectedProject: "ghost",
      board: {
        project: "ghost",
        found: false,
        total: 0,
        unmapped: 0,
        columns: columns(),
      },
    });

    render(<Home />);

    // A 404/not-found board shows an explicit notice, not a silent all-zero
    // board that looks like a real but empty project.
    expect(await screen.findByText(/project not found/i)).toBeInTheDocument();
    expect(screen.queryAllByTestId("issue-card")).toHaveLength(0);
  });
});

function issue(id: string): Issue {
  return { github_id: id, title: `title-${id}`, type_: "feature", status: "Backlog" };
}

function okSwimlane(project: string, byColumn: Record<string, Issue[]> = {}) {
  const cols = columns(byColumn);
  const total = cols.reduce((acc, c) => acc + c.count, 0);
  return { project, status: "OK", total, unmapped: 0, columns: cols };
}

function degradedSwimlane(project: string, status: string) {
  const lane: {
    project: string;
    status: string;
    total: number;
    unmapped: number;
    columns: ReturnType<typeof columns>;
    httpStatus?: number;
  } = { project, status, total: 0, unmapped: 0, columns: columns() };
  if (status === "FORBIDDEN") {
    lane.httpStatus = 403;
  }
  return lane;
}

function portfolioPayload(
  swimlanes: ReturnType<typeof okSwimlane>[] | ReturnType<typeof degradedSwimlane>[],
  overrides: Record<string, unknown> = {},
) {
  const total = swimlanes
    .filter((s) => s.status === "OK")
    .reduce((acc, s) => acc + s.total, 0);
  return {
    swimlanes,
    columns: SEVEN.map((name) => ({ name, count: 0 })),
    total,
    unmapped: 0,
    aggregateStatus: swimlanes.every((s) => s.status === "OK") ? 200 : 207,
    overflow: 0,
    notice: null,
    ...overrides,
  };
}

describe("cockpit portfolio page", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders one swimlane per project with columns, cards, the total, and only GETs", async () => {
    const fetchMock = mockFetch(
      portfolioPayload([
        okSwimlane("alpha", { Backlog: [issue("a1"), issue("a2")] }),
        okSwimlane("beta", { Done: [issue("b1")] }),
      ]),
    );

    render(<Home />);

    await waitFor(() =>
      expect(screen.getAllByTestId("swimlane")).toHaveLength(2),
    );
    // Each swimlane carries its project as a heading (distinct from the selector).
    expect(screen.getByRole("heading", { name: "alpha" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "beta" })).toBeInTheDocument();
    // Seven columns render in each of the two swimlanes (the names repeat).
    expect(screen.getAllByText("Backlog")).toHaveLength(2);
    // The portfolio total sums the OK swimlanes (2 + 1).
    expect(screen.getByTestId("portfolio-total")).toHaveTextContent("3");
    // All three OK issue cards render.
    expect(screen.getAllByTestId("issue-card")).toHaveLength(3);

    // The portfolio view is observe-only: every request is a GET.
    for (const call of fetchMock.mock.calls) {
      const init = call[1] as RequestInit | undefined;
      expect((init?.method ?? "GET").toUpperCase()).toBe("GET");
    }
  });

  it("shows a degraded badge and no cards for UNREACHABLE and FORBIDDEN tenants", async () => {
    mockFetch(
      portfolioPayload([
        okSwimlane("alpha", { Backlog: [issue("a1")] }),
        degradedSwimlane("beta", "UNREACHABLE"),
        degradedSwimlane("gamma", "FORBIDDEN"),
      ]),
    );

    render(<Home />);

    await waitFor(() =>
      expect(screen.getAllByTestId("swimlane")).toHaveLength(3),
    );
    // The unreachable tenant surfaces its state; the forbidden one is denied.
    expect(screen.getByText(/unreachable/i)).toBeInTheDocument();
    expect(screen.getByText(/access denied/i)).toBeInTheDocument();
    // Only the OK tenant's single card renders; degraded tenants show none.
    expect(screen.getAllByTestId("issue-card")).toHaveLength(1);
  });

  it("renders the overflow notice when projects are not shown", async () => {
    mockFetch(
      portfolioPayload([okSwimlane("alpha", { Backlog: [issue("a1")] })], {
        overflow: 1,
        notice: "1 project not shown",
      }),
    );

    render(<Home />);

    expect(await screen.findByText("1 project not shown")).toBeInTheDocument();
  });
});
