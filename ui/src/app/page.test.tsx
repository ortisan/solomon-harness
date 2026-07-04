// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Home, { bucketDoneAt } from "./page";

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

interface VelocityRow {
  personKey: string;
  count: number;
  perTenant: Record<string, number>;
  excluded: number;
  doneAt: string[];
  partial: boolean;
  partialTenants: string[];
}

function velocityRow(
  personKey: string,
  count: number,
  overrides: Partial<VelocityRow> = {},
): VelocityRow {
  return {
    personKey,
    count,
    perTenant: {},
    excluded: 0,
    doneAt: [],
    partial: false,
    partialTenants: [],
    ...overrides,
  };
}

function velocityPayload(rows: VelocityRow[], overrides: Record<string, unknown> = {}) {
  const degraded = rows.some((row) => row.partial) ? ["gamma"] : [];
  return {
    rows,
    aggregateStatus: degraded.length ? 207 : 200,
    degraded,
    window: 14,
    ...overrides,
  };
}

describe("bucketDoneAt", () => {
  // Alice's 9 tracked Done dates, reused from 3a's frozen background
  // (T_now = 2026-06-29T12:00:00): the 14-day window holds 7 of them, the
  // 7-day window 3, the 30-day window all 9.
  const ALICE_DONE_AT = [
    "2026-06-01T09:00:00",
    "2026-06-05T09:00:00",
    "2026-06-16T09:00:00",
    "2026-06-18T09:00:00",
    "2026-06-20T09:00:00",
    "2026-06-21T09:00:00",
    "2026-06-24T09:00:00",
    "2026-06-27T09:00:00",
    "2026-06-28T09:00:00",
  ];
  const TODAY = new Date(2026, 5, 29); // 2026-06-29, local

  it("returns 14 zero-filled daily buckets that sum to the 14-day throughput", () => {
    const buckets = bucketDoneAt(ALICE_DONE_AT, 14, TODAY);

    expect(buckets).toHaveLength(14);
    expect(buckets[0].date).toBe("2026-06-16");
    expect(buckets[buckets.length - 1].date).toBe("2026-06-29");

    const byDate = Object.fromEntries(buckets.map((b) => [b.date, b.count]));
    for (const date of [
      "2026-06-16",
      "2026-06-18",
      "2026-06-20",
      "2026-06-21",
      "2026-06-24",
      "2026-06-27",
      "2026-06-28",
    ]) {
      expect(byDate[date]).toBe(1);
    }
    const sum = buckets.reduce((acc, b) => acc + b.count, 0);
    expect(sum).toBe(7);
  });

  it("spans exactly the selected window and sums to that window's throughput", () => {
    const sevenDay = bucketDoneAt(ALICE_DONE_AT, 7, TODAY);
    expect(sevenDay).toHaveLength(7);
    expect(sevenDay.reduce((acc, b) => acc + b.count, 0)).toBe(3);

    const thirtyDay = bucketDoneAt(ALICE_DONE_AT, 30, TODAY);
    expect(thirtyDay).toHaveLength(30);
    expect(thirtyDay.reduce((acc, b) => acc + b.count, 0)).toBe(9);
  });

  it("returns all-zero buckets for an empty doneAt set", () => {
    const buckets = bucketDoneAt([], 14, TODAY);
    expect(buckets).toHaveLength(14);
    expect(buckets.every((b) => b.count === 0)).toBe(true);
  });
});

