(() => {
  "use strict";

  const REFRESH_INTERVAL_MS = 2000;
  const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
  const state = {
    live: true,
    refreshing: false,
    nextRefresh: Date.now(),
    snapshot: null,
    selected: { scope: "local", id: "local" },
  };

  const elements = {
    activityList: document.getElementById("activityList"),
    chainValue: document.getElementById("chainValue"),
    consensusValue: document.getElementById("consensusValue"),
    detailContent: document.getElementById("detailContent"),
    detailSource: document.getElementById("detailSource"),
    detailSubtitle: document.getElementById("detailSubtitle"),
    detailTitle: document.getElementById("detailTitle"),
    errorMessage: document.getElementById("errorMessage"),
    graphValue: document.getElementById("graphValue"),
    heightValue: document.getElementById("heightValue"),
    kindFilter: document.getElementById("kindFilter"),
    knowledgeGraph: document.getElementById("knowledgeGraph"),
    liveLabel: document.getElementById("liveLabel"),
    liveState: document.getElementById("liveState"),
    liveToggle: document.getElementById("liveToggle"),
    mempoolValue: document.getElementById("mempoolValue"),
    observedAt: document.getElementById("observedAt"),
    peerGraph: document.getElementById("peerGraph"),
    peerValue: document.getElementById("peerValue"),
    refreshButton: document.getElementById("refreshButton"),
    syncValue: document.getElementById("syncValue"),
  };

  elements.liveToggle.addEventListener("click", () => {
    state.live = !state.live;
    state.nextRefresh = Date.now() + REFRESH_INTERVAL_MS;
    elements.liveToggle.textContent = state.live ? "Pause" : "Resume";
    elements.liveToggle.setAttribute("aria-pressed", String(!state.live));
    renderLiveState();
  });
  elements.refreshButton.addEventListener("click", () => refresh());
  elements.kindFilter.addEventListener("change", () => {
    renderKnowledgeGraph();
    renderDetails();
  });

  async function refresh() {
    if (state.refreshing) return;
    state.refreshing = true;
    elements.refreshButton.disabled = true;
    try {
      const response = await fetch("/api/snapshot", { cache: "no-store" });
      if (!response.ok) throw new Error(`Snapshot request failed with ${response.status}`);
      state.snapshot = await response.json();
      state.nextRefresh = Date.now() + REFRESH_INTERVAL_MS;
      elements.errorMessage.hidden = true;
      elements.liveState.classList.remove("error");
      render();
    } catch (error) {
      elements.errorMessage.textContent =
        error instanceof Error ? error.message : "Inspector snapshot unavailable";
      elements.errorMessage.hidden = false;
      elements.liveState.classList.add("error");
    } finally {
      state.refreshing = false;
      elements.refreshButton.disabled = false;
      renderLiveState();
    }
  }

  function render() {
    renderSummary();
    renderKindFilter();
    renderPeerGraph();
    renderKnowledgeGraph();
    renderDetails();
    renderActivity();
  }

  function renderSummary() {
    const snapshot = state.snapshot;
    if (!snapshot) return;
    const node = snapshot.node;
    const graph = snapshot.knowledge_graph;
    elements.chainValue.textContent = node.chain_id;
    elements.syncValue.textContent = node.catching_up ? "Catching up" : "Synchronized";
    elements.heightValue.textContent = node.application_height.toLocaleString();
    elements.consensusValue.textContent = `Round ${node.consensus_round} · ${humanize(node.consensus_step)}`;
    elements.peerValue.textContent = node.peers.length.toLocaleString();
    elements.graphValue.textContent = `${graph.contributions.length} nodes · ${graph.relations.length} edges`;
    elements.mempoolValue.textContent = `${node.mempool_transactions} transactions in local mempool`;
    elements.observedAt.textContent = `Observed ${new Date(snapshot.observed_at).toLocaleString()}`;
  }

  function renderKindFilter() {
    const graph = state.snapshot?.knowledge_graph;
    if (!graph) return;
    const selected = elements.kindFilter.value;
    const kinds = [...new Set(graph.contributions.map((value) => value.kind))].sort();
    const options = [option("all", "All contribution kinds")];
    kinds.forEach((kind) => options.push(option(kind, humanize(kind))));
    elements.kindFilter.replaceChildren(...options);
    elements.kindFilter.value = kinds.includes(selected) ? selected : "all";
  }

  function renderPeerGraph() {
    const node = state.snapshot?.node;
    if (!node) return;
    const peers = node.peers;
    const positions = peers.map((_peer, index) => {
      const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(peers.length, 1);
      return { x: 50 + Math.cos(angle) * 34, y: 50 + Math.sin(angle) * 34 };
    });
    const svg = svgElement("svg", {
      viewBox: "0 0 100 100",
      preserveAspectRatio: "none",
      "aria-hidden": "true",
    });
    peers.forEach((peer, index) => {
      const position = positions[index];
      svg.append(
        svgElement("line", {
          x1: "50",
          y1: "50",
          x2: String(position.x),
          y2: String(position.y),
          class: `graph-edge ${peer.direction}`,
        }),
      );
    });
    const local = graphButton({
      title: node.moniker,
      subtitle: "local node",
      x: 50,
      y: 50,
      className: "local",
      selected: state.selected.scope === "local",
      onSelect: () => select("local", "local"),
    });
    const peerButtons = peers.map((peer, index) =>
      graphButton({
        title: peer.moniker,
        subtitle: peer.direction,
        x: positions[index].x,
        y: positions[index].y,
        className: "peer",
        selected: state.selected.scope === "peer" && state.selected.id === peer.node_id,
        onSelect: () => select("peer", peer.node_id),
      }),
    );
    elements.peerGraph.replaceChildren(svg, local, ...peerButtons);
  }

  function renderKnowledgeGraph() {
    const graph = state.snapshot?.knowledge_graph;
    if (!graph) return;
    const filter = elements.kindFilter.value;
    const contributions = graph.contributions.filter(
      (value) => filter === "all" || value.kind === filter,
    );
    const groups = new Map();
    contributions.forEach((contribution) => {
      const column = columnForKind(contribution.kind);
      if (!groups.has(column)) groups.set(column, []);
      groups.get(column).push(contribution);
    });
    const positions = new Map();
    const xByColumn = [12, 37, 63, 88];
    groups.forEach((values, column) => {
      values.forEach((value, index) => {
        positions.set(value.artifact_ref, {
          x: xByColumn[column],
          y: ((index + 1) * 100) / (values.length + 1),
        });
      });
    });

    const svg = svgElement("svg", {
      viewBox: "0 0 100 100",
      preserveAspectRatio: "none",
      "aria-hidden": "true",
    });
    const defs = svgElement("defs", {});
    const marker = svgElement("marker", {
      id: "relationArrow",
      viewBox: "0 0 10 10",
      refX: "8",
      refY: "5",
      markerWidth: "5",
      markerHeight: "5",
      orient: "auto-start-reverse",
    });
    marker.append(svgElement("path", { d: "M 0 0 L 10 5 L 0 10 z", class: "edge-arrow" }));
    defs.append(marker);
    svg.append(defs);
    graph.relations.forEach((relation) => {
      const from = positions.get(relation.from_contribution);
      const to = positions.get(relation.to_contribution);
      if (!from || !to) return;
      svg.append(
        svgElement("line", {
          x1: String(from.x),
          y1: String(from.y),
          x2: String(to.x),
          y2: String(to.y),
          class: `graph-edge ${relation.kind}`,
          "marker-end": "url(#relationArrow)",
        }),
      );
    });
    const buttons = contributions.map((contribution) => {
      const position = positions.get(contribution.artifact_ref);
      return graphButton({
        title: contribution.title,
        subtitle: humanize(contribution.kind),
        x: position.x,
        y: position.y,
        className: kindClass(contribution.kind),
        selected:
          state.selected.scope === "contribution" &&
          state.selected.id === contribution.artifact_ref,
        onSelect: () => select("contribution", contribution.artifact_ref),
      });
    });
    elements.knowledgeGraph.replaceChildren(svg, ...buttons);
  }

  function renderDetails() {
    const snapshot = state.snapshot;
    if (!snapshot) return;
    const graph = snapshot.knowledge_graph;
    if (state.selected.scope === "peer") {
      const peer = snapshot.node.peers.find((value) => value.node_id === state.selected.id);
      if (peer) renderPeerDetails(peer);
      return;
    }
    if (state.selected.scope === "contribution") {
      const contribution = graph.contributions.find(
        (value) => value.artifact_ref === state.selected.id,
      );
      if (contribution) renderContributionDetails(contribution, graph.relations);
      return;
    }
    if (state.selected.scope === "relation") {
      const relation = graph.relations.find((value) => value.artifact_ref === state.selected.id);
      if (relation) renderRelationDetails(relation, graph.contributions);
      return;
    }
    renderLocalDetails(snapshot.node);
  }

  function renderLocalDetails(node) {
    elements.detailTitle.textContent = node.moniker;
    elements.detailSubtitle.textContent = "Local CometBFT node";
    elements.detailSource.textContent = "Local observation";
    elements.detailContent.replaceChildren(
      detailGrid([
        ["Authenticated node ID", node.node_id, true],
        ["Chain", node.chain_id],
        ["CometBFT", node.version],
        ["Application height", node.application_height.toLocaleString()],
        ["Validator power", node.validator_power.toLocaleString()],
        ["Latest block", new Date(node.latest_block_time).toLocaleString()],
      ]),
    );
  }

  function renderPeerDetails(peer) {
    elements.detailTitle.textContent = peer.moniker;
    elements.detailSubtitle.textContent = "Directly connected CometBFT peer";
    elements.detailSource.textContent = "Observed + peer-reported";
    elements.detailContent.replaceChildren(
      paragraph("The node ID and socket address are locally observed. The moniker is reported by the peer."),
      detailGrid([
        ["Authenticated node ID", peer.node_id, true],
        ["Observed address", peer.observed_address, true],
        ["Direction", humanize(peer.direction)],
        ["Connected", formatDuration(peer.connected_seconds)],
        ["Sent", formatBytes(peer.bytes_sent)],
        ["Received", formatBytes(peer.bytes_received)],
      ]),
    );
  }

  function renderContributionDetails(contribution, relations) {
    elements.detailTitle.textContent = contribution.title;
    elements.detailSubtitle.textContent = humanize(contribution.kind);
    elements.detailSource.textContent = "Consensus-derived";
    const related = relations.filter(
      (relation) =>
        relation.from_contribution === contribution.artifact_ref ||
        relation.to_contribution === contribution.artifact_ref,
    );
    elements.detailContent.replaceChildren(
      paragraph(contribution.body),
      detailGrid([
        ["Artifact reference", contribution.artifact_ref, true],
        ["Signer public key", contribution.signer_public_key, true],
        ["Committed", `height ${contribution.height} · tx ${contribution.transaction_index}`],
        ["Created", new Date(contribution.created_at).toLocaleString()],
        ["Signature", contribution.signature, true],
        ["Relations", related.length.toLocaleString()],
      ]),
      relationButtons(related),
    );
  }

  function renderRelationDetails(relation, contributions) {
    const source = contributions.find((value) => value.artifact_ref === relation.from_contribution);
    const destination = contributions.find(
      (value) => value.artifact_ref === relation.to_contribution,
    );
    elements.detailTitle.textContent = humanize(relation.kind);
    elements.detailSubtitle.textContent = `${source?.title ?? shortRef(relation.from_contribution)} → ${destination?.title ?? shortRef(relation.to_contribution)}`;
    elements.detailSource.textContent = "Consensus-derived edge";
    elements.detailContent.replaceChildren(
      detailGrid([
        ["Relation reference", relation.artifact_ref, true],
        ["Source", source?.title ?? relation.from_contribution],
        ["Destination", destination?.title ?? relation.to_contribution],
        ["Signer public key", relation.signer_public_key, true],
        ["Committed", `height ${relation.height} · tx ${relation.transaction_index}`],
        ["Signature", relation.signature, true],
      ]),
    );
  }

  function renderActivity() {
    const graph = state.snapshot?.knowledge_graph;
    if (!graph) return;
    const contributions = graph.contributions.map((value) => ({
      scope: "contribution",
      id: value.artifact_ref,
      height: value.height,
      title: value.title,
      kind: value.kind,
    }));
    const relations = graph.relations.map((value) => ({
      scope: "relation",
      id: value.artifact_ref,
      height: value.height,
      title: humanize(value.kind),
      kind: "relation",
    }));
    const activity = [...contributions, ...relations]
      .sort((left, right) => right.height - left.height)
      .slice(0, 8);
    elements.activityList.replaceChildren(
      ...activity.map((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "activity-item";
        button.addEventListener("click", () => select(item.scope, item.id));
        const height = document.createElement("span");
        height.className = "activity-height";
        height.textContent = `#${item.height}`;
        const description = document.createElement("span");
        const title = document.createElement("span");
        title.className = "activity-title";
        title.textContent = item.title;
        const meta = document.createElement("span");
        meta.className = "activity-meta";
        meta.textContent = humanize(item.kind);
        description.append(title, meta);
        button.append(height, description);
        return button;
      }),
    );
  }

  function select(scope, id) {
    state.selected = { scope, id };
    renderPeerGraph();
    renderKnowledgeGraph();
    renderDetails();
  }

  function graphButton({ title, subtitle, x, y, className, selected, onSelect }) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `graph-node ${className}`;
    button.style.left = `${x}%`;
    button.style.top = `${y}%`;
    button.setAttribute("aria-pressed", String(selected));
    button.addEventListener("click", onSelect);
    const strong = document.createElement("strong");
    strong.textContent = title;
    const small = document.createElement("small");
    small.textContent = subtitle;
    button.append(strong, small);
    return button;
  }

  function relationButtons(relations) {
    const container = document.createElement("div");
    container.className = "relation-list";
    relations.forEach((relation) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${humanize(relation.kind)} · ${shortRef(relation.artifact_ref)}`;
      button.addEventListener("click", () => select("relation", relation.artifact_ref));
      container.append(button);
    });
    return container;
  }

  function detailGrid(rows) {
    const list = document.createElement("dl");
    list.className = "detail-grid";
    rows.forEach(([label, value, mono = false]) => {
      const row = document.createElement("div");
      row.className = "detail-row";
      const term = document.createElement("dt");
      term.textContent = label;
      const description = document.createElement("dd");
      if (mono) description.className = "mono";
      description.textContent = String(value);
      row.append(term, description);
      list.append(row);
    });
    return list;
  }

  function paragraph(value) {
    const element = document.createElement("p");
    element.className = "detail-lead";
    element.textContent = value;
    return element;
  }

  function option(value, label) {
    const element = document.createElement("option");
    element.value = value;
    element.textContent = label;
    return element;
  }

  function svgElement(name, attributes) {
    const element = document.createElementNS(SVG_NAMESPACE, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  }

  function renderLiveState() {
    elements.liveState.classList.toggle("paused", !state.live);
    if (!elements.errorMessage.hidden) {
      elements.liveLabel.textContent = "Connection error";
      return;
    }
    if (!state.snapshot) {
      elements.liveLabel.textContent = "Connecting";
      return;
    }
    if (!state.live) {
      elements.liveLabel.textContent = "Paused";
      return;
    }
    const remaining = Math.max(0, state.nextRefresh - Date.now());
    elements.liveLabel.textContent = `Live · refresh in ${Math.ceil(remaining / 1000)}s`;
  }

  function tick() {
    renderLiveState();
    if (state.live && Date.now() >= state.nextRefresh) refresh();
  }

  function columnForKind(kind) {
    if (kind === "mathematical_area") return 0;
    if (["problem_statement", "conjecture", "question"].includes(kind)) return 1;
    if (["finding", "lemma", "proof_attempt", "counterexample", "formalization"].includes(kind)) {
      return 2;
    }
    return 3;
  }

  function kindClass(kind) {
    const column = columnForKind(kind);
    return ["kind-area", "kind-problem", "kind-work", "kind-discourse"][column];
  }

  function humanize(value) {
    return String(value)
      .replaceAll("_", " ")
      .replace(/\b\w/g, (character) => character.toUpperCase());
  }

  function shortRef(value) {
    return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-6)}` : value;
  }

  function formatBytes(value) {
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
  }

  function formatDuration(value) {
    const hours = Math.floor(value / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  }

  refresh();
  window.setInterval(tick, 250);
})();
