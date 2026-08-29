#!/usr/bin/env bats

SUMMARY_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/nightly-summary.sh"

setup() {
    TEST_ROOT="$BATS_TEST_TMPDIR/nightly-summary-$BATS_TEST_NUMBER"
    SUMMARY="$TEST_ROOT/summary.md"
    mkdir -p "$TEST_ROOT"
}

write_log() {
    local name=$1 exit_code=$2 pytest_summary=$3
    cat >"$TEST_ROOT/$name" <<EOF
============================= test session starts ==============================
$pytest_summary

============================================================
Finished: 2026-08-24T00:00:00
Duration: 0:00:01
Exit code: $exit_code
============================================================
EOF
}

write_other_passing_logs() {
    local excluded=$1 log
    for log in test-unit.log test-integration.log test-smoke.log test-blns-extra.log; do
        [ "$log" = "$excluded" ] || write_log "$log" 0 "1 passed in 0.01s"
    done
}

run_summary() {
    local outcome=$1
    run bash -c 'cd "$1" && GITHUB_STEP_SUMMARY="$2" "$3" "$4"' \
        _ "$TEST_ROOT" "$SUMMARY" "$SUMMARY_SCRIPT" "$outcome"
}

@test "xfailed pytest outcome remains a passing nightly lane" {
    write_other_passing_logs test-smoke.log
    write_log test-smoke.log 0 \
        "==== 43 passed, 5487 deselected, 1 xfailed, 1 warning in 113.36s ===="

    run_summary success

    [ "$status" -eq 0 ]
    grep -F "| smoke | :white_check_mark: PASS | \`test-smoke.log\` |" "$SUMMARY"
    run grep -F '| smoke | :x: FAIL |' "$SUMMARY"
    [ "$status" -eq 1 ]
    run grep -F '### Failures: smoke' "$SUMMARY"
    [ "$status" -eq 1 ]
}

@test "nonzero recorded exit code produces a failure row and details" {
    write_other_passing_logs test-unit.log
    cat >"$TEST_ROOT/test-unit.log" <<'EOF'
=============================== FAILURES =======================================
____________________________ test_real_failure _______________________________
E   AssertionError: deliberate fixture failure
=========================== short test summary info ============================
FAILED tests/unit/test_example.py::test_real_failure

============================================================
Finished: 2026-08-24T00:00:00
Duration: 0:00:01
Exit code: 1
============================================================
EOF

    run_summary failure

    [ "$status" -eq 0 ]
    grep -F "| unit | :x: FAIL | \`test-unit.log\` |" "$SUMMARY"
    grep -F '### Failures: unit' "$SUMMARY"
    grep -F 'AssertionError: deliberate fixture failure' "$SUMMARY"
}

@test "missing required lane log is reported as invalid evidence" {
    write_other_passing_logs test-smoke.log

    run_summary success

    [ "$status" -eq 1 ]
    grep -F "| smoke | :x: INVALID | \`test-smoke.log\` missing |" "$SUMMARY"
}
