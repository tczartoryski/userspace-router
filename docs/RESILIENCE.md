# Resilience gates and limits

This milestone adds portable checks and coordinator-verified Linux evidence in [actual results](MONITORING-RESULTS.md).
Keep reference workers=1 default: measured multicore throughput and p99 regressed.
[Measured results](MULTICORE-RESULTS.md) remain authoritative and unchanged.

Implemented gates retain capability dropping, attach-only TUN, full validation,
exact wrong-remote filtering before refresh, monotonic expiry and disjoint shard
ownership. The existing exact-boundary/reference-model tests, thread panic
cleanup, saturated input/output queues and bounded writes remain in place.
Additional deterministic generated tests exercise 16,384 affinity assignments,
remote changes, reverse port ownership and malformed pre-worker ingress without
state growth. Real-thread tests export actual state and check queue conservation,
shutdown completion, event-ring bounds and no tuple/payload serialization. A Rust
worker snapshot fixture is accepted by the Python schema validator; it is a
portable test artifact outside the checkout, not live TUN evidence.

Validators reject missing/unknown/private fields, impossible port/capacity or
queue values, report timestamps ahead of capture, incomplete final reports,
nonfinite rates, invented events, and payload/tuple injection into samples. The
controlled DOM test covers schema 1/2, queue meters, stale-rate suppression and
offline clearing, not actual browser rendering. Private regular-file reads are
nonblocking to avoid FIFO stalls; original HTTP origin/path/size guards remain.

Coordinator gates now passed: native Linux schema/privacy/conservation, short
monitoring comparisons and paced periodic export, dedicated four-worker filtering,
expiry/capacity and deliberate queue overload. See [actual results](MONITORING-RESULTS.md).

Still unverified: randomized steady fsync performance, separate per-worker CPU,
live-browser transition capture and broader OS failures (WouldBlock/EOF/hangup/
short-write, monitored panic/process interruption). Portable injections are distinct.

Queues/memory remain bounded, but scheduler pauses, shard skew and packet copies
can increase latency or strand capacity. Shutdown discards queued work explicitly;
it does not promise delivery/drain. SIGKILL/guest loss cannot clean namespaces or
write final telemetry; discard/restart the disposable guest under coordinator
control, never remove unrelated resources. No VM operations occur in these tests.

AF_XDP remains unimplemented: AF_XDP-specific attach/test authority, Ethernet/L2
integration, UMEM/ring lifetime/ownership, wakeup/backpressure and measured real
packet acceptance are missing. No real-NIC attachment, install, zero-copy or
scaling claim. No further dataplane optimization is justified by these new
observability contracts alone.


## Dedicated four-worker acceptance (guest run passed)

`worker_acceptance.py` uses the existing isolated-Linux/root gate, inherited TUN
launcher and owned Lab namespace cleanup. All Python children use-B; SIGINT/TERM
trigger bounded reaping/deletion, with repeated signals ignored during cleanup.
No installs, VM actions or host networking are performed. Setup uses a25-second
job admission budget,18-second server lifetime and15-second client watchdog;
the intended socket workload is below20seconds, plus bounded setup/cleanup.

Fixed4workers,8ports,4total mapping slots gives one slot and two ports per shard.
Clients bind the same source port on separate fixture inside IPs selected by the
specified affinity hash. The harness asserts actual getsockname bindings and
server-observed external ports in all four disjoint ranges; a wrong owner/collision
fails. It first fills only shard0 and proves its second client times out while
other shards have not received requests, then successfully exercises those shards.
Policy uses the existing more-specific inside route. Wrong remote address and
port datagrams are sent separately at bounded intervals, followed by a valid
original-remote reply beyond the two-second idle limit. No wrong/late reply may
arrive, actual Filter/expiry counters must account for attacks, and a previously
rejected same-owner client must subsequently reallocate successfully. This is
not a claim about an exact wall-clock expiry boundary.

A separate1.2-second bounded burst phase (at most32768offered sequences) validates
every received overload echo/TTL/tuple, independent server receipts and actual
router full-queue drops with queue depth1. If no router queue drop is observed,
the overload gate fails rather than claiming overload from offered rate alone.
This is deliberately bursty acceptance, not maximum forwarding capacity. A paced
phase then checks steady snapshots and clean SIGTERM; stopping the router must
break an otherwise identical socket path while the server remains alive.

Pure tests cover hash fixture coverage, payload bounds, altered/incorrect receipts,
strict gate and partial-setup cleanup. Live monitored adversarial correctness, queue overload and steady export PASSED
coordinator acceptance; one run does not prove universal overload reproducibility. A failed gate yields no success artifact. FD EOF/short-write and
monitored worker panic campaigns remain deferred; original portable injections
cover selected paths. Four workers still oversubscribe2vCPU and retain measured
throughput/p99 regressions; reference1 remains default.
