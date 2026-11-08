# Router v2 Linux E2E methodology

This phase implements a bounded real UDP harness and optional software profiling.
The coordinator subsequently completed 144 baseline E2E experiments and three
runs each of software perf and strace, with zero measured payload loss, before
core edits. The [optimization record](OPTIMIZATION-RESULTS.md) identifies that
baseline and retained after measurements. The Linux adapter, old tests
and existing macOS/Linux MICRO baseline artifacts remain unchanged. The earlier
`process` MICRO timings cover the entire public forwarding path, not pure NAT
lookup. No optimization is authorized by source rationale alone.

## Guest commands and bounded matrix

Use only the already approved disposable Ubuntu ARM64 guest with its existing
Rust, Python, iproute2, iptables, perf and strace. The coordinator starts/copies to
that guest separately; these scripts never manage a VM or install anything.
Build with the guest's existing compiler selection (use its versioned Cargo and
RUSTC names if needed), recording the actual compiler in generic metadata:

```sh
cargo build --release --locked --offline
sudo -n env UDP_ROUTER_ISOLATED_LINUX=YES bash scripts/linux-benchmark.sh \
  target/release/udp-router --size 64 --flows 64 --count 1500 --window 64 \
  --repeats 3 --metadata 'Ubuntu 24.04 arm64 2 vCPU 3 GiB existing release compiler' \
  --output /tmp/router-v2-e2e-64-64.json
```

One job runs a single size/flow cell, both backends, cold and warm, three repeats
(12 experiments). Repeat backend order alternates; mode order stays cold then
warm. Each experiment uses newly created namespaces and a fresh router/conntrack
state. Each job admits work for at most 120 seconds, reserving up to 60 seconds
for in-flight readiness/profiler completion and bounded cleanup. A generator
exchange has an 8-second deadline. Setup commands have at most 4 seconds, startup
waits at most 4–5 seconds, TERM/reap at most 2 seconds then KILL/reap at most 2.
If any bound or validation fails, the job fails without emitting success results.
Do not treat missing output as a measurement. No automatic retries or best-run
selection. Split the full matrix into independent bounded jobs:

```sh
for size in 64 128 512 1400; do
  for flows in 1 64 512; do
    sudo -n env UDP_ROUTER_ISOLATED_LINUX=YES bash scripts/linux-benchmark.sh \
      target/release/udp-router --size "$size" --flows "$flows" --count 1500 \
      --window 64 --repeats 3 \
      --metadata 'Ubuntu 24.04 arm64 2 vCPU 3 GiB existing release compiler' \
      --output "/tmp/router-v2-e2e-$size-$flows.json" || exit
  done
done
```

Keep the VM limits fixed; do not run cells concurrently on the 2-vCPU guest.
Counts are configurable up to 20000 for headline runs (default 1500), flows
1..512 and count at least flows; window is 64 or 128, repeats 3..5. Use the same
count/window/compiler/metadata for comparisons. `--backend user|kernel` and
`--mode cold|warm` can split a job further. Results include every repeat and
median/min/max/sample CV, never just the fastest. JSON and Markdown are written
only after all experiments pass. Generated guest data requires separate review
and explicit release allowlisting; no results directory sweep is included.

## Paths, endpoints and controls

All setup is gated by `UDP_ROUTER_ISOLATED_LINUX=YES`, Linux and root, including
helper entry points. All privileged Python children run with `-B`. Random unique
namespace names are registered as owned only after successful creation. Signals
cause cleanup of owned children and successfully created namespaces; repeated
signals are ignored during bounded cleanup. A failed setup also cleans its
partial ownership list. SIGKILL/guest loss cannot run cleanup: discard/restart
the disposable guest rather than deleting unrelated namespaces.

Userspace path: client 10.0.0.2/32 → tun-in → actual release router via inherited
TUN FDs → tun-out → server 198.51.100.2/32 UDP 9000, then reverse. The existing
`traffic.launch` sets namespaces/attaches FDs and execs the actual router; it
never forwards packets. Router PID remains the launcher PID. Capability dropping
and adapter checks remain intact. Namespace forwarding stays disabled. Fresh
router readiness requires the actual ready line and process liveness. Configuration
overrides the tiny correctness-test limits: 40000–49999 ports, max flows equal
to selected flows, idle expiry 120 seconds, MTU 1500, existing /24 lab routes.
No warm mapping can expire during an 8-second measurement.

Kernel path: the same client/server addresses, socket source ports 12000+flow,
server port, payloads, TTL 64, sizes, MTU 1500, count and outstanding window use
two veth pairs and an intermediate router namespace with addresses 10.0.0.1/24
and 198.51.100.1/24. Veth creation occurs *inside* owned namespaces; there is no
transient host interface. Explicit client/server routes lead through that
namespace. Only its `ip_forward` is enabled; only its iptables POSTROUTING rule
SNATs fixture UDP into 198.51.100.1:40000–49999. Reverse conntrack provides replies.
All sysctls and iptables commands run inside owned namespaces; no host route,
firewall, forwarding or persistent configuration is changed.

