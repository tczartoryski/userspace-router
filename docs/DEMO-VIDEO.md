# Historical sampled dashboard video

For the newer, explanatory request/reply, shared-address, policy and recovery
demo, see [the NAT story](NAT-STORY.md) and its [continuous captioned movie](https://raw.githubusercontent.com/tczartoryski/userspace-router/cc95f60414a7aab467db7678ab3f7b32bfd84014/docs/qa/nat-story/nat-story.mp4).
The sampled counter recording below is retained as historical dashboard QA.

Rendered QA PASS as of November 7, 2026. The coordinator inspected genuine
[desktop](qa/rendered/desktop.jpg) and [mobile](qa/rendered/mobile.jpg) full-page
captures and verified keyboard controls, live refresh and no horizontal overflow.
See [rendered QA](qa/RENDERED-QA.md). The earlier November 6 navigation policy
blocker is preserved in [the historical record](qa/BROWSER-BLOCKER.md).

The [movie](qa/rendered/live-demo.mov) was encoded with existing system
Swift/AVFoundation from 12 actual browser PNG captures, frames 0000–0011.
[Capture timestamps](qa/rendered/capture-times.json) span 20.536 seconds, including
scrolling between the upper overview and lower NAT/drop sections. Playback at
1 FPS lasts 12 seconds. This is a genuine sampled, speed-adjusted recording,
not continuous realtime 30 FPS footage. No DOM or metric mocking was used.

System AVFoundation inspection confirmed duration 12 seconds, dimensions
1280×960, H.264 (`avc1`), nominal 1 FPS and 12 timed media samples with presentation
timestamps 0–11 seconds. Zero-sample control buffers are excluded from that count.
All 12 frames decoded successfully in independent coordinator verification using the system AVFoundation decoder. First, middle and last decoded movie frames were visually inspected and matched the original genuine captures. An initial restricted Codex sandbox decode failed, but was not a damaged-movie finding; normal coordinator execution succeeded. No tools were installed and the movie was not changed.

To reproduce encoding from actual captured frames with the existing tool:

```sh
swift scripts/encode-demo.swift docs/qa/rendered/frames demo.mov 1
```

The encoder uses fixed FPS; choose and disclose the replay cadence. This capture
has irregular source intervals and therefore does not preserve real elapsed time.
Keep sensitive tuples hidden and package only approved sanitized assets. Final
browser-error collection remains with the coordinator; the pre-live result was zero.
