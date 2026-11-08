# Actual portable MICRO baseline

Apple M4 10 logical CPUs 16 GiB macOS 27.0.1 Darwin 27 arm64 Rust 1.99.0

3 repeats; 512 operations per case per repeat. Median of repeat p50s; CV uses repeat p50s.
CPU unmeasured. RSS reserved for coordinator sampling. No Linux/TUN/E2E measurement.

| Case | IPv4 bytes | Flows | Median p50 ns | Min–max p50 ns | CV |
|---|---:|---:|---:|---:|---:|
| cold_allocation | 64 | 1 | 83 | 83–292 | 0.790 |
| cold_allocation | 64 | 64 | 292 | 292–750 | 0.595 |
| cold_allocation | 64 | 512 | 1542 | 1542–1542 | 0.000 |
| cold_allocation | 128 | 1 | 125 | 125–125 | 0.000 |
| cold_allocation | 128 | 64 | 333 | 333–334 | 0.002 |
| cold_allocation | 128 | 512 | 1584 | 1584–1584 | 0.000 |
| cold_allocation | 512 | 1 | 458 | 458–458 | 0.000 |
| cold_allocation | 512 | 64 | 667 | 667–667 | 0.000 |
| cold_allocation | 512 | 512 | 1958 | 1917–1958 | 0.012 |
| cold_allocation | 1400 | 1 | 1166 | 1125–1166 | 0.021 |
| cold_allocation | 1400 | 64 | 1333 | 1291–1375 | 0.032 |
| cold_allocation | 1400 | 512 | 2625 | 2583–2625 | 0.009 |
| expiry | 64 | 1 | 41 | 0–83 | 1.004 |
| expiry | 64 | 64 | 1042 | 1042–2000 | 0.406 |
| expiry | 64 | 512 | 8625 | 8583–8750 | 0.010 |
| expiry | 128 | 1 | 0 | 0–0 | 0.000 |
| expiry | 128 | 64 | 1042 | 1042–1083 | 0.022 |
| expiry | 128 | 512 | 8666 | 8625–8750 | 0.007 |
| expiry | 512 | 1 | 0 | 0–0 | 0.000 |
| expiry | 512 | 64 | 1042 | 1041–1042 | 0.001 |
| expiry | 512 | 512 | 8625 | 8583–8708 | 0.007 |
| expiry | 1400 | 1 | 0 | 0–0 | 0.000 |
| expiry | 1400 | 64 | 1042 | 1041–1083 | 0.023 |
| expiry | 1400 | 512 | 8584 | 8500–8667 | 0.010 |
| reverse_lookup | 64 | 1 | 83 | 83–250 | 0.695 |
| reverse_lookup | 64 | 64 | 125 | 125–291 | 0.531 |
| reverse_lookup | 64 | 512 | 458 | 458–458 | 0.000 |
| reverse_lookup | 128 | 1 | 125 | 125–125 | 0.000 |
| reverse_lookup | 128 | 64 | 167 | 166–167 | 0.003 |
| reverse_lookup | 128 | 512 | 500 | 458–500 | 0.050 |
| reverse_lookup | 512 | 1 | 417 | 417–417 | 0.000 |
| reverse_lookup | 512 | 64 | 500 | 458–500 | 0.050 |
| reverse_lookup | 512 | 512 | 833 | 833–833 | 0.000 |
| reverse_lookup | 1400 | 1 | 1125 | 1083–1125 | 0.022 |
| reverse_lookup | 1400 | 64 | 1167 | 1042–1167 | 0.064 |
| reverse_lookup | 1400 | 512 | 1500 | 1458–1500 | 0.016 |
| timestamp | 0 | 0 | 0 | 0–41 | 1.732 |
| warm_outbound | 64 | 1 | 83 | 83–250 | 0.695 |
| warm_outbound | 64 | 64 | 208 | 167–417 | 0.508 |
| warm_outbound | 64 | 512 | 959 | 959–959 | 0.000 |
| warm_outbound | 128 | 1 | 125 | 125–125 | 0.000 |
| warm_outbound | 128 | 64 | 209 | 209–250 | 0.106 |
| warm_outbound | 128 | 512 | 1000 | 916–1000 | 0.050 |
| warm_outbound | 512 | 1 | 417 | 417–417 | 0.000 |
| warm_outbound | 512 | 64 | 542 | 542–542 | 0.000 |
| warm_outbound | 512 | 512 | 1334 | 1291–1334 | 0.019 |
| warm_outbound | 1400 | 1 | 1125 | 1083–1125 | 0.022 |
| warm_outbound | 1400 | 64 | 1250 | 1125–1250 | 0.060 |
| warm_outbound | 1400 | 512 | 2041 | 2000–2083 | 0.020 |
