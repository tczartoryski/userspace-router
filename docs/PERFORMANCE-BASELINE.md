# Router v2 audit and portable baseline

Subsequent target-Linux E2E/profile and measured optimization results are now recorded in [optimization results](OPTIMIZATION-RESULTS.md). This document preserves the initial portable baseline and source audit.

November 7, 2026: source audit plus actual local release MICRO execution. Core
`src/lib.rs`, `src/linux.rs`, existing tests and historical video/evidence claims
are unchanged. This is not Linux profiling or an end-to-end throughput result.

Source-derived audit findings (N = active flows, R = routes): external-port
BTreeMap lookup is O(log N); outbound endpoint-dependent tuple search is O(N).
`expire` retains the entire map, O(N), on each otherwise eligible packet and
also each adapter loop. Port allocation probes at most the configured pool
with tree membership checks. Parser validates IPv4 and UDP checksums over the
payload; rewrite recomputes them and `bytes.to_vec()` allocates/copies each
successful output. Route lookup scans at most 128 entries, O(R); address policy
also scans routes. These are reasons to profile, not measured hotspot attribution.

The Linux adapter owns one 64 KiB stack receive buffer, polls two FDs, reads
one packet per ready FD, then writes the owned Vec. Nonblocking WouldBlock
increments `io_drops` immediately; no queue exists. One thread owns all state.
Periodic snapshots serialize bounded private state, create a 0600 temporary
file, fsync it, then rename atomically inside a checked private parent. Mapping
output truncates explicitly at 2048 and snapshots cap at 1 MiB; parent directory
fsync is not performed. Core forwarding counters describe decisions, not delivery.
Existing exact remote filtering, checksum/policy validation, monotonic time,
capability drop, attach-only TUN and localhost HTTP guards remain intact.

Audit covered every tracked text/code/doc, including package/verifier lifecycle,
UI/replay code, SVG, JSON evidence and manifest. Binary media was not re-audited.
The historical namespace harness verifies correctness, but supplies neither a
rate-controlled performance experiment nor equivalent kernel comparator.

Environment: Apple M4, 10 logical CPUs, 16 GiB, macOS 27.0.1 / Darwin 27 ARM64
(hardware/OS supplied by coordinator); actual PATH compiler reports Rust 1.99.0
(b940084d7, 2026-09-28). Cargo release default optimization, zero dependencies,
offline/locked build. No CPU affinity or frequency control. Background scheduling
and thermal effects remain uncontrolled. Independent coordinator reran the unchanged baseline in the approved Ubuntu 24.04 ARM64 lab: Linux 6.8.0-147-generic, Rust 1.89.0, 2 vCPU, 3 GiB RAM. Native tests: 17 passed. Both extended real-UDP suites passed via bash scripts/guest-demo.sh with zero exit status; test namespaces removed and VM stopped. Software perf task-clock/cpu-clock are available; hardware cycles/instructions unsupported. No host network or profiler-security configuration changed. See [Linux correctness evidence](benchmarks/linux-integration-baseline.json). End-to-end performance and hotspot attribution remain pending.

Reproduce from checkout root with existing PATH tools:

```sh
cargo build --release --example core_bench --locked --offline
python3 -B scripts/benchmark.py target/release/examples/core_bench --count 512 --repeats 3 --metadata 'Apple M4 10 logical CPUs 16 GiB macOS 27.0.1 Darwin 27 arm64 Rust 1.99.0' --output docs/benchmarks/baseline-macos.json
cargo test --locked --offline
python3 -B -m unittest discover -s scripts -p 'test_*.py'
cargo fmt -- --check
cargo clippy --locked --offline --all-targets --features linux-abi-check -- -D warnings
node scripts/test_story_timing.cjs
```

[Machine results](benchmarks/baseline-macos.json) and [actual summary](benchmarks/baseline-macos.md)
contain three independent process repeats, all four total IPv4 sizes
64/128/512/1400, and 1/64/512 flows. Generated packets have real IPv4/UDP layouts,
nonzero validated checksums and fixed payload bytes; they are synthetic MICRO
inputs, never evidence of real traffic. Each warm case seeds all flows outside
timing, cycles tuples, and retains mappings at monotonic time zero. Cold allocation
seeds N−1 flows then times the final new mapping. Expiry seeds N flows and times
one `expire(60)` deleting the full table; its unit is an expiry call, not a packet.
Setup is excluded from each operation but included in case wall time. Warm/reverse
labels time the whole public `process` path, including per-packet expiry,
validation, rewrite, allocation and output destruction, not isolated lookups.

Each record reports actual sample count, nearest-rank p50/p95/p99 in nanoseconds,
sum of observed latencies and case wall elapsed time. `Instant`/black_box empty
calibration is a separate record, not subtracted. Samples are individual calls;
tails at 512 samples have limited resolution. Raw individual samples are not
retained; per-repeat summaries and across-repeat p50 min/max/CV are retained.
CPU time has no portable std API and is explicitly null, not inferred from wall.
RSS is explicitly coordinator sampled and uncollected here. No allocation counts,
NIC rates, syscall timing or Linux speedups are claimed.

Executable accepts samples 1..2000 and optionally flows 1..1000 (within its
10,000-port pool); runner accepts the fixed full matrix and 3..10 repeats with
a total 90-second subprocess budget. Defaults are deliberately small; the executable also checks a 90-second budget
between operations. No automatic setup, install, privileged command or
network change. Metadata is supplied generic text, never discovered personal paths.
Runner validates schema, exact case coverage, finite bounded integer metrics,
percentile ordering and sample counts before writing results; pure unit tests
exercise invalid metrics and aggregation. Results are explicitly allowlisted;
packaging rebuilds the manifest. The checked-in manifest is regenerated for this milestone.

Next profiling phase: coordinator first builds an equivalent real kernel
forwarding/SNAT experiment with identical endpoint workload and loss accounting.
Collect three repeats, packet/s and delivered bytes/s, latency distributions,
process CPU and sampled RSS, generator load and guest limits. Profile release
router stacks and syscall mix under warm outbound, replies, high-flow churn and
expiry storms. Source-derived candidates are tuple scans, retain, checksums,
copy/allocation, repeated route scans, poll/read/write cadence and snapshot fsync.
Only measured samples/stacks can rank them; preserve before/after artifacts and
all correctness/security tests before changing the baseline core.

Local verification: 17 Rust tests and 37 Python tests pass (35 preserved plus two
benchmark tests), formatting and strict Clippy with Linux ABI checks pass, and
the controlled-clock JavaScript replay test passes. Package extraction/repackaging
preserves the explicit allowlist and manifest. The Codex coding executor did not run Linux tests; the independent coordinator did, as recorded above.

Observed examples from the retained run: 64-byte warm outbound median of repeat
p50s is 83 ns at one flow and 959 ns at 512 flows; at 1400 bytes/512 flows it is
2041 ns. These whole-call observations do not isolate the cause. Early 64-byte
cases have high repeat variability (up to 0.790 CV for cold allocation), and
clock quantization yields zero p50 for several tiny expiry/calibration cases.
Zero means below this measurement's resolution, not zero execution cost. Avoid
interpreting these short-call values as precise speedup or packet-rate claims.
