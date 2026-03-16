"""Beszel system metrics fetcher (PocketBase REST API).

Queries PocketBase REST API via SSH tunnel to fetch system stats
for a time window. Parses compact JSON keys into normalised columns
matching the ``beszel_metrics`` table schema.
"""

from __future__ import annotations

import sys

import httpx


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
        On connection or HTTP errors (exit code 1, clear message).
    """
    pb_filter = f'created >= "{start_utc}" && created <= "{end_utc}"'
    results: list[dict] = []
    page = 1

    try:
        with httpx.Client() as client:
            while True:
                resp = client.get(
                    f"{hub_url}/api/collections/{collection}/records",
                    params={
                        "filter": pb_filter,
                        "page": page,
                        "perPage": 200,
                        "sort": "created",
                    },
                )
                resp.raise_for_status()
                body = resp.json()

                for record in body.get("items", []):
                    stats = record.get("stats", {})
                    results.append(
                        {
                            "ts_utc": record["created"],
                            "cpu": stats.get("cpu"),
                            "mem_used": stats.get("mu"),
                            "mem_percent": stats.get("mp"),
                            "net_sent": stats.get("ns"),
                            "net_recv": stats.get("nr"),
                            "disk_read": stats.get("dr"),
                            "disk_write": stats.get("dw"),
                            "load_1": stats.get("l1"),
                            "load_5": stats.get("l5"),
                            "load_15": stats.get("l15"),
                        }
                    )

                total_pages = body.get("totalPages", 1)
                if page >= total_pages:
                    break
                page += 1

    except httpx.ConnectError:
        print(
            f"Error: cannot connect to Beszel hub at {hub_url}. "
            "Is the SSH tunnel running?",
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
