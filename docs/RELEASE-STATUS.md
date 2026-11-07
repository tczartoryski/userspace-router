# Release status

Owner approved the private repository `tczartoryski/userspace-router`. License remains pending owner decision; no license grant or public publication is implied.

## Verified
- 17 Rust tests pass on macOS and native Ubuntu ARM64; formatting and strict Clippy (including Linux adapter static checks) pass.
- 22 Python security/verifier/lifecycle/packaging/bytecode tests pass. Mocked and generated-data tests are not live packet or browser evidence.
- Actual kernel UDP/TUN suites pass independent flow-capacity and port-pool exhaustion, same-port distinct internal clients, idle expiry and late-reply filtering, reallocation, overlapping longest-prefix routes, TTL and stopped-router negative control. Each extended run records forwarded=7, expired=3, active=1, Capacity=1, Policy=1, Filter=4 and io_drops=0, with all received packets accounted.
- One-command demo launched genuine ongoing UDP traffic and loopback-only dashboard; actual current telemetry advanced received counters from 75 to 138. Foreign Host/Origin returned 403 and POST returned 405. Ctrl-C cleanup stopped dashboard and VM; the final hardened run also verified SIGTERM cleanup exits 0 after removing its private staging and stopping dashboard/VM.
- Bounded atomic private snapshots contain actual attached TUN names, current configured routes, live NAT tuples and counters. Sensitive endpoints are hidden by default in the UI, but remain present in local API data. No simulated metrics.
- Release archive uses an audited file allowlist and SHA-256 manifest; historical raw logs/runtime snapshots and absolute local paths are excluded. Fresh extraction, offline test execution and repackaging pass with identical file contents and manifests. Markdown relative links pass.

## Blocked: rendered browser acceptance and genuine video
Two first-class browser navigation attempts to the localhost dashboard returned **browser navigation blocked by policy** despite healthy browser diagnostics. No policy bypass or Gateway configuration change was attempted. Desktop/mobile screenshots, interactive keyboard checks and genuine video are NOT complete. [Exact browser blocker](qa/BROWSER-BLOCKER.md). Existing Swift/AVFoundation encoder support does not substitute for legitimate captured frames.

## Scope and reproduction
See README, ARCHITECTURE.md, architecture.svg and DEMO-VIDEO.md. The local-only stdlib dashboard is not an Internet production server. No TCP, fragmentation, IPv6, L2, ICMP generation or throughput/production claim. Use only an explicitly authorized isolated Linux environment. This private repository starts from the sanitized allowlisted source archive, without the original working history or raw local evidence. The original private working repository is preserved separately. No deployment or GitHub release is published.
