# Measured multicore results

**Correctness milestone, not a speedup: keep workers=1 as default.**
Every tested multicore setting regressed throughput and median p99. Four workers oversubscribe the approved two-vCPU guest, plus dispatcher and endpoints. No four-core scaling claim.

Ubuntu24.04 ARM64 Rust1.89 release,2vCPU/3GiB, same binary. Warm512flows,20000echo attempts/window64,three repeats,64/1400 total IPv4 bytes. Fixed1/2/4 order per size, not randomized. Endpoint CPU/scheduling limit inference.

| Bytes | Workers | Echoes/s median (range) | Change | RTT p50/p95/p99 us | CPU s | RSS bytes |
|---:|---:|---|---:|---|---:|---:|
|64|1|101496 (99776..110912)|+0.00%|466.7/764.9/1574.1|0.06|1966080|
|64|2|85585 (82859..85677)|-15.68%|596.7/1100.2/1744.9|0.10|2097152|
|64|4|85175 (80590..86100)|-16.08%|644.4/1101.8/1610.3|0.13|2097152|
|1400|1|83949 (83798..84688)|+0.00%|684.1/897.9/997.0|0.10|1966080|
|1400|2|63219 (60928..64431)|-24.69%|837.9/1271.6/1561.3|0.16|2228224|
|1400|4|64272 (62278..65001)|-23.44%|849.5/1360.1/1874.7|0.17|2359296|

Legacy delivered_pps counts completed echoes, each requiring two traversals. Socket RTT, not forwarding latency. CPU10ms tick granularity; sampled RSS. Original expiry-optimization p99 regressions remain documented.

## Separate999Hz software perf diagnostics

| Workers | Task-clock ms median | Context switches median | Instrumented rate change |
|---:|---:|---:|---:|
|1|56.15|3991|+0.64%|
|2|104.41|12999|+0.13%|
|4|115.94|21670|-2.45%|

Diagnostic variation is not negative overhead. Samples show syscall/wakeup, datagram receive and channel/futex costs replacing part of tuple-scan share. Extra validation/copies/notifications are candidates, not isolated cost attribution. Aggregate process perf includes threads; separate per-worker CPU unmeasured. Hardware counters unsupported.

26 native Linux Rust tests pass. Original extended capacity/port suites and two-worker extended tests pass same-source-port clients, wrongremote-port rejection, expiry/late reply, capacity, policy, reallocation and stopped-router control. Four-worker socket tests prove payload,NAT,TTL,negative control; live adversarial four-worker expiry/filter stress remains pending.

18 uninstrumented +9 diagnostic experiments, zero payload loss/failed sends. Real-thread saturation/panic tests pass; sustained socket overload remains pending. No shared hot NAT lock; bounded channels synchronize internally. Hash skew can strand global capacity. No migration/batching/multiqueue/AF_XDP/zero-copy claim.

Initial extended invocation omitted required overrides and failed exhaustion with default three-entry pool. Correct intended-limit runs subsequently pass; failed log retained locally. Tool syntax failures dispatched no commands.

Namespace/helper cleanup verified; guest stopped. No installs/host-network/resource changes.

## Raw evidence

- [workers-1-perf.json](benchmarks/multicore/workers-1-perf.json)
- [workers-1-size-1400.json](benchmarks/multicore/workers-1-size-1400.json)
- [workers-1-size-64.json](benchmarks/multicore/workers-1-size-64.json)
- [workers-2-perf.json](benchmarks/multicore/workers-2-perf.json)
- [workers-2-size-1400.json](benchmarks/multicore/workers-2-size-1400.json)
- [workers-2-size-64.json](benchmarks/multicore/workers-2-size-64.json)
- [workers-4-perf.json](benchmarks/multicore/workers-4-perf.json)
- [workers-4-size-1400.json](benchmarks/multicore/workers-4-size-1400.json)
- [workers-4-size-64.json](benchmarks/multicore/workers-4-size-64.json)

## Reproduction

Inside the approved guest, use existing Rust1.89 release binary. Each command is bounded and creates only disposable namespace resources.

    sudo env UDP_ROUTER_ISOLATED_LINUX=YES bash scripts/linux-benchmark.sh target/release/udp-router --backend user --mode warm --size 64 --flows 512 --workers 2 --queue-depth 64 --count 20000 --repeats 3 --metadata "Ubuntu24.04 arm64 2vCPU 3GiB Rust1.89 release" --output /tmp/workers2.json

Repeat worker values1/2/4 at sizes64/1400; separate diagnostics add --profile perf. For original extended acceptance, set UDP_ROUTER_EXTENDED=YES and UDP_ROUTER_BIN to the release binary, with UDP_ROUTER_EXTRA_ARGS JSON array containing --max-flows,2,--idle-seconds,3,--route,198.51.100.3/32=inside. The port-limit variant replaces --max-flows,2 with --ports,40000-40001. Two-worker variant uses both limits and --workers,2. Run scripts/linux-integration.sh with the isolated-Linux opt-in. Missing overrides do not exercise the intended fixture.
