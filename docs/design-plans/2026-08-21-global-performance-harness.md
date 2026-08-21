# Global Performance Harness

**Status:** Current design

## Purpose

PromptGrimoire's performance probes need one repository-owned harness that can
run the same measurement locally or against the split Bunyip target without
changing database, verdict, evidence, or resume semantics. The recovered
scratchpad campaign proved the workload is useful, but it also allowed a remote
server to connect before the test database's clone source was created and kept
campaign truth in private shell state.

This design makes the public harness authoritative for a measurement's
lifecycle and meaning. Private Bunyip infrastructure remains authoritative for
machine provisioning, the live shared-host lease, durable process execution,
staging coordination, credentials, and notifications.

## Authority Sources

| Decision or instruction | Exact source | Resolver | Resolution condition |
|---|---|---|---|
| Queue complete campaigns durably rather than narrating or manually advancing legs | `ccchat:v1:codex:01a01ec9-43cd-7e83-aad4-dc5cacd43d47:id:msg_01a01efc-d92a-71a1-a91a-13b42c3c34af` | `cc-search-chats resolve ccchat:v1:codex:01a01ec9-43cd-7e83-aad4-dc5cacd43d47:id:msg_01a01efc-d92a-71a1-a91a-13b42c3c34af --json` | One human-submitted message asks to queue the full overnight campaign. |
| Build a global perf harness because repeatable performance testing is a project capability | Current Codex thread `01a01ec9-43cd-7e83-aad4-dc5cacd43d47`, human message beginning `well no, we want a global perf harness` | `cc-search-chats search 'well no, we want a global perf harness' --literal --provider codex --json` | One human-submitted message selects the global repository harness over a Bunyip-only runner. |
| Proceed with implementation and retain a durable task queue | Current Codex thread `01a01ec9-43cd-7e83-aad4-dc5cacd43d47`, human message `carry on then, make sure your task queue is durable` | `cc-search-chats search 'carry on then, make sure your task queue is durable' --literal --provider codex --json` | One human-submitted message authorises implementation and durable tracking. |
| A campaign must cover multiple concurrency levels and controlled arm orders such as ABBA | Current Codex thread `01a01ec9-43cd-7e83-aad4-dc5cacd43d47`, human message beginning `the objective of this harness is to be able to run a full campaign` | `cc-search-chats search 'objective of this harness is to be able to run a full campaign' --literal --provider codex --json` | One human-submitted message requires parameter sweeps and ordered comparative arms. |
| Long campaigns must yield between legs when other threads queue short tests | Current Codex thread `01a01ec9-43cd-7e83-aad4-dc5cacd43d47`, human message beginning `and for it to politely get out of the way` | `cc-search-chats search 'politely get out of the way when other threads need to run short tests' --literal --provider codex --json` | One human-submitted message requires cooperative interleaving with short test commands. |

The agreed public/private boundary is also recorded in the project-owned
`.notes/project_issue-571-bunyip-ci-perf-runner.md`. That note preserves current
project state; the human messages above remain the authority for the requested
outcome.

## Universe of discourse

The public universe contains:

- the `grimoire` CLI and its existing `e2e perf` command;
- performance probes under `tests/e2e/` and their result JSON;
- direct test-database preparation and the private clone source used by pytest;
- local managed-server and split external-server targets;
- a campaign comprising a resolved ordered schedule of parameter levels,
  named comparative arms, repetitions, legs, and immutable attempts;
- validation, classification, pause, and resume decisions; and
- repository-local artifact and state files.

The private Bunyip universe contains host addresses, paths, credentials,
provisioning, the implementation of the live heavy-work flock, durable user
service execution, staging interruption/restoration, and terminal
notifications. The public repository defines the target command contract but
contains none of those values.

The first campaign consumer is the full-CRUD soak knee sequence. Assessment
cram and thundering herd are the next real probe consumers. The design does not
introduce a plugin loader, a general scheduler, load/change detectors, or
speculative target types.

