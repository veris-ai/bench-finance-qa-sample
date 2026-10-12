"""Harbor collect hook, run inside the world sidecar after the agent finishes.

Usage: python3 harbor_collect.py <out_dir> <service>=<control_port> ...

Writes <out_dir>/ledger.json — every vendor-plane HTTP event the world recorded, read
page by page until the ledger says there is no more (never cut at one page) — and
<out_dir>/state-<service>.json, each member's final state. Stdlib only. A failed read
exits non-zero: evidence the verifier cannot trust is not handed to it.
"""

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PAGE_LIMIT = 1000
TIMEOUT_S = 60


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
        return json.load(r)


def ledger(control_port: int) -> dict:
    """The sandbox-wide ledger's vendor HTTP events, every page."""
    base = f"http://127.0.0.1:{control_port}/veris/ledger"
    params = {
        "detail": "full",
        "order": "time",
        "dir": "asc",
        "limit": PAGE_LIMIT,
        "plane": "vendor",
        "type": "http",
    }
    events, cursor, envelope = [], None, {}
    while True:
        query = dict(params, **({"cursor": cursor} if cursor else {}))
        envelope = _get(f"{base}?{urllib.parse.urlencode(query)}")
        events.extend(envelope.get("events") or [])
        page = envelope.get("page") or {}
        cursor = page.get("next_cursor")
        if not page.get("has_more") or not cursor:
            break
    return {"clock": envelope.get("clock"), "sources": envelope.get("sources"), "events": events}


def snapshot(control_port: int) -> bytes:
    request = urllib.request.Request(
        f"http://127.0.0.1:{control_port}/veris/snapshot", method="POST", data=b""
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as r:
        return r.read()


def main(argv: list[str]) -> int:
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    members = [arg.split("=", 1) for arg in argv[1:]]
    if not members:
        return 0
    (out / "ledger.json").write_text(json.dumps(ledger(int(members[0][1]))))
    for name, port in members:
        (out / f"state-{name}.json").write_bytes(snapshot(int(port)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
