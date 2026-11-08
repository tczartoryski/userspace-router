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
| Reproducible benchmarking + kernel comparator | Next; uses this baseline | 2–4 days: isolated Linux real UDP/TUN versus equivalent kernel forwarding/SNAT, identical topology/MTU/flows/payload/rate, three repeats, negative controls, loss/latency/CPU/RSS and variability |
| Profile | After reproducible guest baseline | 1–2 days: coordinator captures existing Linux profiler stacks/counters and syscall mix under both directions and churn; distinguish generator saturation |
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
