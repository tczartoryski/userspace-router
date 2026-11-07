# Rendered dashboard and video QA — resolved November 7, 2026

Normal authorized browser QA now PASS: desktop/mobile captures, no horizontal
overflow, keyboard skip link/checkbox/refresh and live metrics. Genuine sampled
video is captured. See [rendered QA](RENDERED-QA.md) and
[video details](../DEMO-VIDEO.md). No policy bypass was used.

## Historical blocker — November 6, 2026

The following records the earlier blocked state, superseded by the resolution above.

2026-11-06 coordinator attempted managed Chromium browser navigation to the genuine live dashboard http://127.0.0.1:8765/ twice, before and after verified server readiness. Both first-class browser.open calls returned exact error **browser navigation blocked by policy**. browser.doctor reports browser/CDP/executable healthy; browser.tabs remains empty. No alternate browser, CDP access, security configuration change, policy bypass, or fabricated screenshot was attempted.

Owner/parent gate: permit browser access to this exact loopback dashboard through the normal authorized policy, or perform rendered desktop/mobile/keyboard screenshot QA from a session already permitted to open it. Gateway configuration changes were explicitly outside task authority. Until then screenshots, interactive keyboard/mobile browser validation and short genuine demo video are NOT completed. Static accessibility/security tests are not a substitute.

Available existing Apple Swift compiler compiled a local AVFoundation H.264 image-sequence encoder successfully (deprecation warnings only); no ffmpeg or other component installed. Lack of legitimate browser frames, not encoder capability, currently blocks the video. A recorded-frame sequence would be labeled time-lapse rather than real-time. No video was manufactured.

Achieved separately: actual localhost server listened only on 127.0.0.1:8765, returned genuine current Rust runtime snapshot, and counters advanced from received=75 to 138 during controlled real UDP pulse traffic. Foreign Host and Origin returned 403; POST returned 405. Raw snapshots are local/private QA evidence, excluded from publication package.
