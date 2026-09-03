import { useEffect, useState } from "react";
import Timeline from "./Timeline.jsx";

const roleLabels = {
  researcher: "Researchers",
  reviewer: "Reviewers",
  principal: "Principals",
  "impact-assessor": "Impact assessor",
};

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [activeRoles, setActiveRoles] = useState(
    new Set(["researcher", "reviewer", "principal", "impact-assessor"]),
  );

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const response = await fetch("/api/timeline", { cache: "no-store" });
        if (!response.ok) throw new Error(`Timeline request failed (${response.status})`);
        const next = await response.json();
        if (!disposed) {
          setData(next);
          setError("");
        }
      } catch (nextError) {
        if (!disposed) setError(nextError.message || "Timeline request failed");
      }
    };
    load();
    const timer = window.setInterval(load, 30_000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);

  const toggleRole = (role) => {
    setActiveRoles((current) => {
      const next = new Set(current);
      if (next.has(role)) next.delete(role);
      else next.add(role);
      return next;
    });
  };

  if (!data) {
    return <main className="loading">{error || "Loading research campaign…"}</main>;
  }

  const summary = data.summary;
  const impact = summary.impact_signals;
  const noteworthy = [...data.annotations]
    .filter(
      (item) =>
        item.impact === "major" ||
        item.impact === "substantial" ||
        item.paper_potential === "high",
    )
    .reverse()
    .slice(0, 6);

  return (
    <main className="app-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">Discovery Net · live campaign</p>
          <h1>Research campaign timeline</h1>
          <p className="subtitle">
            Actual pass durations, problem pivots, approach changes, publications, and calibrated
            impact signals. Refreshes every 30 seconds.
          </p>
        </div>
        <div className="snapshot">
          Snapshot
          <strong>{formatDate(data.snapshot_at)}</strong>
        </div>
      </section>

      <section className="metric-grid" aria-label="Campaign summary">
        <Metric label="Completed passes" value={summary.completed_runs} />
        <Metric label="Running now" value={summary.running_runs} />
        <Metric label="Impact annotations" value={summary.annotations} />
        <Metric
          label="Substantial / major"
          value={`${impact.substantial} / ${impact.major}`}
        />
        <Metric label="High paper potential" value={impact.high_paper_potential} />
      </section>

      <section className="panel timeline-panel">
        <div className="role-controls" aria-label="Visible roles">
          {Object.entries(roleLabels).map(([role, label]) => (
            <button
              type="button"
              key={role}
              data-role={role}
              aria-pressed={activeRoles.has(role)}
              onClick={() => toggleRole(role)}
            >
              <span className={`role-swatch ${role}`} />
              {label}
            </button>
          ))}
        </div>
        <div className="marker-legend" aria-label="Marker legend">
          <span><b className="pivot">◆</b>problem pivot</span>
          <span><b className="approach">●</b>new approach</span>
          <span><b className="publication">■</b>source/publication</span>
          <span><b className="failure">×</b>failed pass</span>
        </div>
        <p className="timeline-note">
          Solid bars are active passes; gaps are cadence or orchestration wait. Impact outlines are
          advisory model judgments, not proof of novelty.
        </p>
        <Timeline data={data} activeRoles={activeRoles} />
      </section>

      <section className="panel impact-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Incremental assessment</p>
            <h2>Recent impact signals</h2>
          </div>
          <p>The assessor reads only new researcher passes plus a bounded GraphQL neighborhood.</p>
        </div>
        {noteworthy.length ? (
          <div className="impact-list">
            {noteworthy.map((item) => (
              <article key={`${item.run_id}-${item.assessed_at}`}>
                <div className="impact-tags">
                  <span className={`tag impact-${item.impact}`}>{item.impact}</span>
                  <span className="tag">{humanize(item.novelty)}</span>
                  <span className="tag">paper potential: {item.paper_potential}</span>
                  <span className="tag">confidence: {item.confidence}</span>
                </div>
                <h3>{item.lane_title}</h3>
                <p>{item.summary}</p>
                <small>{item.agent} · assessed {formatDate(item.assessed_at)}</small>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-state">No substantial or high-paper-potential signals yet.</p>
        )}
      </section>
      {error ? <div className="error-toast">{error}; showing the latest snapshot.</div> : null}
    </main>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function formatDate(value) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}

function humanize(value) {
  return String(value).replaceAll("_", " ");
}
