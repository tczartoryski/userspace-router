# Rendered QA — PASS, November 7, 2026

Coordinator inspected genuine full-page [desktop](rendered/desktop.jpg)
(1440×1000 viewport) and [mobile](rendered/mobile.jpg) (390×844 viewport)
captures. Neither width has horizontal document overflow. The live readiness
fix remained stable on rerun. [Offline capture](rendered/offline.png) is retained.

Keyboard Tab exposed the skip link; Enter navigated to #runtime. Tab to the
address checkbox and Space revealed addresses and restored Hidden. Tab to
Refresh and Enter showed a focus ring and refreshed live telemetry.

Rendered received/forwarded counters advanced 19/12 → 63/40 → 96/62.
Video overview counters advanced from 155/100 to 173/112. Real tun-in/tun-out,
four configured routes, one active mapping, nonzero Filter and I/O=0 were visible.
No DOM or metric mocking was used. Final managed-browser errors were zero. Final current rendered counters reached received=365, forwarded=239, active=1, Filter=119 and I/O drops=0. After SIGTERM the demo exited 0, dashboard listener closed, VM was Stopped, and the browser correctly showed OFFLINE with cleared current metrics.

The [genuine movie](rendered/live-demo.mov) contains 12 actual browser PNG captures
([capture timestamps](rendered/capture-times.json)), spanning 20.536 seconds with
scrolling between the upper overview and lower NAT/drop sections. Playback is
12 seconds at 1 FPS, sampled and speed-adjusted, not continuous realtime 30 FPS.
System AVFoundation verified H.264, 1280×960 and all 12 decoded frames. The restricted Codex sandbox initially could not decode; independent coordinator execution using the same system decoder succeeded. First, middle and last frames extracted from the actual movie were visually inspected and matched the captured overview/mappings/drop sections. Video decode and visual inspection PASS.

Only approved sanitized captures and this report enter the release allowlist;
raw logs and runtime snapshots remain excluded. Historical browser blockers are
preserved in [the blocker record](BROWSER-BLOCKER.md).
