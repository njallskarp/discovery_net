# Graph Report - discovery_net  (2026-08-30)

## Corpus Check
- 173 files · ~76,042 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2477 nodes · 6036 edges · 115 communities (96 shown, 8 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 572 edges (avg confidence: 0.88)
- Token cost: 86,000 input · 6,795 output

## Community Hubs (Navigation)
- Inspector Browser UI
- Local Artifact Ledger
- CometBFT Observation Client
- Knowledge Graph Index
- GraphQL & Domain Enums
- Envelope Codec & Signing
- Cytoscape Vendor Library
- Contribution & Relation Kinds
- CometBFT Callback Handler
- markdown-it Vendor Library
- CometBFT Config & Home
- CometBFT Genesis Writer
- markdown-it Rules Engine
- GraphQL Node Resolvers
- Callback Handler Tests
- ABCI Servicer Interface
- KaTeX DOM Builders
- Integration Node Harness
- ABCI gRPC Service
- Node Launcher Tests
- Cytoscape Layout Internals
- Inspector Service Entrypoint
- Inspector Projection Models
- SQLite Ledger Reader & Queries
- KaTeX Parser Internals
- SQLite Artifact Ledger Store
- Transaction Validator & Limits
- CLI Integration Tests
- CometBFT Validator Provisioning
- Runtime Endpoint & Peer Address
- Artifact Submitter
- CLI Argument Parsing
- Submission RPC Client
- Knowledge Graph Index API
- ABCI Request/Response Bindings
- KaTeX Style & Font Metrics
- KaTeX Expression Parser
- linkify-it URL Grammar
- Broadcast RPC Messages
- Transaction Encoding Tests
- Integration Network Harness
- ABCI gRPC Server
- Integration RPC Client
- Docker Node Harness
- Seeded Inspector Fixtures
- Inspector Service Core
- End-to-End Transaction Tests
- KaTeX Macro Expander
- Wire Format Tests
- Genesis Wire Compatibility Tests
- Cytoscape Rendering Internals
- Background Process Harness
- CometBFT Process Lifecycle
- Process & Provisioner Tests
- Inspector HTTP Server
- localnet.sh Script
- Node Observation Sources
- ABCI Protobuf Definitions
- Network Formation Process
- Integration Network Builder
- ABCI Adapter Tests
- Cytoscape Vendor Internals
- parse5 Entity Tokenizer
- P2P Identity Prep Script
- Genesis Trust Anchor
- Local Deployment Test Support
- Discovery Net CLI Driver
- Recovery & Sync Tests
- Knowledge Graph Query Tests
- Inspector Server Lifecycle
- markdown-it Delimiter Scanner
- Cytoscape Vendor Internals 2
- linkify-it Configuration
- KaTeX Namespace & Groups
- Endpoint Parsing Tests
- deploy.sh Script
- KaTeX Lexer
- Private Validator Key Models
- Broadcast Result & Errors
- Inspector Server Tests
- linkify-it Schema Matcher
- DOMPurify Vendor Library
- localnet Docker Inspection
- Validator Data Directories
- Inspector Certificate Check
- Node Process Tests
- CLI Submission Output Models
- verify.sh Script
- ABCI Package Wiring
- GraphQL Execution Result
- Vendor Parser Internals
- Genesis Document Model
- Validator Formation Tests
- GCP Single-Node Deployment Tests
- Compose Security Check
- KaTeX DOM Node Variant
- Caddy Config Check
- KaTeX DOM Node Variant 2
- Server Shutdown Context
- CometBFT Binary Fixture
- Deployment Config Check Script
- ABCI Info Method
- JSON-RPC HTTP Request
- Submission Lifecycle Doc

## God Nodes (most connected - your core abstractions)
1. `ArtifactLedgerSnapshot` - 65 edges
2. `ArtifactLedgerEntry` - 54 edges
3. `_` - 51 edges
4. `LocalArtifactLedger` - 49 edges
5. `IndexedArtifact` - 45 edges
6. `Contribution` - 44 edges
7. `encode_transaction()` - 44 edges
8. `IntegrationNetwork` - 44 edges
9. `ContributionRelation` - 40 edges
10. `InspectorService` - 38 edges

## Surprising Connections (you probably didn't know these)
- `test_descriptor_round_trips_through_json()` --calls--> `GenesisValidator`  [INFERRED]
  tests/test_genesis_validator.py → src/discovery_net/node/runtime/genesis_validator.py
- `test_transaction_codes_are_stable()` --calls--> `TransactionCode`  [INFERRED]
  tests/test_transaction_validator.py → src/discovery_net/node/transaction_validator.py
- `test_queries_require_a_knowledge_graph_index()` --calls--> `KnowledgeGraphQueries`  [INFERRED]
  tests/test_knowledge_graph_queries.py → src/discovery_net/query/knowledge_graph_queries.py
- `discovery-network genesis CLI` --semantically_similar_to--> `discovery-net CLI knowledge interface`  [INFERRED] [semantically similar]
  README.md → .agents/skills/discovery-net/SKILL.md
- `Discovery Net Inspector UI` --semantically_similar_to--> `discovery-net graphql command`  [INFERRED] [semantically similar]
  src/discovery_net/inspector/static/index.html → .agents/skills/discovery-net/references/graphql.md

## Import Cycles
- 2-file cycle: `src/discovery_net/node/runtime/cometbft_genesis_writer.py -> src/discovery_net/node/runtime/formation_process.py -> src/discovery_net/node/runtime/cometbft_genesis_writer.py`

## Hyperedges (group relationships)
- **Discovery Net interaction skill set** — _agents_skills_discovery_net_skill_discovery_net, _agents_skills_discovery_net_references_graph_model_graph_model, _agents_skills_discovery_net_references_graphql_graphql_guide, _agents_skills_discovery_net_references_submissions_submissions_guide [EXTRACTED 0.90]
- **Single-node cloud deployment stack** — deploy_gcp_single_node_readme_single_node_gcp_deployment, deploy_gcp_single_node_compose_cloud_cloud_overlay, localnet_compose_localnet_stack, src_discovery_net_inspector_static_index_inspector_ui [INFERRED 0.80]
- **Atomic artifact submission pipeline** — src_discovery_net_submission_readme_artifactsubmitter, src_discovery_net_submission_readme_cometbftrpcclient, _agents_skills_discovery_net_references_submissions_submit_command, localnet_compose_cometbft_service [INFERRED 0.75]

## Communities (115 total, 8 thin omitted)

### Community 0 - "Inspector Browser UI"
Cohesion: 0.07
Nodes (51): appendThreadChildren(), applyFeedPage(), applyGraphUpdate(), artifactIndex(), catalogRank(), catalogSection(), compareCatalogEntries(), compareConsensusAscending() (+43 more)

### Community 1 - "Local Artifact Ledger"
Cohesion: 0.07
Nodes (44): Persist and promote the finalized block, returning its new entries., _advance_state_hash(), ArtifactLedgerEntry, LocalArtifactLedger, _position(), ArtifactRef, Return the ledger produced by atomically appending one transaction., Return entries in canonical ledger order. (+36 more)

### Community 2 - "CometBFT Observation Client"
Cohesion: 0.06
Nodes (35): _RPCMethod, _CometBFTObservationClient, _consensus_step(), _peer_observation(), _ResultModel, Return one current observation assembled from CometBFT's local RPC views., Fetches typed read-only observations from one CometBFT JSON-RPC endpoint., Call one observation method and decode its typed result. (+27 more)

### Community 3 - "Knowledge Graph Index"
Cohesion: 0.07
Nodes (36): _AdjacencyKey, defaultdict, _append_state(), _build_state(), _connect(), _ContributionKindNode, _GraphState, _indexed_neighbors() (+28 more)

### Community 4 - "GraphQL & Domain Enums"
Cohesion: 0.08
Nodes (38): ConnectionDirection, PeerObservation, StrEnum, The side that initiated one observed peer connection., Raw metadata observed or reported for one direct CometBFT peer., _contribution(), _entry(), _peer() (+30 more)

### Community 5 - "Envelope Codec & Signing"
Cohesion: 0.09
Nodes (40): Return the signed envelope containing this artifact., _canonical_json(), _contribution_value(), _ContributionPayload, decode_envelope(), _encode_datetime(), encode_envelope(), encode_signing_payload() (+32 more)

### Community 6 - "Cytoscape Vendor Library"
Cohesion: 0.05
Nodes (20): cc(), eu(), Gl(), gs(), hc(), Il(), Iu(), Jl() (+12 more)

### Community 7 - "Contribution & Relation Kinds"
Cohesion: 0.06
Nodes (50): Contribution kinds, counterexample contribution kind, formalization contribution kind, Discovery Net graph model, mathematical_area contribution kind, objection contribution kind, problem_statement contribution kind, proof_attempt contribution kind (+42 more)

### Community 8 - "CometBFT Callback Handler"
Cohesion: 0.08
Nodes (31): IntEnum, CometBFTABCIAdapter, Translates ABCI protobuf messages into local callback operations., ArtifactLedgerHead, CometBFTCallbackHandler, _PendingBlock, Validate this node's supported genesis and return its initial state hash., Return the longest transaction prefix within the proposal byte limit. (+23 more)

### Community 9 - "markdown-it Vendor Library"
Cohesion: 0.07
Nodes (32): Pe(), after(), attrGet(), attrIndex(), attrJoin(), attrPush(), attrSet(), Be() (+24 more)

### Community 10 - "CometBFT Config & Home"
Cohesion: 0.08
Nodes (32): _CometBFTConfig, _mutable_table(), Path, Writes the complete supported runtime configuration without touching identity., Atomically apply settings and verify their parsed on-disk representation., Reject a configuration that does not encode the requested runtime settings., _replace_file(), _require_settings() (+24 more)

### Community 11 - "CometBFT Genesis Writer"
Cohesion: 0.09
Nodes (30): field_serializer, CometBFTGenesisWriter, _FormedGenesisDocument, _GenesisTemplate, _GenesisValidatorDocument, _PublicKeyDocument, BaseModel, Path (+22 more)

### Community 12 - "markdown-it Rules Engine"
Cohesion: 0.12
Nodes (43): p(), at(), s(), bt(), c(), ct(), Dt(), $e() (+35 more)

### Community 13 - "GraphQL Node Resolvers"
Cohesion: 0.13
Nodes (14): field, ID, Info, interface, _artifact_node(), _ArtifactNode, _contribution_node(), _contribution_nodes() (+6 more)

### Community 14 - "Callback Handler Tests"
Cohesion: 0.13
Nodes (37): FinalizeBlockResult, Validate a transaction against committed state without changing it., The deterministic response produced after executing an agreed block., The deterministic application result for one transaction., TransactionResult, callback_handler(), invalid_signature_transaction(), MemoryArtifactLedgerStore (+29 more)

### Community 15 - "ABCI Servicer Interface"
Cohesion: 0.05
Nodes (20): ABCIServicer, NOTE: When using custom types, mind the warnings.…, Missing associated documentation comment in .proto file., Missing associated documentation comment in .proto file., Missing associated documentation comment in .proto file., Missing associated documentation comment in .proto file., Missing associated documentation comment in .proto file., Missing associated documentation comment in .proto file. (+12 more)

### Community 16 - "KaTeX DOM Builders"
Cohesion: 0.07
Nodes (9): Bt, Ct(), Gt(), I, It, Lt(), qt, U (+1 more)

### Community 17 - "Integration Node Harness"
Cohesion: 0.07
Nodes (20): IntegrationNode, CometBFTRPCClient, Path, Start CometBFT, optionally waiting for its application handshake., Wait until the CometBFT JSON-RPC endpoint responds., Wait until CometBFT finishes block sync and accepts transactions., Return the locally persisted ledger snapshot when it exists., Owns the application, consensus process, addresses, and local ledger for one… (+12 more)

### Community 18 - "ABCI gRPC Service"
Cohesion: 0.06
Nodes (27): _ABCIGRPCService, RequestCheckTx, RequestCommit, RequestEcho, RequestFinalizeBlock, RequestFlush, RequestInitChain, RequestPrepareProposal (+19 more)

### Community 19 - "Node Launcher Tests"
Cohesion: 0.13
Nodes (30): CometBFTNodeLauncher, Path, Starts CometBFT without importing signing state or arranging validator…, launch_settings(), Path, Return one complete loopback launch configuration rooted in a test directory., Create the minimal file layout emitted by CometBFT init for isolated tests., Write one deterministic pristine Ed25519 identity and return its public key. (+22 more)

### Community 20 - "Cytoscape Layout Internals"
Cohesion: 0.12
Nodes (33): Ai(), Be(), Ce(), Cl(), co(), De(), Es(), Fi() (+25 more)

### Community 21 - "Inspector Service Entrypoint"
Cohesion: 0.09
Nodes (24): _argument_parser(), _inspector_service(), main(), ArgumentParser, Namespace, Run the configured inspector until interrupted., CometBFTObservationSource, Reads the current state reported by one local CometBFT RPC endpoint. (+16 more)

### Community 22 - "Inspector Projection Models"
Cohesion: 0.12
Nodes (32): InspectorContribution, InspectorContributionSummary, InspectorFeedPage, InspectorFeedTransaction, InspectorKnowledgeGraph, _InspectorModel, InspectorNode, InspectorNodeSnapshot (+24 more)

### Community 23 - "SQLite Ledger Reader & Queries"
Cohesion: 0.11
Nodes (29): _ledger_entry(), _bytes(), contains_entries(), create_schema(), insert_entries(), _integer(), Connection, Return persisted entries committed after the supplied block height. (+21 more)

### Community 24 - "KaTeX Parser Internals"
Cohesion: 0.09
Nodes (17): _, ar(), At(), br(), d(), ee(), g, handler() (+9 more)

### Community 25 - "SQLite Artifact Ledger Store"
Cohesion: 0.17
Nodes (26): ArtifactLedgerSnapshot, The ordered ledger entries persisted at a committed block height., Path, Persists append-only artifact-ledger snapshots transactionally., Load the latest committed snapshot, or return none before the first commit., SQLiteArtifactLedgerStore, Load this node's committed application state from its isolated store., entry() (+18 more)

### Community 26 - "Transaction Validator & Limits"
Cohesion: 0.08
Nodes (24): ArtifactLedgerLookup, Protocol, Looks up artifacts already recorded in committed ledger state., Return a committed artifact envelope by reference, if present., _is_contribution(), ArtifactRef, Return a deterministic result without modifying committed state., CodecError (+16 more)

### Community 27 - "CLI Integration Tests"
Cohesion: 0.15
Nodes (31): main(), Exception, Run one Discovery Net command and return its process exit code., _write_error(), _ledger_entry(), _output_refs(), Artifact, ArtifactRef (+23 more)

### Community 28 - "CometBFT Validator Provisioning"
Cohesion: 0.14
Nodes (21): _exclusive_lock(), Path, Create one unstarted home whose validator identity never leaves it., Bind one unstarted validator home to its final shared genesis., _replace_genesis(), _require_complete_home(), _require_unstarted_home(), _sync_directory() (+13 more)

### Community 29 - "Runtime Endpoint & Peer Address"
Cohesion: 0.12
Nodes (15): Endpoint, Identifies one TCP host and port without implying an exposure policy., Return whether the host denotes every local network interface., Render the endpoint in CometBFT's TCP URL form., PeerAddress, Pairs a CometBFT node identity with its dialable P2P endpoint., _argument_parser(), _peer_addresses() (+7 more)

### Community 30 - "Artifact Submitter"
Cohesion: 0.12
Nodes (16): AttachedRelation, ArtifactSubmitter, ArtifactRef, Signs artifacts and asks a local CometBFT node to broadcast them., Submit a contribution and its initial directed relations atomically., Submit a directed relation between existing contributions., _require_artifact_count(), _resolve_relation() (+8 more)

### Community 31 - "CLI Argument Parsing"
Cohesion: 0.14
Nodes (27): _add_contribution_traversal_arguments(), _add_relation_kind_argument(), _add_submission_arguments(), _argument_parser(), _artifact_reference(), _ArtifactOutput, _execute_query(), _graphql() (+19 more)

### Community 32 - "Submission RPC Client"
Cohesion: 0.11
Nodes (23): _RPCRequest, Ed25519PrivateKey, _BroadcastResponse, The immediate response returned by a CometBFT broadcast call., _CometBFTRPCClient, Sends encoded transactions to a local CometBFT RPC endpoint., Broadcast transaction bytes and return CometBFT's immediate CheckTx result., Return the chain identifier reported by the local CometBFT node. (+15 more)

### Community 33 - "Knowledge Graph Index API"
Cohesion: 0.18
Nodes (23): KnowledgeGraphIndex, Atomically append newly committed entries and advance the indexed height., Return all artifacts in canonical ledger order., Provides in-memory graph queries over a committed ledger snapshot., Return the committed height represented by this index., Atomically rebuild the index from a committed ledger snapshot., _contribution(), _entry() (+15 more)

### Community 34 - "ABCI Request/Response Bindings"
Cohesion: 0.07
Nodes (22): RequestCheckTx, RequestCommit, RequestFinalizeBlock, RequestInfo, RequestInitChain, RequestPrepareProposal, RequestProcessProposal, ResponseCheckTx (+14 more)

### Community 35 - "KaTeX Style & Font Metrics"
Cohesion: 0.12
Nodes (4): f, htmlBuilder(), mathmlBuilder(), Yt

### Community 37 - "linkify-it URL Grammar"
Cohesion: 0.13
Nodes (27): get_auth(), get_domain(), get_domain_root(), get_fuzzy_link_search(), get_fuzzy_mail_host(), get_fuzzy_mail_host_search(), get_fuzzy_url_host_port(), get_host_terminator() (+19 more)

### Community 38 - "Broadcast RPC Messages"
Cohesion: 0.13
Nodes (19): _BroadcastParameters, _BroadcastRequest, _BroadcastRPCResponse, _EmptyParameters, _NodeInfo, model_validator, Self, A successful or failed JSON-RPC response to a transaction broadcast. (+11 more)

### Community 39 - "Transaction Encoding Tests"
Cohesion: 0.23
Nodes (26): encode_transaction(), Encode an atomic signed transaction into its unique wire representation., append(), contribution(), envelope(), Artifact, parametrize, signed_transaction() (+18 more)

### Community 40 - "Integration Network Harness"
Cohesion: 0.09
Nodes (17): IntegrationNetwork, _peer_memberships(), BaseException, TracebackType, Start every application and CometBFT node in the requested topology., Start consensus for applications that are already running., Stop every CometBFT process while leaving applications running., Stop every consensus process and application. (+9 more)

### Community 41 - "ABCI gRPC Server"
Cohesion: 0.13
Nodes (21): ABCIStub, NOTE: When using custom types, mind the warnings.…, Constructor. Args: channel: A grpc.Channel., ABCIGRPCServer, Self, Runs the local CometBFT ABCI gRPC endpoint with explicit lifecycle ownership., Return the TCP port selected while binding the server., Start accepting ABCI requests. (+13 more)

### Community 42 - "Integration RPC Client"
Cohesion: 0.14
Nodes (18): boolean_field(), CometBFTRPCClient, integer_field(), json_object(), object_field(), JSONObject, Return one required string field., Return one required integer field. (+10 more)

### Community 43 - "Docker Node Harness"
Cohesion: 0.12
Nodes (14): CompletedProcess, DockerNode, CometBFTRPCClient, Wait until every expected moniker is directly connected., Require both P2P-direct and Docker-host routes to reject remote RPC., Run the configured consensus service once and return its exit result., Return bounded diagnostics for every service in this project., Return the complete explicit configuration for this Compose project. (+6 more)

### Community 44 - "Seeded Inspector Fixtures"
Cohesion: 0.18
Nodes (22): Returns one deterministic local-node observation for the demo., Returns deterministic committed ledger updates for the demo., Build an inspector service backed entirely by deterministic seed data., Create a small valid mathematical graph from signed network transactions., seed_ledger_snapshot(), SeedArtifactLedgerReader, seeded_inspector_service(), SeedNodeObservationSource (+14 more)

### Community 45 - "Inspector Service Core"
Cohesion: 0.13
Nodes (15): Return seeded entries committed after the supplied height., InspectorService, _node_view(), ArtifactRef, Return one reverse-chronological page of committed transactions., Return one full contribution body and provenance by artifact reference., Builds sanitized read-only views from node and committed ledger state., Return the latest internally consistent inspector snapshot. (+7 more)

### Community 46 - "End-to-End Transaction Tests"
Cohesion: 0.12
Nodes (23): parametrize, Path, Path: committed artifact → CheckTx; guards duplicate artifacts entering the…, Path: hostile transaction → CheckTx; guards malformed, foreign, and forged…, Path: empty proposal → Commit; guards height progress from mutating artifact…, Path: concurrent RPCs → one proposal → Commit; guards block order and aggregate…, Path: submitter → RPC → consensus → SQLite; guards the production outbound path., Path: CLI process → submitter → consensus → SQLite; guards the complete user… (+15 more)

### Community 48 - "Wire Format Tests"
Cohesion: 0.20
Nodes (23): encode_payload(), Encode a supported knowledge-graph artifact into canonical JSON bytes., area_contribution(), parametrize, sample_contribution(), sample_relation(), signed(), test_artifact_reference_covers_signer_chain_payload_and_signature() (+15 more)

### Community 49 - "Genesis Wire Compatibility Tests"
Cohesion: 0.12
Nodes (18): _InitChainRecorder, _observe_init_chain(), _OmittedType, parametrize, Path, RequestEcho, RequestFlush, RequestInfo (+10 more)

### Community 50 - "Cytoscape Rendering Internals"
Cohesion: 0.18
Nodes (21): b(), e(), el(), g(), kl(), lr(), m(), Mu() (+13 more)

### Community 51 - "Background Process Harness"
Cohesion: 0.12
Nodes (14): BackgroundProcess, Path, Runs one subprocess and retains its output for failure diagnostics., Fail with captured diagnostics if the process exited unexpectedly., Wait for an expected exit and return whether it occurred in time., Return all process output written so far., Interrupt the process and release its diagnostic log., Start the Discovery Net process and wait for its ABCI listener. (+6 more)

### Community 52 - "CometBFT Process Lifecycle"
Cohesion: 0.10
Nodes (12): RuntimeError, _ResultModel, Decode the successful result as its method-specific model., Wait until shutdown, returning whether the wait timed out., NoReturn, Path, Verify the exact startup capabilities used by this launcher., Create a new CometBFT home using the configured binary. (+4 more)

### Community 53 - "Process & Provisioner Tests"
Cohesion: 0.25
Nodes (18): _CometBFTProcess, Initializes and replaces the current process with a compatible CometBFT binary., CometBFTValidatorProvisioner, Owns fresh validator identity generation and one-time home provisioning., Path, test_process_accepts_the_complete_required_command_surface(), test_process_exec_rechecks_genesis_without_invoking_a_shell(), test_process_reports_missing_required_capabilities() (+10 more)

### Community 54 - "Inspector HTTP Server"
Cohesion: 0.22
Nodes (9): HTTPStatus, _InspectorRequestHandler, _katex_font(), _optional_feed_cursor(), _optional_query_integer(), BaseHTTPRequestHandler, BaseModel, _require_query_fields() (+1 more)

### Community 55 - "localnet.sh Script"
Cohesion: 0.25
Nodes (19): abspath(), cmd_bootstrap(), cmd_build(), cmd_down(), cmd_join(), cmd_logs(), cmd_node_id(), cmd_status() (+11 more)

### Community 56 - "Node Observation Sources"
Cohesion: 0.12
Nodes (10): NodeObservation, field_validator, The latest local observation of one CometBFT node., Return the seeded local-node observation., ArtifactLedgerReader, NodeObservationSource, Protocol, Observes the current state of one local consensus node. (+2 more)

### Community 58 - "Network Formation Process"
Cohesion: 0.24
Nodes (19): _argument_parser(), _create_genesis(), _emit(), _export_validator(), _GenesisOutput, _HomeOutput, _initialize_validator(), _install_genesis() (+11 more)

### Community 59 - "Integration Network Builder"
Cohesion: 0.19
Nodes (15): _available_ports(), _chain_id(), _node(), Path, Create a shared-genesis network with independent local ports and ledgers., Form a validator network exclusively through the production provisioning API., Create one validator, optionally reusing genesis or application state., _run() (+7 more)

### Community 60 - "ABCI Adapter Tests"
Cohesion: 0.20
Nodes (15): adapter(), MemoryArtifactLedgerStore, parametrize, test_adapter_rejects_the_wrong_request_message(), test_check_tx_maps_validation_code_without_changing_state(), test_commit_persists_before_returning_an_acknowledgement(), test_finalize_block_preserves_transaction_order_and_returns_app_hash(), test_finalize_block_rejects_an_oversized_transaction_that_bypassed_check_tx() (+7 more)

### Community 61 - "Cytoscape Vendor Internals"
Cohesion: 0.17
Nodes (16): a(), ch(), d(), Gd(), kh(), lh(), Nn(), a() (+8 more)

### Community 62 - "parse5 Entity Tokenizer"
Cohesion: 0.17
Nodes (18): A(), emitNamedEntityData(), emitNotTerminatedNamedEntity(), emitNumericEntity(), end(), ge(), he(), me() (+10 more)

### Community 63 - "P2P Identity Prep Script"
Cohesion: 0.13
Nodes (15): BASE_COMPOSE, CLOUD_COMPOSE, COMETBFT_DATA_DIRECTORY, compose(), ENV_FILE, env_value(), GENESIS_FILE, GENESIS_SHA256 (+7 more)

### Community 64 - "Genesis Trust Anchor"
Cohesion: 0.20
Nodes (14): GenesisTrustAnchor, Path, Self, Contains the expected identity of one exact CometBFT genesis document., Read once and verify the exact genesis bytes that will be installed., Write genesis test input and return the matching trust anchor., write_genesis(), parametrize (+6 more)

### Community 65 - "Local Deployment Test Support"
Cohesion: 0.17
Nodes (16): available_ports(), build_image(), create_p2p_network(), Build the exact runtime image used by every independent test node., Create the shared transport without granting a route to the Docker host., Remove the exact transport created for this test run., Remove the exact disposable image built for this test run., Reserve and release host-loopback ports for independent RPC proxies. (+8 more)

### Community 66 - "Discovery Net CLI Driver"
Cohesion: 0.17
Nodes (11): DiscoveryNetCLI, ArtifactRef, Ed25519PrivateKey, Path, Self, Submit a contribution package and return all artifact references., Submit a post-hoc relation between committed contributions., Runs production submission commands against one CometBFT RPC endpoint. (+3 more)

### Community 67 - "Recovery & Sync Tests"
Cohesion: 0.19
Nodes (14): Path, Path: commit → full restart → commit; guards durable state and handshake…, Path: commit → consensus restart → commit; guards ABCI reconnection and height…, test_application_and_cometbft_restart_then_commit_again(), test_cometbft_restart_reconnects_to_the_running_application(), Path, Path: existing validator → late peer block sync → local app; guards history…, Path: non-validator RPC → peer gossip → validator → all apps; guards ingress… (+6 more)

### Community 68 - "Knowledge Graph Query Tests"
Cohesion: 0.28
Nodes (14): _append(), _contribution(), _graph_fixture(), _GraphFixture, Artifact, ArtifactRef, _refs(), _relation() (+6 more)

### Community 69 - "Inspector Server Lifecycle"
Cohesion: 0.14
Nodes (7): InspectorServer, Self, Serve requests until shutdown is requested., Stop a running serve loop., Hosts one local read-only inspector service and its browser interface., Return the host bound by the local HTTP server., Return the port bound by the local HTTP server.

### Community 70 - "markdown-it Delimiter Scanner"
Cohesion: 0.20
Nodes (14): F(), ft(), k(), ke(), Le(), mt(), N(), P() (+6 more)

### Community 71 - "Cytoscape Vendor Internals 2"
Cohesion: 0.19
Nodes (13): ah(), fs(), Gc(), hn(), Ih(), jd(), i(), nh() (+5 more)

### Community 72 - "linkify-it Configuration"
Cohesion: 0.19
Nodes (13): configure(), constructor(), de(), En(), enable(), enableOnly(), q(), set() (+5 more)

### Community 73 - "KaTeX Namespace & Groups"
Cohesion: 0.18
Nodes (3): an(), w(), Yn

### Community 74 - "Endpoint Parsing Tests"
Cohesion: 0.23
Nodes (9): Self, Parse a host-and-port authority into an endpoint., Self, Parse CometBFT's node-id-at-endpoint peer representation., parametrize, test_endpoint_rejects_incomplete_or_ambiguous_values(), test_endpoint_round_trips_supported_authorities(), test_peer_address_normalizes_the_node_identity() (+1 more)

### Community 75 - "deploy.sh Script"
Cohesion: 0.27
Nodes (10): BASE_COMPOSE, CLOUD_COMPOSE, compose(), ENV_FILE, env_value(), INFRA_ENV_FILE, metadata_value(), refresh_infra_env() (+2 more)

### Community 76 - "KaTeX Lexer"
Cohesion: 0.18
Nodes (3): en, tn, Xn

### Community 77 - "Private Validator Key Models"
Cohesion: 0.24
Nodes (7): _EncodedKey, _PrivateValidatorKey, _PrivateValidatorState, BaseModel, field_validator, model_validator, Self

### Community 78 - "Broadcast Result & Errors"
Cohesion: 0.22
Nodes (7): _BroadcastResult, BaseModel, field_validator, Raise the submission-layer representation of this RPC error., _RPCError, Raised when a local CometBFT node cannot provide a valid broadcast response., SubmissionError

### Community 79 - "Inspector Server Tests"
Cohesion: 0.27
Nodes (7): HTTPMessage, _available_loopback_port(), _FailingNodeSource, _get(), test_inspector_process_starts_the_seeded_application(), test_server_reports_an_unavailable_observation_without_leaking_details(), _wait_for_snapshot()

### Community 80 - "linkify-it Schema Matcher"
Cohesion: 0.22
Nodes (10): add(), __compile__(), dn(), fn(), match(), matchAtStart(), mn(), normalize() (+2 more)

### Community 82 - "DOMPurify Vendor Library"
Cohesion: 0.33
Nodes (6): e(), L(), M(), P(), t(), U()

### Community 83 - "localnet Docker Inspection"
Cohesion: 0.36
Nodes (6): _json_object(), _peer_moniker(), JSONObject, Return Docker's runtime description for one project service., Return the monikers currently connected through CometBFT P2P., _rpc_call()

### Community 84 - "Validator Data Directories"
Cohesion: 0.22
Nodes (6): initialize_validator(), Path, Create one test-only validator fixture without changing launcher scope., Return the host directory containing only CometBFT state., Return the host directory containing only application state., Return the host-visible artifact ledger path.

### Community 85 - "Inspector Certificate Check"
Cohesion: 0.39
Nodes (7): _check(), main(), _name_values(), _parser(), ArgumentParser, Namespace, _validate_certificate()

### Community 86 - "Node Process Tests"
Cohesion: 0.46
Nodes (7): Popen, _available_loopback_address(), Path, _start_node(), _stop_node(), test_node_process_serves_abci_and_restores_committed_state(), _transaction()

### Community 87 - "CLI Submission Output Models"
Cohesion: 0.29
Nodes (4): BaseModel, field_validator, model_validator, _SubmissionOutput

### Community 88 - "verify.sh Script"
Cohesion: 0.33
Nodes (6): CONNECT_RULE, env_value(), INFRA_ENV_FILE, INSPECTOR_URL, RPC_URL, verify.sh script

### Community 90 - "GraphQL Execution Result"
Cohesion: 0.29
Nodes (5): GraphQLResult, JSONObject, Execute one GraphQL operation and return its data and formatted errors., The serializable result of one GraphQL operation., Return whether execution completed without GraphQL errors.

### Community 91 - "Vendor Parser Internals"
Cohesion: 0.33
Nodes (7): b(), i(), l(), parse(), r(), Re(), Ze()

### Community 92 - "Genesis Document Model"
Cohesion: 0.33
Nodes (3): _GenesisDocument, BaseModel, field_validator

### Community 93 - "Validator Formation Tests"
Cohesion: 0.48
Nodes (6): _genesis_trust_anchor(), Path, Path: independent identities → shared genesis → quorum → restart; guards key…, Return the exact trust anchor used to test post-start reprovisioning rejection., _signed_height(), test_formed_validator_network_commits_survives_outage_and_restarts()

### Community 94 - "GCP Single-Node Deployment Tests"
Cohesion: 0.48
Nodes (6): _certificate(), _certificate_validator(), _deployment_root(), Path, test_ip_certificate_health_accepts_only_short_lived_lets_encrypt_certificates(), test_terraform_contract_defaults_to_ip_https_without_exposing_internal_ports()

### Community 95 - "Compose Security Check"
Cohesion: 0.67
Nodes (5): _assert_hardened(), _fail(), main(), _published_ports(), Any

### Community 97 - "Caddy Config Check"
Cohesion: 0.60
Nodes (4): _fail(), main(), Any, _walk()

### Community 99 - "Server Shutdown Context"
Cohesion: 0.40
Nodes (3): BaseException, TracebackType, Stop accepting requests and release the worker pool.

### Community 100 - "CometBFT Binary Fixture"
Cohesion: 0.40
Nodes (4): cometbft_binary(), fixture, Path, Return the configured CometBFT executable or skip when none is available.

### Community 101 - "Deployment Config Check Script"
Cohesion: 0.50
Nodes (3): CADDY_IMAGE, check-config.sh script, TERRAFORM_DIRECTORY

### Community 102 - "ABCI Info Method"
Cohesion: 0.50
Nodes (3): RequestInfo, ResponseInfo, Report the latest committed application state.

## Knowledge Gaps
- **31 isolated node(s):** `check-config.sh script`, `TERRAFORM_DIRECTORY`, `CADDY_IMAGE`, `BASE_COMPOSE`, `CLOUD_COMPOSE` (+26 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 696 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_datetime()` connect `CometBFT Genesis Writer` to `CometBFT Observation Client`, `GraphQL & Domain Enums`, `Envelope Codec & Signing`, `GraphQL Node Resolvers`, `Inspector Projection Models`, `Node Observation Sources`, `Network Formation Process`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `ABCIServicer` connect `ABCI Servicer Interface` to `ABCI Package Wiring`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `ArtifactLedgerSnapshot` connect `SQLite Artifact Ledger Store` to `Knowledge Graph Index API`, `Local Artifact Ledger`, `Knowledge Graph Index`, `GraphQL & Domain Enums`, `Knowledge Graph Query Tests`, `CometBFT Callback Handler`, `Seeded Inspector Fixtures`, `Callback Handler Tests`, `Inspector Server Tests`, `Integration Node Harness`, `SQLite Ledger Reader & Queries`, `CLI Integration Tests`, `ABCI Adapter Tests`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Are the 23 inferred relationships involving `ArtifactLedgerSnapshot` (e.g. with `_build_state()` and `KnowledgeGraphIndex`) actually correct?**
  _`ArtifactLedgerSnapshot` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `ArtifactLedgerEntry` (e.g. with `_append_state()` and `IndexedArtifact`) actually correct?**
  _`ArtifactLedgerEntry` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `LocalArtifactLedger` (e.g. with `CometBFTCallbackHandler` and `_PendingBlock`) actually correct?**
  _`LocalArtifactLedger` has 29 INFERRED edges - model-reasoned connections that need verification._
- **What connects `check-config.sh script`, `TERRAFORM_DIRECTORY`, `CADDY_IMAGE` to the rest of the system?**
  _31 weakly-connected nodes found - possible documentation gaps or missing edges._