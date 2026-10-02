#!/bin/bash
# launchd entry point. Never enable xtrace or expose a credential in arguments.
set -euo pipefail
set +x
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
directory=$(cd "$(dirname "$0")" && pwd)
exec python3.12 "$directory/runner.py" "$@"
