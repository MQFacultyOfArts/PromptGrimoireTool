#!/bin/bash
# Detached perf-lane runner.
#
# Claude Code's background-shell reaper kills main-session background
# tasks when a cgroup memory-pressure event coincides with >=30 min of
# user idleness (found 2026-08-18; see
# .notes/project_session-state-2026-08-17-perf-cram.md). Perf runs are
# both long and the very thing that generates that pressure, so they
# must not run inside the agent's cgroup at all. This wrapper launches
# the command as a transient systemd user unit: own cgroup, immune to
# the reaper, survives the launching terminal.
#
# Usage:
#   scripts/perf-run.sh <logfile> <command...>
# Example:
#   scripts/perf-run.sh /tmp/soak_n25.log \
#     env E2E_SOAK_SESSIONS=25 E2E_SOAK_DIAG_PATH=perf-data/soak_n25.json \
#     uv run grimoire e2e perf tests/e2e/test_soak_full_crud_load.py
#
# The unit runs in the current directory. Progress: tail the logfile or
# `systemctl --user status <unit>`. On completion the logfile ends with
# "=== perf-run exit=<code>" and "<logfile>.done" is created holding the
# exit code, so a poller has an unambiguous end signal.
set -euo pipefail

if [ $# -lt 2 ]; then
    echo "usage: $0 <logfile> <command...>" >&2
    exit 2
fi

log=$(realpath -m "$1")
shift
unit="perf-run-$(date +%Y%m%d-%H%M%S)"
rm -f "$log.done"

# Bounce through bash -c so redirection and the done-marker live inside
# the unit; printf %q survives arguments with spaces.
cmd=$(printf '%q ' "$@")
systemd-run --user --collect --unit="$unit" --same-dir \
    --property=Nice=19 \
    bash -c "{ echo \"=== perf-run start \$(date +%F' '%T) unit=$unit\";
               $cmd; rc=\$?;
               echo \"=== perf-run exit=\$rc \$(date +%F' '%T)\";
               echo \$rc >'$log.done'; } >'$log' 2>&1"

echo "launched $unit (log: $log)"
echo "watch: tail -f $log   status: systemctl --user status $unit"
