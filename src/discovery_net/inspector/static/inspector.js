(() => {
  "use strict";

  const REFRESH_INTERVAL_MS = 2000;
  const RESPONSE_RELATIONS = new Set([
    "replies_to",
    "supports",
    "contradicts",
    "verifies",
    "reproduces",
    "formalizes",
    "refines",
  ]);
  const PROBLEM_KINDS = new Set(["problem_statement", "conjecture", "question"]);
  const WORK_KINDS = new Set([
    "finding",
    "lemma",
    "proof_attempt",
    "counterexample",
    "formalization",
  ]);
  const PRESENTATION_PRIORITY = new Map([
    ["subarea_of", 0],
    ["about", 1],
    ...[...RESPONSE_RELATIONS].map((kind) => [kind, 2]),
  ]);
  const state = {
    currentView: "feed",
    exploreRef: null,
    graphFingerprint: null,
    knowledgeFingerprint: null,
    live: true,
    networkFingerprint: null,
    networkGraph: null,
    nextRefresh: Date.now(),
    refreshing: false,
    selectedPeerRef: "local",
    selectedRef: null,
    snapshot: null,
    viewModel: null,
  };

  const elements = {
    chainValue: document.getElementById("chainValue"),
    consensusValue: document.getElementById("consensusValue"),
    errorMessage: document.getElementById("errorMessage"),
    exploreBreadcrumbs: document.getElementById("exploreBreadcrumbs"),
    exploreCatalog: document.getElementById("exploreCatalog"),
    exploreDetail: document.getElementById("exploreDetail"),
    feedDetail: document.getElementById("feedDetail"),
    feedList: document.getElementById("feedList"),
    fitGraph: document.getElementById("fitGraph"),
    graphDetail: document.getElementById("graphDetail"),
    graphValue: document.getElementById("graphValue"),
    heightValue: document.getElementById("heightValue"),
    kindFilter: document.getElementById("kindFilter"),
    knowledgeGraph: document.getElementById("knowledgeGraph"),
    liveLabel: document.getElementById("liveLabel"),
    liveState: document.getElementById("liveState"),
    liveToggle: document.getElementById("liveToggle"),
    mempoolValue: document.getElementById("mempoolValue"),
    networkDetail: document.getElementById("networkDetail"),
    observedAt: document.getElementById("observedAt"),
    peerGraph: document.getElementById("peerGraph"),
    peerValue: document.getElementById("peerValue"),
    refreshButton: document.getElementById("refreshButton"),
    syncValue: document.getElementById("syncValue"),
  };

  class MarkdownRenderer {
    constructor() {
      this.markdown = window.markdownit({
        breaks: false,
        html: false,
        linkify: true,
        typographer: true,
      });
    }

    render(markdown) {
      const container = document.createElement("div");
      container.className = "markdown-body";
      const protectedMath = protectMath(markdown);
      const rendered = this.markdown.render(protectedMath.markdown);
      container.replaceChildren(
        window.DOMPurify.sanitize(rendered, {
          ALLOW_ARIA_ATTR: true,
          ALLOW_DATA_ATTR: false,
          FORBID_ATTR: ["style"],
          FORBID_TAGS: ["button", "embed", "form", "iframe", "input", "object", "style"],
          RETURN_DOM_FRAGMENT: true,
          SANITIZE_NAMED_PROPS: true,
          USE_PROFILES: { html: true },
        }),
      );
      restoreMath(container, protectedMath.expressions);
      container.querySelectorAll("a").forEach((link) => {
        link.rel = "noreferrer noopener";
      });
      window.renderMathInElement(container, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "\\[", right: "\\]", display: true },
          { left: "\\(", right: "\\)", display: false },
          { left: "$", right: "$", display: false },
        ],
        ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option"],
        maxExpand: 1000,
        maxSize: 20,
        strict: "ignore",
        throwOnError: false,
        trust: false,
      });
      return container;
    }
  }

  class KnowledgeGraphViewModel {
    constructor(graph) {
      this.graph = graph;
      this.contributions = [...graph.contributions].sort(compareConsensusAscending);
      this.relations = [...graph.relations].sort(compareConsensusAscending);
      this.contributionsByRef = new Map(
        this.contributions.map((contribution) => [contribution.artifact_ref, contribution]),
      );
      this.incomingByRef = groupRelations(this.relations, "to_contribution");
      this.outgoingByRef = groupRelations(this.relations, "from_contribution");
      this.presentationParents = this.buildPresentationParents();
    }

    contribution(ref) {
      return this.contributionsByRef.get(ref) ?? null;
    }

    incidentRelations(ref) {
      const relations = [...(this.incomingByRef.get(ref) ?? []), ...(this.outgoingByRef.get(ref) ?? [])];
      return uniqueBy(relations, (relation) => relation.artifact_ref).sort(compareConsensusAscending);
    }

    threadChildren(ref) {
      const seen = new Set();
      return (this.incomingByRef.get(ref) ?? [])
        .filter((relation) => RESPONSE_RELATIONS.has(relation.kind))
        .map((relation) => ({
          contribution: this.contribution(relation.from_contribution),
          relation,
        }))
        .filter(({ contribution }) => contribution !== null)
        .filter(({ contribution }) => {
          if (seen.has(contribution.artifact_ref)) return false;
          seen.add(contribution.artifact_ref);
          return true;
        })
        .sort((left, right) => compareConsensusAscending(left.contribution, right.contribution));
    }

    rootAreas() {
      const areas = this.contributions.filter(
        (contribution) => contribution.kind === "mathematical_area",
      );
      const roots = areas.filter((area) => {
        const parent = this.presentationParents.get(area.artifact_ref);
        return !parent || this.contribution(parent)?.kind !== "mathematical_area";
      });
      return roots.length > 0 ? roots : areas;
    }

    catalogChildren(ref) {
      const relations = this.incomingByRef.get(ref) ?? [];
      const seen = new Set();
      return relations
        .filter((relation) => ["subarea_of", "about"].includes(relation.kind))
        .map((relation) => this.contribution(relation.from_contribution))
        .filter((contribution) => contribution !== null)
        .filter((contribution) => {
          if (seen.has(contribution.artifact_ref)) return false;
          seen.add(contribution.artifact_ref);
          return true;
        })
        .sort(compareCatalogEntries);
    }

    breadcrumb(ref) {
      const path = [];
      const seen = new Set();
      let cursor = ref;
      while (cursor && !seen.has(cursor)) {
        seen.add(cursor);
        const contribution = this.contribution(cursor);
        if (!contribution) break;
        path.unshift(contribution);
        cursor = this.presentationParents.get(cursor) ?? null;
      }
      return path;
    }

    transactions() {
      const groups = new Map();
      [...this.contributions, ...this.relations].forEach((artifact, ordinal) => {
        const key = `${artifact.height}:${artifact.transaction_index}`;
        if (!groups.has(key)) {
          groups.set(key, {
            artifacts: [],
            height: artifact.height,
            transactionIndex: artifact.transaction_index,
          });
        }
        groups.get(key).artifacts.push({ artifact, ordinal });
      });
      return [...groups.values()]
        .map((group) => ({
          ...group,
          artifacts: group.artifacts
            .sort((left, right) => artifactOrder(left) - artifactOrder(right))
            .map(({ artifact }) => artifact),
        }))
        .sort(
          (left, right) =>
            right.height - left.height || right.transactionIndex - left.transactionIndex,
        );
    }

    graphElements(kind) {
      const contributions = this.contributions.filter(
        (contribution) => kind === "all" || contribution.kind === kind,
      );
      const included = new Set(contributions.map((contribution) => contribution.artifact_ref));
      const nodes = [
        {
          classes: "layout-tree synthetic-root",
          data: {
            artifactRef: null,
            id: "mathematics-root",
            kind: "root",
            label: "Mathematics",
          },
        },
        ...contributions.map((contribution) => ({
          classes: `layout-tree ${kindClass(contribution.kind)}`,
          data: {
            artifactRef: contribution.artifact_ref,
            id: contribution.artifact_ref,
            kind: contribution.kind,
            label: contribution.title,
          },
        })),
      ];
      const layoutEdges = contributions.map((contribution) => {
        const proposedParent = this.presentationParents.get(contribution.artifact_ref);
        const parent = proposedParent && included.has(proposedParent) ? proposedParent : "mathematics-root";
        return {
          classes: "layout-tree layout-edge",
          data: {
            id: `layout:${contribution.artifact_ref}`,
            source: parent,
            target: contribution.artifact_ref,
          },
        };
      });
      const realEdges = this.relations
        .filter(
          (relation) =>
            included.has(relation.from_contribution) && included.has(relation.to_contribution),
        )
        .map((relation) => ({
          classes: `real-edge relation-${relation.kind}`,
          data: {
            artifactRef: relation.artifact_ref,
            id: `relation:${relation.artifact_ref}`,
            kind: relation.kind,
            label: humanize(relation.kind),
            source: relation.from_contribution,
            target: relation.to_contribution,
          },
        }));
      return [...nodes, ...layoutEdges, ...realEdges];
    }

    buildPresentationParents() {
      const parents = new Map();
      this.contributions.forEach((contribution) => {
        const candidates = (this.outgoingByRef.get(contribution.artifact_ref) ?? [])
          .filter(
            (relation) =>
              PRESENTATION_PRIORITY.has(relation.kind) &&
              this.contributionsByRef.has(relation.to_contribution),
          )
          .sort(
            (left, right) =>
              PRESENTATION_PRIORITY.get(left.kind) - PRESENTATION_PRIORITY.get(right.kind) ||
              left.to_contribution.localeCompare(right.to_contribution) ||
              left.artifact_ref.localeCompare(right.artifact_ref),
          );
        for (const candidate of candidates) {
          if (!wouldCreateCycle(contribution.artifact_ref, candidate.to_contribution, parents)) {
            parents.set(contribution.artifact_ref, candidate.to_contribution);
            break;
          }
        }
      });
      return parents;
    }
  }

  class RadialKnowledgeGraph {
    constructor(container, onSelect) {
      this.container = container;
      this.onSelect = onSelect;
      this.graph = null;
    }

    render(viewModel, kind) {
      this.destroy();
      this.graph = window.cytoscape({
        container: this.container,
        elements: viewModel.graphElements(kind),
        minZoom: 0.18,
        maxZoom: 3,
        style: graphStyles(),
      });
      this.graph
        .elements(".layout-tree")
        .layout({
          name: "breadthfirst",
          roots: "#mathematics-root",
          circle: true,
          directed: true,
          avoidOverlap: true,
          nodeDimensionsIncludeLabels: true,
          spacingFactor: 1.35,
          padding: 48,
          animate: false,
        })
        .run();
      this.graph.on("tap", "node", (event) => {
        const ref = event.target.data("artifactRef");
        if (!ref) {
          this.clearSelection();
          return;
        }
        this.highlight(ref);
        this.onSelect(ref);
      });
      this.graph.on("tap", (event) => {
        if (event.target === this.graph) this.clearSelection();
      });
    }

    highlight(ref) {
      if (!this.graph) return;
      const selected = this.graph.getElementById(ref);
      if (selected.empty()) return;
      this.graph.elements().removeClass("faded incident selected");
      this.graph.nodes().not(selected).addClass("faded");
      this.graph.edges(".real-edge").addClass("faded");
      selected.addClass("selected").removeClass("faded");
      const edges = selected.connectedEdges(".real-edge");
      edges.addClass("incident").removeClass("faded");
      edges.connectedNodes().addClass("incident").removeClass("faded");
    }

    clearSelection() {
      this.graph?.elements().removeClass("faded incident selected");
    }

    fit() {
      this.graph?.fit(this.graph.elements(".layout-tree"), 48);
    }

    resize() {
      this.graph?.resize();
    }

    destroy() {
      this.graph?.destroy();
      this.graph = null;
    }
  }

  const markdownRenderer = new MarkdownRenderer();
  const knowledgeGraph = new RadialKnowledgeGraph(elements.knowledgeGraph, selectContribution);

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });
  document.querySelectorAll("[data-view-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      showView(link.dataset.viewLink);
    });
  });
  elements.liveToggle.addEventListener("click", () => {
    state.live = !state.live;
    state.nextRefresh = Date.now() + REFRESH_INTERVAL_MS;
    elements.liveToggle.textContent = state.live ? "Pause" : "Resume";
    elements.liveToggle.setAttribute("aria-pressed", String(!state.live));
    renderLiveState();
  });
  elements.refreshButton.addEventListener("click", refresh);
  elements.kindFilter.addEventListener("change", () => renderKnowledgeGraph(true));
  elements.fitGraph.addEventListener("click", () => knowledgeGraph.fit());

  async function refresh() {
    if (state.refreshing) return;
    state.refreshing = true;
    elements.refreshButton.disabled = true;
    try {
      const response = await fetch("/api/snapshot", { cache: "no-store" });
      if (!response.ok) throw new Error(`Snapshot request failed with ${response.status}`);
      state.snapshot = await response.json();
      state.viewModel = new KnowledgeGraphViewModel(state.snapshot.knowledge_graph);
      if (state.selectedRef && !state.viewModel.contribution(state.selectedRef)) {
        state.selectedRef = null;
      }
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
    const fingerprint = knowledgeFingerprint(state.viewModel);
    if (fingerprint !== state.knowledgeFingerprint) {
      state.knowledgeFingerprint = fingerprint;
      renderKindFilter();
      renderFeed();
      renderExplore();
      renderKnowledgeGraph(false);
      renderSelectedDetails();
    }
    renderPeerGraph();
  }

  function showView(view) {
    if (!["feed", "explore", "graph", "network"].includes(view)) return;
    state.currentView = view;
    document.querySelectorAll("[data-view-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.viewPanel !== view;
    });
    document.querySelectorAll("[data-view]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.view === view));
    });
    if (view === "graph") {
      knowledgeGraph.resize();
      knowledgeGraph.fit();
    }
    if (view === "network") {
      state.networkGraph?.resize();
      state.networkGraph?.fit(undefined, 52);
    }
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
    const viewModel = state.viewModel;
    if (!viewModel) return;
    const selected = elements.kindFilter.value;
    const kinds = [...new Set(viewModel.contributions.map((value) => value.kind))].sort();
    elements.kindFilter.replaceChildren(
      option("all", "All contribution kinds"),
      ...kinds.map((kind) => option(kind, humanize(kind))),
    );
    elements.kindFilter.value = kinds.includes(selected) ? selected : "all";
  }

  function renderFeed() {
    const viewModel = state.viewModel;
    if (!viewModel) return;
    const groups = viewModel.transactions();
    if (groups.length === 0) {
      elements.feedList.replaceChildren(emptyState("No committed artifacts yet."));
      return;
    }
    elements.feedList.replaceChildren(
      ...groups.map((group) => {
        const article = document.createElement("article");
        article.className = "feed-card";
        const heading = document.createElement("header");
        const position = document.createElement("span");
        position.className = "consensus-position";
        position.textContent = `Block ${group.height} · transaction ${group.transactionIndex}`;
        const count = document.createElement("span");
        count.className = "artifact-count";
        count.textContent = `${group.artifacts.length} atomic artifact${group.artifacts.length === 1 ? "" : "s"}`;
        heading.append(position, count);
        const content = document.createElement("div");
        content.className = "feed-card-content";
        group.artifacts.forEach((artifact) => {
          if ("title" in artifact) {
            content.append(feedContribution(artifact));
          }
        });
        const relations = group.artifacts.filter((artifact) => "from_contribution" in artifact);
        if (relations.length > 0) content.append(relationContext(relations, viewModel));
        article.append(heading, content);
        return article;
      }),
    );
  }

  function feedContribution(contribution) {
    const article = document.createElement("article");
    article.className = "feed-contribution";
    const kind = document.createElement("span");
    kind.className = `kind-badge ${kindClass(contribution.kind)}`;
    kind.textContent = humanize(contribution.kind);
    const title = linkButton(contribution.title, () => selectContribution(contribution.artifact_ref));
    title.className = "title-button";
    const body = markdownRenderer.render(contribution.body);
    body.classList.add("feed-body");
    const signer = document.createElement("small");
    signer.className = "signer-line mono";
    signer.textContent = `Signed ${shortRef(contribution.signer_public_key)}`;
    article.append(kind, title, body, signer);
    return article;
  }

  function relationContext(relations, viewModel) {
    const container = document.createElement("div");
    container.className = "atomic-relations";
    const heading = document.createElement("strong");
    heading.textContent = "Relations committed atomically";
    const list = document.createElement("ul");
    relations.forEach((relation) => {
      const item = document.createElement("li");
      const source = viewModel.contribution(relation.from_contribution);
      const target = viewModel.contribution(relation.to_contribution);
      item.textContent = `${source?.title ?? shortRef(relation.from_contribution)} ${humanize(relation.kind).toLowerCase()} ${target?.title ?? shortRef(relation.to_contribution)}`;
      list.append(item);
    });
    container.append(heading, list);
    return container;
  }

  function renderExplore() {
    const viewModel = state.viewModel;
    if (!viewModel) return;
    const current = state.exploreRef ? viewModel.contribution(state.exploreRef) : null;
    if (state.exploreRef && !current) state.exploreRef = null;
    const path = state.exploreRef ? viewModel.breadcrumb(state.exploreRef) : [];
    elements.exploreBreadcrumbs.replaceChildren(
      linkButton("Mathematics", () => {
        state.exploreRef = null;
        renderExplore();
      }),
      ...path.flatMap((contribution) => [
        separator(),
        linkButton(contribution.title, () => {
          state.exploreRef = contribution.artifact_ref;
          selectContribution(contribution.artifact_ref);
          renderExplore();
        }),
      ]),
    );
    const children = state.exploreRef
      ? viewModel.catalogChildren(state.exploreRef)
      : viewModel.rootAreas();
    const sections = state.exploreRef
      ? [
          ["Subareas", children.filter((value) => value.kind === "mathematical_area")],
          ["Problems", children.filter((value) => PROBLEM_KINDS.has(value.kind))],
          [
            "Work and discussion",
            children.filter(
              (value) => value.kind !== "mathematical_area" && !PROBLEM_KINDS.has(value.kind),
            ),
          ],
        ]
      : [["Areas of mathematics", children]];
    const rendered = sections
      .filter(([_title, contributions]) => contributions.length > 0)
      .map(([title, contributions]) => catalogSection(title, contributions));
    elements.exploreCatalog.replaceChildren(
      ...(rendered.length > 0 ? rendered : [emptyState("Nothing has been cataloged here yet.")]),
    );
  }

  function catalogSection(title, contributions) {
    const section = document.createElement("section");
    section.className = "catalog-section";
    const heading = document.createElement("h2");
    heading.textContent = title;
    const list = document.createElement("div");
    list.className = "catalog-list";
    contributions.forEach((contribution) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "catalog-item";
      button.addEventListener("click", () => {
        selectContribution(contribution.artifact_ref);
        if (contribution.kind === "mathematical_area" || PROBLEM_KINDS.has(contribution.kind)) {
          state.exploreRef = contribution.artifact_ref;
          renderExplore();
        }
      });
      const label = document.createElement("span");
      label.className = "catalog-title";
      label.textContent = contribution.title;
      const meta = document.createElement("span");
      meta.className = "catalog-meta";
      meta.textContent = humanize(contribution.kind);
      const arrow = document.createElement("span");
      arrow.className = "catalog-arrow";
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = "→";
      button.append(label, meta, arrow);
      list.append(button);
    });
    section.append(heading, list);
    return section;
  }

  function renderKnowledgeGraph(force) {
    const viewModel = state.viewModel;
    if (!viewModel) return;
    const fingerprint = `${elements.kindFilter.value}:${viewModel.contributions.map((item) => item.artifact_ref).join(",")}:${viewModel.relations.map((item) => item.artifact_ref).join(",")}`;
    if (!force && fingerprint === state.graphFingerprint) return;
    state.graphFingerprint = fingerprint;
    knowledgeGraph.render(viewModel, elements.kindFilter.value);
    if (state.selectedRef) knowledgeGraph.highlight(state.selectedRef);
  }

  function renderPeerGraph() {
    const node = state.snapshot?.node;
    if (!node) return;
    const fingerprint = `${node.node_id}:${node.peers.map((peer) => `${peer.node_id}:${peer.direction}`).join(",")}`;
    if (fingerprint === state.networkFingerprint) {
      renderNetworkDetails();
      return;
    }
    state.networkFingerprint = fingerprint;
    state.networkGraph?.destroy();
    const graphElements = [
      {
        data: { id: "local", label: node.moniker, scope: "local" },
        classes: "network-local",
      },
      ...node.peers.map((peer) => ({
        data: { id: peer.node_id, label: peer.moniker, scope: "peer" },
        classes: "network-peer",
      })),
      ...node.peers.map((peer) => ({
        data: {
          id: `peer:${peer.node_id}`,
          source: peer.direction === "outbound" ? "local" : peer.node_id,
          target: peer.direction === "outbound" ? peer.node_id : "local",
        },
        classes: peer.direction,
      })),
    ];
    state.networkGraph = window.cytoscape({
      container: elements.peerGraph,
      elements: graphElements,
      minZoom: 0.35,
      maxZoom: 2.5,
      style: networkStyles(),
      layout: { name: "circle", padding: 52, avoidOverlap: true },
    });
    state.networkGraph.on("tap", "node", (event) => {
      state.selectedPeerRef = event.target.id();
      state.networkGraph.nodes().removeClass("selected");
      event.target.addClass("selected");
      renderNetworkDetails();
    });
    renderNetworkDetails();
  }

  function renderNetworkDetails() {
    const node = state.snapshot?.node;
    if (!node) return;
    if (state.selectedPeerRef === "local") {
      elements.networkDetail.replaceChildren(
        detailHeading(node.moniker, "Local CometBFT node", "Local observation"),
        detailGrid([
          ["Authenticated node ID", node.node_id, true],
          ["Chain", node.chain_id],
          ["CometBFT", node.version],
          ["Application height", node.application_height.toLocaleString()],
          ["Validator power", node.validator_power.toLocaleString()],
          ["Latest block", new Date(node.latest_block_time).toLocaleString()],
        ]),
      );
      return;
    }
    const peer = node.peers.find((value) => value.node_id === state.selectedPeerRef);
    if (!peer) {
      state.selectedPeerRef = "local";
      renderNetworkDetails();
      return;
    }
    elements.networkDetail.replaceChildren(
      detailHeading(peer.moniker, "Directly connected CometBFT peer", "Observed + peer-reported"),
      paragraph(
        "The node ID and socket address are locally observed. The moniker is reported by the peer.",
      ),
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

  function selectContribution(ref) {
    state.selectedRef = ref;
    renderSelectedDetails();
    knowledgeGraph.highlight(ref);
  }

  function renderSelectedDetails() {
    const viewModel = state.viewModel;
    if (!viewModel || !state.selectedRef) return;
    [elements.feedDetail, elements.exploreDetail, elements.graphDetail].forEach((container) => {
      renderContributionDetail(container, state.selectedRef, viewModel);
    });
  }

  function renderContributionDetail(container, ref, viewModel) {
    const contribution = viewModel.contribution(ref);
    if (!contribution) return;
    const relations = viewModel.incidentRelations(ref);
    const article = document.createElement("article");
    article.className = "artifact-detail";
    article.append(
      detailHeading(contribution.title, humanize(contribution.kind), "Consensus-derived"),
      markdownRenderer.render(contribution.body),
      detailGrid([
        ["Artifact reference", contribution.artifact_ref, true],
        ["Signer public key", contribution.signer_public_key, true],
        [
          "Committed",
          `height ${contribution.height} · tx ${contribution.transaction_index} · artifact ${artifactIndex(contribution, 0)}`,
        ],
        ["Created", new Date(contribution.created_at).toLocaleString()],
        ["Signature", contribution.signature, true],
      ]),
      relatedArtifacts(relations, ref, viewModel),
      renderThread(ref, viewModel),
    );
    container.replaceChildren(article);
  }

  function relatedArtifacts(relations, currentRef, viewModel) {
    const section = document.createElement("section");
    section.className = "related-section";
    const heading = document.createElement("h3");
    heading.textContent = `Relations (${relations.length})`;
    const list = document.createElement("div");
    list.className = "relation-list";
    relations.forEach((relation) => {
      const outgoing = relation.from_contribution === currentRef;
      const otherRef = outgoing ? relation.to_contribution : relation.from_contribution;
      const other = viewModel.contribution(otherRef);
      const button = linkButton(
        `${outgoing ? "→" : "←"} ${humanize(relation.kind)} · ${other?.title ?? shortRef(otherRef)}`,
        () => selectContribution(otherRef),
      );
      list.append(button);
    });
    if (relations.length === 0) list.append(emptyState("No committed relations."));
    section.append(heading, list);
    return section;
  }

  function renderThread(rootRef, viewModel) {
    const section = document.createElement("section");
    section.className = "thread-section";
    const heading = document.createElement("h3");
    heading.textContent = "Discussion thread";
    const tree = document.createElement("div");
    tree.className = "thread-tree";
    const seen = new Set([rootRef]);
    appendThreadChildren(tree, rootRef, viewModel, seen);
    if (tree.childElementCount === 0) tree.append(emptyState("No responses have been committed."));
    section.append(heading, tree);
    return section;
  }

  function appendThreadChildren(container, parentRef, viewModel, seen) {
    viewModel.threadChildren(parentRef).forEach(({ contribution, relation }) => {
      if (seen.has(contribution.artifact_ref)) return;
      seen.add(contribution.artifact_ref);
      const branch = document.createElement("article");
      branch.className = "thread-branch";
      const relationLabel = document.createElement("span");
      relationLabel.className = `thread-relation relation-${relation.kind}`;
      relationLabel.textContent = humanize(relation.kind);
      const title = linkButton(contribution.title, () => selectContribution(contribution.artifact_ref));
      title.className = "thread-title";
      const body = markdownRenderer.render(contribution.body);
      body.classList.add("thread-body");
      const children = document.createElement("div");
      children.className = "thread-children";
      appendThreadChildren(children, contribution.artifact_ref, viewModel, seen);
      branch.append(relationLabel, title, body);
      if (children.childElementCount > 0) branch.append(children);
      container.append(branch);
    });
  }

  function detailHeading(title, subtitle, source) {
    const header = document.createElement("header");
    header.className = "detail-heading";
    const text = document.createElement("div");
    const heading = document.createElement("h2");
    heading.textContent = title;
    const description = document.createElement("p");
    description.textContent = subtitle;
    const provenance = document.createElement("span");
    provenance.className = "provenance";
    provenance.textContent = source;
    text.append(heading, description);
    header.append(text, provenance);
    return header;
  }

  function detailGrid(rows) {
    const list = document.createElement("dl");
    list.className = "detail-grid";
    rows.forEach(([label, value, mono = false]) => {
      const row = document.createElement("div");
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

  function graphStyles() {
    const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const palette = dark
      ? { surface: "#181b21", text: "#f2f4f7", muted: "#9fa8b7", border: "#3a414d" }
      : { surface: "#ffffff", text: "#17191d", muted: "#69707c", border: "#cfd5de" };
    return [
      {
        selector: "node",
        style: {
          label: "data(label)",
          color: palette.text,
          "background-color": palette.surface,
          "border-color": palette.border,
          "border-width": 1.5,
          shape: "round-rectangle",
          width: 112,
          height: 46,
          "font-size": 10,
          "font-weight": 600,
          "text-wrap": "ellipsis",
          "text-max-width": 96,
          "text-valign": "center",
          "text-halign": "center",
        },
      },
      { selector: ".synthetic-root", style: { "background-color": palette.text, color: palette.surface, width: 96 } },
      { selector: ".kind-area", style: { "border-color": "#7650bd", "border-width": 3 } },
      { selector: ".kind-problem", style: { "border-color": "#b36b14", "border-width": 3 } },
      { selector: ".kind-work", style: { "border-color": "#4169d8", "border-width": 3 } },
      { selector: ".kind-discourse", style: { "border-color": "#2c9464", "border-width": 3 } },
      {
        selector: ".layout-edge",
        style: {
          width: 1,
          "line-color": palette.border,
          "target-arrow-shape": "none",
          "curve-style": "straight",
          opacity: 0.62,
          events: "no",
        },
      },
      {
        selector: ".real-edge",
        style: {
          width: 1.6,
          "line-color": palette.muted,
          "target-arrow-color": palette.muted,
          "target-arrow-shape": "triangle",
          "arrow-scale": 0.8,
          "curve-style": "bezier",
          opacity: 0.16,
        },
      },
      { selector: ".relation-contradicts", style: { "line-color": "#c44750", "target-arrow-color": "#c44750" } },
      { selector: ".relation-supports, .relation-verifies", style: { "line-color": "#2c9464", "target-arrow-color": "#2c9464" } },
      { selector: ".selected", style: { "border-color": "#3157d5", "border-width": 5 } },
      { selector: ".incident", style: { opacity: 1, "z-index": 10 } },
      { selector: ".faded", style: { opacity: 0.13 } },
    ];
  }

  function networkStyles() {
    return [
      {
        selector: "node",
        style: {
          label: "data(label)",
          width: 72,
          height: 72,
          shape: "ellipse",
          "background-color": "#4169d8",
          color: "#ffffff",
          "font-size": 10,
          "text-wrap": "ellipsis",
          "text-max-width": 62,
          "text-valign": "center",
          "text-halign": "center",
        },
      },
      { selector: ".network-local", style: { "background-color": "#17191d", width: 88, height: 88 } },
      {
        selector: "edge",
        style: {
          width: 2,
          "curve-style": "bezier",
          "line-color": "#5c76c8",
          "target-arrow-color": "#5c76c8",
          "target-arrow-shape": "triangle",
        },
      },
      { selector: ".inbound", style: { "line-style": "dashed", "line-color": "#2c9464", "target-arrow-color": "#2c9464" } },
      { selector: ".selected", style: { "border-width": 5, "border-color": "#d9e2ff" } },
    ];
  }

  function groupRelations(relations, field) {
    const grouped = new Map();
    relations.forEach((relation) => {
      const key = relation[field];
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(relation);
    });
    return grouped;
  }

  function wouldCreateCycle(child, proposedParent, parents) {
    const seen = new Set([child]);
    let cursor = proposedParent;
    while (cursor) {
      if (seen.has(cursor)) return true;
      seen.add(cursor);
      cursor = parents.get(cursor);
    }
    return false;
  }

  function compareConsensusAscending(left, right) {
    return (
      left.height - right.height ||
      left.transaction_index - right.transaction_index ||
      artifactIndex(left, 0) - artifactIndex(right, 0) ||
      left.artifact_ref.localeCompare(right.artifact_ref)
    );
  }

  function compareCatalogEntries(left, right) {
    return (
      catalogRank(left.kind) - catalogRank(right.kind) ||
      left.title.localeCompare(right.title) ||
      left.artifact_ref.localeCompare(right.artifact_ref)
    );
  }

  function catalogRank(kind) {
    if (kind === "mathematical_area") return 0;
    if (PROBLEM_KINDS.has(kind)) return 1;
    if (WORK_KINDS.has(kind)) return 2;
    return 3;
  }

  function artifactIndex(artifact, fallback) {
    return Number.isInteger(artifact.artifact_index) ? artifact.artifact_index : fallback;
  }

  function artifactOrder({ artifact, ordinal }) {
    return Number.isInteger(artifact.artifact_index) ? artifact.artifact_index : 1_000_000 + ordinal;
  }

  function knowledgeFingerprint(viewModel) {
    if (!viewModel) return null;
    return `${viewModel.graph.indexed_height}:${viewModel.contributions.map((item) => item.artifact_ref).join(",")}:${viewModel.relations.map((item) => item.artifact_ref).join(",")}`;
  }

  function uniqueBy(values, key) {
    const seen = new Set();
    return values.filter((value) => {
      const identity = key(value);
      if (seen.has(identity)) return false;
      seen.add(identity);
      return true;
    });
  }

  function kindClass(kind) {
    if (kind === "mathematical_area") return "kind-area";
    if (PROBLEM_KINDS.has(kind)) return "kind-problem";
    if (WORK_KINDS.has(kind)) return "kind-work";
    return "kind-discourse";
  }

  function linkButton(label, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "link-button";
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
  }

  function option(value, label) {
    const element = document.createElement("option");
    element.value = value;
    element.textContent = label;
    return element;
  }

  function separator() {
    const element = document.createElement("span");
    element.className = "breadcrumb-separator";
    element.setAttribute("aria-hidden", "true");
    element.textContent = "/";
    return element;
  }

  function emptyState(message) {
    const element = document.createElement("div");
    element.className = "empty-state";
    element.textContent = message;
    return element;
  }

  function paragraph(value) {
    const element = document.createElement("p");
    element.className = "detail-lead";
    element.textContent = value;
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

  function humanize(value) {
    return String(value)
      .replaceAll("_", " ")
      .replace(/\b\w/g, (character) => character.toUpperCase());
  }

  function shortRef(value) {
    return value.length > 22 ? `${value.slice(0, 11)}…${value.slice(-7)}` : value;
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

  function protectMath(markdown) {
    const expressions = [];
    const pattern = /(?<!\\)(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$(?!\$)(?:\\.|[^$\n])+\$)/g;
    return {
      markdown: markdown.replace(pattern, (expression) => {
        const placeholder = `\uE000MATH${expressions.length}\uE001`;
        expressions.push([placeholder, expression]);
        return placeholder;
      }),
      expressions,
    };
  }

  function restoreMath(container, expressions) {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      let value = node.data;
      expressions.forEach(([placeholder, expression]) => {
        value = value.replaceAll(placeholder, expression);
      });
      node.data = value;
    }
  }

  function tick() {
    renderLiveState();
    if (state.live && Date.now() >= state.nextRefresh) refresh();
  }

  showView("feed");
  refresh();
  window.setInterval(tick, 250);
})();
