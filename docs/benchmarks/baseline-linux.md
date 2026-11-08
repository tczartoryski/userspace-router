# Actual portable MICRO baseline

Ubuntu 24.04 Linux 6.8.0 ARM64 2 vCPU 3 GiB Rust 1.89.0 Lima VZ

3 repeats; 512 operations per case per repeat. Median of repeat p50s; CV uses repeat p50s.
CPU unmeasured. RSS reserved for coordinator sampling. No Linux/TUN/E2E measurement.

| Case | IPv4 bytes | Flows | Median p50 ns | Min–max p50 ns | CV |
|---|---:|---:|---:|---:|---:|
| cold_allocation | 64 | 1 | 83 | 83–83 | 0.000 |
| cold_allocation | 64 | 64 | 292 | 292–292 | 0.000 |
| cold_allocation | 64 | 512 | 1541 | 1541–1542 | 0.000 |
| cold_allocation | 128 | 1 | 125 | 125–125 | 0.000 |
| cold_allocation | 128 | 64 | 334 | 333–334 | 0.002 |
| cold_allocation | 128 | 512 | 1584 | 1583–1667 | 0.030 |
| cold_allocation | 512 | 1 | 417 | 417–458 | 0.055 |
| cold_allocation | 512 | 64 | 667 | 625–667 | 0.037 |
| cold_allocation | 512 | 512 | 1917 | 1917–1917 | 0.000 |
| cold_allocation | 1400 | 1 | 1083 | 1042–1125 | 0.038 |
| cold_allocation | 1400 | 64 | 1292 | 1250–1333 | 0.032 |
| cold_allocation | 1400 | 512 | 2625 | 2583–2625 | 0.009 |
| expiry | 64 | 1 | 41 | 41–41 | 0.000 |
| expiry | 64 | 64 | 1000 | 1000–1000 | 0.000 |
| expiry | 64 | 512 | 9083 | 9042–9125 | 0.005 |
| expiry | 128 | 1 | 41 | 41–41 | 0.000 |
| expiry | 128 | 64 | 1041 | 1000–1041 | 0.023 |
| expiry | 128 | 512 | 9125 | 9084–9125 | 0.003 |
| expiry | 512 | 1 | 41 | 41–41 | 0.000 |
| expiry | 512 | 64 | 1000 | 1000–1000 | 0.000 |
| expiry | 512 | 512 | 9083 | 9042–9166 | 0.007 |
| expiry | 1400 | 1 | 41 | 41–41 | 0.000 |
| expiry | 1400 | 64 | 1000 | 1000–1000 | 0.000 |
| expiry | 1400 | 512 | 8667 | 8625–8667 | 0.003 |
| reverse_lookup | 64 | 1 | 83 | 83–83 | 0.000 |
| reverse_lookup | 64 | 64 | 125 | 125–166 | 0.171 |
| reverse_lookup | 64 | 512 | 459 | 459–500 | 0.050 |
| reverse_lookup | 128 | 1 | 125 | 125–125 | 0.000 |
| reverse_lookup | 128 | 64 | 208 | 208–208 | 0.000 |
| reverse_lookup | 128 | 512 | 541 | 500–542 | 0.045 |
| reverse_lookup | 512 | 1 | 417 | 417–458 | 0.055 |
| reverse_lookup | 512 | 64 | 500 | 500–541 | 0.046 |
| reverse_lookup | 512 | 512 | 834 | 833–875 | 0.028 |
| reverse_lookup | 1400 | 1 | 1042 | 1042–1125 | 0.045 |
| reverse_lookup | 1400 | 64 | 1125 | 1125–1208 | 0.042 |
| reverse_lookup | 1400 | 512 | 1541 | 1417–1541 | 0.048 |
| timestamp | 0 | 0 | 0 | 0–0 | 0.000 |
| warm_outbound | 64 | 1 | 83 | 83–83 | 0.000 |
| warm_outbound | 64 | 64 | 208 | 167–209 | 0.123 |
| warm_outbound | 64 | 512 | 1000 | 1000–1000 | 0.000 |
| warm_outbound | 128 | 1 | 125 | 125–125 | 0.000 |
| warm_outbound | 128 | 64 | 250 | 250–250 | 0.000 |
| warm_outbound | 128 | 512 | 1042 | 959–1083 | 0.061 |
| warm_outbound | 512 | 1 | 458 | 417–458 | 0.053 |
| warm_outbound | 512 | 64 | 542 | 541–542 | 0.001 |
| warm_outbound | 512 | 512 | 1333 | 1333–1375 | 0.018 |
| warm_outbound | 1400 | 1 | 1125 | 1125–1166 | 0.021 |
| warm_outbound | 1400 | 64 | 1250 | 1167–1250 | 0.039 |
| warm_outbound | 1400 | 512 | 1917 | 1916–2083 | 0.049 |
