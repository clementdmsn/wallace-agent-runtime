#!/bin/sh
set -eu

init_runtime_dirs() {
    mkdir -p /sandbox /state
    chown wallace:wallace /sandbox /state
    chmod 700 /sandbox /state

    if [ ! -e /state/curl_whitelist.json ]; then
        printf '{"domains": []}\n' > /state/curl_whitelist.json
    fi
    chown wallace:wallace /state/curl_whitelist.json
    chmod 600 /state/curl_whitelist.json
}

if [ "$(id -u)" = "0" ]; then
    init_runtime_dirs
    exec gosu wallace "$@"
fi

exec "$@"