These are contextual system paths, not an isolated algorithm comparison. Kernel
veth/L2/neighbor/softirq/offload/conntrack behavior differs from userspace TUN
read/poll/write, process scheduling and custom endpoint-dependent filtering.
Both decrement IPv4 TTL once, but their NAT policy and unsupported-packet
semantics are not equivalent. No custom-dataplane restructuring hides these
differences. Cold kernel ARP/neighbor work is part of its observed path; warm
seeding normally resolves it. There is no hardware NIC measurement.

Each experiment verifies no delivery after stopping/reaping the userspace router
or disabling forwarding in the owned kernel router namespace, while keeping the
server and endpoint topology alive. The control sends a distinct-stage UDP packet
on the same tuple and observes for 300 ms; output distinguishes timeout from a
kernel ICMP rejection. It never labels an error as a received echo. Bounded
no-delivery is a path control, not proof of indefinite absence.

## Measurement boundaries and accounting

Packets are real kernel UDP socket datagrams, never raw generated IP. Total IPv4
sizes 64/128/512/1400 mean UDP payloads 36/100/484/1372 (20-byte IPv4 + 8-byte UDP
headers). Payload includes magic, stage, flow, sequence and exact deterministic
body bytes. Both socket endpoints validate complete payload bytes, flow/sequence,
source tuple, untruncated recvmsg ancillary data and actual TTL **63**. Kernel
UDP checksum acceptance plus exact payload validation and the unchanged core
checksum checks guard correctness; this is not an independent raw checksum
capture. Wire corruption discarded by the kernel appears as loss, not a fabricated
checksum-error attribution. Server validates a stable distinct external SNAT port
per observed flow and publishes the distinct count, without retaining tuples.

Cold means newly created router/namespace/NAT state at the start of the batch;
subsequent packets reuse mappings as usual. It does **not** mean every packet is
a new allocation. Warm seeds every selected flow, requires its correct echo,
then starts measurement on the same sockets and mappings. Seeding happens outside
the interval and has its own validated server count. Seed sequence space is
separate from measured sequence space.

The nonblocking generator sends each offered sequence once, allows at most the
configured outstanding window, and waits via selectors. A send WouldBlock counts
as send_failed. Each pending request times out after 500 ms without retry. Late
valid replies within the final observation grace still count. An up-to-50-ms final
receive grace observes duplicates/late packets; it is **included** in elapsed
wall and rate denominator, so this is a finite-batch delivered rate, not a
saturation/capacity claim. The grace starts only when replies are missing and
stops as soon as all unique replies have arrived; complete batches have no
forced idle tail. `wall_ns` is the monotonic interval from exchange entry,
before payload preparation/first send, through completion of the pending-request
loop and any conditional late collection. It includes Python payload work,
selector handling and timeout checks, but excludes warm seeding, subsequent
RTT sorting/JSON writing and clock calibration. PPS uses precisely this same
window and counts any valid late replies collected within it. It is not a
first-send-to-last-recv-only or rate-adjusted duration. Small lossy batches can
be dominated by timeout/grace and Python work. The bounded drain handles at most 128 packets per readiness
pass; it cannot spin indefinitely.

RTT is monotonic_ns immediately before sendto through immediately after recvmsg
returns, including kernel, scheduling, echo and application effects. It is socket
round-trip latency, never per-hop or one-way. Nearest-rank p50/p95/p99 use all
unique delivered replies; sample count is explicit. 512 empty timestamp pairs
calibrate clock overhead separately without subtraction. Out-of-order means a
unique sequence below the largest previously observed sequence, globally across
flows; cross-flow reordering can be normal. Duplicate traffic fails the current
acceptance gate and its counts remain available in private endpoint evidence.

Independent client/server sequence sets must agree before summaries are emitted:
received ⊆ server_seen ⊆ sent, attempted = sent + send_failed, and
sent = received + dropped. Derived client_to_server_loss and echo_or_reply_loss
split observed loss without attributing a specific device cause. Wrong bytes,
TTL, source, port collision, impossible sequence sets, counts or RTTs fail closed.
Server errors cause failure even if some echoes succeeded. Successful results
record actual attempted/sent/received/dropped, duplicate and reorder counts,
server_seen and distinct NAT ports. Delivered PPS is unique echoed requests per
elapsed second; IP Mbps uses one delivered datagram's total IP bytes and UDP
application goodput uses payload bytes. Neither counts the request and echo twice
or includes L2 overhead.

Userspace final router counters are parsed from the actual fresh process log;
conservation and bounded state/expiry are checked against endpoint evidence.
Unexpected core drops fail; incidental Protocol drops are allowed and retained.
I/O drops remain actual separate counters and may explain some loss; core
forwarded counts decisions, not delivery. Counts include warm seeds when warm.
Kernel mode has no router-process counters or assignable process CPU: those
fields are null, not inferred from a fabricated process.

