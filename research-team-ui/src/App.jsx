import { useEffect, useState } from "react";
import Timeline from "./Timeline.jsx";

const roleLabels = {
  researcher: "Researchers",
  reviewer: "Reviewers",
  principal: "Principals",
  orchestrator: "Orchestrator",
  "impact-assessor": "Impact assessor",
};

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [activeRoles, setActiveRoles] = useState(
    new Set(["researcher", "reviewer", "principal", "orchestrator", "impact-assessor"]),
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
  const resources = data.resources;
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
          <p className="eyebrow"><span className="live-dot" />Discovery Net · live campaign</p>
          <h1>Research fleet</h1>
          <p className="subtitle">
            Two teams, one reviewer, and independent impact assessment.
          </p>
        </div>
        <div className="snapshot">
          Snapshot
          <strong>{formatDate(data.snapshot_at)}</strong>
        </div>
      </section>

      {resources ? <ResourceStrip resources={resources} /> : null}

      <section className="metric-grid" aria-label="Campaign summary">
        <Metric label="Active agents" value={summary.active_agents} />
        <Metric label="Passes running" value={summary.running_runs} />
        <Metric label="Completed this campaign" value={summary.completed_runs} />
        <Metric
          label="Substantial / major"
          value={`${impact.substantial} / ${impact.major}`}
        />
        <Metric label="Failed passes" value={summary.failed_runs} tone={summary.failed_runs ? "danger" : "normal"} />
      </section>

      <section className="panel timeline-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Current campaign</p>
            <h2>Agent activity</h2>
          </div>
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
        </div>
        <div className="timeline-key">
          <div className="marker-legend" aria-label="Marker legend">
            <span><b className="pivot">◆</b>problem pivot</span>
            <span><b className="approach">●</b>new approach</span>
            <span><b className="publication">■</b>publication</span>
            <span><b className="failure">×</b>failed pass</span>
          </div>
          <p>Bars show active work. Select one for details.</p>
        </div>
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

function Metric({ label, value, tone = "normal" }) {
  return (
    <div className={`metric metric-${tone}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function ResourceStrip({ resources }) {
  const memoryAvailable = resources.memory_available_bytes / (1024 ** 3);
  const memoryTotal = resources.memory_total_bytes / (1024 ** 3);
  const memoryUsed = Math.max(0, 100 - (memoryAvailable / memoryTotal) * 100);
  const pressure = resources.cpu_percent >= 90 || resources.load1 > resources.cpu_count;
  return (
    <section className={`resource-strip ${pressure ? "resource-pressure" : ""}`} aria-label="Host resources">
      <div className="resource-status">
        <span className="resource-dot" />
        <strong>{pressure ? "Host under pressure" : "Host healthy"}</strong>
      </div>
      <Resource label="CPU" value={`${Math.round(resources.cpu_percent)}%`} percent={resources.cpu_percent} />
      <Resource label={`Load / ${resources.cpu_count} CPUs`} value={resources.load1.toFixed(1)} percent={(resources.load1 / resources.cpu_count) * 100} />
      <Resource label="Memory" value={`${Math.round(memoryUsed)}%`} percent={memoryUsed} />
      <Resource label="Scratch" value={`${Math.round(resources.scratch_used_percent)}%`} percent={resources.scratch_used_percent} />
    </section>
  );
}

function Resource({ label, value, percent }) {
  return (
    <div className="resource">
      <div><span>{label}</span><strong>{value}</strong></div>
      <div className="resource-bar"><i style={{ width: `${Math.min(100, Math.max(2, percent))}%` }} /></div>
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
