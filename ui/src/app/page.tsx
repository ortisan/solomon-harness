"use client";

import { useEffect, useState } from "react";

// Read-only delivery cockpit. With no project selected it renders the
// cross-tenant portfolio (one swimlane per project, slice 1b); selecting a
// project drills down into that one tenant's board (slice 1a). It issues only
// GET reads: there is no drag-and-drop, no move modal, and no write-back.

const COLUMNS = [
  "Ideas",
  "Backlog",
  "Ready",
  "In Progress",
  "Code Review",
  "QA",
  "Done",
];

const ALL_PROJECTS = "";
const ALL_USERS = "";
// The reserved subject for issues with no assignee, mirrored from the composer.
const UNASSIGNED_USER = "unassigned";

// The board (current snapshot) and velocity (per-user throughput) views.
const BOARD_VIEW = "board";
const VELOCITY_VIEW = "velocity";
// The selectable velocity windows in days, mirrored from the route's allowed set.
const VELOCITY_WINDOWS = [7, 14, 30];
const DEFAULT_WINDOW = 14;

interface Issue {
  github_id: string;
  title: string;
  type_: string;
  status: string;
  personKey?: string;
}

interface BoardColumn {
  name: string;
  count: number;
  issues: Issue[];
}

interface Board {
  project: string;
  found?: boolean;
  total: number;
  unmapped: number;
  columns: BoardColumn[];
}

interface Dashboard {
  projects: string[];
  selectedProject: string;
  board: Board;
}

interface SwimlaneData {
  project: string;
  status: string;
  httpStatus?: number;
  total: number;
  unmapped: number;
  columns: BoardColumn[];
}

interface Portfolio {
  swimlanes: SwimlaneData[];
  columns: { name: string; count: number }[];
  total: number;
  unmapped: number;
  aggregateStatus: number;
  overflow: number;
  notice: string | null;
  filteredUser?: string;
}

interface VelocityRowData {
  personKey: string;
  count: number;
  perTenant: Record<string, number>;
  excluded: number;
  doneAt: string[];
  partial: boolean;
  partialTenants: string[];
}

interface Velocity {
  rows: VelocityRowData[];
  aggregateStatus: number;
  degraded: string[];
  window: number;
}

type DashboardData = Dashboard | Portfolio | Velocity;

function isPortfolio(data: DashboardData): data is Portfolio {
  return "swimlanes" in data;
}

function isVelocity(data: DashboardData): data is Velocity {
  return "rows" in data;
}

function fallbackColumns(): BoardColumn[] {
  return COLUMNS.map((name) => ({ name, count: 0, issues: [] }));
}

// The people surfaced by one portfolio load: the personKeys across its
// swimlanes plus the reserved unassigned subject, deduped and sorted. A filtered
// load carries only the matched person, so this is read from an unfiltered load
// and persisted, never re-derived from the already-narrowed response.
function collectUsers(portfolio: Portfolio): string[] {
  const keys = new Set<string>([UNASSIGNED_USER]);
  for (const lane of portfolio.swimlanes) {
    for (const column of lane.columns) {
      for (const issue of column.issues) {
        if (issue.personKey) {
          keys.add(issue.personKey);
        }
      }
    }
  }
  return Array.from(keys).sort();
}

// The filter's option set: the persisted full user list unioned with the
// currently selected user. The union guarantees the controlled <select> value
// always has a matching <option> (even a hand-crafted ?user= that matches zero
// issues), so the selector never collapses to the filtered person and switching
// directly from one user to another stays possible.
function userFilterOptions(allUsers: string[], selectedUser: string): string[] {
  const keys = new Set<string>(allUsers);
  if (selectedUser) {
    keys.add(selectedUser);
  }
  return Array.from(keys).sort();
}

