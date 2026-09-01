# Conformance smoke check

Both runners must pass this before either is trusted with a research firing.
It is read-only: it queries, it writes one worklog line, it submits nothing.

Run it with the binding under test:

```bash
agents/runners/<runner>.sh agents/conformance/smoke-prompt.txt "$REPO_ROOT" "$RUN_DIR"
```

## The prompt

> You are running a conformance check, not a research task. Do exactly these
> five steps and then stop.
>
> 1. Report which skills you can see. Name the three you expect:
>    `discovery-net`, `math-research`, `math-review`.
> 2. `curl -s $DN_RPC_URL/status` and report `node_info.network`,
>    `sync_info.latest_block_height`, and `sync_info.catching_up`.
> 3. Run `$DN_GRAPHQL_CMD '{ indexedHeight }'` and report the value.
> 4. State whether the indexer is keeping up: report
>    `latest_block_height - indexedHeight`. A static height is NOT a fault --
>    this chain runs `create_empty_blocks = false` and only advances on
>    transactions.
> 5. Append one line to `$DN_WORKLOG` in the form
>    `conformance <ISO8601> <runner> height=<H> indexed=<I> skills=<N>`.
>
> Submit nothing. Create nothing in the notes clone. Do not restart or
> reconfigure anything.

## Passing

Both runners report the same three skills, the same heights, and write a
worklog line of the same shape. If they diverge here they will diverge on
research, and the reviewer ends up refereeing work of uneven quality without
knowing why.
