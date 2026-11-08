# Actual portable MICRO baseline

Ubuntu 24.04 Linux 6.8.0 ARM64 2 vCPU 3 GiB Rust 1.89.0 Lima VZ

3 repeats; 512 operations per case per repeat. Median of repeat p50s; CV uses repeat p50s.
CPU unmeasured. RSS reserved for coordinator sampling. No Linux/TUN/E2E measurement.

| Case | IPv4 bytes | Flows | Median p50 ns | Min–max p50 ns | CV |
|---|---:|---:|---:|---:|---:|
| cold_allocation | 64 | 1 | 83 | 83–83 | 0.000 |
| cold_allocation | 64 | 64 | 250 | 250–250 | 0.000 |
| cold_allocation | 64 | 512 | 1166 | 1166–1166 | 0.000 |
| cold_allocation | 128 | 1 | 125 | 125–125 | 0.000 |
| cold_allocation | 128 | 64 | 292 | 292–292 | 0.000 |
| cold_allocation | 128 | 512 | 1208 | 1208–1208 | 0.000 |
| cold_allocation | 512 | 1 | 458 | 458–458 | 0.000 |
| cold_allocation | 512 | 64 | 625 | 584–625 | 0.039 |
| cold_allocation | 512 | 512 | 1541 | 1500–1542 | 0.016 |
| cold_allocation | 1400 | 1 | 1084 | 1042–1166 | 0.057 |
| cold_allocation | 1400 | 64 | 1250 | 1209–1333 | 0.050 |
| cold_allocation | 1400 | 512 | 2209 | 2208–2250 | 0.011 |
| expiry | 64 | 1 | 41 | 41–42 | 0.014 |
| expiry | 64 | 64 | 958 | 958–959 | 0.001 |
| expiry | 64 | 512 | 8458 | 8417–8500 | 0.005 |
| expiry | 128 | 1 | 41 | 41–42 | 0.014 |
| expiry | 128 | 64 | 959 | 958–1000 | 0.025 |
| expiry | 128 | 512 | 8875 | 8833–9000 | 0.010 |
| expiry | 512 | 1 | 41 | 41–42 | 0.014 |
| expiry | 512 | 64 | 958 | 958–959 | 0.001 |
| expiry | 512 | 512 | 8542 | 8459–8583 | 0.007 |
| expiry | 1400 | 1 | 41 | 41–42 | 0.014 |
| expiry | 1400 | 64 | 958 | 917–959 | 0.025 |
| expiry | 1400 | 512 | 8500 | 8459–8583 | 0.007 |
| reverse_lookup | 64 | 1 | 83 | 83–83 | 0.000 |
| reverse_lookup | 64 | 64 | 84 | 83–84 | 0.007 |
| reverse_lookup | 64 | 512 | 125 | 84–125 | 0.213 |
| reverse_lookup | 128 | 1 | 125 | 125–125 | 0.000 |
| reverse_lookup | 128 | 64 | 166 | 166–166 | 0.000 |
| reverse_lookup | 128 | 512 | 167 | 166–167 | 0.003 |
| reverse_lookup | 512 | 1 | 417 | 417–417 | 0.000 |
| reverse_lookup | 512 | 64 | 417 | 417–458 | 0.055 |
| reverse_lookup | 512 | 512 | 500 | 500–500 | 0.000 |
| reverse_lookup | 1400 | 1 | 1083 | 1042–1166 | 0.058 |
| reverse_lookup | 1400 | 64 | 1084 | 1083–1125 | 0.022 |
| reverse_lookup | 1400 | 512 | 1166 | 1083–1166 | 0.042 |
| timestamp | 0 | 0 | 0 | 0–0 | 0.000 |
| warm_outbound | 64 | 1 | 83 | 83–83 | 0.000 |
| warm_outbound | 64 | 64 | 166 | 125–166 | 0.155 |
| warm_outbound | 64 | 512 | 625 | 625–625 | 0.000 |
| warm_outbound | 128 | 1 | 125 | 125–125 | 0.000 |
| warm_outbound | 128 | 64 | 208 | 208–208 | 0.000 |
| warm_outbound | 128 | 512 | 584 | 584–667 | 0.078 |
| warm_outbound | 512 | 1 | 458 | 417–458 | 0.053 |
| warm_outbound | 512 | 64 | 500 | 500–542 | 0.047 |
| warm_outbound | 512 | 512 | 1000 | 959–1000 | 0.024 |
| warm_outbound | 1400 | 1 | 1166 | 1166–1166 | 0.000 |
| warm_outbound | 1400 | 64 | 1125 | 1125–1209 | 0.042 |
| warm_outbound | 1400 | 512 | 1625 | 1541–1667 | 0.040 |
