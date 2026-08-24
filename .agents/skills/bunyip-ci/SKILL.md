---
name: bunyip-ci
description: Run, wait for, diagnose, and report PromptGrimoire CI lanes submitted to the shared bunyip wrapper. Use for bunyip act, nightly, browser, NiceGUI, quality, image-build, or other heavy-lane work where an agent must track completion, inspect failures, verify cleanup, or hand back exact evidence.
---

# Bunyip CI

Use the operator-installed wrapper as the only entry point. The wrapper owns
the kernel `flock`; never acquire a second lock or infer availability from a
note, timestamp, PID, port, process name, or lock-file existence.

## Shared-host affordances

- A durable interruptible staging service may remain healthy while the heavy
  lock is free. Its container, listener, and health endpoint do not mean act or
  another heavy workload is running.
- The wrapper acquires the shared flock before stopping staging, then restores
  staging during cleanup before releasing the flock. Loud preemption and
  restoration messages are expected.
- Perf uses the same flock for each atomic leg and releases it between legs.
  CI waits for a running leg; it never kills one. Do not dispatch a second
  workload or invent another lock.
- Only successful `flock` acquisition establishes exclusive use. Durable
  services and retained caches or artifacts are outside that ownership signal.

For focused red/green work, pass the repository command as an argument vector:

```bash
run-tests.sh focused -- uv run grimoire test run path/to/test.py::test_name
```

The focused lane supplies the prepared image and PostgreSQL. Do not replace a
focused run with an entire regular lane; run the regular lane once after the
focused test is restored.

## Submit and await completion

1. Launch the wrapper once from the checkout being tested in a background
   terminal that emits a completion event. Keep that terminal attached to the
   wrapper; do not detach the wrapper into an unobservable shell process. Retain
   every monitor handle until the wrapper exits. Yield the agent turn only when
   the runtime guarantees that its completion event survives the yield.
2. Treat `waiting for the bunyip heavy-work queue` as queued, not stalled. Do
   not submit a duplicate.
3. Do not poll processes, logs, note files, or the lock while the run is active.
   Await only the attached monitor, using its longest supported wait. If it
   yields without an exit status, wait again on the same handle. Wrapper state
   transitions such as queued, started, staging preemption, and restoration are
   authoritative and may be reported once. Individual test output is non-final:
   do not interpret, summarize, quote, or narrate it unless the user explicitly
   asks for progress. An empty wait is not a state change and needs no update.
4. Consider the lane finished only when the attached wrapper exits. A test
   summary is not completion: artifact handling, container cleanup, and
   interrupted staging restoration happen afterward.
5. After notification, read the terminal result once and record the lane,
   revision, artifact directory, start/end times, wrapper exit status, and its
   final `PASS` or `FAIL` line. On an interrupted run, also verify the wrapper
   completed its cleanup/restoration path before reporting done.

## Diagnose failure

Do not rerun first. Preserve the initial failure and classify it from evidence:

1. Read the first failing step and the final job summary from the captured
   output.
2. Inspect the printed artifact directory and the lane's retained test log.
   Report exact failing tests, counts, and artifact paths.
3. If tests passed but artifact upload failed, report an artifact-service
   failure rather than a test failure.
4. If a container vanished or exited abruptly, inspect its exit/OOM state and
   the host kernel OOM record before calling it a test failure.
5. If many unrelated tests fail on one missing host capability or path, prove
   that common cause with one focused reproduction. Do not label the failures
   flaky or patch individual tests.
6. After failure, confirm run-scoped containers, networks, and listeners are
   gone and any preempted staging service is healthy. Preserve declared caches
   and evidence artifacts.

Rerun only after identifying a falsifiable cause or applying a relevant fix.
Use the smallest focused lane that proves the fix, then rerun the originally
failed lane when required for acceptance.

## Report

Return the lane and exact revision, wrapper exit status, elapsed time, test
counts, first/root failure, artifact location, cache result, cleanup result,
and staging restoration result. Distinguish observed facts from inference.
