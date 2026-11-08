# Release status

Public repository tczartoryski/userspace-router: visibility verified through GitHub metadata and unauthenticated source retrieval on November 7, 2026, after reachable-history and media audit. License remains pending owner decision; no license grant is implied. See [publication audit](PUBLICATION-AUDIT.md).

## Verified
- 17 Rust tests pass on macOS and native Ubuntu ARM64; formatting and strict Clippy (including Linux adapter static checks) pass.
- 35 Python security/verifier/lifecycle/packaging/bytecode/documentation/story tests pass, plus the controlled-clock JavaScript replay check. Mocked and generated-data tests are not live packet or browser evidence.
- Actual kernel UDP/TUN suites pass independent flow-capacity and port-pool exhaustion, same-port distinct internal clients, idle expiry and late-reply filtering, reallocation, overlapping longest-prefix routes, TTL and stopped-router negative control. Each extended run records forwarded=7, expired=3, active=1, Capacity=1, Policy=1, Filter=4 and io_drops=0, with all received packets accounted.
- One-command demo launched genuine ongoing UDP traffic and loopback-only dashboard; actual current telemetry advanced received counters from 75 to 138. Foreign Host/Origin returned 403 and POST returned 405. Ctrl-C cleanup stopped dashboard and VM; the final hardened run also verified SIGTERM cleanup exits 0 after removing its private staging and stopping dashboard/VM.
- Bounded atomic private snapshots contain actual attached TUN names, current configured routes, live NAT tuples and counters. Sensitive endpoints are hidden by default in the UI, but remain present in local API data. No simulated metrics.
- Release archive uses an audited file allowlist and SHA-256 manifest; historical raw logs/runtime snapshots and absolute local paths are excluded. Fresh extraction, offline test execution and repackaging pass with identical file contents and manifests. Markdown relative links pass.

## Rendered acceptance resolved — November 7, 2026
Desktop (1440×1000 viewport, full-page capture), mobile (390×844 viewport,
full-page capture), keyboard controls and live refresh PASS. Neither viewport
has horizontal document overflow. The readiness fix remains stable on the live
rerun. Actual telemetry shows tun-in/tun-out, four routes, one active mapping,
nonzero Filter and zero I/O drops; no DOM or metric mocking was used.
See [rendered QA](qa/RENDERED-QA.md) and the
[historical browser blocker and resolution](qa/BROWSER-BLOCKER.md).

The genuine video uses 12 actual browser captures collected over 20.536 seconds,
replayed at 1 FPS for 12 seconds; it is sampled/speed-adjusted, not continuous
realtime 30 FPS footage. AVFoundation confirms H.264, 1280×960, 12 timed media
samples and 12-second duration. Independent coordinator verification decoded all 12 frames and visually inspected first/middle/last frames from the actual movie; see [video details](DEMO-VIDEO.md). Final managed-browser errors=0. Final genuine rendered counters reached received=365, forwarded=239, active=1, Filter=119 and I/O drops=0. SIGTERM exited 0, closed the listener and stopped the VM; the browser then correctly showed OFFLINE and cleared current metrics. License remains pending owner decision.

## Explanatory NAT demo — November 7, 2026
All four real Linux UDP scenario checks PASS: bidirectional captured translation,
same-port clients with distinct SNAT ports, route-induced Policy drop versus
allowed delivery, and stopped-router timeout followed by fresh-process recovery.
The approved guest's owned namespaces/helpers/staging were removed and the VM
was verified stopped. No host network configuration or core dataplane changed.

The [captioned movie](qa/nat-story/nat-story.mp4) is a **57.08-second, 25 FPS,
1440×900 H.264 MP4**: 1,427 continuous browser-recording frames, all independently
decoded after unchanged-cadence conversion. Its four chapters contain 13
editorially timed substages (52 seconds), based exclusively on the reviewed
[real observations](qa/nat-story/observations.json). It is explicitly labeled
replay—not live packet-time footage. No audio tracks or asset metadata. Actual
browser QA passed all 13 states without desktop overflow, mobile horizontal
layout, manual/keyboard controls and zero page errors. No GitHub Actions workflow
is configured; check results are local and isolated-Linux evidence, not CI.
See [capture details](NAT-STORY.md) and [capture record](qa/nat-story/capture.json).

## Scope and reproduction
See README, ARCHITECTURE.md, architecture.svg and DEMO-VIDEO.md. The local-only stdlib dashboard is not an Internet production server. No TCP, fragmentation, IPv6, L2, ICMP generation or throughput/production claim. Use only an explicitly authorized isolated Linux environment. This sanitized repository starts from the sanitized allowlisted source archive, without original working history or raw local evidence. The original private working repository is preserved separately and must never be pushed. No deployment or GitHub release is published.
