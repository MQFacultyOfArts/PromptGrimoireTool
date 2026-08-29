# Clean-box CI with `act`

This is the authoritative public runbook for executing PromptGrimoire CI on a
clean Ubuntu 24.04 LTS box with Docker and `act` 0.2.89. It describes the
repository-facing contract only. Keep hostnames, addresses, credentials,
credential paths, network assessments, and machine-specific provisioning in a
private operator runbook.

Use one installation and one host-wide wrapper for all repositories on the
box. Retire older per-repository wrappers after migrating their callers; two
independent locks or act configurations do not provide mutual exclusion.

## What runs where

`uv run grimoire e2e all` is eight serial lane invocations. GitHub's regular CI
splits the common lanes for speed; the nightly workflow is the canonical
single-job full-suite environment and runs `e2e slow`, a superset of `e2e all`.

| `e2e all` lane | Regular `.github/workflows/ci.yml` | Canonical full CI and local act |
|---|---|---|
| JavaScript | `test-all` via `test all` | nightly `e2e-slow` |
| BATS | `test-all` via `test all` | nightly `e2e-slow` |
| unit | `test-all` via `test all` | nightly `e2e-slow` |
| integration | not run | nightly `e2e-slow` |
| Playwright | `e2e-playwright`, Chromium and Firefox | nightly `e2e-slow`, Chromium |
| NiceGUI | `nicegui-ui` | nightly `e2e-slow` |
| smoke | not run | nightly `e2e-slow` |
| BLNS + extra | not run | nightly `e2e-slow` |

The nightly command additionally enables `noci` Playwright tests and compiled
PDF validation. `.github/workflows/act-ci.yml` is a local diagnostic copy of
the three regular test jobs plus quality; it does not claim eight-lane
coverage. Both local workflows use PostgreSQL 16, matching GitHub.

## Exact-SHA pre-PR route

`.github/workflows/pre-pr-ci.yml` is a separate manual route for running the
complete pre-PR campaign on an isolated one-job self-hosted runner. It is
`workflow_dispatch`-only and must remain on the repository's default branch.
Ordinary pushes and pull requests, including forks, continue to use
GitHub-hosted runners through `ci.yml`.

The trusted submitter supplies a full pushed commit SHA and an unpredictable
request identifier. A GitHub-hosted preparation job validates that GitHub
resolves the exact SHA and creates the dedicated `ci/pre-pr-isolated` pending
status. The isolated job requires both its static labels and the unique request
identifier, checks out that exact SHA without persisting checkout credentials,
and receives only `contents: read`. A GitHub-hosted finalizer writes success,
failure, or error to the same exact SHA.

The isolated job runs the quality gates, the canonical `e2e slow` suite, and
the ordinary Firefox E2E lane. It always uploads request metadata and available
test evidence. The self-hosted executor is an operational boundary: it must be
one-job/disposable, have no repository secrets or persistent GitHub credential,
and be destroyed before its host releases the shared heavy-work lease. Its
machine-specific provisioning, submission command, network policy, and
evidence locations belong only in the private operator runbook.

## Provision a clean box

Allow at least 30 GB free for Docker images, action caches, browser downloads,
and artifacts. Install Docker Engine, the GitHub CLI if desired, `flock`, and
the pinned `act` binary. Transfer the repository without `.env`, production
secrets, dependency directories, output, or logs; the runner needs no GitHub
credentials for a public checkout copied from another machine.

Build the repository image and positively verify its PostgreSQL client:

```bash
docker build -t grimoire-act-runner -f Dockerfile.act .
docker run --rm grimoire-act-runner psql --version
```

The Dockerfile also proves `psql` during the build. This is required because
the canonical workflows quieten PostgreSQL before checkout.

Configure Docker-published ports to bind to loopback by default. Changing the
Docker daemon configuration requires a coordinated daemon restart: announce
the interruption, confirm no act, deployment, or performance job is live,
restart Docker, then verify both the listener and an attempted connection from
a separate host. The acceptance condition is: the service succeeds through
`localhost:<published-port>` on the runner and cannot be reached through any
non-loopback interface. Do not publish the observed address or network details.

Under act 0.2.89 the service container is on its per-job bridge while job steps
run on the host network. Docker publishes the service port to the host, so job
steps correctly use `localhost:<published-port>`. The health-check crash is a
dry-run-only act bug; do not disable real-run health checks because of it.

