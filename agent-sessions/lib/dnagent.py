#!/usr/bin/env python3
"""Data plane for the agent wrapper: config, rendering, gates, ledger, status.

Stdlib only, and no f-string-only-in-3.12 tricks: this runs on whatever python3
a macOS laptop and a Debian VM happen to have. run.sh does process control; every
decision that needs parsing lives here.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# budget.toml
#
# tomllib is 3.11+, and the point of this file is to run anywhere, so parse the
# flat subset we actually use rather than depend on the version. Sections and
# scalar key = value only; that is all budget.toml is allowed to contain.
# --------------------------------------------------------------------------


def load_config(path):
    cfg, section = {}, ""
    for raw in Path(path).read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if "=" not in line:
            continue
        key, val = (p.strip() for p in line.split("=", 1))
        if val.startswith('"') and val.endswith('"'):
            parsed = val[1:-1]
        elif val in ("true", "false"):
            parsed = val == "true"
        else:
            try:
                parsed = int(val)
            except ValueError:
                try:
                    parsed = float(val)
                except ValueError:
                    parsed = val
        cfg[(section + "." if section else "") + key] = parsed
    return cfg


def interval_seconds(text):
    m = re.fullmatch(r"\s*(\d+)\s*([smh])\s*", str(text))
    if not m:
        raise SystemExit(f"bad interval: {text!r} (want 30m, 2h, 900s)")
    return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600}[m.group(2)]


# --------------------------------------------------------------------------
# prompt rendering
#
# Substitute ONLY ${DN_*}. A bare $ inside a code fence in the prompt has to
# survive, which is why this is not envsubst with no argument (and not envsubst
# at all: it is absent on a stock macOS).
# --------------------------------------------------------------------------


def render(template, out):
    src = Path(template).read_text()
    missing = []

    def sub(m):
        name = m.group(1)
        val = os.environ.get(name)
        if val is None:
            missing.append(name)
            return m.group(0)
        return val

    body = re.sub(r"\$\{(DN_[A-Z0-9_]+)\}", sub, src)
    if missing:
        raise SystemExit("binding is missing: " + ", ".join(sorted(set(missing))))
    Path(out).write_text(body)


# --------------------------------------------------------------------------
# ledger
# --------------------------------------------------------------------------


def read_runs(state_root):
    runs = []
    root = Path(state_root)
    if not root.is_dir():
        return runs
    for ledger in sorted(root.glob("*/runs.jsonl")):
        for line in ledger.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                runs.append(json.loads(line))
            except ValueError:
                continue  # a torn line is not worth failing a firing over
    return runs


def month_to_date_usd(state_root):
    # timezone.utc, not the datetime.UTC alias ruff prefers: that alias is 3.11+
    # and this file has to run under whatever python3 is on PATH.
    prefix = datetime.now(timezone.utc).strftime("%Y-%m")  # noqa: UP017
    return sum(
        float(r.get("cost_usd") or 0.0)
        for r in read_runs(state_root)
        if str(r.get("started_at", "")).startswith(prefix)
    )


def last_run(state_dir):
    ledger = Path(state_dir) / "runs.jsonl"
    if not ledger.is_file():
        return None
    lines = [line for line in ledger.read_text().splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------
# usage parsing
#
# The one real asymmetry between runners: Claude Code reports dollars, Codex
# reports tokens. Both end up in the same row or the monthly cap governs half
# the fleet.
# --------------------------------------------------------------------------


def parse_usage(runner, raw_path, cfg):
    tokens = {"in": 0, "cached_in": 0, "out": 0}
    cost = None
    text = Path(raw_path).read_text() if Path(raw_path).is_file() else ""

    if runner == "claude":
        # --output-format json: one object, carrying total_cost_usd.
        try:
            doc = json.loads(text)
        except ValueError:
            doc = {}
            for line in text.splitlines():  # tolerate stream-json
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if isinstance(ev, dict) and "total_cost_usd" in ev:
                    doc = ev
        if isinstance(doc, dict):
            if doc.get("total_cost_usd") is not None:
                cost = float(doc["total_cost_usd"])
            usage = doc.get("usage") or {}
            tokens["in"] = int(usage.get("input_tokens") or 0)
            tokens["cached_in"] = int(usage.get("cache_read_input_tokens") or 0)
            tokens["out"] = int(usage.get("output_tokens") or 0)

    elif runner == "codex":
        # --json: JSON Lines; usage rides on turn.completed. Tokens only, so the
        # price table below is what makes a Codex row comparable to a Claude one.
        for line in text.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict) and ev.get("type") == "turn.completed":
                u = ev.get("usage") or {}
                tokens["in"] += int(u.get("input_tokens") or 0)
                tokens["cached_in"] += int(u.get("cached_input_tokens") or 0)
                tokens["out"] += int(u.get("output_tokens") or 0)

    if cost is None:
        rate_in = float(cfg.get(f"pricing.{runner}.input_per_mtok", 0.0) or 0.0)
        rate_cached = float(cfg.get(f"pricing.{runner}.cached_input_per_mtok", 0.0) or 0.0)
        rate_out = float(cfg.get(f"pricing.{runner}.output_per_mtok", 0.0) or 0.0)
        cost = (
            tokens["in"] / 1e6 * rate_in
            + tokens["cached_in"] / 1e6 * rate_cached
            + tokens["out"] / 1e6 * rate_out
        )
        priced_from_table = True
    else:
        priced_from_table = False

    return {"tokens": tokens, "cost_usd": round(cost, 6), "priced_from_table": priced_from_table}


# --------------------------------------------------------------------------
# final text
#
# The conformance check greps the agent's closing summary. It cannot grep the
# raw file: --output-format json is ONE json object on ONE line, so a
# line-anchored pattern never matches no matter what the agent wrote. Same
# asymmetry as parse_usage, so it lives next to it rather than in the shell.
# --------------------------------------------------------------------------


def final_text(runner, raw_path):
    text = Path(raw_path).read_text() if Path(raw_path).is_file() else ""

    if runner == "claude":
        try:
            doc = json.loads(text)
        except ValueError:
            return text
        if isinstance(doc, dict) and isinstance(doc.get("result"), str):
            return doc["result"]
        return text

    if runner == "codex":
        # JSON Lines. The event carrying the closing message is not pinned down
        # yet -- see CODEX-CANARY.md, canary-4 -- so collect any string payload
        # that looks like assistant text and fall back to the raw file.
        parts = []
        for line in text.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            for key in ("text", "message", "content", "delta"):
                val = ev.get(key)
                if isinstance(val, str):
                    parts.append(val)
        return "\n".join(parts) if parts else text

    return text


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------


def write_status(state_dir, payload):
    d = Path(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "status.json.tmp"
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    tmp.replace(d / "status.json")  # atomic; a reader never sees a half file


def append_run(state_dir, record):
    d = Path(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "runs.jsonl", "a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: UP017


def render_status_table(state_root, cap_usd):
    root = Path(state_root)
    rows = []
    for d in sorted(root.glob("*/")):
        sf = d / "status.json"
        if not sf.is_file():
            continue
        try:
            s = json.loads(sf.read_text())
        except ValueError:
            continue
        left = ""
        if s.get("state") == "running" and s.get("deadline_epoch"):
            left = f"{max(0, int(s['deadline_epoch'] - time.time()))}s"
        rows.append(
            (
                s.get("agent", d.name),
                s.get("runner", "-"),
                s.get("state", "-"),
                str(s.get("cycle", "-")),
                s.get("last_exit", "-"),
                left,
                str(s.get("indexed_height") if s.get("indexed_height") is not None else "-"),
            )
        )
    if not rows:
        return f"no agent state under {state_root} yet"
    head = ("AGENT", "RUNNER", "STATE", "CYCLE", "LAST EXIT", "LEFT", "HEIGHT")
    widths = [max(len(r[i]) for r in [head, *rows]) for i in range(len(head))]
    fmt = "  ".join("%-" + str(w) + "s" for w in widths)
    out = [fmt % head, fmt % tuple("-" * w for w in widths)]
    out += [fmt % r for r in rows]
    mtd = month_to_date_usd(state_root)
    pct = (mtd / cap_usd * 100.0) if cap_usd else 0.0
    out.append("")
    out.append(f"month to date: ${mtd:.2f} of ${cap_usd:.2f} ({pct:.0f}%)")
    return "\n".join(out)


# --------------------------------------------------------------------------


def main(argv):
    if len(argv) < 2:
        raise SystemExit("usage: dnagent.py <command> [args]")
    cmd = argv[1]

    if cmd == "config":
        cfg = load_config(argv[2])
        print(cfg.get(argv[3], argv[4] if len(argv) > 4 else ""))

    elif cmd == "interval-seconds":
        print(interval_seconds(argv[2]))

    elif cmd == "render":
        render(argv[2], argv[3])

    elif cmd == "gate-cadence":
        # exit 0 = due, 1 = too soon. Timers fire at the shortest interval and
        # this decides whether the tick is a firing, so cadence is a repo setting
        # rather than a systemd unit needing root and a daemon-reload.
        state_dir, interval = argv[2], interval_seconds(argv[3])
        prev = last_run(state_dir)
        if not prev or not prev.get("started_epoch"):
            sys.exit(0)
        due_in = int(prev["started_epoch"]) + interval - int(time.time())
        if due_in > 0:
            print(f"next firing in {due_in}s")
            sys.exit(1)
        sys.exit(0)

    elif cmd == "gate-budget":
        state_root, cap = argv[2], float(argv[3])
        mtd = month_to_date_usd(state_root)
        print(f"{mtd:.4f}")
        sys.exit(1 if cap and mtd >= cap else 0)

    elif cmd == "last-indexed-height":
        prev = last_run(argv[2])
        print((prev or {}).get("indexed_height", ""))

    elif cmd == "final-text":
        print(final_text(argv[2], argv[3]))

    elif cmd == "parse-usage":
        print(json.dumps(parse_usage(argv[2], argv[3], load_config(argv[4]))))

    elif cmd == "append-run":
        append_run(argv[2], json.loads(sys.stdin.read()))

    elif cmd == "write-status":
        write_status(argv[2], json.loads(sys.stdin.read()))

    elif cmd == "now":
        print(now_iso())

    elif cmd == "status":
        print(render_status_table(argv[2], float(argv[3]) if len(argv) > 3 else 0.0))

    else:
        raise SystemExit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main(sys.argv)
