# Actual Linux E2E run

Ubuntu24.04 ARM64 Linux6.8.0 2vCPU 3GiB Rust1.89 before long

REAL-LINUX-E2E

Contextual TUN userspace versus veth kernel comparison. No isolated algorithm speedup claim.

| Backend | Mode | Size | Flows | PPS median (min..max) | PPS CV | Loss per repeat |
|---|---|---:|---:|---:|---:|---|
| user | warm | 64 | 512 | 92037.6 (91379.9..94939.8) | 0.020 | [0, 0, 0] |