function BoardColumns({ columns }: { columns: BoardColumn[] }) {
  return (
    <div className="board-columns">
      {columns.map((column) => (
        <div key={column.name} className="board-column">
          <div className="column-header">
            <div className="column-title">
              <span>{column.name}</span>
              <span className="column-badge">{column.count}</span>
            </div>
          </div>
          <div className="column-cards">
            {column.issues.map((issue) => (
              <div
                key={issue.github_id}
                className="issue-card"
                data-testid="issue-card"
              >
                <span
                  className={`card-type-badge type-${(issue.type_ ?? "").toLowerCase()}`}
                >
                  {issue.type_}
                </span>
                <h4 className="card-title">{issue.title}</h4>
                <div className="card-meta">
                  <span className="card-id text-mono">#{issue.github_id}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "UNREACHABLE") {
    return (
      <span className="status-badge status-unreachable" role="status">
        Unreachable
      </span>
    );
  }
  if (status === "FORBIDDEN") {
    return (
      <span className="status-badge status-forbidden" role="status">
        Access denied
      </span>
    );
  }
  return null;
}

function SwimlaneBody({
  lane,
  filteredUser,
}: {
  lane: SwimlaneData;
  filteredUser?: string;
}) {
  // A degraded tenant carries no issue rows, so only its badge renders.
  if (lane.status !== "OK") {
    return null;
  }
  // Under an active filter, an OK lane with no matching card stays present with
  // an explicit per-lane affordance rather than vanishing (narrow, not hide).
  if (filteredUser && lane.total === 0) {
    return (
      <p className="swimlane-empty text-muted" role="status">
        0 issues for {filteredUser}
      </p>
    );
  }
  return <BoardColumns columns={lane.columns} />;
}

function Swimlane({
  lane,
  filteredUser,
}: {
  lane: SwimlaneData;
  filteredUser?: string;
}) {
  return (
    <section className="swimlane" data-testid="swimlane" aria-label={lane.project}>
      <header className="swimlane-header">
        <h3 className="swimlane-title">{lane.project}</h3>
        <StatusBadge status={lane.status} />
        <span className="swimlane-total">{lane.total}</span>
      </header>
      <SwimlaneBody lane={lane} filteredUser={filteredUser} />
    </section>
  );
}

function PortfolioView({ portfolio }: { portfolio: Portfolio }) {
  const filteredUser = portfolio.filteredUser;
  // A filter that matched nobody anywhere gets one explicit cross-project empty
  // state naming the subject and the number of lanes scanned.
  const emptyUnderFilter = Boolean(filteredUser) && portfolio.total === 0;
  return (
    <div className="portfolio">
      <div className="portfolio-summary">
        <span data-testid="portfolio-total">
          Portfolio total: {portfolio.total}
        </span>
        {portfolio.notice && (
          <p className="text-warning" role="status">
            {portfolio.notice}
          </p>
        )}
        {emptyUnderFilter && (
          <p className="text-warning" role="status">
            No issues for {filteredUser} across {portfolio.swimlanes.length}{" "}
            projects
          </p>
        )}
      </div>
      <div className="swimlanes">
        {portfolio.swimlanes.map((lane) => (
          <Swimlane key={lane.project} lane={lane} filteredUser={filteredUser} />
        ))}
      </div>
    </div>
  );
}

interface DayBucket {
  date: string;
  count: number;
}

// Buckets `doneAt` (naive local ISO-8601 timestamps) into the last `window`
// calendar days ending at `today`, zero-filled, oldest first. Day labels come
// from `today`'s local getters (never `toISOString()`, which reinterprets in
// UTC and can shift the calendar date depending on the browser's timezone);
// `doneAt` entries are matched by their raw date-prefix string (never
// `Date`-parsed), so there is no timezone re-coercion on either side.
export function bucketDoneAt(
  doneAt: string[],
  window: number,
  today: Date,
): DayBucket[] {
  const buckets: DayBucket[] = [];
  for (let offset = window - 1; offset >= 0; offset--) {
    const day = new Date(
      today.getFullYear(),
      today.getMonth(),
      today.getDate() - offset,
    );
    const date = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
    buckets.push({ date, count: 0 });
  }
  const indexByDate = new Map(buckets.map((bucket, i) => [bucket.date, i]));
  for (const timestamp of doneAt) {
    const index = indexByDate.get(timestamp.slice(0, 10));
    if (index !== undefined) {
      buckets[index].count += 1;
    }
  }
  return buckets;
}

function VelocityChart({ buckets }: { buckets: DayBucket[] }) {
  const max = Math.max(1, ...buckets.map((bucket) => bucket.count));
  return (
    <div className="velocity-chart" data-testid="velocity-chart">
      {buckets.map((bucket) => (
        <span
          key={bucket.date}
          className="velocity-chart-bar"
          data-testid="velocity-chart-bar"
          title={`${bucket.date}: ${bucket.count}`}
          style={{ height: `${(bucket.count / max) * 100}%` }}
        />
      ))}
    </div>
  );
}

function VelocityRow({
  row,
  window,
  today,
}: {
  row: VelocityRowData;
  window: number;
  today: Date;
}) {
  return (
    <li className="velocity-row" data-testid="velocity-row">
      <span className="velocity-subject">{row.personKey}</span>
      <span className="velocity-count" data-testid="velocity-count">
        {row.count}
      </span>
      {row.excluded > 0 && (
        <span className="velocity-excluded text-warning">
          {row.excluded} excluded (no tracked history)
        </span>
      )}
      {row.partial && (
        <span className="velocity-partial-badge" role="status">
          partial ({row.partialTenants.join(", ")})
        </span>
      )}
      {row.doneAt.length > 0 ? (
        <VelocityChart buckets={bucketDoneAt(row.doneAt, window, today)} />
      ) : (
        <p
          className="velocity-empty text-warning"
          data-testid="velocity-empty"
          role="status"
        >
          No activity in window
        </p>
      )}
    </li>
  );
}

function VelocityView({ velocity }: { velocity: Velocity }) {
  // Every figure is a reachable subtotal when a tenant is degraded; the per-row
  // partial badge names which, and this banner states the window-wide gap.
  const today = new Date();
  return (
    <div className="velocity" data-testid="velocity">
      <div className="velocity-summary">
        <span data-testid="velocity-window">
          Throughput over {velocity.window} days
        </span>
        {velocity.degraded.length > 0 && (
          <p className="text-warning" role="status">
            Partial: {velocity.degraded.join(", ")} unreachable
          </p>
        )}
      </div>
      <ul className="velocity-rows">
        {velocity.rows.map((row) => (
          <VelocityRow
            key={row.personKey}
            row={row}
            window={velocity.window}
            today={today}
          />
        ))}
      </ul>
    </div>
  );
}

function SingleBoardView({ board }: { board?: Board }) {
  if (board?.found === false) {
    // A not-found project gets an explicit notice, never a silent all-zero
    // board that would be indistinguishable from a real but empty project.
    return (
      <p className="text-warning" role="status">
        Project not found
      </p>
    );
  }
  return <BoardColumns columns={board?.columns ?? fallbackColumns()} />;
}

export default function Home() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [allUsers, setAllUsers] = useState<string[]>([]);
  const [view, setView] = useState<string>(BOARD_VIEW);
  const [windowDays, setWindowDays] = useState<number>(DEFAULT_WINDOW);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void load();
    // Load once on mount; the selectors trigger subsequent loads.
  }, []);

  async function fetchInto(url: string) {
    setLoading(true);
    try {
      const res = await fetch(url);
      const json = await res.json();
      if (json?.error) {
        throw new Error(json.error);
      }
      setData(json as DashboardData);
      // Refresh the persisted user list only from an unfiltered portfolio load,
      // so filtering to one person never collapses the selector to that person.
      if (isPortfolio(json) && !json.filteredUser) {
        setAllUsers(collectUsers(json));
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the board");
    } finally {
      setLoading(false);
    }
  }

  async function load(project?: string, user?: string) {
    const params = new URLSearchParams();
    if (project) {
      params.set("project", project);
    }
    if (user) {
      params.set("user", user);
    }
    const query = params.toString();
    await fetchInto(query ? `/api/dashboard?${query}` : "/api/dashboard");
  }

  async function loadVelocity(days: number) {
    await fetchInto(`/api/dashboard?view=${VELOCITY_VIEW}&window=${days}`);
  }

  function changeView(next: string) {
    const nextView = next === VELOCITY_VIEW ? VELOCITY_VIEW : BOARD_VIEW;
    setView(nextView);
    if (nextView === VELOCITY_VIEW) {
      void loadVelocity(windowDays);
    } else {
      void load();
    }
  }

  function changeWindow(days: number) {
    setWindowDays(days);
    void loadVelocity(days);
  }

  const portfolio = data && isPortfolio(data) ? data : null;
  const velocity = data && isVelocity(data) ? data : null;
  const dashboard =
    data && !isPortfolio(data) && !isVelocity(data) ? data : null;
  const projects =
    dashboard?.projects ?? portfolio?.swimlanes.map((s) => s.project) ?? [];
  const selectedProject = dashboard?.selectedProject ?? ALL_PROJECTS;
  const selectedUser = portfolio?.filteredUser ?? ALL_USERS;
  const userOptions = userFilterOptions(allUsers, selectedUser);

  return (
    <div className="app-container">
      <header className="navbar">
        <div className="navbar-brand">
          <span>Solomon Harness Cockpit</span>
          <span className="navbar-tag">Read-only delivery board</span>
        </div>
      </header>

      <section className="repo-header">
        <div className="repo-title-wrapper">
          <div className="repo-title">
            <span>Project:</span>
            <select
              aria-label="Project"
              className="select-input"
              value={selectedProject}
              onChange={(event) => void load(event.target.value)}
            >
              <option value={ALL_PROJECTS}>All projects</option>
              {projects.map((project) => (
                <option key={project} value={project}>
                  {project}
                </option>
              ))}
            </select>
          </div>
          <div className="repo-title">
            <span>User:</span>
            <select
              aria-label="User"
              className="select-input"
              value={selectedUser}
              onChange={(event) => void load(undefined, event.target.value)}
            >
              <option value={ALL_USERS}>All users</option>
              {userOptions.map((user) => (
                <option key={user} value={user}>
                  {user}
                </option>
              ))}
            </select>
          </div>
          <div className="repo-title">
            <span>View:</span>
            <select
              aria-label="View"
              className="select-input"
              value={view}
              onChange={(event) => changeView(event.target.value)}
            >
              <option value={BOARD_VIEW}>Board</option>
              <option value={VELOCITY_VIEW}>Velocity</option>
            </select>
          </div>
          {view === VELOCITY_VIEW && (
            <div className="repo-title">
              <span>Window:</span>
              <select
                aria-label="Window"
                className="select-input"
                value={windowDays}
                onChange={(event) => changeWindow(Number(event.target.value))}
              >
                {VELOCITY_WINDOWS.map((days) => (
                  <option key={days} value={days}>
                    {days} days
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </section>

      <main className="main-content">
        {error && (
          <p className="text-danger" role="alert">
            {error}
          </p>
        )}
        {loading && !data && <p>Loading board...</p>}

        {velocity ? (
          <VelocityView velocity={velocity} />
        ) : portfolio ? (
          <PortfolioView portfolio={portfolio} />
        ) : (
          <SingleBoardView board={dashboard?.board} />
        )}
      </main>
    </div>
  );
}
