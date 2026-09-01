#!/usr/bin/env bash
#
#   agent-sessions/conformance/run-smoke.sh <agent> [output-file]
#
# Renders the conformance prompt against an agent's binding pair and hands it to
# that agent's runner. Read-only: it queries, writes one worklog line, and
# submits nothing.
#
# Run it once per runner against the SAME node, then diff the two summaries. If
# they disagree here they will disagree on research, and the reviewer ends up
# refereeing uneven work without knowing why.

set -eu
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
SESSIONS="$(cd -- "$HERE/.." && pwd)"
REPO_ROOT="$(cd -- "$SESSIONS/.." && pwd)"
AGENT="${1:?usage: run-smoke.sh <agent> [output-file]}"

. "$SESSIONS/lib/binding.sh"
resolve_binding "$SESSIONS" "$AGENT" || exit $?

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
DN_REPO="${DN_REPO:-$REPO_ROOT}" \
  python3 "$SESSIONS/lib/dnagent.py" render "$HERE/smoke-prompt.md" "$WORK/prompt.md"

OUT="${2:-$SESSIONS/conformance/smoke-$DN_RUNNER-$DN_AGENT.out}"
echo "running the conformance prompt: $DN_AGENT via $DN_RUNNER"
"$SESSIONS/runners/$DN_RUNNER.sh" "$WORK/prompt.md" "$REPO_ROOT" "$WORK" > "$OUT" 2>&1 || true
echo "wrote $OUT"
echo
grep -E '^(skills|chain|height|indexed|lag|worklog_line_written)=' "$OUT" || {
  echo "no summary block found — the runner did not follow the prompt."
  echo "that is itself a conformance failure; inspect $OUT"
  exit 1
}