## Current state

`promptgrimoire.cli.e2e.perf` calls `_pre_test_db_cleanup()` before target
selection. Its shared `_run_pytest()` helper calls the same destructive
preparation again. In split mode the private runner starts the remote server
before invoking the CLI, so the server may own a pooled source-database session
when either clone occurs. The n=75 attempt failed at `CREATE DATABASE ...
TEMPLATE` for exactly this reason and emitted no diagnostic JSON.

The probes already emit useful run metadata and server-page-load summaries,
but their JSON is probe-specific and written before the final assertions. A
pytest exit code therefore cannot distinguish a measured collapse from
collection, configuration, database, browser, or target failure. The recovered
runner partly corrected this by treating nonzero as unclassified and writing
validated pass markers, but those semantics live in a private scratchpad
script.

The regular E2E runner already supplies useful patterns: stable artifact roots,
per-run directories, subprocess isolation, worker metadata, and one shared
host-test flock. The perf harness extends those patterns rather than building a
second scheduler.

## Goals and non-goals

### Goals

- Prepare the database exactly once while the measured server is stopped.
- Run the same lifecycle and verdict rules against local and split targets.
- Prove direct, pooled, harness, and server database identity before measuring.
- Preserve every attempt immutably and record campaign state atomically.
- Resolve full sweeps and controlled comparative sequences such as ABBA into a
  durable leg schedule before the first measurement.
- Resume only from revalidated terminal leg records.
- Distinguish pass, pass with degradation, measured collapse, infrastructure
  failure, and invalid evidence.
- Pause only between atomic legs and resume without rerunning valid legs.
- Hold scarce local and Bunyip resources for one atomic leg only, then yield to
  already-queued short test work before attempting the next leg.
- Give private Bunyip infrastructure one exact-argv, machine-readable target
  contract while keeping private values outside the repository.
- Keep `grimoire e2e perf` as a compatible single-run entry point backed by the
  same lifecycle primitives.

### Non-goals

- Scheduling or daemonising jobs in the public repository.
- Replacing Bunyip's live shared-host lease or notifications.
- Automatically changing remote Git checkouts or provisioning hosts.
- Inventing arbitrary target plugins before a third real target exists.
- Treating performance campaigns as CI release gates.
- Interpreting browser-side degradation as a server knee.

## Design

### Lifecycle coordinator

One coordinator owns this state sequence for every attempt:

```text
created -> preparing_database -> starting_target -> attesting_target
        -> measuring -> stopping_target -> collecting_evidence
        -> validating -> terminal
```

The terminal classifications are `pass`, `pass_with_degradation`, `collapse`,
`infrastructure_failure`, and `invalid_evidence`. Only a valid probe result may
produce the first three. A missing result, pytest collection error, target
failure, database failure, or provenance mismatch cannot become a collapse.

Cleanup runs from every non-terminal state. Target stop and evidence collection
are attempted before the attempt is classified, without overwriting the
original failure. The private wrapper holds the live Bunyip lease around one
whole public attempt and releases it only after cleanup.

### Prepared database context

Database preparation becomes a single operation returning a
`PreparedTestDatabase` value containing the resolved direct URL, expected
database name, clone-source URL, and preparation identity. The harness and
pytest subprocess receive that context; `_run_pytest()` must not prepare again
when one is supplied.

Direct and pooled URLs are parsed, not compared as strings. Their database
names must equal the expected name. Branch suffixing is disabled for the
resolved performance database on both harness and measured-server sides.

The target is started only after migrations, truncation, clone-source creation,
and engine disposal finish. Target attestation must then positively report the
same database name and a successful pooled query. A probe-specific positive
fixture-visibility preflight may strengthen this boundary, but URL inference
alone never substitutes for server observation.

### Two target seams

`LocalPerfTarget` owns the existing managed `_server_script.py` process and
local log discovery.

