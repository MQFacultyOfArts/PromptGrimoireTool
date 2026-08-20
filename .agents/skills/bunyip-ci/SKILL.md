---
name: bunyip-ci
description: Run, wait for, diagnose, and report PromptGrimoire CI lanes submitted to the shared bunyip wrapper. Use for bunyip act, nightly, browser, NiceGUI, quality, image-build, or other heavy-lane work where an agent must track completion, inspect failures, verify cleanup, or hand back exact evidence.
---

# Bunyip CI

Use the operator-installed wrapper as the only entry point. The wrapper owns
the kernel `flock`; never acquire a second lock or infer availability from a
note, timestamp, PID, port, process name, or lock-file existence.

## Track completion

1. Run the wrapper in the foreground from the checkout being tested. If the
   execution tool returns a session identifier, keep polling that same session.
2. Treat `waiting for the bunyip heavy-work queue` as queued, not stalled. Do
   not submit a duplicate.
3. Capture the printed lane, revision, artifact directory, start time, and
   resource limits.
4. Consider the lane finished only when the wrapper exits. A test summary is
   not completion: artifact handling, container cleanup, and interrupted
   staging restoration happen afterward.
5. Record the wrapper exit status and its final `PASS` or `FAIL` line. On an
   interrupted run, also verify the wrapper completed its cleanup/restoration
   path before reporting done.

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
