#!/bin/bash
# Config reader for uconsole.conf (INI format)
# Usage: source config.sh; val=$(read_config section.key default)

# guard against double-sourcing
[ -n "${_CONFIG_SH_LOADED:-}" ] && return 0
_CONFIG_SH_LOADED=1

_CONF_FILE="/etc/uconsole/uconsole.conf"
_CONF_DEFAULT="/etc/uconsole/uconsole.conf.default"

# read_config SECTION.KEY [DEFAULT]
# Reads from uconsole.conf, falls back to uconsole.conf.default, then DEFAULT.
read_config() {
    local lookup="$1"
    local default="${2:-}"
    local section="${lookup%%.*}"
    local key="${lookup#*.}"

    local val
    val=$(_ini_get "$_CONF_FILE" "$section" "$key")
    if [ -z "$val" ]; then
        val=$(_ini_get "$_CONF_DEFAULT" "$section" "$key")
    fi
    printf '%s' "${val:-$default}"
}

# _ini_get FILE SECTION KEY — parse INI value (no dependencies)
_ini_get() {
    local file="$1" target_section="$2" target_key="$3"
    [ -f "$file" ] || return 0
    local in_section=0
    while IFS= read -r line || [ -n "$line" ]; do
        # strip inline comments and whitespace
        line="${line%%#*}"
        line="${line##[[:space:]]}"
        line="${line%%[[:space:]]}"
        [ -z "$line" ] && continue
        # section header
        if [[ "$line" =~ ^\[([^]]+)\]$ ]]; then
            if [ "${BASH_REMATCH[1]}" = "$target_section" ]; then
                in_section=1
            else
                [ "$in_section" -eq 1 ] && return 0
                in_section=0
            fi
            continue
        fi
        # key = value
        if [ "$in_section" -eq 1 ] && [[ "$line" =~ ^([^=]+)=(.*)$ ]]; then
            local k="${BASH_REMATCH[1]}"
            local v="${BASH_REMATCH[2]}"
            k="${k##[[:space:]]}"
            k="${k%%[[:space:]]}"
            v="${v##[[:space:]]}"
            v="${v%%[[:space:]]}"
            if [ "$k" = "$target_key" ]; then
                printf '%s' "$v"
                return 0
            fi
        fi
    done < "$file"
}