describe("cockpit velocity view", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  function wireByView(portfolio: unknown, velocity: unknown) {
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () =>
          String(url).includes("view=velocity") ? velocity : portfolio,
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;
    return fetchMock;
  }

  it("renders one throughput row per subject with the excluded affordance, the partial badge, and an unassigned row", async () => {
    const fetchMock = wireByView(
      portfolioPayload([okSwimlane("alpha", { Backlog: [issue("a1")] })]),
      velocityPayload([
        velocityRow("alice@example.com", 7, {
          perTenant: { alpha: 4, beta: 3 },
          excluded: 2,
          partial: true,
          partialTenants: ["gamma"],
        }),
        velocityRow("gh:bob", 0, { partial: true, partialTenants: ["gamma"] }),
        velocityRow("unassigned", 2, {
          perTenant: { alpha: 2 },
          partial: true,
          partialTenants: ["gamma"],
        }),
      ]),
    );

    render(<Home />);

    // Switch to the velocity view; the page re-fetches with ?view=velocity.
    const viewSelect = (await screen.findByLabelText("View")) as HTMLSelectElement;
    fireEvent.change(viewSelect, { target: { value: "velocity" } });

    // One throughput row per subject, including the unassigned bucket.
    await waitFor(() =>
      expect(screen.getAllByTestId("velocity-row")).toHaveLength(3),
    );
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(urls.some((url) => url.includes("view=velocity") && url.includes("window=14"))).toBe(true);
    });

    // Scope row lookups to the velocity panel; the unassigned subject also
    // appears as a (here irrelevant) user-filter option outside it.
    const panel = screen.getByTestId("velocity");

    // alice's throughput number renders inside her row.
    const aliceRow = within(panel)
      .getByText("alice@example.com")
      .closest("[data-testid='velocity-row']");
    expect(aliceRow).not.toBeNull();
    expect(within(aliceRow as HTMLElement).getByText("7")).toBeInTheDocument();

    // The coverage gap is surfaced, never silent.
    expect(
      within(aliceRow as HTMLElement).getByText(/2 excluded \(no tracked history\)/i),
    ).toBeInTheDocument();

    // The reachable-subtotal figure is flagged partial, naming the degraded tenant.
    expect(within(aliceRow as HTMLElement).getByText(/partial/i)).toBeInTheDocument();
    expect(within(aliceRow as HTMLElement).getByText(/gamma/i)).toBeInTheDocument();

    // The unassigned bucket is its own row reading 2, not merged into a person.
    const unassignedRow = within(panel)
      .getByText("unassigned")
      .closest("[data-testid='velocity-row']");
    expect(unassignedRow).not.toBeNull();
    expect(within(unassignedRow as HTMLElement).getByText("2")).toBeInTheDocument();

    // The velocity view is observe-only: every request is a GET.
    for (const call of fetchMock.mock.calls) {
      const init = call[1] as RequestInit | undefined;
      expect((init?.method ?? "GET").toUpperCase()).toBe("GET");
    }
  });

  it("renders a per-day activity chart bar for each day in the window", async () => {
    wireByView(
      portfolioPayload([okSwimlane("alpha", { Backlog: [issue("a1")] })]),
      velocityPayload([
        velocityRow("alice@example.com", 2, {
          doneAt: ["2026-06-27T09:00:00", "2026-06-28T09:00:00"],
        }),
      ]),
    );

    render(<Home />);
    const viewSelect = (await screen.findByLabelText("View")) as HTMLSelectElement;
    fireEvent.change(viewSelect, { target: { value: "velocity" } });

    const aliceRow = (
      await screen.findByText("alice@example.com")
    ).closest("[data-testid='velocity-row']") as HTMLElement;

    const chart = within(aliceRow).getByTestId("velocity-chart");
    expect(within(chart).getAllByTestId("velocity-chart-bar")).toHaveLength(14);
  });

  it("shows the empty state instead of a chart for a user with no activity in the window", async () => {
    wireByView(
      portfolioPayload([okSwimlane("alpha", { Backlog: [issue("a1")] })]),
      velocityPayload([velocityRow("gh:bob", 0)]),
    );

    render(<Home />);
    const viewSelect = (await screen.findByLabelText("View")) as HTMLSelectElement;
    fireEvent.change(viewSelect, { target: { value: "velocity" } });

    const bobRow = (
      await screen.findByText("gh:bob")
    ).closest("[data-testid='velocity-row']") as HTMLElement;

    expect(within(bobRow).getByTestId("velocity-empty")).toHaveTextContent(
      /no activity in window/i,
    );
    expect(within(bobRow).queryByTestId("velocity-chart")).not.toBeInTheDocument();
  });

  it("renders the chart over the reachable doneAt set alongside the existing partial badge", async () => {
    wireByView(
      portfolioPayload([okSwimlane("alpha", { Backlog: [issue("a1")] })]),
      velocityPayload([
        velocityRow("alice@example.com", 1, {
          doneAt: ["2026-06-28T09:00:00"],
          partial: true,
          partialTenants: ["gamma"],
        }),
      ]),
    );

    render(<Home />);
    const viewSelect = (await screen.findByLabelText("View")) as HTMLSelectElement;
    fireEvent.change(viewSelect, { target: { value: "velocity" } });

    const aliceRow = (
      await screen.findByText("alice@example.com")
    ).closest("[data-testid='velocity-row']") as HTMLElement;

    expect(within(aliceRow).getByTestId("velocity-chart")).toBeInTheDocument();
    expect(within(aliceRow).getByText(/partial/i)).toBeInTheDocument();
    expect(within(aliceRow).getByText(/gamma/i)).toBeInTheDocument();
  });
});
