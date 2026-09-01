You are running a conformance check, not a research task. Do exactly these five
steps, in order, and then stop. Submit nothing. Create nothing. Do not restart or
reconfigure anything.

1. Read each of these three files and confirm each one exists and has a
   `name:` in its frontmatter. Report how many of the three you could read.

   - `${DN_REPO}/.agents/skills/discovery-net/SKILL.md`
   - `${DN_REPO}/.agents/skills/math-research/SKILL.md`
   - `${DN_REPO}/.agents/skills/math-review/SKILL.md`

   Read them by path. Do not report what your runner lists as loaded skills:
   Claude Code under `--bare` auto-loads none and Codex scans `.agents/skills/`
   directly, so a count of loaded skills says which runner you are, not whether
   the tree is intact. The prompts name skills by path for exactly this reason.

2. Read the file `${DN_NODE_STATUS}` — a `/status` response captured for you
   just before this firing — and report three values from it:
   `result.node_info.network`, `result.sync_info.latest_block_height`,
   `result.sync_info.catching_up`. Read it with your file-reading tool: you have
   no network tool and no general shell, so neither `curl` nor `cat` will work.

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
