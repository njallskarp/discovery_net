You are running a conformance check, not a research task. Do exactly these five
steps, in order, and then stop. Submit nothing. Create nothing. Do not restart or
reconfigure anything.

1. List the skills you can see. Name the three you should have: `discovery-net`,
   `math-research`, `math-review`. Say how many you found.

2. Run `curl -s ${DN_RPC_URL}/status` and report three values:
   `node_info.network`, `sync_info.latest_block_height`, `sync_info.catching_up`.

3. Run `${DN_GRAPHQL_CMD} '{ indexedHeight }'` and report the value.

4. Report `latest_block_height - indexedHeight`. State whether the indexer is
   keeping up. A static height is **not** a fault: this chain runs
   `create_empty_blocks = false` and only advances on transactions.

5. Append one line to `${DN_WORKLOG}`, exactly this shape and nothing else:

   `conformance <ISO8601-UTC> ${DN_RUNNER} height=<H> indexed=<I> skills=<N>`

Then finish with a summary in this exact form, one field per line, so the two
runners can be compared mechanically:

```
skills=<N>
chain=<network>
height=<H>
indexed=<I>
lag=<H-I>
worklog_line_written=<yes|no>
```
