"""Beszel system metrics fetcher (PocketBase REST API).

Queries PocketBase REST API via SSH tunnel to fetch system stats
for a time window. Requires superuser auth token. Parses compact
JSON keys into normalised columns matching ``beszel_metrics``.

Stats dict field reference (Beszel v0.9+)::

    cpu       float   CPU usage %
    mu        float   Memory used (GB)
    mp        float   Memory percent
    dr        float   Disk read (MB/s)
    dw        float   Disk write (MB/s)
    b         [int, int]   Bandwidth [sent, recv] bytes/s
    la        [float, float, float]   Load average [1m, 5m, 15m]
    ni        {iface: [sent, recv, total_sent, total_recv]}
    dio       [read_bytes, write_bytes]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

_BESZEL_ENV_FILE = Path.home() / ".config" / "beszel" / "env"


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a shell-style env file into a dict.

    Handles ``export`` prefix and single/double-quoted values.
    """
    result: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:]
        key, _, val = stripped.partition("=")
        result[key] = val.strip("'\"")
    return result


def _load_beszel_creds() -> tuple[str, str]:
    """Load Beszel credentials from env vars or ~/.config/beszel/env."""
    email = os.environ.get("BESZEL_EMAIL", "")
    password = os.environ.get("BESZEL_PASSWORD", "")

    if (not email or not password) and _BESZEL_ENV_FILE.exists():
        file_vars = _parse_env_file(_BESZEL_ENV_FILE)
        email = email or file_vars.get("BESZEL_EMAIL", "")
        password = password or file_vars.get("BESZEL_PASSWORD", "")

    if not email or not password:
        print(
            "Error: BESZEL_EMAIL and BESZEL_PASSWORD must be set.\n"
            f"Set in environment or in {_BESZEL_ENV_FILE}\n"
            "These are the PocketBase superuser credentials for the "
            "Beszel hub.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return email, password


def _authenticate(client: httpx.Client, hub_url: str) -> str:
    """Authenticate with PocketBase superuser API, return auth token."""
    email, password = _load_beszel_creds()

    resp = client.post(
        f"{hub_url}/api/collections/_superusers/auth-with-password",
        json={"identity": email, "password": password},
    )
    if resp.status_code != 200:
        print(
            f"Error: Beszel auth failed (HTTP {resp.status_code}). "
            "Check BESZEL_EMAIL/BESZEL_PASSWORD.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return resp.json()["token"]


def fetch_beszel_metrics(
    hub_url: str,
    start_utc: str,
    end_utc: str,
    collection: str = "system_stats",
) -> list[dict]:
    """Fetch Beszel system metrics for a UTC time window.

    Parameters
    ----------
    hub_url:
        PocketBase hub URL (e.g. ``http://localhost:8090`` via SSH tunnel).
    start_utc:
        ISO 8601 UTC start time.
    end_utc:
        ISO 8601 UTC end time.
    collection:
        PocketBase collection name (default ``system_stats``).

    Returns
    -------
    list[dict]
        Each dict has keys matching ``beszel_metrics`` columns:
        ``ts_utc``, ``cpu``, ``mem_used``, ``mem_percent``,
        ``net_sent``, ``net_recv``, ``disk_read``, ``disk_write``,
        ``load_1``, ``load_5``, ``load_15``.

    Raises
    ------
    SystemExit
        On connection, auth, or HTTP errors (exit code 1, clear message).
    """
    pb_filter = f'created >= "{start_utc}" && created <= "{end_utc}"'
    results: list[dict] = []
    page = 1

    try:
        with httpx.Client() as client:
            token = _authenticate(client, hub_url)
            headers = {"Authorization": f"Bearer {token}"}

            while True:
                resp = client.get(
                    f"{hub_url}/api/collections/{collection}/records",
                    params={
                        "filter": pb_filter,
                        "page": page,
                        "perPage": 200,
                        "sort": "created",
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                body = resp.json()

                for record in body.get("items", []):
                    stats = record.get("stats", {})
                    la = stats.get("la", [None, None, None])
                    # b = [sent, recv] bandwidth in bytes/s
                    bandwidth = stats.get("b", [None, None])
                    results.append(
                        {
                            "ts_utc": record["created"],
                            "cpu": stats.get("cpu"),
                            "mem_used": stats.get("mu"),
                            "mem_percent": stats.get("mp"),
                            "net_sent": bandwidth[0] if bandwidth else None,
                            "net_recv": bandwidth[1] if bandwidth else None,
                            "disk_read": stats.get("dr"),
                            "disk_write": stats.get("dw"),
                            "load_1": la[0] if la else None,
                            "load_5": la[1] if len(la) > 1 else None,
                            "load_15": la[2] if len(la) > 2 else None,
                        }
                    )

                total_pages = body.get("totalPages", 1)
                if page >= total_pages:
                    break
                page += 1

    except httpx.ConnectError:
        print(
            f"Error: cannot connect to Beszel hub at {hub_url}. "
            "Is the SSH tunnel running?\n"
            "  ssh -L 8090:localhost:8090 brian.fedarch.org",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except httpx.HTTPStatusError as exc:
        print(
            f"Error: Beszel API returned HTTP {exc.response.status_code}.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    return results