`ExternalPerfTarget` invokes one configured executable with exact argument
vectors. It is deliberately a single command seam, not a plugin framework. The
executable supports machine-readable `start`, `stop`, and `collect` operations.
`start` succeeds only after fresh-instance and database attestation and returns
a versioned JSON identity containing the opaque target handle, server URL,
boot identity, PID, full commit, database name, pool mode/reason, and remote log
identity. `stop` and `collect` require that opaque handle.

The adapter does not migrate, clone, provision fixtures, classify results,
write pass markers, or decide resume. Its errors are infrastructure failures.
Credentials and private host values are resolved inside the private adapter and
must not appear in its JSON or public artifacts.

### Probe contract and result envelope

Campaign-capable probes use a small in-repository registry. Each entry names a
real test path, its typed session knob, diagnostic environment variable, and
validator. The initial entries are full-CRUD soak, assessment cram, and
thundering herd; no dynamic discovery is required.

Every completed measurement writes one atomic, versioned result envelope with:

- campaign, leg, and attempt identity;
- probe name and resolved typed parameters;
- run window and source identity;
- explicit probe verdict and reasons;
- load failures, fatal action failures, degraded actions, and attainment;
- server-page-load summary and provenance; and
- probe-specific observations.

The probe determines the measured boundary from its domain rules. The harness
validates the envelope and adds target/artifact provenance; it does not infer a
knee from pytest output. A passed systemic gate with nonzero degradation is
`pass_with_degradation`, never described as clean.

### Campaign definition and resolved schedule

A campaign definition names a probe, target, stop policy, typed parameter
levels, and optional named arms. An arm supplies explicit probe, server-profile,
source-identity, or feature-flag overrides; it never contains an arbitrary shell
fragment. A schedule declaration expands the definition before execution:

- a sweep produces one leg for each ordered parameter level;
- repetitions produce distinct legs rather than overwriting an earlier result;
- an arm pattern such as `A,B,B,A` is expanded independently at each selected
  parameter level; and
- an explicit leg list remains available for irregular but intentional
  campaigns.

The resolved schedule, including leg IDs, N/parameter values, arm, repetition,
expected source identity, and resolved overrides, is persisted in
`campaign.json` before the first attempt. Resume reads that immutable schedule;
it does not regenerate it from current defaults. Comparative campaigns default
to completing the entire schedule. Knee campaigns use an explicit
stop-on-valid-collapse policy.

The harness records leg order and per-leg evidence without manufacturing a
causal A/B claim. A campaign summary groups outcomes by parameter level and arm
and retains within-arm spread; interpretation still follows the repository's
performance-evidence contract.

### Durable campaign state

Campaign state lives under `output/perf-campaigns/<campaign-id>/` by default:

```text
campaign.json                 immutable resolved definition
state.json                    atomic current campaign state
legs/<leg-id>.json            atomic validated terminal leg record
attempts/<leg-id>/<attempt-id>/
  attempt.json                state transitions and terminal classification
  probe.json                  raw result envelope
  pytest.log / junit.xml
  target-start.json / target-stop.json
  target/                     collected server evidence
  manifest.json               paths, sizes, and SHA-256 values
  validation.json
```

The campaign definition fixes probe, resolved ordered schedule, target kind,
source identities, arm overrides, and stop policy. Reusing a campaign ID with a
different definition fails before work begins.

State and leg records are written by temporary sibling plus atomic replace.
Attempt directories are never reused. A terminal leg record references one
attempt and its manifest hashes. Resume reopens and revalidates that evidence;
JSON existence alone is never completion. Infrastructure and invalid attempts
remain diagnostic history and receive new attempt IDs on retry.

The campaign checks an atomic `pause_requested` state only between legs. A
collapse stop policy stops only on a validated `collapse`; infrastructure or
invalid evidence stops safely without moving the last validated pass.

