# Resolve an agent's binding pair. Sourced by run.sh and by the conformance
# check, so the two cannot disagree about how a binding is assembled.
#
#   resolve_binding <sessions-dir> <agent>
#
# Sets every DN_* the prompts use. DN_SUBMIT_BASE (node) and DN_KEY_PATH
# (agent) are exported separately and only ever joined inside tools/dn-submit,
# so the agent's command line never carries the key path and cannot choose a
# different one.

resolve_binding() {
  __rb_dir="$1"; __rb_agent="$2"

  __rb_agent_file="${DN_BINDING:-$__rb_dir/bindings/agents/$__rb_agent.env}"
  [ -f "$__rb_agent_file" ] || { echo "no agent binding: $__rb_agent_file
run agent-setup/init-agent.sh to create one" >&2; return 2; }
  set -a; . "$__rb_agent_file"; set +a

  : "${DN_AGENT:?agent binding must set DN_AGENT}"
  : "${DN_ROLE:?agent binding must set DN_ROLE}"
  : "${DN_RUNNER:?agent binding must set DN_RUNNER}"
  : "${DN_NODE_BINDING:?agent binding must name its node}"

  __rb_node_file="$__rb_dir/bindings/nodes/$DN_NODE_BINDING.env"
  [ -f "$__rb_node_file" ] || { echo "no node binding: $__rb_node_file
run agent-setup/init-node.sh to create one" >&2; return 2; }
  set -a; . "$__rb_node_file"; set +a

  : "${DN_SUBMIT_BASE:?node binding must set DN_SUBMIT_BASE}"
  : "${DN_GRAPHQL_CMD:?node binding must set DN_GRAPHQL_CMD}"
  : "${DN_KEY_PATH:?agent binding must set DN_KEY_PATH}"
  : "${DN_NOTES_CLONE:?agent binding must set DN_NOTES_CLONE}"
}
