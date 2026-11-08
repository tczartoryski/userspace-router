# NAT story: real observations, recorded replay

The coordinator ran the approved isolated Linux VM on November 7, 2026:
**all four real UDP scenario verifier gates PASS**. The supplied host evidence
was reviewed and independently rechecked with `nat_story.py verify` during this
UI revision. The VM is stopped and namespaces/helpers were removed, as reported
by the coordinator. The collector is unchanged. Portable test fixtures remain
separate from real acceptance evidence. The reviewed [observations](qa/nat-story/observations.json),
[capture record](qa/nat-story/capture.json), and [explanatory MP4](https://raw.githubusercontent.com/tczartoryski/userspace-router/cc95f60414a7aab467db7678ab3f7b32bfd84014/docs/qa/nat-story/nat-story.mp4)
are bundled after coordinator verification and privacy review. The direct MP4
link downloads the verified file; GitHub does not preview this 16.4 MB source
asset inline. No hosted live demo or inline player is implied.

Use only the already approved `router-lab` Lima guest, with `mounts: []`,
`networks: []`, and ignored forwards. Do not create/reconfigure a VM, install
prerequisites, or change host routes, firewall, or forwarding. Use the existing
package/copy staging workflow in [demo.py](../scripts/demo.py), but run the commands
below instead of its retained dashboard command. Commands run from the extracted
`udp-router` directory inside the guest. Keep the existing guest compiler selection:

```sh
RUSTC=rustc-1.89 cargo-1.89 build --locked --offline
sudo -n env PYTHONDONTWRITEBYTECODE=1 UDP_ROUTER_ISOLATED_LINUX=YES \
  python3 -B scripts/nat_story.py collect "$PWD/target/debug/udp-router" /tmp/nat-story.json
sudo -n python3 -B scripts/nat_story.py verify /tmp/nat-story.json
```

The coordinator copies only `/tmp/nat-story.json` back to a task-owned host file
(using `limactl copy router-lab:/tmp/nat-story.json /tmp/nat-story.json` with the
existing approved limactl executable). Review the JSON before publishing it.
It contains only fixed fixture payloads, documentation-range external addresses,
private fixture client addresses, tuples, TTLs, bounded packet observations and
final counters. It contains no filenames, process IDs, raw logs or credentials.
Do not package the temporary guest staging directory or raw process logs.
Then on the host, from this checkout:

```sh
python3 -B scripts/serve_story.py /tmp/nat-story.json --port 8766
```

Open `http://127.0.0.1:8766`. The read-only server validates evidence once before
listening and serves that immutable recording, plus three fixed UI assets. It has
no VM bridge, path API, write API, credentials, or external dependencies. Exact
Host/Origin checks and CSP restrict its loopback boundary. Ctrl-C closes it.
The evidence file must be regular, not a symlink, and at most 64 KiB.

Capture continuous rendered browser output at 1440×900 using the existing
Playwright-core and ffmpeg tools; do not install dependencies. The source
recording is 25 FPS VP9 WebM. The published H.264 MP4 is **57.08 seconds**,
1440×900, **1,427 frames**, with no audio tracks or asset metadata. Every source
frame was decoded and re-encoded in order at unchanged 25 FPS—no cuts or time
scaling. The 52-second editorial sequence is surrounded by genuine initial
loading and final completion frames. This is continuous capture of an evidence
replay, not contemporaneous video of packet acquisition.

The existing Playwright expected a different ffmpeg cache revision and VP8.
A task-local executable adapter selected the already-present ffmpeg VP9 encoder;
no package was installed and no installed library/binary was edited. Its source
WebM decoded completely with ffmpeg. The existing Swift/AVFoundation encoder
then produced MP4, which a separate AVAssetReader decoded completely.

Capture interface: wait for `#chapter[data-sequence-state="ready"]`, begin
recording, click `#play`, then wait for
`#chapter[data-sequence-state="complete"]` (allow 60 seconds). The explicit
button starts from chapter 1 every time. There are 13 substages × 4 seconds =
**52 seconds**; completion holds a finished summary without looping. No query
parameter is needed. `data-chapter` (1–4), `data-phase` (1-based), and
`data-direction` expose editorial state, not packet telemetry. Pausing cancels
the timer; pressing Start restarts the whole cycle. Chapter buttons and previous/
next chapter controls select chapters; Step buttons and arrow keys select
substages. Reduced-motion preference disables arrow movement and transitions
while retaining every caption and observation.

The prominent recording/replay disclosure and editorial-timing note stay visible.
Reply arrows point left, client A/B use actual separate observed ports, policy
shows allowed/delivered then policy/dropped, and recovery shows running/stopped/
restarted. Evidence is read without modification; no packets or metrics are
synthesized. All 13 actual browser substages fit 1440×900 without horizontal or vertical
document overflow. Mobile 390×844 uses a stacked scrollable layout without
horizontal overflow. Manual chapter/step controls and actual ArrowLeft navigation
passed. Managed UI and recorded browser page errors were zero. First, middle,
last and key-event decoded frames were visually inspected. Each distinct substage
was reviewed for presentation/privacy.
The controlled-clock JS check validates finite duration, all 13 substages,
completion, restart/pause, and manual reply/port controls:

```sh
node --check story/app.js
node scripts/test_story_timing.cjs
```

The four objective checks are enforced together before output:

1. Kernel socket send, outside server-observed SNAT source, socket reply, and
   actual inside/outside TUN IP packet tuples with TTL 64→63 each direction.
2. Clients 10.0.0.2 and 10.0.0.3 bind the same port 12345, while the server sees
   198.51.100.1 with distinct allocated ports. Both receive their own echo.
3. Allowed .2 delivers; .3 has a more specific inside route and is rejected by
   ingress/egress policy. A socket is bound at .3 to make no-delivery meaningful.
   Exactly one Policy drop, timeout, no outside packet and no server receipt are
   required. This is route-induced policy rejection, not a configurable ACL.
4. Router termination is reaped before an identical-tuple timeout. The server
   and namespaces remain. Restart uses a distinct empty ready log and process
   liveness checks before a successful exchange and reverse packet capture.

AF_PACKET/SOCK_DGRAM is passive: it records actual IP datagrams at the TUN network
devices, never constructs or injects packets. Only known payloads are retained;
non-UDP background traffic is omitted from capture and Protocol counters may
reflect incidental IPv6. Packet-socket direction denotes kernel device outgoing
(client request/server reply) versus incoming (router writes). Verification
requires every expected packet exactly once; unsupported capture behavior fails
closed. Both endpoint addresses on each side reside in one namespace, with
separate bound sockets, rather than separate client machines.

A verifier detects inconsistent/altered evidence, not a malicious author who
fabricates a fully consistent document. JSON is not signed or independently
attested. The no-delivery claims cover bounded observation windows (700 ms
client timeout), not indefinite absence. Endpoint and capture helpers have
35-second lifetime limits, startup is bounded, every setup command has a
4-second deadline, and owned children have TERM→2 s→KILL→2 s cleanup. Only uniquely
named namespaces created by this run are deleted. Private temporary logs are
removed on exit; only verified sanitized output is retained. SIGKILL or VM loss
cannot run cleanup; discard/restart the isolated guest if interrupted that way.
No core dataplane code, host configuration, or original repository is changed.

Portable validation (use a temporary Cargo target directory to preserve the
checkout's existing `target/`):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s scripts -p 'test_*.py'
CARGO_TARGET_DIR=/tmp/udp-router-story-check cargo test --locked --offline
cargo fmt -- --check
CARGO_TARGET_DIR=/tmp/udp-router-story-check cargo clippy --locked --offline --all-targets --features linux-abi-check -- -D warnings
```

The package source/UI/media allowlist is explicit. Only the four reviewed story
assets are included; raw process logs, temporary paths and bulk decoded frames
remain excluded. No license is added.
