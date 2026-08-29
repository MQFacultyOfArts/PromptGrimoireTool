#!/bin/bash
set -euo pipefail

run_outcome=${1:?usage: nightly-summary.sh RUN_OUTCOME}
: "${GITHUB_STEP_SUMMARY:?GITHUB_STEP_SUMMARY is required}"
exec >>"$GITHUB_STEP_SUMMARY"

echo "## Nightly E2E Slow Results"
echo ""
echo "| Lane | Status | Log |"
echo "|------|--------|-----|"

overall_ok=true
summary_valid=true

log_exit_code() {
    awk '/^Exit code: [0-9]+$/ { code=$3 } END { if (code != "") print code }' "$1"
}

# The harness footer is the lane's positive completion signal. Pytest summary
# words such as "xfailed" are descriptive counts, not process status.
for log in test-unit.log test-integration.log test-smoke.log test-blns-extra.log; do
    if [ ! -f "$log" ]; then
        lane=${log#test-}
        lane=${lane%.log}
        echo "| $lane | :x: INVALID | \`$log\` missing |"
        overall_ok=false
        summary_valid=false
        continue
    fi
    lane=${log#test-}
    lane=${lane%.log}
    exit_code=$(log_exit_code "$log")
    if [ "$exit_code" = 0 ]; then
        echo "| $lane | :white_check_mark: PASS | \`$log\` |"
    elif [[ "$exit_code" =~ ^[0-9]+$ ]]; then
        echo "| $lane | :x: FAIL | \`$log\` |"
        overall_ok=false
    else
        echo "| $lane | :x: INVALID | \`$log\` has no exit footer |"
        overall_ok=false
        summary_valid=false
    fi
done

# JS and BATS don't produce log files — check exit code from step.
if [ "$run_outcome" = failure ] && [ "$overall_ok" = true ]; then
    echo "| js/bats/playwright | :x: FAIL | (no log file — check step output) |"
fi

echo ""

# Extract FAILURES sections from each failed log for copy-paste debugging.
for log in test-unit.log test-integration.log test-smoke.log test-blns-extra.log; do
    if [ ! -f "$log" ]; then
        continue
    fi
    exit_code=$(log_exit_code "$log")
    if [[ "$exit_code" =~ ^[0-9]+$ ]] && [ "$exit_code" -ne 0 ]; then
        lane=${log#test-}
        lane=${lane%.log}
        echo "### Failures: $lane"
        echo ""
        echo '```'
        # Print from "= FAILURES =" through "= short test summary =".
        sed -n '/^=\+ FAILURES =\+$/,/^=\+ short test summary/p' "$log"
        echo '```'
        echo ""
    fi
done

[ "$summary_valid" = true ]