Public campaign state is durable across process death. Private Bunyip
infrastructure remains responsible for keeping the process itself alive and
queued under the host lease.

### Cooperative resource admission

One leg is the maximum non-preemptible measurement unit. A running leg is not
interrupted because doing so invalidates its measurement window. After target
cleanup and evidence retention, the coordinator releases the local browser/test
host slot and the private adapter releases the Bunyip heavy-work lease before
the next leg may queue.

The local test-run lock gains a bounded two-class admission protocol using the
existing lock rather than a scheduler. Ordinary `grimoire test` and `grimoire
e2e` commands enter through the short-work turnstile. A campaign leg enters as
campaign work. If short work is already waiting when a leg ends, at least one
short command acquires the shared resource before the campaign can reacquire
it. The campaign then queues normally for its next leg. The private Bunyip
wrapper provides the equivalent per-leg behaviour around its authoritative
flock.

The campaign command must therefore not acquire the normal test-run slot once
for its entire process lifetime. Each leg acquires and releases a scoped slot.
Waiting, running, and yielding are durable campaign states, not inferred from
host load or process lists. Manual pause remains available, but ordinary short
tests do not require a human to pause the campaign.

### Backward compatibility

`grimoire e2e perf` remains a single-run command. It delegates to the same
prepare/start/run/stop primitives and performs database preparation once.
Unsafe legacy split mode, where an already-running external server is supplied
before destructive preparation, fails with a directed error rather than
silently retaining the race.

Existing raw probe payload fields remain available during migration. The
versioned envelope is additive until all three campaign probes consume the
shared writer and validator.

## Failure and recovery

- A preparation failure records `infrastructure_failure`; no target start is
  attempted.
- A stale PID, wrong boot identity, wrong commit, wrong database, failed pooled
  query, or wrong pool-fidelity reason is an infrastructure failure.
- A pytest nonzero exit without a valid result envelope is an infrastructure
  failure, not a collapse.
- A valid envelope whose target, source, window, or artifact provenance does
  not match is `invalid_evidence`.
- Stop or collection failure preserves the probe result but prevents pass or
  collapse validation because the evidence set is incomplete.
- SIGINT or SIGTERM records interruption, stops the owned target, collects what
  is available, and leaves the current leg incomplete for a new attempt.
- Resume never mutates old attempts. It revalidates completed legs and starts a
  new attempt at the first incomplete or invalid leg.

## Decisions

### Repository coordinator with a private command adapter

The repository coordinator is selected over a Bunyip-owned campaign script
because database preparation, probe semantics, and evidence validity are
application contracts. The private executable seam keeps machine secrets and
host policy private. This adds an explicit JSON protocol, but prevents local
and split campaigns from diverging.

This decision becomes invalid if a future target cannot implement the bounded
start/stop/collect contract without exposing secrets or moving probe semantics
out of the repository. A third target would justify revisiting whether a formal
adapter registration mechanism is useful.

### Persistent files, not a public scheduler

Atomic campaign files are selected over a public queue daemon or database. The
real private consumer already has systemd execution and a shared-host lease;
adding another scheduler would duplicate policy and failure recovery. The
files make semantic resume durable while the private layer makes execution
durable.

This decision becomes invalid if campaigns must be submitted concurrently by
multiple independent users on hosts without an external execution queue.

### Explicit schedules rather than an experiment optimiser

The harness resolves sweeps, repetitions, and named arm patterns but does not
choose sample sizes, randomise arms, detect changes, or stop on statistical
confidence. This covers the real N ramps and ABBA campaigns while keeping
experimental intent reviewable and resumable.

This decision becomes invalid if a future accepted evidence contract requires
adaptive experimental design rather than explicit predeclared schedules.

## Acceptance criteria

- **PERF-HARNESS-1:** A positive lifecycle test observes database preparation
  exactly once before either local or external target start. A start-before-
  prepare or second preparation fails the test.
