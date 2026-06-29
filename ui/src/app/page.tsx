"use client";

import { useEffect, useState } from "react";

// Read-only delivery board (slice 1a). The page selects one project and renders
// its board across the seven fixed columns. It issues only GET reads: there is
// no drag-and-drop, no move modal, no optimistic update, and no write-back.

const COLUMNS = [
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

function fallbackColumns(): BoardColumn[] {
  return COLUMNS.map((name) => ({ name, count: 0, issues: [] }));
}

export default function Home() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void load();
    // Load once on mount; the selector triggers subsequent loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load(project?: string) {
    setLoading(true);
    try {
      const url = project
        ? `/api/dashboard?project=${encodeURIComponent(project)}`
        : "/api/dashboard";
      const res = await fetch(url);
      const json = await res.json();
      if (json?.error) {
        throw new Error(json.error);
      }
      setData(json as Dashboard);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the board");
    } finally {
      setLoading(false);
    }
  }

  const projects = data?.projects ?? [];
  const selectedProject = data?.selectedProject ?? "";
  const boardColumns = data?.board?.columns ?? fallbackColumns();

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
              {projects.map((project) => (
                <option key={project} value={project}>
                  {project}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <main className="main-content">
        {error && (
          <p className="text-danger" role="alert">
            {error}
          </p>
        )}
        {loading && !data && <p>Loading board...</p>}

        <div className="board-columns">
          {boardColumns.map((column) => (
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
      </main>
    </div>
  );
}
