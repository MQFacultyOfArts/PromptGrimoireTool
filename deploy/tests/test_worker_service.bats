#!/usr/bin/env bats
# Unit tests for deploy/promptgrimoire-worker.service
#
# Validates systemd unit file structure and resource controls
# match the design specification.

UNIT_FILE="$BATS_TEST_DIRNAME/../promptgrimoire-worker.service"

# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------

@test "worker service unit file exists and is non-empty" {
    [ -s "$UNIT_FILE" ]
}

# ---------------------------------------------------------------------------
# Required directives
# ---------------------------------------------------------------------------

@test "service type is notify (for sd_notify watchdog)" {
    run grep -E '^Type=notify$' "$UNIT_FILE"
    [ "$status" -eq 0 ]
}

@test "WatchdogSec is configured" {
    run grep -E '^WatchdogSec=' "$UNIT_FILE"
    [ "$status" -eq 0 ]
}

@test "MemoryMax is configured" {
    run grep -E '^MemoryMax=' "$UNIT_FILE"
    [ "$status" -eq 0 ]
}

@test "OOMScoreAdjust is configured" {
    run grep -E '^OOMScoreAdjust=' "$UNIT_FILE"
    [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Resource controls match design spec
# ---------------------------------------------------------------------------

@test "Nice=19 (lowest CPU priority)" {
    run grep -E '^Nice=19$' "$UNIT_FILE"
    [ "$status" -eq 0 ]
}

@test "CPUWeight=10 (1/10th CPU share)" {
    run grep -E '^CPUWeight=10$' "$UNIT_FILE"
    [ "$status" -eq 0 ]
}

@test "MemoryMax=3G (hard kill limit)" {
    run grep -E '^MemoryMax=3G$' "$UNIT_FILE"
    [ "$status" -eq 0 ]
}

@test "OOMScoreAdjust=500 (killed before app and PG)" {
    run grep -E '^OOMScoreAdjust=500$' "$UNIT_FILE"
    [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Shutdown behaviour
# ---------------------------------------------------------------------------

@test "TimeoutStopSec is set (cleanup headroom)" {
    run grep -E '^TimeoutStopSec=' "$UNIT_FILE"
    [ "$status" -eq 0 ]
}

@test "KillSignal=SIGTERM (not SIGKILL)" {
    run grep -E '^KillSignal=SIGTERM$' "$UNIT_FILE"
    [ "$status" -eq 0 ]
}
