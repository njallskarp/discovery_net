# Conformance smoke check

Both runners must pass this before either is trusted with a research firing.
It is read-only: it queries, it writes one worklog line, it submits nothing.

Run it once per runner, against the same node:

```bash
agent-sessions/conformance/run-smoke.sh <claude-agent>
agent-sessions/conformance/run-smoke.sh <codex-agent>
diff agent-sessions/conformance/smoke-claude-*.out \
     agent-sessions/conformance/smoke-codex-*.out
```

`run-smoke.sh` renders `smoke-prompt.md` against the agent's binding pair and
invokes that agent's runner. It shares binding resolution with `run.sh`, so the
check exercises the same assembly a real firing uses.

## The prompt

`smoke-prompt.md`, rendered against the binding. It asks the runner to list its
skills, read `/status`, read `indexedHeight`, report the lag, append one worklog
line, and finish with a fixed summary block:

```
skills=<N>
chain=<network>
height=<H>
indexed=<I>
lag=<H-I>
worklog_line_written=<yes|no>
```

The fixed shape is the point: it makes two runners comparable with `diff`
instead of by reading.

## Passing

Both runners report the same three skills, the same heights, and write a
worklog line of the same shape. If they diverge here they will diverge on
research, and the reviewer ends up refereeing work of uneven quality without
knowing why.
