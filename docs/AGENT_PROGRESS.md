# Router v2 progress and handoff

Branch: `feat/router-v2`. Review base: `59ff117`. Main, license, release and
visibility remain unchanged. Final review/presentation is delivered on the feature
branch for owner review; merging is not authorized. No production-readiness or multicore speedup claim.

## Verified stages and measured tradeoffs

- `5ec52e7`: full source/documentation audit and reproducible portable MICRO baseline.
- `01300cc`: real Linux E2E/kernel comparison and pre-optimization software profiles.
- `0d4e818`: same-second expiry sweep elimination. Matched long 512-flow completed
  echo rates improved 13.89%, 15.57%, 10.23% and 19.76% at 64/128/512/1400 total
  IPv4 bytes. Each echo completes two router traversals, not NIC line rate.
  **64-byte p99 increased from 1243.6 µs to 1847.8 µs; 512-byte p99 also worsened.**
  Whole-core MICRO p50 fell from 1000 ns to 625 ns for 64 bytes/512 flows;
  separate diagnostic median task-clock fell from 82.06 ms to 55.98 ms.
- `f6679fb`: bounded owned packet I/O and private NAT workers with disjoint ports,
  socket/reverse affinity, bounded queues and panic shutdown. **Multicore was
  15.68–24.69% slower with worse median p99. Reference one-worker mode stays default.**
  Four workers oversubscribe the approved two-vCPU guest. Aggregate profiles show
  channel/futex, syscall/wakeup and datagram receive costs; no isolated attribution.
- `59ff117`: private schema-2 worker/queue/TX snapshots, monotonic rates, optional
  capped tuple-free events and strict dashboard/readers. Schema 1 remains supported.
  Native Linux 30 Rust tests and 58 Python tests passed at that stage.

Actual four-worker adversarial acceptance covers same-source-port ownership,
wrong address/port rejection without refresh, expiry/late replies, local capacity
with global space free, policy, reallocation and stopped-path controls. Deliberate
burst overload offered 26,304 datagrams: 771 verified replies, 25,398 input-full
and 135 output-full drops. This is overload loss, not a zero-loss benchmark.
Twenty-seven paced echoes over 3.297 s produced three periodic live snapshots;
private permissions and final queue/TX conservation passed. Backend errors do not
publish clean stopped snapshots. The 24 monitoring off/on/sampled experiments
retain all ranges; short cells do not isolate steady fsync/export cost.

Retained actual stopped dashboard captures passed desktop/mobile rendering; they
are not live traffic footage. Namespaces/helpers were cleaned and the approved
guest was verified stopped by the coordinator. No new guest runs in this phase.

## Current final review and presentation

[Focused review](FINAL-REVIEW.md) found and fixed poisoned output-ledger cleanup
that could panic during Drop. Cleanup now joins/drains and returns failure without
trusting poisoned metrics. Portable poison injection verifies no double panic.
The packet hot path and reference-default policy are unchanged.

[Engineering report](V2-ENGINEERING-REPORT.md), [all-data inventory](V2-ALL-DATA.md)
and deterministic SVGs cover all 59 reviewed JSON artifacts, 94 uninstrumented
cells, all MICRO cases and every diagnostic repeat. Gains, regressions, sampling
limits and contextual kernel-path differences remain explicit. No new benchmark
measurements or cherry-picked best runs were generated.

[Verified live capture](LIVE-V2-DEMO.md) passed after moving state to the fixed
root-owned 0700 `/tmp/udp-router-v2-live`, preserving snapshot 0600 and all guards.
Actual UDP echoes, owned SIGSTOP/SIGCONT/SIGTERM and sampled browser states are
retained with all 44 frames, metadata and 1-fps video. No timestamps or DOM were
rewritten. One resume request remained outstanding at shutdown; see exact counts.
Coordinator cleaned/stopped the guest and viewer. Portable final gates: 31 Rust,
66 Python tests; final feature PR is delivered for owner review.

## Remaining conditional gates

- Wider OS FD/EOF/hangup/short-write, monitored panic and SIGKILL recovery campaign.
- Longer randomized steady monitoring/fsync timing and separate per-worker CPU.
  Hardware cycles/instructions are unsupported; no inferred CPU results.
- AF_XDP is unimplemented: specific attach/test authority, Ethernet/L2 semantics,
  UMEM/ring ownership and real acceptance/measurement are missing. No zero-copy,
  batching, migration or scalable-performance claim.
- Owner review of the sanitized feature PR. No main merge, release or license change.

## Portable checks and cost scope

This review passes 31 Rust tests and 66 Python tests, strict Clippy including Linux
ABI, formatting, JS DOM/replay, shell and explicit package/manifest gates. Newly
added checks are portable, not a replacement for native guest acceptance.
One native Sol lane; no extra agents, installs, provider/resource changes or paid
services. Last supplied weekly usage was 5%, historical rather than current.
Exact dollar/token totals and aggregate tool/call counts are unavailable.
