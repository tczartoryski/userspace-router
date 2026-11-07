#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
RUSTC=rustc-1.89 RUSTDOC=rustdoc-1.89 cargo-1.89 test --locked --offline
RUSTC=rustc-1.89 cargo-1.89 build --locked --offline
# Separate allocator bounds: flow capacity first, port capacity second.
for args in '["--max-flows","2","--ports","40000-40002"]' '["--max-flows","3","--ports","40000-40001"]'; do
  extra=$(python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1])+["--idle-seconds","3","--route","198.51.0.0/16=inside","--route","198.51.100.3/32=inside"]))' "$args")
  sudo -n env UDP_ROUTER_ISOLATED_LINUX=YES UDP_ROUTER_EXTENDED=YES UDP_ROUTER_EXTRA_ARGS="$extra" bash scripts/linux-integration.sh
done
if [[ ${1:-} == --retain ]]; then
  sudo -n mkdir -m 700 /tmp/udp-router-demo
  trap 'sudo -n rm -f /tmp/udp-router-demo/snapshot.json; sudo -n rmdir /tmp/udp-router-demo' EXIT
  extra='["--max-flows","2","--ports","40000-40002","--idle-seconds","3","--route","198.51.0.0/16=inside","--route","198.51.100.3/32=inside","--snapshot","/tmp/udp-router-demo/snapshot.json"]'
  sudo -n env UDP_ROUTER_ISOLATED_LINUX=YES UDP_ROUTER_EXTENDED=YES UDP_ROUTER_RETAIN=YES UDP_ROUTER_EXTRA_ARGS="$extra" bash scripts/linux-integration.sh
fi
