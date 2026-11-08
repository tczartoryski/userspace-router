# Actual Linux E2E run

Ubuntu24.04 ARM64 Linux6.8.0 2vCPU 3GiB Rust1.89 baseline diagnostic

PROFILE-DIAGNOSTIC

Contextual TUN userspace versus veth kernel comparison. No isolated algorithm speedup claim.

| Backend | Mode | Size | Flows | PPS median (min..max) | PPS CV | Loss per repeat |
|---|---|---:|---:|---:|---:|---|
| user | warm | 64 | 512 | 6666.0 (6472.4..34011.8) | 1.008 | [0, 0, 0] |
