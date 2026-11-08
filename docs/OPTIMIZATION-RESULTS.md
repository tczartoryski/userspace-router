# Router v2 expiry optimization — measured acceptance

Status: retained after actual same-condition before/after measurements and correctness gates. Throughput and CPU improve; p99 RTT does not improve universally. No production-capacity claim.
Only the redundant same-second expiry sweep is optimized; NAT lookup, allocation,
packet validation, checksums, routes, capabilities and TUN behavior are unchanged.

## Actual baseline evidence before editing

The coordinator profiled the unchanged baseline core at `01300cc`. The frozen
Linux release binary SHA-256 is
`a115e1bf2b1c9eb87121eeba1342b63389501f46bb24aefc7bdfa4e46197ec0d`.
The measured [software perf artifact](benchmarks/e2e-baseline/profile-perf.json)
contains three actual warm, 512-flow, 64-byte, 20,000-packet diagnostic runs at
999 Hz. BTreeMap ExtractIf retain iterator samples account for 40.00%, 46.25%
and 41.98% in those runs, the leading sampled core hotspot. Router process CPU
was 0.08/0.09/0.09 seconds and task-clock 82.06/81.67/82.27 ms. Approximately
80 samples/run make these coarse percentages, not exact exclusive-time attribution.
The earlier 99-Hz pilot is not substituted for these final profiles.

The coordinator also completed 144 E2E experiments across both paths and
cold/warm modes, all four sizes, 1/64/512 flows and three repeats, with zero
measured payload loss. The [methodology](BENCHMARK-METHODOLOGY.md) preserves
TUN-versus-veth and custom NAT-versus-kernel conntrack caveats.
The [Linux MICRO baseline](benchmarks/baseline-linux.json) contains 49 cases,
three repeats and 512 samples/case: 64-byte warm outbound at 512 flows has
median repeat p50 1000 ns, reverse whole-path 459 ns, and 512-flow expiry call
9083 ns. These are different measurement boundaries; they are not E2E rates or
isolated NAT-lookup timings. Both Linux MICRO files are explicitly allowlisted.

## Change and correctness argument

`Router::expire(now)` still rejects `now < last_time` first. It now returns
success immediately for `now == last_time`, using the existing field. Advancing
time still performs the original full retain and exact expired-counter update.
No extra cache, index or scheduling mechanism is introduced.

Invariant: `last_time` is the greatest accepted expiry time. After a full sweep
at integer second t, every survivor satisfies t − flow.last < idle_seconds.
Without time advancing, that predicate cannot become false. A successful packet
can only insert or refresh a mapping with last = t, whose age is zero; configuration
requires idle_seconds >= 1. Rejected packets never lower or refresh a flow's last
time. Thus no newly eligible expiration can appear at the same t. A failed
backward-time call leaves both clock and table unchanged. Initial last_time = 0
needs no special sweep flag because the table starts empty and any new flow at
zero has age zero. These arguments also hold at u64::MAX without addition or
wraparound. The first call at an advanced second still expires age exactly equal
to idle_seconds, before reverse filtering and before allocating a new mapping.

The adapter already calls expire each loop, and eligible packet processing calls
it again. Both now skip the scan when the supplied integer second is unchanged.
Skipped calls are O(1); advancing-time sweeps remain O(N), with a possible
once-per-second burst. Outbound tuple search remains O(N), reverse map lookup
O(log N), and checksum/copy/route costs remain. Idle periods that skip seconds
still sweep at the next advanced call. There is no throughput guarantee.

## Regression coverage and benchmark boundaries

The added boundary test exercises second zero, repeated outbound/reverse/rejected
remote packets, exact one-second expiry, mapping creation after that second's
sweep, backward calls, and counter conservation. A deterministic dependency-free
reference test performs 4096 operations for each idle bound 1/2/10/u64::MAX,
comparing against a simple fixed-slot model that sweeps on every eligible call.
It mixes creation/reuse/capacity, reverse hits/misses, rejected remotes, corrupt
checksums, explicit expiration, same-time runs, forward/backward time and
saturation, comparing outputs, active count and every counter after each step.
Existing parser/checksum/filter/security tests remain intact.

Harness timestamps were already recorded before receiving, and server collision
checks already used constant-time port ownership. No duplicate fix was applied.
The remaining conditional receive-grace loop now exits immediately on complete
receipt; tests cover both no idle tail on immediate delivery and counting a late
reply after 500 ms without waiting the rest of the optional 50-ms grace. Existing
zero-loss baseline measurement boundaries are unchanged by this completion guard.
`wall_ns` still includes exchange setup/handling and any actual timeout/conditional
collection; it excludes seeding, sorting, calibration and serialization. The
methodology now states that exact boundary and correctly records 999 Hz.

## Measured acceptance

The candidate is retained for measured throughput and CPU improvement, not universal tail-latency improvement. [Complete measured comparison](benchmarks/optimization-comparison.md) and [machine-readable results](benchmarks/optimization-comparison.json) preserve all four longer-run packet-size cases and tradeoffs. All planned before/after and diagnostic runs are complete, with zero payload loss; native Linux correctness passed. The original full kernel baseline is reused unchanged.
