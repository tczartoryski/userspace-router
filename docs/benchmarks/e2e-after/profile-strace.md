# Actual Linux E2E run

Ubuntu24.04 ARM64 Linux6.8.0 2vCPU 3GiB Rust1.89 optimized diagnostic

PROFILE-DIAGNOSTIC

Contextual TUN userspace versus veth kernel comparison. No isolated algorithm speedup claim.

| Backend | Mode | Size | Flows | PPS median (min..max) | PPS CV | Loss per repeat |
|---|---|---:|---:|---:|---:|---|
| user | warm | 64 | 512 | 7744.9 (7479.7..7915.4) | 0.028 | [0, 0, 0] |