Generator CPU is process_time_ns over its exchange (user+system CPU). Receiver
and userspace-router CPU use /proc/PID/stat utime+stime delta divided by actual
CLK_TCK. Their denominator is the outer go-to-generator-exit monitor interval,
which includes small synchronization/result-writing overhead. CPU fractions use
1.0 for one fully occupied CPU, can exceed 1.0 for multithreaded future backends,
and are not normalized to two guest CPUs. Short runs can quantize to zero ticks.
Router RSS is sampled before go and every 20 ms, reported in bytes via actual
page size: it is not a lifetime high-water mark and can miss short peaks.

Guest /proc/stat first eight aggregate counters provide total and idle+iowait
deltas over that same monitor interval. Busy seconds exclude idle/iowait, total
seconds sum CPU time across guest CPUs, and busy_fraction is busy/total. This
includes generator, server, profiler, orchestrator, kernel work and unrelated guest
activity; it cannot isolate kernel forwarding CPU. CPU and RSS are actual guest
samples, with process labels and units, not extrapolated from wall time.

## Profiling before optimization

Profile runs are separate jobs marked PROFILE-DIAGNOSTIC; never compare their
rates with uninstrumented headline runs. Up to 20,000 packets per experiment are
allowed for useful sampling, still under generator/job deadlines. Warm 512-flow
64-byte and 1400-byte jobs expose flow-table and payload scaling. Examples:

```sh
sudo -n env UDP_ROUTER_ISOLATED_LINUX=YES bash scripts/linux-benchmark.sh \
  target/release/udp-router --backend user --mode warm --size 64 --flows 512 \
  --count 20000 --repeats 3 --profile perf \
  --metadata 'Ubuntu 24.04 arm64 2 vCPU 3 GiB existing release compiler' \
  --output /tmp/router-v2-profile-perf.json
sudo -n env UDP_ROUTER_ISOLATED_LINUX=YES bash scripts/linux-benchmark.sh \
  target/release/udp-router --backend user --mode warm --size 64 --flows 512 \
  --count 20000 --repeats 3 --profile strace \
  --metadata 'Ubuntu 24.04 arm64 2 vCPU 3 GiB existing release compiler' \
  --output /tmp/router-v2-profile-strace.json
```

Perf attaches to the actual forwarding PID after warm seeds: software cpu-clock
record at 999 Hz with callchains and separate task-clock/context-switch/page-fault
stat. No unsupported hardware cycles/instructions are requested. Strace -f -c
attaches to that same process including its threads. Attachment liveness is checked before go; profiler
SIGINT completion is bounded before router shutdown. Raw profiler data, process
logs and per-sequence evidence live only in private temporary directories outside
the checkout and are removed during cleanup. Selected outputs retain bounded
symbol percentages/software events or numeric syscall aggregate rows, excluding
raw paths/PIDs. Empty/unsupported profiler results fail; increase a bounded packet
count or choose a better workload separately, never invent samples. Missing
callchains/symbols and sampling overhead remain limitations; the release build
has its normal symbol/debug configuration, unchanged by the harness.

Source-derived candidates remain tuple scans, expiry retain, checksums, output
allocation/copy, route scans and poll/read/write cadence. Coordinator software
stacks, syscall counts and actual CPU/RSS/loss measurements must rank them before
any core edit. Compare generator/receiver CPU and workload ceilings first: on a
2-vCPU guest the Python endpoint workload may be the bottleneck. Preserve actual
before/after conditions, variability and security/correctness gates. No speedup,
production capacity, hardware-counter result or real guest profile is claimed by
this implementation phase.

For less timer-quantized process CPU and targeted stability checks, --count 20000 is also accepted without profiling, under the same 140-second job and 8-second exchange deadlines. Defaults remain 1500; compare identical counts/windows and compiler settings. Longer batches are still workload-limited, not maximum capacity.

Rate naming: legacy delivered_pps counts completed echo replies per second. Every validated echo entails two actual router packet traversals, but this field is not their sum. Report completed echoes/s or explicitly derive bidirectional packet processing from verified counters; do not present it as NIC line rate.


## Opt-in worker ownership milestone

The [multicore design](MULTICORE-DESIGN.md) defines the new owned packet-I/O
boundary, per-worker NAT ranges/capacities, bounded queues and shutdown limits.
`--workers 1` retains the original reference loop; `--workers 2` or `4` selects
actual independent worker states behind one dispatcher. `--queue-depth 64` is
the default; all packet channels are bounded and nonblocking on send. Results
record actual requested worker/queue configuration and keep repeat groups separate.
Four workers oversubscribe the approved 2-vCPU guest. [Actual multicore results](MULTICORE-RESULTS.md) report throughput and p99
regressions. Run matched cells and examine p99, losses, CPU and RSS, not
only PPS; existing 64-byte and 512-byte p99 regressions remain unresolved.
Parallel snapshots are implemented; see [observability](OBSERVABILITY.md) and
[measured monitoring results](MONITORING-RESULTS.md). AF_XDP remains unimplemented.
