"""Executable end-to-end demonstration of a coordinator and three peer nodes."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, cast

import httpx


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_health(url: str) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/health", timeout=0.5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"service did not become healthy: {url}")


def post(url: str, path: str, document: dict[str, Any] | None = None) -> dict[str, Any]:
    response = httpx.post(f"{url}{path}", json=document, timeout=10)
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def main() -> None:
    ports = [free_port() for _ in range(4)]
    coordinator_url = f"http://127.0.0.1:{ports[0]}"
    node_urls = [f"http://127.0.0.1:{port}" for port in ports[1:]]
    processes: list[subprocess.Popen[bytes]] = []

    try:
        with tempfile.TemporaryDirectory(prefix="discovery-net-demo-") as temporary_directory:
            root = Path(temporary_directory)
            with ExitStack() as stack:
                coordinator_log = stack.enter_context((root / "coordinator.log").open("wb"))
                coordinator = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "discovery_net_poc.coordinator_cli",
                        "--port",
                        str(ports[0]),
                        "--database",
                        str(root / "coordinator.sqlite3"),
                        "--key-file",
                        str(root / "coordinator-key.json"),
                        "--log-level",
                        "warning",
                    ],
                    stdout=coordinator_log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(coordinator)
                wait_for_health(coordinator_url)

                for index, (port, node_url) in enumerate(zip(ports[1:], node_urls, strict=True)):
                    log = stack.enter_context((root / f"node-{index}.log").open("wb"))
                    command = [
                        sys.executable,
                        "-m",
                        "discovery_net_poc.node_cli",
                        "--port",
                        str(port),
                        "--public-url",
                        node_url,
                        "--database",
                        str(root / f"node-{index}.sqlite3"),
                        "--key-file",
                        str(root / f"node-{index}-key.json"),
                        "--coordinator",
                        coordinator_url,
                        "--log-level",
                        "warning",
                    ]
                    for peer in node_urls:
                        if peer != node_url:
                            command.extend(["--peer", peer])
                    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                    processes.append(process)

                for node_url in node_urls:
                    wait_for_health(node_url)
                    post(node_url, "/coordinator/register")

                created = post(
                    node_urls[0],
                    "/contributions",
                    {
                        "kind": "problem_statement",
                        "title": "A finite-field incidence problem",
                        "body": (
                            "Determine the sharp upper bound under the stated "
                            "incidence constraints."
                        ),
                        "review_policy_version": "v1",
                    },
                )
                contribution = created["artifact"]
                contribution_id = contribution["payload"]["contribution_id"]

                review_states: list[dict[str, Any]] = []
                for node_url in node_urls[1:]:
                    claimed = post(node_url, "/assignments/claim")
                    assignment = claimed["assignment"]["payload"]["data"]
                    reviewed = post(
                        node_url,
                        "/reviews",
                        {
                            "assignment_id": assignment["assignment_id"],
                            "target_contribution_id": assignment["target_contribution_id"],
                            "verdict": "approve",
                            "body": (
                                "The statement is coherent, mathematically meaningful, "
                                "and not duplicated."
                            ),
                        },
                    )
                    review_states.append(reviewed["coordinator"]["state"])

                final_state = httpx.get(
                    f"{coordinator_url}/states/{contribution_id}", timeout=5
                ).json()
                feed = httpx.get(f"{coordinator_url}/feed", timeout=5).json()
                replicated_objects = httpx.get(f"{node_urls[2]}/objects", timeout=5).json()
                replicated_ids = {artifact["artifact_id"] for artifact in replicated_objects}

                if final_state["status"] != "published":
                    raise RuntimeError(f"unexpected final state: {final_state}")
                if contribution["artifact_id"] not in replicated_ids:
                    raise RuntimeError("the contribution did not replicate to the third peer")

                print(
                    json.dumps(
                        {
                            "coordinator": coordinator_url,
                            "nodes": node_urls,
                            "contribution_id": contribution_id,
                            "artifact_id": contribution["artifact_id"],
                            "review_states": review_states,
                            "final_state": final_state,
                            "published_feed_size": len(feed),
                            "third_node_object_count": len(replicated_objects),
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )

    finally:
        for process in reversed(processes):
            process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
