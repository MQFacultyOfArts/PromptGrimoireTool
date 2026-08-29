#!/bin/bash
set -euo pipefail

STATUS_CONTEXT=ci/pre-pr-isolated

die() {
    echo "pre-pr-status: $*" >&2
    exit 1
}

usage() {
    echo "usage: $0 validate-request | set {pending|success|failure|error}" >&2
    exit 2
}

require_request() {
    : "${GH_TOKEN:?GH_TOKEN is required}"
    : "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
    : "${REQUESTED_SHA:?REQUESTED_SHA is required}"
    : "${REQUEST_ID:?REQUEST_ID is required}"

    [[ "$REQUESTED_SHA" =~ ^[0-9a-fA-F]{40}$ ]] \
        || { echo "pre-pr-status: requested SHA must be 40 hexadecimal characters" >&2; exit 2; }
    [[ "$REQUEST_ID" =~ ^prepr-[0-9a-f]{32}$ ]] \
        || { echo "pre-pr-status: request ID must be prepr- followed by 32 lowercase hexadecimal characters" >&2; exit 2; }
    [[ "$GITHUB_REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] \
        || { echo "pre-pr-status: invalid repository slug" >&2; exit 2; }
}

validate_commit() {
    local resolved
    resolved=$(gh api \
        --method GET \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2026-03-10" \
        "/repos/$GITHUB_REPOSITORY/commits/$REQUESTED_SHA" \
        --jq .sha)
    [ "${resolved,,}" = "${REQUESTED_SHA,,}" ] \
        || die "resolved commit does not match requested SHA"
}

set_status() {
    local state=$1 description
    case "$state" in
        pending) description="Isolated pre-PR CI queued" ;;
        success) description="Isolated pre-PR CI passed" ;;
        failure) description="Isolated pre-PR CI failed" ;;
        error) description="Isolated pre-PR CI did not complete" ;;
        *) usage ;;
    esac
    : "${STATUS_TARGET_URL:?STATUS_TARGET_URL is required}"
    [[ "$STATUS_TARGET_URL" == https://* ]] \
        || { echo "pre-pr-status: status target must use HTTPS" >&2; exit 2; }

    require_request
    validate_commit
    gh api \
        --method POST \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2026-03-10" \
        "/repos/$GITHUB_REPOSITORY/statuses/$REQUESTED_SHA" \
        -f "state=$state" \
        -f "target_url=$STATUS_TARGET_URL" \
        -f "description=$description" \
        -f "context=$STATUS_CONTEXT" >/dev/null
}

case ${1:-} in
    validate-request)
        [ "$#" -eq 1 ] || usage
        require_request
        validate_commit
        ;;
    set)
        [ "$#" -eq 2 ] || usage
        case "$2" in
            pending|success|failure|error) ;;
            *) usage ;;
        esac
        set_status "$2"
        ;;
    *) usage ;;
esac
