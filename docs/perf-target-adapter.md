# External Performance Target Adapter Protocol

The public performance campaign coordinator owns database preparation,
measurement semantics, evidence validation, classification, resume, and stop
policy. A private target adapter owns provisioning details, credentials, target
process supervision, and the live remote heavy-work lease. The boundary is one
exact-argument executable protocol; neither side imports the other.

Set `E2E_PERF_TARGET_ADAPTER` to the adapter executable and
`E2E_PERF_DIRECT_DATABASE_URL` to the public harness's direct PostgreSQL URL.
The campaign prepares that database before invoking `start`. Database URLs and
credentials never cross the adapter protocol, and the adapter subprocess does
not inherit the public harness's database or clone-source environment.

All commands return exactly one JSON object on stdout. Every response has
`"schema_version": 1`; a nonzero exit, timeout, malformed JSON, unsupported
version, or secret-bearing response is an infrastructure failure. Diagnostic
text may use stderr. Response keys containing `password`, `secret`, `token`,
`credential`, or `database_url`, and PostgreSQL URLs in response values, are
rejected.

## Start

Invocation:

```text
ADAPTER start --request /absolute/path/to/target-request.json
```

The request is written atomically before invocation:

```json
{
  "schema_version": 1,
  "campaign_id": "capacity-abba",
  "leg_id": "leg-0001-sessions-25-A-r01-p01",
  "attempt_id": "attempt-0001",
  "boot_id": "public-random-boot-id",
  "expected_source_identity": "full-immutable-source-identity",
  "expected_database": "promptgrimoire_test_perf",
  "preparation_id": "public-random-preparation-id",
  "expected_pool_mode_reason": "pool_fidelity"
}
```

The adapter must:

1. acquire and continuously hold the authoritative Bunyip heavy-work lease;
2. start a fresh target at `expected_source_identity` against the already
   prepared `expected_database`, through its private pooled connection;
3. pass the requested boot and preparation IDs to the target;
4. positively verify the new PID, boot ID, source identity, database name,
   successful pooled database query, preparation ID, and pool-fidelity mode;
5. retain all structured logs and rotations under a new immutable log identity;
6. return success only while both the target PID and its own lease are live.

The successful response is:

```json
{
  "schema_version": 1,
  "handle": "opaque-target-handle",
  "server_url": "http://target-host:8080",
  "boot_id": "public-random-boot-id",
  "pid": 12345,
  "source_identity": "full-immutable-source-identity",
  "database_name": "promptgrimoire_test_perf",
  "database_query_ok": true,
  "preparation_id": "public-random-preparation-id",
  "pool_mode_reason": "pool_fidelity",
  "log_identity": "immutable-target-log-id",
  "lease_held": true
}
```

`server_url` must be an HTTP(S) origin without credentials, query, or fragment.
The handle is private and opaque. `start` is transactional: interruption,
timeout, failed readiness, failed attestation, or inability to return the
success response must stop any process it created and release its lease.

For the repository's managed E2E target, the attestation fields are available
from `/api/test/diagnostics`. The private launcher supplies
`E2E_PERF_BOOT_ID`, `_PROMPTGRIMOIRE_DATABASE_PREPARATION_ID`, and
`_PROMPTGRIMOIRE_POOL_FIDELITY=1`; it does not run migrations, truncate tables,
or clone databases.

## Stop

Invocation:

```text
ADAPTER stop --handle opaque-target-handle
```

The adapter stops the exact recorded PID, waits for process exit and log flush,
seals an immutable per-handle snapshot of every log rotation, then releases the
exact lease owned by the handle. Success is:

```json
{
  "schema_version": 1,
  "handle": "opaque-target-handle",
  "stopped": true,
  "pid_exit_observed": true,
  "evidence_sealed": true,
  "lease_released": true
}
```

`stop` is idempotent for the same handle. It must not acknowledge success merely
because no matching process was found or because some process holds the flock.
The seal must finish while the lease is still held, so a following short test
cannot rotate, replace, or append to the evidence later returned by `collect`.

## Collect

Invocation:

```text
ADAPTER collect --handle opaque-target-handle \
  --output-dir /absolute/attempt/target \
  --probe-result /absolute/attempt/probe.json
```

Collection runs after stop and copies the target's sealed structured JSONL set
into `output-dir`. `probe-result` identifies the completed measurement
window when present; if measurement failed before producing it, the handle's
recorded start/stop window still governs collection. Rotations are listed
oldest to newest. Success is:

```json
{
  "schema_version": 1,
  "handle": "opaque-target-handle",
  "log_identity": "immutable-target-log-id",
  "window_start_covered": true,
  "files": [
    {
      "path": "server.jsonl.2",
      "size": 1234,
      "sha256": "hex-sha256"
    },
    {
      "path": "server.jsonl",
      "size": 5678,
      "sha256": "hex-sha256"
    }
  ]
}
```

Paths are relative to `output-dir` and may not be symlinks or escape that
directory. The public coordinator reopens every file, verifies its size and
hash, requires `log_identity` to match `start`, and parses raw JSONL itself. A
valid measured leg requires window-start coverage, at least one in-window
annotation `page_load_profile`, exactly the attested PID and source identity,
and a `db_pool_mode` record for that PID with reason `pool_fidelity`. The adapter
does not classify pass, degradation, collapse, invalid evidence, or
infrastructure failure.

## Lifecycle and scheduling boundary

One adapter handle exists for at most one atomic campaign leg:

```text
public prepare DB -> private start/attest -> public measure
                  -> private stop -> private collect -> public validate/classify
```

The public coordinator releases its local shared test slot after cleanup and
evidence retention. The private adapter releases its remote lease during
`stop`. The next campaign leg must reacquire both resources, allowing already
queued short tests to run between legs. Private durable execution and
notifications may resume the public command, but must not create pass markers,
skip legs, interpret evidence, or decide a knee.
