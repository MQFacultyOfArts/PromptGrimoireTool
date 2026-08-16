#!/usr/bin/env bats

HELPERS="$BATS_TEST_DIRNAME/../restart_helpers.sh"

@test "required env value returns the single non-empty value" {
    env_file=$(mktemp)
    printf '%s\n' 'ADMIN__PRE_RESTART_TOKEN=test-secret' > "$env_file"

    run bash -c 'source "$1"; read_required_env_value "$2" ADMIN__PRE_RESTART_TOKEN' \
        _ "$HELPERS" "$env_file"

    [ "$status" -eq 0 ]
    [ "$output" = "test-secret" ]
}

@test "required env value rejects a missing value" {
    env_file=$(mktemp)
    printf '%s\n' 'DATABASE__URL=postgresql:///promptgrimoire' > "$env_file"

    run bash -c 'source "$1"; read_required_env_value "$2" ADMIN__PRE_RESTART_TOKEN' \
        _ "$HELPERS" "$env_file"

    [ "$status" -ne 0 ]
}

@test "required env value rejects duplicate definitions" {
    env_file=$(mktemp)
    printf '%s\n' \
        'ADMIN__PRE_RESTART_TOKEN=first' \
        'ADMIN__PRE_RESTART_TOKEN=second' > "$env_file"

    run bash -c 'source "$1"; read_required_env_value "$2" ADMIN__PRE_RESTART_TOKEN' \
        _ "$HELPERS" "$env_file"

    [ "$status" -ne 0 ]
}

@test "JSON count parser accepts a non-negative integer" {
    run bash -c 'source "$1"; parse_json_count "$2" initial_count' \
        _ "$HELPERS" '{"initial_count":12}'

    [ "$status" -eq 0 ]
    [ "$output" = "12" ]
}

@test "JSON count parser rejects a missing field" {
    run bash -c 'source "$1"; parse_json_count "$2" initial_count' \
        _ "$HELPERS" '{}'

    [ "$status" -ne 0 ]
}

@test "JSON count parser rejects null negative fractional and string values" {
    for value in null -1 1.5 '"0"'; do
        run bash -c 'source "$1"; parse_json_count "$2" count' \
            _ "$HELPERS" "{\"count\":$value}"
        [ "$status" -ne 0 ]
    done
}
