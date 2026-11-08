#!/usr/bin/env bash
# Run only in the already approved disposable guest. No installs or VM commands.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
[[ ${UDP_ROUTER_ISOLATED_LINUX:-} == YES ]] || { echo 'Explicit isolated Linux opt-in required.' >&2; exit 2; }
[[ $(uname -s) == Linux && $(id -u) == 0 ]] || { echo 'Isolated Linux root required.' >&2; exit 2; }
exec python3 -B "$(dirname -- "$0")/e2e_benchmark.py" "$@"
