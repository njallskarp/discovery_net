import * as d3 from "d3";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

const roleTitle = {
  researcher: "Researcher",
  reviewer: "Reviewer",
  principal: "Principal",
  "impact-assessor": "Impact assessor",
};

export default function Timeline({ data, activeRoles }) {
  const hostRef = useRef(null);
  const tooltipRef = useRef(null);
  const [selection, setSelection] = useState("Select a bar or marker for exact timing and context.");

  useLayoutEffect(() => {
    const host = hostRef.current;
    const tooltip = tooltipRef.current;
    if (!host || !tooltip || !data.runs.length || !data.lanes.length) return undefined;

    const draw = () => {
      const width = Math.max(1_800, host.parentElement?.clientWidth || 1_800);
      const margin = { top: 38, right: 18, bottom: 66, left: 330 };
      const laneHeight = 43;
      const innerHeight = laneHeight * data.lanes.length;
      const height = margin.top + margin.bottom + innerHeight;
      host.replaceChildren();

      const runs = data.runs.map((run) => ({
        ...run,
        start: new Date(run.started_at),
        end: new Date(run.finished_at),
      }));
      const events = data.events.map((event) => ({ ...event, at: new Date(event.time) }));
      const extent = d3.extent(runs.flatMap((run) => [run.start, run.end]));
      const padding = 5 * 60 * 1_000;
      const x = d3.scaleUtc()
        .domain([new Date(+extent[0] - padding), new Date(+extent[1] + padding)])
        .range([margin.left, width - margin.right]);
      const y = d3.scaleBand()
        .domain(data.lanes.map((lane) => lane.id))
        .range([margin.top, margin.top + innerHeight])
        .paddingInner(0.18)
        .paddingOuter(0.04);
      const centerY = (lane) => y(lane) + y.bandwidth() / 2;

      const svg = d3.select(host).append("svg")
        .attr("class", "timeline-svg")
        .attr("viewBox", `0 0 ${width} ${height}`)
        .attr("width", width)
        .attr("height", height)
        .attr("role", "img")
        .attr("aria-label", "Research-team agent timeline with actual pass duration and impact annotations.");
      svg.append("title").text("Discovery Net research-team agent timeline");
      svg.append("desc").text("Solid bars show active passes. Markers show problem pivots, approach changes, publication, and failures.");

      svg.append("rect")
        .attr("class", "chart-frame")
        .attr("x", margin.left)
        .attr("y", margin.top)
        .attr("width", width - margin.left - margin.right)
        .attr("height", innerHeight);
      svg.append("g").selectAll("line")
        .data(data.lanes.slice(1))
        .join("line")
        .attr("class", "lane-rule")
        .attr("x1", margin.left)
        .attr("x2", width - margin.right)
        .attr("y1", (lane) => y(lane.id) - laneHeight * 0.09)
        .attr("y2", (lane) => y(lane.id) - laneHeight * 0.09);
      svg.append("g").selectAll("text")
        .data(data.lanes)
        .join("text")
        .attr("x", margin.left - 12)
        .attr("y", (lane) => centerY(lane.id) + 4)
        .attr("text-anchor", "end")
        .text((lane) => lane.full);

      const tickFormat = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/New_York",
        month: "short",
        day: "numeric",
        hour: "numeric",
      });
      const axis = d3.axisBottom(x).ticks(15).tickSizeOuter(0).tickFormat((date) => tickFormat.format(date));
      svg.append("g")
        .attr("class", "axis")
        .attr("transform", `translate(0,${margin.top + innerHeight})`)
        .call(axis);
      svg.append("text")
        .attr("class", "axis-title")
        .attr("x", margin.left + (width - margin.left - margin.right) / 2)
        .attr("y", height - 13)
        .attr("text-anchor", "middle")
        .text("Time in New York");
      svg.append("text")
        .attr("class", "axis-title")
        .attr("transform", `translate(14,${margin.top + innerHeight / 2}) rotate(-90)`)
        .attr("text-anchor", "middle")
        .text("Agent / problem lane");

      const snapshot = new Date(data.snapshot_at);
      svg.append("line")
        .attr("class", "snapshot-line")
        .attr("x1", x(snapshot)).attr("x2", x(snapshot))
        .attr("y1", margin.top).attr("y2", margin.top + innerHeight);
      svg.append("text")
        .attr("x", Math.min(width - margin.right - 2, x(snapshot) - 5))
        .attr("y", margin.top - 11)
        .attr("text-anchor", "end")
        .text("snapshot");

      const runGroups = svg.append("g").selectAll("g")
        .data(runs)
        .join("g")
        .attr("class", (run) => `role-item role-${run.role}${activeRoles.has(run.role) ? "" : " hidden-role"}`);
      runGroups.filter((run) => run.annotation?.impact === "substantial" || run.annotation?.impact === "major")
        .append("rect")
        .attr("class", (run) => `impact-outline impact-${run.annotation.impact}`)
        .attr("x", (run) => x(run.start) - 3)
        .attr("y", (run) => centerY(run.lane) - 11)
        .attr("width", (run) => Math.max(8, x(run.end) - x(run.start) + 6))
        .attr("height", 22)
        .attr("rx", 3);
      runGroups.append("rect")
        .attr("class", (run) => `run ${run.role}${run.state === "running" ? " current" : ""}`)
        .attr("x", (run) => x(run.start))
        .attr("y", (run) => centerY(run.lane) - 7.5)
        .attr("width", (run) => Math.max(2, x(run.end) - x(run.start)))
        .attr("height", 15);
      runGroups.filter((run) => run.state === "running").append("line")
        .attr("class", "current-cap")
        .attr("x1", (run) => x(run.end)).attr("x2", (run) => x(run.end))
        .attr("y1", (run) => centerY(run.lane) - 9.5)
        .attr("y2", (run) => centerY(run.lane) + 9.5);
      runGroups.filter((run) => run.state === "failed").each(function drawFailure(run) {
        const group = d3.select(this);
        const cx = x(run.end);
        const cy = centerY(run.lane);
        group.append("line").attr("class", "failure-cross").attr("x1", cx - 5).attr("x2", cx + 5).attr("y1", cy - 5).attr("y2", cy + 5);
        group.append("line").attr("class", "failure-cross").attr("x1", cx - 5).attr("x2", cx + 5).attr("y1", cy + 5).attr("y2", cy - 5);
      });
      runGroups.append("rect")
        .attr("class", "hit-target")
        .attr("x", (run) => x(run.start) - 4)
        .attr("y", (run) => centerY(run.lane) - Math.max(32, y.bandwidth()) / 2)
        .attr("width", (run) => Math.max(32, x(run.end) - x(run.start) + 8))
        .attr("height", Math.max(32, y.bandwidth()))
        .on("pointerenter pointermove", (event, run) => showTooltip(tooltip, event, runTitle(run), runDetail(run, data.lanes)))
        .on("pointerleave", () => hideTooltip(tooltip))
        .on("click", (_, run) => setSelection(runDetail(run, data.lanes)));

      const markerLayer = svg.append("g");
      events.filter((event) => event.from).forEach((event) => {
        markerLayer.append("line")
          .attr("class", `pivot-link role-item role-${event.role}${activeRoles.has(event.role) ? "" : " hidden-role"}`)
          .attr("x1", x(event.at)).attr("x2", x(event.at))
          .attr("y1", centerY(event.from)).attr("y2", centerY(event.lane));
      });
      const markerGroups = markerLayer.selectAll("g.event-mark")
        .data(events)
        .join("g")
        .attr("class", (event) => `event-mark role-item role-${event.role}${activeRoles.has(event.role) ? "" : " hidden-role"}`)
        .attr("transform", (event) => `translate(${x(event.at)},${centerY(event.lane)})`);
      markerGroups.each(function drawMarker(event) {
        const group = d3.select(this);
        if (event.type === "problem_pivot") {
          group.append("path").attr("d", d3.symbol().type(d3.symbolDiamond).size(90)()).attr("fill", "var(--viz-series-2)");
        } else if (event.type === "new_approach") {
          group.append("circle").attr("r", 5).attr("fill", "var(--viz-series-4)");
        } else if (event.type === "source_publication") {
          group.append("rect").attr("x", -5).attr("y", -5).attr("width", 10).attr("height", 10).attr("fill", "var(--viz-series-6)");
        }
      });
      markerGroups.append("circle")
        .attr("class", "hit-target")
        .attr("r", 16)
        .on("pointerenter pointermove", (event, marker) => showTooltip(tooltip, event, markerTitle(marker.type), markerDetail(marker)))
        .on("pointerleave", () => hideTooltip(tooltip))
        .on("click", (_, marker) => setSelection(markerDetail(marker)));
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(host.parentElement || host);
    return () => observer.disconnect();
  }, [data, activeRoles]);

  useEffect(() => () => hideTooltip(tooltipRef.current), []);

  return (
    <div className="timeline-root">
      <div className="timeline-scroll">
        <div className="timeline-chart" ref={hostRef} />
      </div>
      <div className="timeline-selection" aria-live="polite">{selection}</div>
      <div className="timeline-tooltip" role="tooltip" ref={tooltipRef} />
    </div>
  );
}

