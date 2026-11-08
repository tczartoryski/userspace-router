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

1. Packet-I/O and ownership milestone completed and measured below. Reference remains default because multicore regressed. Further changes need profile-selected justification, not worker-count marketing.
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


## Packet-I/O / ownership milestone (Linux acceptance measured)

Design was written first in [MULTICORE-DESIGN.md](MULTICORE-DESIGN.md). Implemented
an owned nonblocking PacketIo contract and TUN adapter, plus opt-in std-thread
per-worker Router states with disjoint external port ranges/capacity remainders,
internal-socket outbound affinity and reverse external-port ownership. No shared
NAT lock or new dependency. All input/output queues and interrupt retries are
bounded; output notification is nonblocking, saturation drops are counted, and
shutdown joins all workers even after panic. Default workers=1 preserves the
reference loop and snapshots. Multicore --snapshot is explicitly rejected until
actual aggregate/private export exists; live dashboard/decision sampling remains
next-stage work. Worker queue counters are separate from core decisions.

Portable tests cover real worker threads, replies and collision-free ownership,
wrong remote address/port before refresh, exact expiry/backward clocks, partition
remainders including port65535, truncated input, bounded I/O, full queues and panic
shutdown. Guest tools accept workers1/2/4, preserve separate repeat groups and
label4workers oversubscribed on2vCPU. Original tiny-pool reference integration
fixtures remain unchanged; opt-in worker integration uses the real-socket harness.
Linux acceptance and matched1/2/4-worker measurements completed:26 native Rust
tests, original capacity/port extended suites and two-worker extended suite pass.
27 actual experiments have zero payload losses/failed sends. See
[multicore results](MULTICORE-RESULTS.md). Throughput regressed15.68–24.69%
and median p99 worsened: keep reference default. Aggregate process profiling
includes threads; separate per-worker CPU, sustained live overload and four-worker
adversarial expiry stress remain pending. No generated
result, throughput scaling, p99 improvement or full-v2 completion is claimed.
Known64-byte and512-byte p99 regressions remain prominent acceptance concerns.
AF_XDP is conditional/unimplemented with exact blockers in the design. Approved VM used for bounded validation then verified stopped. No installs,
host networking changes, extra agents or releases.

Portable gate for this milestone:26 Rust tests (19 existing plus7 I/O/worker
checks),50 Python tests (48 existing plus2 worker-tooling checks), Rust fmt,
strict Clippy including Linux ABI, JS syntax/replay, shell syntax, package
round-trip/allowlist and whitespace checks pass. Actual Linux results are verified above. The explicit manifest is regenerated;
historical benchmark artifacts are unchanged. Nine audited raw measurement files
are explicitly allowlisted; private raw logs remain outside the repository.


## Verified actual-state observability and resilience

[Contract](OBSERVABILITY.md), [resilience gates](RESILIENCE.md) and
[actual results](MONITORING-RESULTS.md) describe private schema2 snapshots,
per-worker periodic state, bounded queue accounting, actual TUN TX and monotonic
rates. Schema1 remains supported. Sampling is off by default, newest64 per worker,
zero tuples/payloads in schema2. Strict privacy and0700/0600/atomic/loopback guards.

30 native Linux Rust tests pass.58 Python and portable fmt/strict Clippy/Linux ABI,
JS/DOM/shell/package gates pass. Actual four-worker adversarial wrongremote/expiry,
local exhaustion with global free capacity, same-source-port disjoint NAT,
reallocation, policy and stopped-path controls pass.26304overload datagrams yielded
771verified replies,25398input-full and135output-full drops: deliberate overload
loss.27paced echoes over3.297s generated3periodic live snapshots; monitored final
queue/TX conservation and clean joins pass. Backend errors suppress clean final
snapshots, tested separately by portable injection.

24monitoring off/on/sampled experiments completed without payload loss. Two-worker
p99 worsened1040.4us to1262.9us (sampled1622.2us). Four-worker sampled rate fell2.08%
with worsened p99. Full ranges retained; no free monitoring claim. Short timing
cells do not isolate steady fsync cost; paced acceptance is not a timing substitute.
Earlier multicore15.68–24.69% regressions remain prominent; reference1default retained.

Rendered retained actual stopped snapshot checked at desktop1440px/mobile390px:
4workers,70redacted decisions, OFFLINE/unavailable rates, no overflow/console errors.
Not live traffic footage. Guest acceptance separately validates periodic live writes.

Namespaces/helpers cleaned; VM verified stopped. Task-owned QA server intentionally
SIGTERM terminated (exit15), listener gone and QA tab closed. Only audited aggregate,
fixture-network evidence and screenshots packaged. No installs/host networking,
resource/provider/cost/merge/license/release changes.

## Remaining final-review gates

- Live dashboard current/stale/offline browser transitions, compelling v2 demo,
  architecture/performance charts and final presentation/README polish.
- Wider OS fault campaign (WouldBlock/EOF/hangup/shortwrite, monitored worker panic,
  SIGKILL recovery) not established by portable injections. Explicitly unverified.
- Longer randomized steady monitoring/fsync timing and separate per-worker CPU
  remain limitations; no hardware counters or universal multicore speedup.
- AF_XDP conditional/unimplemented: L2 semantics, attach authority, UMEM/ring
  ownership and actual acceptance/measurement missing.
- Final sanitized review PR; no merge or main changes.
