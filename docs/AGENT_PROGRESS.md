# Router v2 progress

Branch: feat/router-v2. Main is unchanged; no merge, release, visibility or license change.

## Completed and verified

- Full source/documentation audit and portable baseline: commit5ec52e7.
- Real Linux E2E/kernel comparison and pre-optimization profiling: commit01300cc.
- Profile-selected same-second expiry sweep elimination: implemented, correctness checked and measured; retained for throughput/core/CPU gains.
- Dependency-free reproducible MICRO and actual UDP echo harnesses; controlled packet sizes64/128/512/1400, flows1/64/512, cold/warm batches, three repeats, loss/tuple/TTL controls, CPU/RSS and separate perf/strace evidence.
- 252 retained baseline/after/long/diagnostic experiments: zero payload losses and failed sends. The unchanged kernel baseline was reused after optimization.
- Longer512-flow uninstrumented comparisons: completed echoes/s improved13.89%,15.57%,10.23%,19.76% for64/128/512/1400bytes. Each echo entails two actual router packet traversals; not NIC line rate.
- 64-byte512-flow MICRO whole-core p50:1000ns to625ns. Separate diagnostic median task-clock82.06ms to55.98ms. Approximate sampled RSS unchanged at1835008bytes.
- Important tradeoff:64-byte p99 socket RTT increased1243.6us to1847.8us;512-byte p99 also worsened. This is not a universal latency win. Do not selectively rerun to hide tails.
- Portable/native Linux19 Rust tests,48 Python tests, exact-boundary and16384-operation reference-model checks, original extended real-UDP suites, formatting, strict Clippy/Linux ABI, JS and packaging gates pass.
- Approved guest2vCPU/3GiB/16GiB, no mounts or host-network changes. All benchmark namespaces/helpers removed; VM verified stopped.

## Evidence and reproduction

[Baseline](PERFORMANCE-BASELINE.md), [methodology](BENCHMARK-METHODOLOGY.md),
[optimization proof and results](OPTIMIZATION-RESULTS.md),
[comparison](benchmarks/optimization-comparison.md),
[machine comparison](benchmarks/optimization-comparison.json).
Raw per-repeat results are explicitly allowlisted under docs/benchmarks.
Kernel-veth versus userspace-TUN comparison has different device/NAT paths;
contextual comparison is not an isolated algorithm speedup. RTT is socket RTT,
not one-way forwarding latency. MICRO calls use generated packet layouts.

## Next dependencies and remaining gates

1. Small pluggable packet-I/O boundary preserving reference TUN: buffer ownership, nonblocking receive/transmit, bounded backpressure/drop semantics and shutdown. Approximate engineering effort1–2working days.
2. Multicore design/implementation: per-worker state and collision-free ports, both-direction affinity, bounded queues, shutdown/race testing and actual1/2/4-worker measurements. Approved guest has only2CPUs;4workers must be labeled oversubscribed, not4-core scaling. Approximate effort3–5days, uncertain until ownership design is validated.
3. Extend existing real-state loopback dashboard: per-worker/queue/backend/rate metrics and optional bounded privacy-preserving decision samples; measure overhead. Approximate effort1–2days after ownership settles.
4. Resilience/overload/concurrency/fuzz gates, architecture diagrams/charts, compelling real demo, sanitized feature-branch publication and final review PR. Approximate effort2–3days; no merge without explicit approval.
5. AF_XDP remains conditional and unimplemented/unverified. Investigate safe disposable-interface feasibility, account for Ethernet/L2 and ring ownership; no real-interface attachment, privileged installation or zero-copy claim without authority/evidence.

Estimates express engineering effort, not deadlines or automatic resource approval.
Existing profiling now points to outbound map iteration and syscall cadence as
next candidates; profile and measure before adding complexity.

## Cost and safety

One implementation lane, native Codex Sol primary executor; no Astra, new paid
services, installations or duplicated agents. Subscription headroom was checked;
dollar/token costs are unavailable, not estimated. Benchmarks have explicit job,
exchange, packet-count and retry bounds; no simultaneous performance cells.
Original private development history stays separate and unpublished. Only the
sanitized public ancestry is used. No final PR or full-v2 completion claim yet.