function runTitle(run) {
  if (run.state === "failed") return "Failed pass";
  if (run.state === "running") return "Pass in progress";
  return "Completed pass";
}

function runDetail(run, lanes) {
  const lane = lanes.find((item) => item.id === run.lane)?.full || run.lane;
  const details = [
    `${run.agent}${run.pass ? ` · pass ${run.pass}` : ""}`,
    lane,
    `${formatTime(run.start)}–${formatTime(run.end)} · ${duration(run.start, run.end)}`,
    `${roleTitle[run.role] || run.role} · ${run.state}`,
  ];
  if (run.model) details.push(`${run.model} · ${run.effort || "default"} · ${run.tier || "default"}`);
  if (run.annotation) {
    details.push(`Impact: ${run.annotation.impact}; novelty: ${humanize(run.annotation.novelty)}; paper potential: ${run.annotation.paper_potential}; confidence: ${run.annotation.confidence}.`);
    details.push(run.annotation.summary);
    details.push(`Rationale: ${run.annotation.rationale}`);
    if (run.annotation.caveats?.length) details.push(`Caveats: ${run.annotation.caveats.join(" · ")}`);
  }
  if (run.error) details.push(run.error);
  return details.join("\n");
}

function markerTitle(type) {
  return {
    problem_pivot: "Problem pivot",
    new_approach: "Approach change",
    source_publication: "Publication milestone",
  }[type] || "Campaign event";
}

function markerDetail(marker) {
  return `${formatTime(marker.at)} · ${marker.label || "Recorded campaign change"}`;
}

function showTooltip(element, event, title, detail) {
  if (!element) return;
  element.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = title;
  const body = document.createElement("span");
  body.className = "muted";
  body.textContent = detail;
  element.append(heading, document.createElement("br"), body);
  element.style.opacity = "1";
  const rootBox = element.parentElement.getBoundingClientRect();
  const box = element.getBoundingClientRect();
  let left = event.clientX - rootBox.left + 12;
  let top = event.clientY - rootBox.top + 12;
  if (left + box.width > rootBox.width) left = event.clientX - rootBox.left - box.width - 12;
  if (top + box.height > rootBox.height) top = event.clientY - rootBox.top - box.height - 12;
  element.style.left = `${Math.max(0, left)}px`;
  element.style.top = `${Math.max(0, top)}px`;
}

function hideTooltip(element) {
  if (element) element.style.opacity = "0";
}

function formatTime(date) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function duration(start, end) {
  const seconds = Math.max(0, Math.round((end - start) / 1_000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m${seconds % 60 ? ` ${seconds % 60}s` : ""}`;
}

function humanize(value) {
  return String(value).replaceAll("_", " ");
}
