#!/usr/bin/env bats
# Literal source patterns must not expand.
# shellcheck disable=SC2016
# Structural and guard tests for deploy/update-texlive.sh.

SCRIPT="$BATS_TEST_DIRNAME/../update-texlive.sh"

@test "script has valid Bash syntax" {
    run bash -n "$SCRIPT"
    [ "$status" -eq 0 ]
}

@test "non-root user is rejected before maintenance" {
    if [ "$EUID" -eq 0 ]; then
        skip "running as root"
    fi

    run bash "$SCRIPT"
    [ "$status" -eq 1 ]
    [[ "$output" == *"run as root"* ]]
}

@test "script pins an accessible working directory before changing user" {
    cd_line=$(grep -n 'cd "$APP_DIR"' "$SCRIPT" | head -1 | cut -d: -f1)
    tlmgr_line=$(grep -n 'tlmgr version' "$SCRIPT" | head -1 | cut -d: -f1)

    [ -n "$cd_line" ]
    [ -n "$tlmgr_line" ]
    [ "$cd_line" -lt "$tlmgr_line" ]
}

@test "filesystem snapshot precedes package updates" {
    snapshot_line=$(grep -n 'tar -C "$SERVICE_HOME"' "$SCRIPT" | head -1 | cut -d: -f1)
    update_line=$(grep -n 'tlmgr update --self' "$SCRIPT" | head -1 | cut -d: -f1)

    [ -n "$snapshot_line" ]
    [ -n "$update_line" ]
    [ "$snapshot_line" -lt "$update_line" ]
}

@test "snapshot is archive-tested and checksummed before package updates" {
    archive_test_line=$(grep -n 'tar -tzf "$tex_snapshot"' "$SCRIPT" | head -1 | cut -d: -f1)
    checksum_line=$(grep -n 'sha256sum "$tex_snapshot"' "$SCRIPT" | head -1 | cut -d: -f1)
    update_line=$(grep -n 'tlmgr update --self' "$SCRIPT" | head -1 | cut -d: -f1)

    [ -n "$archive_test_line" ]
    [ -n "$checksum_line" ]
    [ -n "$update_line" ]
    [ "$archive_test_line" -lt "$update_line" ]
    [ "$checksum_line" -lt "$update_line" ]
}

@test "maintenance takes an exclusive lock" {
    grep -q 'flock --exclusive --nonblock' "$SCRIPT"
}

@test "package backups are enabled before package updates" {
    backupdir_line=$(grep -n '^run_as_service tlmgr option backupdir ' "$SCRIPT" | cut -d: -f1)
    autobackup_line=$(grep -n '^run_as_service tlmgr option autobackup 5$' "$SCRIPT" | cut -d: -f1)
    update_line=$(grep -n 'tlmgr update --self' "$SCRIPT" | head -1 | cut -d: -f1)

    [ -n "$backupdir_line" ]
    [ -n "$autobackup_line" ]
    [ -n "$update_line" ]
    [ "$backupdir_line" -lt "$update_line" ]
    [ "$autobackup_line" -lt "$update_line" ]
}

@test "manager update precedes package update" {
    self_line=$(grep -n 'tlmgr update --self' "$SCRIPT" | head -1 | cut -d: -f1)
    all_line=$(grep -n 'tlmgr update --all' "$SCRIPT" | head -1 | cut -d: -f1)

    [ -n "$self_line" ]
    [ -n "$all_line" ]
    [ "$self_line" -lt "$all_line" ]
}

@test "smoke export passes before worker returns" {
    smoke_line=$(grep -n 'grimoire test smoke-export' "$SCRIPT" | head -1 | cut -d: -f1)
    start_line=$(grep -n 'systemctl start promptgrimoire-worker.service' "$SCRIPT" | tail -1 | cut -d: -f1)

    [ -n "$smoke_line" ]
    [ -n "$start_line" ]
    [ "$smoke_line" -lt "$start_line" ]
}
