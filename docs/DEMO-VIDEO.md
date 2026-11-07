# Genuine demonstration capture workflow

Current status (2026-11-06): rendered screenshots, mobile/keyboard validation and
video are BLOCKED. Two managed `browser.open` attempts to localhost returned
**browser navigation blocked by policy**; `browser.doctor` was healthy. Do not
bypass policy or alter configuration. Exact local record: [browser blocker](qa/BROWSER-BLOCKER.md).
The existing Swift encoder compiled, but no legitimate browser frames are available.

The coordinator separately passed BOTH actual extended suites and ran the actual
one-command demo with real traffic/current telemetry; Ctrl-C stopped the VM and
dashboard successfully. This is live packet/lifecycle evidence, not rendered QA.
Follow-up mocked lifecycle and synthetic telemetry tests do not replace that proof.

After normal authorized browser access is available, coordinator: run `python3 scripts/demo.py`, wait for the real-packet suites to
pass, then open http://127.0.0.1:8765 in the existing browser. Confirm CURRENT,
visible actual interfaces/routes, changing received/forwarded counters, real
mappings, and nonzero Filter drops. Capture rendered browser frames with the
existing browser screenshot tool; never replace data or generate fake traffic.
Check desktop, narrow mobile viewport, Tab focus, checkbox, refresh and skip link.

For a short video, retain timestamped browser PNG frames while the live demo
runs. On macOS, an existing Swift compiler can use AVFoundation AVAssetWriter
with AVVideoCodecType.h264 and a pixel-buffer adaptor to encode those actual
frames at their recorded timestamps into a local .mov. Check compiler availability
first; do not install ffmpeg or other tools. If capture/encoding tools are absent,
report video unavailable rather than fabricate a recording. Inspect the movie
before distribution and keep sensitive tuples redacted. Video capture and final
encoding are coordinator tasks, not claimed completed by these instructions.

Ctrl-C or SIGTERM in the startup terminal stops dashboard/demo and the VM. Verify Lima is
stopped. Any interrupted guest shell can be cleaned by stopping router-lab; no
host routes/firewall configuration is involved.

Concrete encoder (existing Swift + system AVFoundation only):

```sh
# Capture frames at a fixed cadence, e.g. 2 FPS, named 000001.png, 000002.png…
# All frames must be the same even pixel dimensions.
CLANG_MODULE_CACHE_PATH=/tmp/udp-router-clang-cache swift \
  -module-cache-path /tmp/udp-router-swift-cache \
  scripts/encode-demo.swift /tmp/router-browser-frames /tmp/router-demo.mov 2
```

This encoder consumes only actual screenshots; FPS must match capture cadence.
No frames or movie were fabricated or captured in this implementation session.
