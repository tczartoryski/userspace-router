# Measured expiry optimization comparison

Actual isolated Linux observations; three repeats of 20,000 echoes, 512 flows, window64. Before and after used the same Rust1.89 release compiler and 2-vCPU/3GiB guest. The same current harness drove both binaries, alternating before/after job order by packet size.

| Total IPv4 bytes | Before completed echoes/s | After completed echoes/s | Change | Before p50/p95/p99 RTT us | After p50/p95/p99 RTT us |
|---|---:|---:|---:|---|---|
| 64 | 92038 | 104824 | +13.89% | 569.0/758.9/1243.6 | 468.8/668.8/1847.8 |
| 128 | 90659 | 104776 | +15.57% | 586.3/770.1/910.6 | 477.1/682.7/821.1 |
| 512 | 86337 | 95167 | +10.23% | 652.4/851.0/975.0 | 538.0/714.1/1040.5 |
| 1400 | 68249 | 81738 | +19.76% | 890.7/1174.8/1270.5 | 694.0/913.9/1172.6 |

Each completed echo represents two actually forwarded IPv4 packets. The legacy JSON name delivered_pps counts completed replies, not both packet directions. Rates and Mbps are lab observations, not NIC capacity or production claims.

All252 retained baseline/after/long/diagnostic experiments had zero payload losses and zero failed sends. The original kernel comparison was reused rather than rerun after an unchanged kernel path. Raw per-repeat ranges and quantiles are retained.

**Tail tradeoff:** 64-byte p99 increased from1243.6us to1847.8us;512-byte p99 also increased. p50 and throughput improved, but tail latency did not improve universally. Keep this change for measured CPU/core/throughput gains, not as an across-the-board latency win. Do not cherry-pick reruns to hide this result.

64-byte/512-flow core MICRO median p50: warm outbound1000ns to625ns (-37.5%); reverse459ns to125ns. Coarse timer quantization limits these short-call values.

Separate diagnostic perf median task-clock82.06ms to55.98ms (-31.78%); before expiry-retain samples were40–46.25% of observed router CPU samples, afterward outbound-map iteration became the leading visible core candidate. Software sampling is coarse; hardware cycles/instructions unsupported.

64-byte long-run sampled router RSS remained1835008bytes; process CPU median0.08s to0.06s (10ms tick granularity). Native Linux19 tests and both extended actual UDP suites passed. VM and helpers are stopped.

[Machine comparison](optimization-comparison.json) · [Before/after raw long runs](comparison-long/before-64-512.json) · [Full after matrix and diagnostics](e2e-after/e2e-64-512.json)