## Required wrapper contract

All act and performance entry points must take the same host-wide `flock`.
Performance legs own the box exclusively. An interactive act request abstains
while a leg is live. A GitHub-triggered priority request may stop a leg only
through the private perf controller's checkpoint/stop hook, run CI under the
lock, and invoke its resume hook afterward; never kill an uncheckpointed leg.
Perf provisioning and hook implementation remain private and separate.

For every invocation the wrapper must:

1. take the shared lock before inspecting or changing services;
2. refuse overlap with a live performance leg unless using the coordinated
   stop/resume path;
3. use unique run-scoped container, network, artifact, and temporary resource
   names, and reserve non-conflicting ports;
4. pass readable, explicitly empty env, secret, input, and var files when the
   workflow requires none—never inherit ambient values;
5. bind act's cache and artifact servers to loopback and preserve normal
   `setup-uv` and `actions/cache@v4` locations;
6. set CPU, memory, and shared-memory limits appropriate to the host;
7. use a fixed, documented concurrency budget, serialize jobs whose published
   ports collide, and record the revision, exact command, versions, timestamps,
   exit status, and artifact directory; and
8. remove run-scoped containers and networks on exit while retaining declared
   caches and evidence artifacts according to the operator's retention policy.

`actions/cache@v4` works with act 0.2.89 and has restored the setup-uv cache in
a real run. Do not set `cache-local-path` or redirect caches to `/tmp`.
`actions/upload-artifact@v4` is the supported artifact action for this setup;
do not upgrade it independently to v6 or v7.

## Run and record evidence

Create four zero-byte files outside the checkout for env, secrets, inputs, and
vars. A wrapper can do that without assigning a durable credential path:

```bash
run_state=$(mktemp -d)
trap 'rm -rf -- "$run_state"' EXIT
touch "$run_state"/{env,secrets,inputs,vars}

act workflow_dispatch \
  --env-file "$run_state/env" \
  --secret-file "$run_state/secrets" \
  --input-file "$run_state/inputs" \
  --var-file "$run_state/vars" \
  --cache-server-addr 127.0.0.1 --cache-server-port 0 \
  --artifact-server-addr 127.0.0.1 --artifact-server-port 34567 \
  --artifact-server-path "$run_state/artifacts" \
  --rm --concurrent-jobs 1 \
  -W .github/workflows/act-ci.yml --list
```

For a real run, put artifacts in a unique retained run directory rather than
the temporary example above. Keep act's default cache-server path so action
caches survive runs.

List jobs using the workflow's actual event:

```bash
act workflow_dispatch -W .github/workflows/act-ci.yml --list
```

Run the five regular PR executions under one wrapper-owned lock: `quality`,
`test-all`, `e2e-playwright` with Chromium, `e2e-playwright` with Firefox,
and `nicegui-ui`. Independent jobs may share the campaign's fixed capacity;
jobs using the same published port must remain serial unless the wrapper gives
each one a unique port. For the authoritative eight-lane proof,
run the `e2e-slow` job from `.github/workflows/nightly-e2e-slow.yml`; its
`e2e slow` command covers all eight lanes plus the documented nightly extras.
Never use `pull_request` with `act-ci.yml`: that workflow declares only
`workflow_dispatch`.

During a database-backed job, verify PostgreSQL is healthy, `psql` can execute
`SELECT 1` through localhost, migrations complete before seed/application
startup, and the schema-backed health check succeeds. From a separate host,
verify the published service port is unreachable. After each job, save logs and
artifacts, record cache restore/save results, and confirm no run-scoped
containers, networks, or listeners remain before releasing the lock.

Do not use `--dryrun` as evidence: act 0.2.89 may crash while tearing down
service health-check stubs. Do not use `--reuse` for the final clean-box proof.

## Supported boundary

Supported pins are Ubuntu 24.04 LTS, act 0.2.89, PostgreSQL 16,
`actions/cache@v4`, and `actions/upload-artifact@v4`. Routine independent
upgrades are unsupported; update the workflows, image, contract test, and a
recorded clean-box run together.

Before publishing changes, search this file and evidence intended for the
repository for machine names, addresses, usernames, tokens, secret or
credential paths, and private network/security commentary. Keep those only in
the private operator runbook.
