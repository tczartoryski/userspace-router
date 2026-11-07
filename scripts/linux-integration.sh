#!/usr/bin/env bash
# Explicit opt-in, existing isolated Linux only. Never run on a shared host.
set -euo pipefail
# Set inside the root harness: sudo may strip the caller's environment.
# Root imports must not leave bytecode in the unprivileged guest staging tree.
export PYTHONDONTWRITEBYTECODE=1
if [[ ${UDP_ROUTER_ISOLATED_LINUX:-} != YES ]]; then
  echo 'Refusing: set UDP_ROUTER_ISOLATED_LINUX=YES only inside an explicitly permitted isolated Linux environment.' >&2
  exit 2
fi
[[ $(uname -s) == Linux ]] || { echo 'Linux required; integration NOT RUN.' >&2; exit 2; }
[[ $(id -u) == 0 ]] || { echo 'Namespace/TUN setup requires root inside the isolated Linux environment.' >&2; exit 2; }
for tool in ip python3 sysctl; do command -v "$tool" >/dev/null || { echo "Missing existing prerequisite: $tool" >&2; exit 2; }; done
[[ -c /dev/net/tun ]] || { echo 'Existing /dev/net/tun required; no installation or module loading performed.' >&2; exit 2; }
project=$(cd -- "$(dirname -- "$0")/.." && pwd)
binary=${UDP_ROUTER_BIN:-$project/target/debug/udp-router}
[[ -x $binary ]] || { echo "Build the Linux binary first: $binary" >&2; exit 2; }
artifact=$(mktemp -d "${TMPDIR:-/tmp}/udp-router-evidence.XXXXXXXX")
tag="ur-$$-${RANDOM}"
client="$tag-c"; server="$tag-s"; router="$tag-r"
created=(); router_pid=''; server_pid=''
cleanup() {
  local rc=$?
  trap - EXIT
  if [[ -n $router_pid ]]; then kill "$router_pid" 2>/dev/null || true; wait "$router_pid" 2>/dev/null || true; fi
  if [[ -n $server_pid ]]; then kill "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true; fi
  for ns in "${created[@]}"; do ip netns del "$ns"; done
  echo "Evidence retained at $artifact (exit=$rc)"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for ns in "$client" "$server" "$router"; do
  ip netns add "$ns"; created+=("$ns")
  ip -n "$ns" link set lo up
  ip netns exec "$ns" sysctl -q -w net.ipv4.ip_forward=0 net.ipv4.conf.all.rp_filter=0 net.ipv4.conf.default.rp_filter=0
  ip netns exec "$ns" sysctl net.ipv4.ip_forward >> "$artifact/sysctls.txt"
done
ip -n "$client" tuntap add dev tun-in mode tun
ip -n "$server" tuntap add dev tun-out mode tun
ip -n "$client" addr add 10.0.0.2/32 dev tun-in
for n in 3 4 5; do ip -n "$client" addr add "10.0.0.$n/32" dev tun-in; done
ip -n "$server" addr add 198.51.100.2/32 dev tun-out
ip -n "$client" link set tun-in mtu 1500 up
ip -n "$server" link set tun-out mtu 1500 up
ip -n "$client" route add 198.51.100.0/24 dev tun-in src 10.0.0.2
ip -n "$server" route add 198.51.100.1/32 dev tun-out src 198.51.100.2
for ns in "$client" "$server" "$router"; do
  ip -n "$ns" addr show >> "$artifact/topology.txt"
  ip -n "$ns" route show table all >> "$artifact/topology.txt"
done
# All devices are precreated. The helper only attaches and passes their descriptors.
ip netns exec "$router" python3 "$project/scripts/traffic.py" launch "$client" "$server" "$binary" >"$artifact/router.stdout" 2>"$artifact/router.log" &
router_pid=$!
if [[ ${UDP_ROUTER_EXTENDED:-} == YES ]]; then
  ip netns exec "$server" python3 "$project/scripts/extended.py" server "$artifact/server.ready" "$artifact/server.jsonl" &
  server_pid=$!
  python3 "$project/scripts/traffic.py" ready "$artifact/server.ready" "$artifact/router.log" "$router_pid" "$server_pid"
  ip netns exec "$client" python3 "$project/scripts/extended.py" client "$artifact"
  kill -TERM "$router_pid"; wait "$router_pid"; router_pid=''
  ip netns exec "$client" python3 "$project/scripts/traffic.py" client negative > "$artifact/client-negative.json"
  python3 "$project/scripts/extended.py" verify "$artifact"
  if [[ ${UDP_ROUTER_RETAIN:-} == YES ]]; then
    echo 'Retained demo: restart router; Ctrl-C performs namespace/process cleanup.'
    ip netns exec "$router" python3 "$project/scripts/traffic.py" launch "$client" "$server" "$binary" >>"$artifact/router.stdout" 2>>"$artifact/router.log" &
    router_pid=$!
    while kill -0 "$router_pid" && kill -0 "$server_pid"; do
      ip netns exec "$client" python3 "$project/scripts/extended.py" pulse
      sleep 1
    done
  fi
else
ip netns exec "$server" python3 "$project/scripts/traffic.py" server "$artifact/server.ready" "$artifact/server.jsonl" >"$artifact/server.stdout" 2>"$artifact/server.stderr" &
server_pid=$!
python3 "$project/scripts/traffic.py" ready "$artifact/server.ready" "$artifact/router.log" "$router_pid" "$server_pid"
ip netns exec "$client" python3 "$project/scripts/traffic.py" client positive > "$artifact/client-positive.json"
# Negative control: wait for the actual router to exit before trying the same path.
kill -TERM "$router_pid"
wait "$router_pid"
router_pid=''
ip netns exec "$client" python3 "$project/scripts/traffic.py" client negative > "$artifact/client-negative.json"
kill -0 "$server_pid"
python3 "$project/scripts/traffic.py" verify "$artifact"
echo 'PASS: real UDP request/reply, observed SNAT and TTL; stopping router broke path.'

fi
