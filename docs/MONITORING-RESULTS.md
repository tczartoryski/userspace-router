# Monitoring overhead and resilience observations

Actual Ubuntu24.04 ARM64/Rust1.89 release,2vCPU/3GiB,512 warm flows,64-byte IPv4 packets,20000attempts,window64,three repeats. Same binary, fixed off/on/sampled order by worker, not randomized.24 experiments completed without payload loss/failed sends. Four workers oversubscribed; no scaling claim. Reference default retained: earlier multicore15.68–24.69% throughput regressions and worsened p99 remain authoritative.

| Workers | Monitoring | Echoes/s median (range) | vs off | p50/p95/p99 RTT us | CPU s median | Sampled RSS bytes median |
|---:|---|---|---:|---|---:|---:|
|1|off|106277 (106105..108364)|+0.00%|457.1/664.4/768.8|0.05|1966080|
|1|on|107019 (105414..107119)|+0.70%|469.4/667.9/728.0|0.06|2097152|
|2|off|87222 (85298..89450)|+0.00%|592.3/880.0/1040.4|0.10|2097152|
|2|on|86732 (83729..88088)|-0.56%|616.4/948.0/1262.9|0.12|2228224|
|2|sampled|87288 (84681..89578)|+0.08%|608.3/966.9/1622.2|0.12|2228224|
|4|off|83926 (83676..86342)|+0.00%|665.1/1027.2/1446.4|0.13|2097152|
|4|on|84290 (82554..85928)|+0.43%|652.0/1028.9/1263.7|0.13|2228224|
|4|sampled|82182 (81694..85623)|-2.08%|624.8/1056.1/1500.4|0.12|2228224|

Sampling every100processed decisions, capped newest64/worker. On/off rate differences are within run variability: positive differences are not negative cost. Two-worker monitored p99 worsened1040.4us to1262.9us (sampled1622.2us). Four-worker sampled throughput fell2.08% versus off and p99 rose1446.4us to1500.4us. Do not claim monitoring free or universal latency improvement. CPU10ms granularity; sampled RSS, endpoint/scheduler limits.

Short timing cells finish before steady periodic fsync/export: these primarily measure ledgers/sampling, not complete steady-state export overhead. Final snapshot validation is outside active echo timing. The separate paced acceptance below proves periodic export correctness, not isolated steady-state fsync performance. Longer randomized monitoring performance remains a limitation, not silently replaced by these trials.

## Actual adversarial and paced-export acceptance

- Four same-source-port clients reached all four disjoint NAT shards; actual server receipts verify ports40000/40002/40004/40006.
- One shard exhausted while other capacity was free; route policy, wrongremote address/port filtering without refresh, late reply after expiry, reallocation and stopped-router negative control passed. Portable exact-boundary checks remain separate from wall-clock live expiry.
- Bounded overload offered 26304 valid datagrams; 771 verified replies, zero duplicates/send failures. Input full drops=25398, output full drops=135. Loss is intentional overload evidence, not a zero-loss workload.
- 27 paced echoes over 3.297s, 3 distinct periodic live snapshots;0700 parent/0600 regular file, strict schema/privacy/rate fields checked. Graceful shutdown joined workers and final queue/TX conservation passed.
- OS WouldBlock/EOF/hangup/short-write campaign, SIGKILL recovery and separately measured per-worker CPU remain unverified. Portable injections and generated properties are not substituted for OS fault tests.

## Rendered QA

[Desktop](qa/v2-monitoring/desktop.png) and [mobile390px](qa/v2-monitoring/mobile.png) show the **retained actual stopped snapshot**, not live traffic. OFFLINE and unavailable rates are accurate. Browser reported four worker rows,70 redacted events, no horizontal viewport overflow and zero console errors. DOM contract separately covers current/stale/offline and schema1/2; live-browser transition/video capture remains pending. Task-owned local server was intentionally terminated (exit15), listener gone, QA tab closed.

30 native Linux Rust tests passed; portable gates recorded in progress. All namespaces/helpers removed; approved VM verified stopped after measurements. No installs/host-network changes.

## Raw observations

- [router-worker-acceptance.json](benchmarks/monitoring/router-worker-acceptance.json)
- [workers-1-monitoring-off.json](benchmarks/monitoring/workers-1-monitoring-off.json)
- [workers-1-monitoring-on.json](benchmarks/monitoring/workers-1-monitoring-on.json)
- [workers-2-monitoring-off.json](benchmarks/monitoring/workers-2-monitoring-off.json)
- [workers-2-monitoring-on.json](benchmarks/monitoring/workers-2-monitoring-on.json)
- [workers-2-monitoring-sampled.json](benchmarks/monitoring/workers-2-monitoring-sampled.json)
- [workers-4-monitoring-off.json](benchmarks/monitoring/workers-4-monitoring-off.json)
- [workers-4-monitoring-on.json](benchmarks/monitoring/workers-4-monitoring-on.json)
- [workers-4-monitoring-sampled.json](benchmarks/monitoring/workers-4-monitoring-sampled.json)