- **PERF-HARNESS-2:** Parsed direct, pooled, harness, and attested server
  database identities must all match. A one-name mismatch fails before
  measurement.
- **PERF-HARNESS-3:** Local and fake-external target contract tests execute the
  same coordinator states. Stale identity, wrong SHA, failed query, or malformed
  adapter JSON produces infrastructure failure.
- **PERF-HARNESS-4:** Pass, degraded pass, collapse, infrastructure failure,
  and invalid evidence each have positive fixtures and cannot be produced by a
  different fixture.
- **PERF-HARNESS-5:** A diagnostic JSON without a validated leg record is
  rerun. A valid record is skipped only after its manifest and provenance are
  revalidated. Corruption or a wrong source identity starts a new attempt.
- **PERF-HARNESS-6:** Every retry uses a new immutable attempt directory and
  preserves prior logs and results.
- **PERF-HARNESS-7:** Pause requested during a leg takes effect only after that
  leg reaches terminal cleanup. Resume begins at the first nonvalidated leg.
- **PERF-HARNESS-7A:** A sweep with N values and an `A,B,B,A` arm pattern
  resolves to the exact durable order at every N. Repetitions have unique leg
  and attempt identities, and resume never changes the schedule.
- **PERF-HARNESS-7B:** When a short test queues during a campaign leg, the
  current leg finishes atomically, releases both resource slots, and the short
  test acquires before the next campaign leg. No manual pause or load detector
  is involved.
- **PERF-HARNESS-8:** Collection includes the complete run-window log set and
  fails validation when rotation loses the beginning of the window.
- **PERF-HARNESS-9:** SIGTERM and failures in preparation, start, measurement,
  stop, or collect leave no owned server running and keep the campaign
  resumable.
- **PERF-HARNESS-10:** Existing local `grimoire e2e perf` focused tests remain
  green and prove that `_pre_test_db_cleanup()` is called once.
- **PERF-HARNESS-11:** A local n=1 soak UAT and a Bunyip n=1 soak UAT each
  provision a workspace visible to the measured server, report positive
  server-page-load evidence from the attested process, and leave the server
  stopped.

## Implementation phases

### Phase 1: Single-run lifecycle and result boundary

Refactor database preparation into a returned context, eliminate the duplicate
preparation, and introduce the common result envelope and classifications with
the soak probe as the first consumer. Existing local single-run perf remains
usable. This phase owns PERF-HARNESS-1, 2, 4, and 10.

### Phase 2: Durable campaign and resume

Add the fixed probe registry, campaign definition, atomic state, immutable
attempts, manifest validation, pause, resume, parameter sweeps, arm patterns,
and per-leg cooperative admission. Exercise a soak knee sequence and a small
ABBA mechanics campaign against the local target. This phase owns
PERF-HARNESS-5, 6, 7, 7A, and 7B.

### Phase 3: Split target command seam

Add the bounded external command adapter, target identity validation, evidence
collection contract, and failure cleanup. Publish the exact protocol for the
private Bunyip implementation. This phase owns PERF-HARNESS-3, 8, and 9.

### Phase 4: Remaining real probes and operational UAT

Move assessment cram and thundering herd onto the result envelope, then execute
the local and split n=1 UAT. Private infrastructure supplies the durable job,
lease, staging restoration, and notifications. This phase owns
PERF-HARNESS-11 and leaves all current campaign probes on one harness.

## Verification and human judgment

Unit and focused CLI tests can prove lifecycle order, classifications, atomic
state, resume, adapter parsing, and cleanup. Ruff, formatting, and ty own code
quality claims. A local mechanics run can prove the managed target path.

Only a live Bunyip UAT can prove that private lease ownership, credentials,
remote process identity, log transport, and staging restoration satisfy the
public contract. Human acceptance must also confirm that campaign status and
degraded-pass presentation are operationally understandable. No PR is opened
and no branch is pushed without separate approval.
