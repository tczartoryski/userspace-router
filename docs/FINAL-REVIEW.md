# Focused final code review

Reviewed against sanitized source baseline `59ff117`, with prior stages
`f6679fb` ownership, `0d4e818` expiry and `01300cc` pre-change profiling. Scope:
concurrency/NAT, checksums/expiry, backpressure/shutdown and private snapshots.
This is a focused reasoned review and test gate, not formal verification.

## Finding fixed in this review

A poisoned output-ledger mutex could panic in `Pool::shutdown`, including a
second panic from Drop during unwinding. Cleanup now joins every worker first,
drains owned completions without trusting poisoned state, and returns failure.
It never publishes a clean final observation from that failure. Added poison
injection checks explicit shutdown and subsequent Drop do not panic. No hot-path
packet behavior or performance optimization is introduced. Native Rust checks, including the poison injections, passed: 31 tests.

## Verified invariants and tradeoffs

- Dispatcher owns TUN FDs; worker owns its Router. No shared hot NAT lock. Channels
  synchronize internally and optional metric locks add overhead. Publication
  copies bounded reports rather than holding a NAT-table lock on the dispatcher.
- Output metric locks are released before input completion/publication; dispatcher
  clones report and releases its guard before reading input metrics. No lock-order
  cycle or blocking data send is required. Stop flag/disconnection do not require
  free queue slots. Join all workers after failure; bounded core work/20-ms waits
  allow shutdown. A callback supplied by the runtime is nonblocking; arbitrary
  externally supplied blocking callbacks are outside that guarantee.
- Inclusive disjoint port ranges and effective-capacity remainders sum correctly,
  including port 65535. Capacity is per shard: hash skew can strand free global
  capacity. No migration or duplicate allocator is hidden in the design.
- Internal-socket hash and external destination-port dispatch select ownership,
  not authorization. Core policy and exact remote address/port checks precede
  refresh. Unexpected destination addresses/unallocated ports still fail closed.
- Parser bounds lengths before indexing, rejects options/fragments/invalid UDP,
  checks IPv4/UDP checksums and rewrites full checksums. Core zero UDP checksum
  acceptance/ffff result encoding remains the documented IPv4 behavior. No
  validation/capability/attachment weakening was found in the focused diff.
- Backward time is checked before same-second expiry skip. Integer-second timeout
  >=1 and empty initial state prove the skip; portable boundary/reference tests
  remain. Workers sample one process epoch at processing time, not stale queued
  timestamps. Arrival-versus-processing time under overload is a disclosed limit.
- Queue full/WouldBlock drops and shutdown discards remain separate from core
  decisions. Input occupancy includes in-flight work. Final successful snapshots
  conserve admitted/completed/shutdown and actual TX counts; periodic worker
  reports may lag newer queue observations and are not globally simultaneous.
- Prior dispatcher-error fix is intact: outcome, joins and backend shutdown must
  all succeed before clean final publication. A backend failure leaves the last
  actual observation unchanged to age stale. Panic/poison errors are failures,
  not successful smaller-worker runs. No fabricated failure telemetry is added.
- Private parent 0700/owner checks, create-new 0600/fsync/rename and 1 MiB cap remain.
  Schema2 exports no tuples/payloads and bounded events; schema1 sensitivity is
  retained explicitly. Reader now also refuses FIFO/symlink/nonprivate files and
  supports only two fixed CLI-selected paths. HTTP cannot choose a guest path.

## Presentation and completion gate

[Engineering report](V2-ENGINEERING-REPORT.md) and deterministic charts include
all reviewed raw measurement files, all cells/repeats and regressions. Multicore
is a safe-ownership/per-worker-observability demonstrator, not a scaling win.
Reference 1 stays default. Expiry throughput/CPU gains do not erase64/512-byte tail
regressions. No unmeasured batching, AF_XDP or zero-copy claim is introduced.

Portable checks cover poisoned cleanup plus existing backend-failure/panic/full
queues, ownership/generated packets, checksums/expiry, schema/privacy, readers,
DOM/replay and packaging: 31 Rust and 66 Python tests pass. The corrected
current→stale→recovered→offline browser gate passed; [live evidence](LIVE-V2-DEMO.md)
retains the successful sampled capture, all source frames and exact limitations.
Wider OS FD/fault/SIGKILL campaigns, long randomized steady-fsync overhead and
per-worker CPU remain gaps. No commit/push/merge/release/license action here.
