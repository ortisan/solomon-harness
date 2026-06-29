// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  personKey?: string;
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

function personIssue(id: string, personKey: string): Issue {
  return { github_id: id, title: `title-${id}`, type_: "feature", status: "Backlog", personKey };
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

describe("cockpit cross-user filter", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("offers a user filter and re-fetches with ?user= when a user is picked", async () => {
    const fetchMock = mockFetch(
      portfolioPayload([
        okSwimlane("alpha", { Backlog: [personIssue("a1", "alice@example.com")] }),
        okSwimlane("beta", { Done: [personIssue("b1", "bob@example.com")] }),
      ]),
    );

    render(<Home />);

    // The user filter control is present by its accessible label and lists the
    // people surfaced across the loaded swimlanes.
    const userSelect = (await screen.findByLabelText("User")) as HTMLSelectElement;
    expect(
      screen.getByRole("option", { name: "alice@example.com" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "bob@example.com" }),
    ).toBeInTheDocument();

    fireEvent.change(userSelect, { target: { value: "alice@example.com" } });

    // Picking a user re-fetches, threading the chosen key as ?user=.
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(urls.some((url) => url.includes("user=alice%40example.com"))).toBe(true);
    });

    // Every request is a GET: the filter never mutates state.
    for (const call of fetchMock.mock.calls) {
      const init = call[1] as RequestInit | undefined;
      expect((init?.method ?? "GET").toUpperCase()).toBe("GET");
    }
  });

  it("narrows the swimlanes to one user, keeping an empty lane present", async () => {
    mockFetch(
      portfolioPayload(
        [
          okSwimlane("alpha", {
            Backlog: [personIssue("a1", "alice@example.com")],
            "In Progress": [personIssue("a2", "alice@example.com")],
            Done: [personIssue("a3", "alice@example.com")],
          }),
          okSwimlane("beta", {
            Ready: [personIssue("b1", "alice@example.com")],
            QA: [personIssue("b2", "alice@example.com")],
          }),
          okSwimlane("gamma", {}),
        ],
        { filteredUser: "alice@example.com" },
      ),
    );

    render(<Home />);

    // One lane per project survives: gamma stays present (not hidden), just empty.
    await waitFor(() => expect(screen.getAllByTestId("swimlane")).toHaveLength(3));
    expect(screen.getByRole("heading", { name: "gamma" })).toBeInTheDocument();
    // alice's five cards render across alpha and beta.
    expect(screen.getAllByTestId("issue-card")).toHaveLength(5);
    // The portfolio total reflects the filtered set, not the unfiltered board.
    expect(screen.getByTestId("portfolio-total")).toHaveTextContent("5");
    // The empty matched lane shows a per-lane affordance naming the user.
    expect(
      screen.getByText(/0 issues for alice@example.com/i),
    ).toBeInTheDocument();
  });

  it("keeps every user selectable after filtering and switches directly between users", async () => {
    // The server filters: an unfiltered load carries both people, while a
    // ?user=alice load carries only alice's cards (bob's lane is now empty).
    const unfiltered = portfolioPayload([
      okSwimlane("alpha", { Backlog: [personIssue("a1", "alice@example.com")] }),
      okSwimlane("beta", { Done: [personIssue("b1", "bob@example.com")] }),
    ]);
    const aliceOnly = portfolioPayload(
      [
        okSwimlane("alpha", { Backlog: [personIssue("a1", "alice@example.com")] }),
        okSwimlane("beta", {}),
      ],
      { filteredUser: "alice@example.com" },
    );
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () => (String(url).includes("user=") ? aliceOnly : unfiltered),
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    render(<Home />);

    // After the unfiltered load both people are options.
    const userSelect = (await screen.findByLabelText("User")) as HTMLSelectElement;
    expect(
      screen.getByRole("option", { name: "alice@example.com" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "bob@example.com" }),
    ).toBeInTheDocument();

    // Filtering to alice narrows the response to alice-only, yet bob stays a
    // selectable option because the option set is the persisted unfiltered list.
    fireEvent.change(userSelect, { target: { value: "alice@example.com" } });
    await waitFor(() =>
      expect(screen.getByText(/0 issues for alice@example.com/i)).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("option", { name: "alice@example.com" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "bob@example.com" }),
    ).toBeInTheDocument();

    // Switching straight from alice to bob (no reset to All users) re-fetches
    // with ?user=bob.
    fireEvent.change(userSelect, { target: { value: "bob@example.com" } });
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(urls.some((url) => url.includes("user=bob%40example.com"))).toBe(true);
    });
  });

  it("renders a matching option and the empty state for a filtered user with zero issues", async () => {
    // A hand-crafted ?user=carol lands directly on a filtered payload: carol
    // matches nobody, so she surfaces in no card yet is the controlled value.
    mockFetch(
      portfolioPayload(
        [okSwimlane("alpha", {}), okSwimlane("beta", {})],
        { filteredUser: "carol@example.com", total: 0 },
      ),
    );

    render(<Home />);

    // The controlled select value has a matching option, so there is no missing
    // -option mismatch even though carol appears in no loaded card.
    const userSelect = (await screen.findByLabelText("User")) as HTMLSelectElement;
    expect(userSelect.value).toBe("carol@example.com");
    expect(
      screen.getByRole("option", { name: "carol@example.com" }),
    ).toBeInTheDocument();
    // The cross-project empty state still renders cleanly.
    expect(
      screen.getByText(/no issues for carol@example.com across 2 projects/i),
    ).toBeInTheDocument();
  });

  it("shows the cross-project empty state when the filtered total is 0", async () => {
    mockFetch(
      portfolioPayload(
        [okSwimlane("alpha", {}), okSwimlane("beta", {}), okSwimlane("gamma", {})],
        { filteredUser: "carol@example.com", total: 0 },
      ),
    );

    render(<Home />);

    // A distinct cross-project empty state names the subject and the lane count.
    expect(
      await screen.findByText(/no issues for carol@example.com across 3 projects/i),
    ).toBeInTheDocument();
    // No issue card renders anywhere under the empty filter.
    expect(screen.queryAllByTestId("issue-card")).toHaveLength(0);
  });
});
