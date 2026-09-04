# Where things live. Sourced by run.sh, agentctl, the conformance check and the
# setup scripts, so no two of them can disagree about a path.
#
#   DN_CONFIG_ROOT   bindings (human-written, agent-readable, never agent-writable)
#                    laptop: ~/.config/discovery-net     host: /etc/discovery-net
#   DN_STATE_ROOT    run ledgers, status, per-run dirs (the wrapper writes here)
#                    laptop: ~/.local/state/discovery-net-agents
#                    host:   /srv/agent-sessions/state
#   DN_AGENTS_ROOT   each agent's worklog, key, notes clone, and the shared claims.d
#                    laptop: ~/agent-sessions              host: /srv/agent-sessions/agents
#
# Bindings are config, not state: they are sourced with set -a and their read
# command is eval'd by every tick, so they must sit where the agent cannot
# write. The checkout is not that place -- --add-dir puts it in scope.

DN_CONFIG_ROOT="${DN_CONFIG_ROOT:-${XDG_CONFIG_HOME:-$HOME/.config}/discovery-net}"
DN_STATE_ROOT="${DN_STATE_ROOT:-$HOME/.local/state/discovery-net-agents}"
DN_AGENTS_ROOT="${DN_AGENTS_ROOT:-$HOME/agent-sessions}"
DN_BINDINGS_DIR="${DN_BINDINGS_DIR:-$DN_CONFIG_ROOT/bindings}"
