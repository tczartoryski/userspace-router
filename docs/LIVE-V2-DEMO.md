# Verified sampled live v2 capture and reproduction

**Corrected guest live gate and sampled browser capture passed.** Earlier monitoring
screenshots show genuine retained stopped data, not live traffic footage. This
script creates actual traffic and process transitions; it does not open a browser,
encode video, manage a VM or change host networking. Four workers oversubscribe
the approved two-vCPU lab and measured throughput/p99 regressed; default remains1.

Inside the already approved guest's copied sanitized project, using existing
compiler/prerequisites:

```sh
cargo build --release --locked --offline
sudo -n env UDP_ROUTER_ISOLATED_LINUX=YES python3 -B scripts/live_v2_demo.py \
  target/release/udp-router --output /tmp/live-v2-observations.json
```

The root/Linux/isolated opt-in gate applies to every helper. Fixed
`/tmp/udp-router-v2-live` must not already exist: the script refuses every
pre-existing entry and exclusively creates its own root-owned 0700 directory.
The snapshot is 0600 and schema 2 contains no tuples or payloads. A project under
a guest-owned 0700 home cannot be traversed by capability-dropped root; the fixed
/tmp location avoids that failure without changing home or runtime permissions.
The reader accepts only the legacy fixed demo path or fixed
`/tmp/udp-router-v2-live/snapshot.json` selected by `--v2-live`; there is no
arbitrary path API. The corrected startup-path gate passed.
Actual attached TUN devices and four workers forward between kernel UDP sockets.
Events sample every 100 actual worker decisions; source payloads are bounded
fixture sequences, not dashboard metrics.

On the host, with the existing authorized guest bridge executable already
configured by this project, start only the loopback viewer (replace the example
guest-root with the exact task-owned copied project root):

```sh
python3 -B scripts/dashboard.py --guest --guest-live \
  --guest-root /tmp/TASK_STAGE/udp-router --port 8765
```

The CLI root is supplied by the coordinator, never HTTP. It selects a fixed
argv-only guest reader command with a four-second deadline. No listener, network
forwarding, host mount or public access is created by the guest harness. Open
`http://127.0.0.1:8765` through the normal authorized browser for actual rendered
capture. Do not substitute DOM fixtures or retained stopped snapshots for live
traffic evidence. Start capture before launching the guest script if desired.

The approximately 40-second sequence is 12 seconds current real echoes, 7 seconds
of SIGSTOP on the owned router (actual timestamps age stale beyond 5 seconds),
12 seconds resumed SIGCONT with verified new echoes and progressing TX, then
SIGTERM/reap and 9 seconds showing the actual stopped/offline snapshot. Endpoint
helpers continue; packets offered after router shutdown must not be delivered.
Counts validate exact echoed payloads/tuples/TTL63; control labels are annotations,
not synthesized timestamps. No snapshot timestamp is rewritten to force a state.
Logs identify phases; output retains actual phase snapshots and aggregate echo
verification only after all gates and cleanup succeed.

All children/namespaces are owned by this run. Bounded helpers, selector waits,
packet counts and command deadlines apply; interrupt cleanup SIGCONTs an owned
paused router before termination, then reaps/deletes owned resources. Normal
completion removes only its exclusively created live snapshot directory. A
pre-existing directory or unexpected remaining file causes failure, not broad
cleanup. SIGKILL/guest loss cannot run cleanup: inspect/discard the disposable
guest under coordinator control. Close the task-owned viewer after capture.
The successful reviewed observations, capture metadata, video and all 44 frames
are explicitly packaged; the failed attempt is excluded.

## Verified live browser evidence

The corrected fixed-private-directory guest gate passed. [Capture metadata](qa/v2-live/capture.json),
[actual socket observations](qa/v2-live/observations.json), all 44 source PNGs and
[H.264 video](qa/v2-live/live-v2.mp4) retain the successful run. Genuine browser
stills targeted 1 Hz; the 44-second, 1440×1300 video encodes those 44 frames at
1 fps with no audio. This is sampled footage, not continuous full-frame-rate video.
Coordinator AVFoundation validation decoded all 44 frames and checked dimensions,
duration, audio absence and extracted current/stale/offline frames. No DOM or
snapshot timestamps were rewritten; source hashes and actual capture times remain.

| Browser chapter | Frame | Actual capture elapsed |
|---|---:|---:|
| First current snapshot | 3 | 3.579 s |
| Stale after owned-router SIGSTOP | 19 | 19.568 s |
| Current recovery after SIGCONT | 21 | 21.565 s |
| Stopped/offline after SIGTERM | 33 | 33.588 s |

Initial unavailable frames precede the first snapshot; final unavailable frames
follow cleanup. All frames are retained, including those transitions. Verified
replies by **send phase** were current 444/444, stale 116/116, resume 443/444 and
offline 0/148. Stale-phase sends were delivered after resume, not during SIGSTOP;
one resume request was outstanding at shutdown. The server echoed 1003 packets.
This is not a zero-loss whole-movie claim or throughput benchmark. Periodic worker
observations can lag dispatcher TX, so live TX may exceed sampled core decisions;
final joined counters conserve all 2006 forwarding decisions and writes.

The initial failed private-home traversal attempt is excluded from public capture
artifacts. The fix exclusively creates root-owned `/tmp/udp-router-v2-live` 0700
with snapshot 0600, without chmod or security weakening. The coordinator stopped
and cleaned the guest, namespaces and helpers; intentionally SIGTERMed the viewer
(exit 15) and closed the tab. No live process is distributed with this evidence.
