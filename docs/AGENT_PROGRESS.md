# Router v2 progress

First bounded milestone: audit and portable MICRO baseline implemented on
`feat/router-v2`. Core and Linux adapter remain unchanged. Baseline feature-branch commit prepared; no push to main.
All tracked UTF-8 source, scripts, UI, SVG, JSON, manifests and documentation
were read; binary media was excluded. Historical evidence retains its original
scope. See [baseline and audit](PERFORMANCE-BASELINE.md).

Sequential dependencies and rough remaining engineering effort (working days,
not deadlines; lab availability and findings can expand them):

| Phase | State / dependency | Remaining effort and acceptance |
|---|---|---|
| Audit + baseline | This milestone complete | Portable tests and bounded release MICRO run; no Linux performance claim |
| Reproducible benchmarking + kernel comparator | Harness implemented; coordinator execution pending | 1–3 days: isolated Linux real UDP/TUN versus equivalent kernel forwarding/SNAT, identical topology/MTU/flows/payload/rate, three repeats, negative controls, loss/latency/CPU/RSS and variability |
| Profile | Software perf/strace attachment implemented; actual guest profiles pending | 1–2 days: coordinator captures existing Linux profiler stacks/counters and syscall mix under both directions and churn; distinguish generator saturation |
| Measured optimization | After profiles | 3–6 days: one justified core change at a time, before/after identical runs, correctness/security regression gates; retain only measured improvements |
| Pluggable TUN I/O | After stable core | 3–5 days: explicit backend interface, existing poll backend, bounded batching/queues and backpressure semantics; real partial-write/EINTR/WouldBlock tests |
| Multicore real reverse NAT affinity | After I/O interface | 5–10 days: real multiqueue ownership, collision-free ports, replies dispatched to owning state, expiry and shutdown correctness under contention; no synthetic affinity claim |
| Actual metrics/privacy bounded sampled decisions | After dataplane ownership | 3–5 days: real delivered/drop/queue metrics, bounded sampling, tuple minimization and explicit opt-in retention; test overload/privacy |
| Resilience | After metrics | 3–5 days: overload, expiry storms, FD failure, stale snapshots, restart and shutdown fault injection, bounded memory and recovery |
| Docs/demo final PR, no merge | After all gates | 2–3 days: reviewed actual Linux comparisons/profiles, genuine demo, reproducible instructions, sanitized explicit packaging, draft/final PR review; no merge |

Current limits: MICRO timings are single-thread core calls on macOS, contain
instrumentation overhead, and exclude kernel/TUN/scheduler/queue effects. Existing
Linux correctness evidence was independently rerun: 17 native tests and both extended real-UDP suites passed; performance remains pending. The approved Ubuntu 24.04 ARM64 lab
(2 vCPU, 3 GiB RAM, 16 GiB disk) remains stopped; coordinator executes guest work
separately. Coordinator started only the existing authorized VM for bounded correctness/profiler probes, then stopped it. No installs or host network changes.
No new paid charges; no dollar-cost figure is available. Account/authentication
identifiers and personal paths are excluded from artifacts.


Linux E2E/profile harness implementation milestone: `scripts/e2e_benchmark.py`
and `scripts/linux-benchmark.sh` add bounded real UDP socket experiments for both
inherited-TUN userspace and namespace-local veth/kernel SNAT, cold/warm batches,
three repeats, loss/sequence/tuple/TTL verification, path controls, actual guest
CPU/RSS sampling, and separate optional software perf/strace diagnostics. See
[methodology and coordinator commands](BENCHMARK-METHODOLOGY.md). Portable tests
cover altered evidence, aggregation, generator flow and scoped partial cleanup.
Generated Linux E2E/profile data is not yet collected or release-allowlisted.
No VM commands, installs or host networking changes were performed. Core and
macOS baseline are unchanged; do not optimize until coordinator measurements.
No commit or push for this phase. Next gate: execute split guest matrix and
profiles, review sanitized results and limitations, then decide optimization scope.

Portable implementation checks: 17 Rust tests, 47 Python tests (37 preserved plus
10 harness tests), strict Clippy including Linux ABI, Rust formatting, JavaScript
syntax/replay checks, shell syntax, package round-trip and diff whitespace checks
pass. These are portable/mocked checks, not real Linux E2E or profiler acceptance.
The package allowlist adds only reviewed harness source/tests/methodology; the
manifest is regenerated. Independently supplied untracked Linux MICRO artifacts
are preserved and are not E2E evidence or newly release-allowlisted here.

Measured coordinator milestone: 144 real E2E experiments (4 sizes x 3 flow counts x 2 backends x 2 cold/warm modes x 3 repeats) passed, plus 3 software-perf and 3 strace diagnostic runs. Zero measured payload losses. Namespaces cleaned and VM stopped. Baseline core unchanged before profiling. Software perf at 999 Hz found expiry retain iterator the largest core hotspot; see docs/benchmarks/e2e-baseline/profile-perf.json. Kernel-veth comparison remains contextual, not identical to TUN. Next: one profile-driven expiry optimization, then same-condition before/after verification.
