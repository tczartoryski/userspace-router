# Actual-state observability contract

Multicore is still 15.68–24.69% slower with worse median p99 in the measured
comparisons. Reference workers=1 remains default. Monitoring and sampling overhead
are measured in [actual results](MONITORING-RESULTS.md), including p99 regressions; not assumed free. No per-worker CPU is
inferred, no hardware counters or AF_XDP backend is claimed.

## Runtime and privacy

Reference workers=1 preserves schema 1 and its existing bounded sensitive mapping
export. Multicore with `--snapshot PRIVATE_DIRECTORY/FILE` emits schema 2. Both
require the existing caller-owned 0700 directory and create-new 0600 temporary
file, file fsync and atomic rename; size remains capped at 1 MiB. Parent-directory
fsync is not a durability guarantee. The warning about sensitive reference tuples
is retained. No snapshot path means optional queue ledgers and sampling are off;
existing periodic worker counter copies still support runtime reports.

Schema 2 contains no mappings, IP addresses, socket ports of conversations,
packet payload, paths, credentials or hashes of tuples. Configured external port
*range bounds* and worker capacities describe ownership, not active endpoints.
Zero tuples is the aggregate tuple-output bound. Interface names identify the
actual attached devices. The private localhost viewer retains exact Host/Origin,
GET-only allowlists, CSP, no CORS and bounded reads. Schema 1 stays supported;
schema 2 rejects unknown fields at every nesting level, including decision samples.

`--event-sample-every N` is opt-in, off at zero. Positive N requires multicore
and a private snapshot. Every Nth actually processed worker decision may enter
that worker's newest-64 ring: monotonic nanoseconds, Inside/Outside, core
Forward/drop reason, and total IP size only. Worker identity comes from its
containing report. No timestamps/decisions are synthesized; unprocessed dispatcher
rejects and queue drops are not sampled. Forward means a core decision, not TX.
This bounded activity disclosure still belongs in private storage. Sampling is
periodic/deterministic, not statistically representative tracing.

## Schema 2 fields and boundaries

- `backend=tun-poll`, `mode=workers`, `monitoring=true`, actual interfaces,
  running/stopped state, Unix time, uptime seconds and process monotonic ns.
- `workers`: 2..32 entries with stable ID, disjoint contiguous configured port
  ranges, capacity, core counters/active state and `observed_ns`. Workers publish
  copies approximately every 250 ms and on shutdown; no shared NAT-table lock or
  tuple enumeration is introduced. Reports are not simultaneous. The dispatcher
  copies reports before reading newer queue ledgers; report received <= completed.
- Each input ledger reports admitted, completed, occupancy, high water, full-queue
  drops and shutdown discards. **Input occupancy includes the in-flight worker
  packet**, so capacity = channel_capacity + 1. Completed means core processing
  finished. `admitted = completed + occupancy + shutdown_drops`. Queues remain
  bounded; ledgers synchronize their counters, adding measurable overhead.
- Output uses channel capacity only; completed means dispatcher dequeue, not TX.
  Its admission/drop counters cover actual worker forwarding outputs. Actual TUN
  successful writes/IPv4 bytes and WouldBlock drops live separately in `tx`.
  Short writes remain fatal, never continued as a second packet.
- `dispatcher` holds actual pre-worker validation rejects. Core received excludes
  unprocessed queue drops. `io_drops` sums input/output full and shutdown drops
  plus actual TX WouldBlock, without folding them into core forwarding decisions.
- At graceful shutdown all worker reports are final: worker core received equals
  input completed, summed core forwarded equals output admitted + output drops,
  and output completed equals TX writes + WouldBlock. Worker panic/backend errors
  fail the run; a successful final snapshot is not fabricated after failure.

`rates` uses consecutive actual snapshot counter differences divided by elapsed
process-monotonic nanoseconds: TX packets/s, TX IPv4 Mbps and core decisions/s.
First interval is null/unavailable. Core-rate timing includes periodic report lag;
TX counters are dispatcher-local. These are sample-interval rates, not inferred
NIC capacity or packet payload goodput. Stale/offline dashboard states suppress
current rates and retain explicit observation age. Queue meters/tables use the
same actual counts; no simulated backend controls exist.

## Coordinator commands and pending gates

Only inside the approved guest, using the existing release compiler/binary:

```sh
for monitoring in off on; do
  extra=()
  if [ "$monitoring" = on ]; then extra=(--snapshot-telemetry); fi
  sudo -n env UDP_ROUTER_ISOLATED_LINUX=YES bash scripts/linux-benchmark.sh \
    target/release/udp-router --backend user --mode warm --workers 4 \
    --size 64 --flows 512 --count 20000 --repeats 3 \
    --metadata 'Ubuntu24.04 arm64 2vCPU 3GiB telemetry comparison' \
    "${extra[@]}" --output "/tmp/telemetry-$monitoring.json" || exit
done
```

Repeat monitoring on with `--event-sample-every 100` and a distinct output name;
repeat worker counts 1/2/4 (events only for 2/4), both sizes/modes as bounded cells.
Four workers oversubscribe 2 vCPUs. Preserve p99/loss/CPU/RSS variability and all
repeats. Snapshot enablement/settings are explicit grouping keys. The harness
validates the actual final private snapshot, retaining only schema-2 aggregates
or a schema-1 reference counter summary; raw tuple snapshots/private paths stay
in temporary storage and are removed. Audited coordinator results are explicitly allowlisted; raw private snapshots/paths are not.

Short runs may finish before the one-second periodic filesystem snapshot and
250-ms worker publication. They measure ledger/sampler costs but not full steady
periodic fsync/export cost: longer bounded acceptance and rendered browser QA are
separately documented. Coordinator live acceptance and retained-snapshot rendered QA
passed; short-run timing does not prove steady fsync cost.


## Failure and steady-export follow-up

Dispatcher poll/write errors now skip clean `running=false` publication even when
all worker joins succeed. Worker joins and backend shutdown still execute first;
the previous observation is left unchanged and ages stale. No explicit failure
state is invented in either schema. A portable injected backend-failure gate
asserts all worker handles are joined and the clean publisher is never called.

A separate guest-only `worker_acceptance.py` performs paced real echo traffic for
at least3.2seconds after adversarial/burst phases, observing at least two distinct
new periodic snapshots after pacing starts, then validates graceful final state.
It checks0700parent/0600file ownership, privacy schema, actual partition settings
and queue conservation. It is acceptance, not a throughput/overhead timing cell:

```sh
sudo -n env UDP_ROUTER_ISOLATED_LINUX=YES python3 -B scripts/worker_acceptance.py   target/release/udp-router --output /tmp/router-worker-acceptance.json
```

Guest execution PASSED; see [actual evidence](MONITORING-RESULTS.md). Output is written only after all gates and owned
resource cleanup succeed; raw private logs and paths are not published. Controlled
fixture socket bindings/observed NAT tuples in acceptance receipts are distinct
from the zero-tuple schema2 snapshot contract. Do not feed acceptance receipts
into the live dashboard or treat them as a new benchmark baseline.
