#!/usr/bin/env bats

SCRIPT="$BATS_TEST_DIRNAME/../../scripts/pre-pr-status.sh"

setup() {
    TEST_ROOT="$BATS_TEST_TMPDIR/pre-pr-status-$BATS_TEST_NUMBER"
    BIN_DIR="$TEST_ROOT/bin"
    TRACE="$TEST_ROOT/gh.trace"
    mkdir -p "$BIN_DIR"

    cat >"$BIN_DIR/gh" <<'EOF'
#!/bin/bash
set -euo pipefail
printf '%q ' "$@" >>"$GH_TRACE"
printf '\n' >>"$GH_TRACE"
if [[ " $* " == *" --method GET "* ]]; then
    printf '%s\n' "$GH_RESOLVED_SHA"
fi
EOF
    chmod +x "$BIN_DIR/gh"
    export GH_TRACE="$TRACE"
    export GH_RESOLVED_SHA=0123456789abcdef0123456789abcdef01234567
}

run_script() {
    local requested_sha=${REQUESTED_SHA:-0123456789abcdef0123456789abcdef01234567}
    local request_id=${REQUEST_ID:-prepr-0123456789abcdef0123456789abcdef}
    run env \
        PATH="$BIN_DIR:$PATH" \
        GH_TOKEN=test-token \
        GITHUB_REPOSITORY=owner/repository \
        GH_RESOLVED_SHA="$GH_RESOLVED_SHA" \
        REQUESTED_SHA="$requested_sha" \
        REQUEST_ID="$request_id" \
        STATUS_TARGET_URL=https://github.example.invalid/actions/runs/123 \
        "$SCRIPT" "$@"
}

@test "validate-request resolves the exact pushed commit" {
    run_script validate-request

    [ "$status" -eq 0 ]
    grep -F -- '--method GET' "$TRACE"
    grep -F -- '/repos/owner/repository/commits/0123456789abcdef0123456789abcdef01234567' "$TRACE"
}

@test "validate-request rejects a malformed request label before GitHub access" {
    REQUEST_ID=guessable run_script validate-request

    [ "$status" -eq 2 ]
    [ ! -e "$TRACE" ]
}

@test "validate-request rejects a commit resolution mismatch" {
    GH_RESOLVED_SHA=ffffffffffffffffffffffffffffffffffffffff \
        run_script validate-request

    [ "$status" -eq 1 ]
    [[ "$output" == *"resolved commit does not match requested SHA"* ]]
}

@test "set posts the exact SHA and dedicated commit-status context" {
    run_script set success

    [ "$status" -eq 0 ]
    grep -F -- '--method POST' "$TRACE"
    grep -F -- '/repos/owner/repository/statuses/0123456789abcdef0123456789abcdef01234567' "$TRACE"
    grep -F -- 'state=success' "$TRACE"
    grep -F -- 'context=ci/pre-pr-isolated' "$TRACE"
    grep -F -- 'target_url=https://github.example.invalid/actions/runs/123' "$TRACE"
}

@test "set rejects an unsupported state before posting" {
    run_script set neutral

    [ "$status" -eq 2 ]
    [ ! -e "$TRACE" ]
}
