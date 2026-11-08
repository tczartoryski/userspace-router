# Packet I/O and multicore ownership design

Implementation contract written before this milestone's code. Linux acceptance and matched measurements are recorded in
[MULTICORE-RESULTS.md](MULTICORE-RESULTS.md): correctness passed, performance regressed. The existing single-worker loop remains
the default reference (`--workers 1`); multicore is opt-in, not a scaling claim.
The existing 64-byte and 512-byte p99 RTT regressions remain acceptance concerns.

## Assignment and capacity

One dispatcher owns both preattached TUN files. Workers own independent Router
instances; no NAT table or hot NAT mutex is shared. A stable hash of the original
inside source IPv4 address and UDP source port assigns outbound traffic. All
remote conversations of that internal socket therefore stay on one worker; the
core still keys mappings by the full endpoint-dependent tuple. Packet payload,
arrival order and worker scheduling cannot change ownership. Hash skew can
exhaust one shard while others have space; there is no migration/fallback that
would split a flow or race reverse state. This is bounded partitioning, not
load balancing or protection against adversarial skew.

For W workers, split the inclusive configured external port pool into contiguous
disjoint ranges: length P/W plus one for the first P%W workers. Split effective
capacity C=min(max_flows,P) the same way, including its remainder. Require W<=C
and W<=P, so every worker gets positive capacity and ports; capacities sum to C
and never exceed each worker's range. Upper port 65535 is handled with wider
arithmetic. A reply's external destination port identifies its sole owner,
independent of the remote tuple, hash or presence of a live mapping. Unowned
ports are sent to worker zero for normal core rejection. Wrong external addresses,
wrong remote address/port and expired mappings must still pass through the
unchanged core policy/filter checks. Assignment never authenticates a reply.
Remote checks occur before refreshing last activity. Different shard ranges
make allocation collisions impossible without a shared allocator.

## Time, buffers and queues

The dispatcher validates packet format/checksum before affinity selection; the
worker repeats the complete existing validation before rewriting. This extra
checksum pass is a measurable cost, not an optimization claim. Truncated and
invalid packets fail closed with counters. The portable I/O boundary accepts
owned IP buffers up to 65535 bytes, reports nonblocking empty/backpressure, and
never reuses a buffer while another owner has it. TUN receive retains a full
65536-byte scratch buffer so oversize/truncation cannot be confused with valid
MTU-sized packets. No zero-copy claim: ingress ownership and core output allocate.

Each worker has one bounded input FIFO and one bounded shared completion FIFO.
All data sends use try_send: full input drops the incoming packet, full completion
drops the forwarding result. Neither side waits for queue space. Bounds are
explicit; there is at most one in-flight input and output per worker beyond
queue capacities, plus one dispatcher packet and receive scratch. No unbounded
packet backlog or per-packet spawned thread exists. FIFO ordering within each
worker preserves packet order. Idle workers
expire using the same process Instant epoch; submitted work must not carry an
older sampled timestamp than a worker idle tick. Workers therefore use the shared
epoch at processing time, including timeout ticks. The queue changes idle-time
semantics from arrival to processing time; overload can delay work, so queues
are bounded and no latency guarantee is made. Core backward-clock behavior
remains unchanged and is directly tested outside the runtime clock adapter.

## Shutdown and I/O

Only the dispatcher performs nonblocking TUN receive/transmit. Output WouldBlock
is an immediate I/O drop, with no retry queue; short TUN writes are fatal, never
continued as a second packet. Interrupted syscalls retry only while running.
Worker completions wake the dispatcher via a nonblocking Unix datagram notifier;
notification saturation is safe because a queued wake already exists and the
dispatcher also polls with a finite timeout. Queue contents, not wake count, are
source of truth. Backend errors and worker failure terminate the run.

Shutdown sets an atomic stop flag and drops input senders. Workers check stop
between bounded packet operations and use timed receives; no stop message must
fit in a full queue. Completions never block, so full queues cannot form a cyclic
wait. Join every worker even after one panics; report failure rather than silently
running fewer shards. Queued inputs/outputs discarded at shutdown are explicit
queue/shutdown drops. Final counters come from actual per-worker state, separate
from dispatcher/queue/I/O drops; forwarded still means a core decision. No shared live tuples or invented dashboard snapshots: multicore schema 2
exports bounded actual worker observations and queue ledgers. Reference schema 1
remains supported. See [observability](OBSERVABILITY.md) for privacy and timing.

AF_XDP is unimplemented: no AF_XDP-specific approved attach/test topology,
L2/neighbor integration, ring/UMEM ownership implementation or measured comparison exists.
No real NIC attachment, installation or zero-copy claim is part of this milestone.

## Implemented limits and reproduction

Runtime workers are bounded to 1..32; the matched guest tooling offers 1/2/4.
Queue depth is 1..1024 with at most 4096 total queued packet slots across all
worker inputs and shared outputs. At the worst accepted packet size, queued
buffers therefore have at most 4096×65535 bytes of payload capacity, plus one
input and one generated output per worker, scratch, dispatcher ownership,
channel metadata, thread stacks and NAT state. Default depth 64 is much smaller.
This is a memory bound, not a claim that allocator overhead or RSS equals it.
Counters publish at most every 250 ms through small per-worker report mutexes;
these contain copies of counters only, never NAT state or per-packet locking.
Final counters are taken after joining workers. Input/queued shutdown drops are
outside core received counters; output drops remain forwarded core decisions.
All queue/shutdown drops are added to the runtime's actual io_drops field.
Workers keep periodic expiry even during rejected traffic. No clock timestamp
is carried across a queue, so idle ticks cannot make a queued timestamp regress.

No baseline or after artifact is regenerated here. In the approved guest only,
build using its existing compiler, then run sequential bounded jobs:

```sh
cargo build --release --locked --offline
for workers in 1 2 4; do
  sudo -n env UDP_ROUTER_ISOLATED_LINUX=YES bash scripts/linux-benchmark.sh \
    target/release/udp-router --backend user --mode warm --size 64 --flows 512 \
    --workers "$workers" --queue-depth 64 --count 1500 --repeats 3 \
    --metadata 'Ubuntu24.04 arm64 2vCPU 3GiB worker comparison' \
    --output "/tmp/router-v2-workers-$workers.json" || exit
done
```

Repeat cells separately for sizes 64/128/512/1400, flows 1/64/512 and cold/warm
with identical count/window/queue/compiler/guest conditions. Four workers are
explicitly oversubscribed on the approved 2-vCPU guest, not four-core scaling.
Reference workers=1 bypasses queues and the pluggable adapter, preserving its
original packet loop; queue-depth is unused and recorded as null for that mode.
Kernel runs record null workers rather than claiming a kernel thread count.

Original tiny-flow/port exhaustion integration suites stay unchanged in reference
mode. Optional `UDP_ROUTER_WORKERS=2` or `4` on `linux-integration.sh` selects the
bounded real-socket worker acceptance job instead: partition-local exhaustion has
different capacity behavior, so old tiny-pool expected counters must not be
silently reinterpreted. The per-shard portable tests cover that ownership model.
The socket harness retains both endpoint TTL/tuple/payload checks, actual final
counters, stop-path control and three repeats. Worker metrics do not fabricate
private snapshots. Native Linux TUN and worker stress/expiry acceptance passed; matched
throughput/CPU/RSS/p99 and aggregate profiles are retained in
[multicore results](MULTICORE-RESULTS.md). Separate per-thread CPU remains unrun.
The known reference optimization's p99 regressions remain prominent; additional
queue/scheduling tails may be worse. Reject or revise based on those measurements.
