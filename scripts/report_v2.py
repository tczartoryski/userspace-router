#!/usr/bin/env python3
"""Deterministic stdlib report from every explicitly reviewed benchmark JSON.
No measurements, network, Git writes, external rendering or best-run selection.
"""
import hashlib
from html import escape
import json
import math
from pathlib import Path
import statistics
import package

ROOT=package.ROOT
DOCS=ROOT/'docs'


def stats(values):
    if not values or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values):
        raise ValueError('invalid measured metrics')
    mean=statistics.mean(values)
    return dict(median=statistics.median(values),minimum=min(values),maximum=max(values),cv=statistics.stdev(values)/mean if len(values)>1 and mean else 0)


def groups(data):
    result={}
    for row in data['rows']:
        key=tuple(row.get(k,default) for k,default in [('backend','user'),('mode','warm'),('size',0),('flows',0),('workers',1),('telemetry_enabled',False),('event_sample_every',0),('attempted',0),('window',0)])
        result.setdefault(key,[]).append(row)
    return sorted(result.items(),key=lambda pair:repr(pair[0]))


def summarize(rows):
    return dict(rate=stats([r['delivered_pps'] for r in rows]),
                rtt={k:stats([r['rtt'][k]/1000 for r in rows]) for k in ('p50_ns','p95_ns','p99_ns')},
                cpu=None if rows[0]['router_cpu_seconds'] is None else stats([r['router_cpu_seconds'] for r in rows]),
                rss=None if rows[0]['router_sampled_peak_rss_bytes'] is None else stats([r['router_sampled_peak_rss_bytes'] for r in rows]),
                dropped=sum(r['dropped'] for r in rows),failed=sum(r['send_failed'] for r in rows))


def span(v,decimals=1):
    if v is None:return 'unmeasured'
    return f"{v['median']:.{decimals}f} ({v['minimum']:.{decimals}f}–{v['maximum']:.{decimals}f})"


def svg(title,subtitle,items,unit):
    # One common zero-based axis per figure. Whiskers retain repeat min/max.
    width=1200;height=120+len(items)*30
    maximum=max((v['maximum'] for _,v,_ in items),default=1) or 1
    scale=600/maximum
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
         f'<title id="title">{escape(title)}</title><desc id="desc">{escape(subtitle)}. Bars are medians; whiskers are all retained repeat minima and maxima. Units: {escape(unit)}.</desc>',
         f'<rect width="{width}" height="{height}" fill="#101f26"/>',
         '<g font-family="system-ui,sans-serif" fill="#edf8f5">',
         f'<text x="20" y="30" font-size="22">{escape(title)}</text>',f'<text x="20" y="54" font-size="13">{escape(subtitle)}</text>',
         f'<text x="350" y="78" font-size="12">0 → {maximum:.1f} {escape(unit)} (common zero-based axis)</text>']
    for i,(label,v,color) in enumerate(items):
        y=95+i*30
        out.extend([f'<text x="20" y="{y+13}" font-size="12">{escape(label)}</text>',
                    f'<rect x="350" y="{y}" width="{v["median"]*scale:.3f}" height="18" fill="{color}"/>',
                    f'<line x1="{350+v["minimum"]*scale:.3f}" x2="{350+v["maximum"]*scale:.3f}" y1="{y+9}" y2="{y+9}" stroke="#ffffff" stroke-width="2"/>',
                    f'<text x="970" y="{y+13}" font-size="11">{escape(span(v))}</text>'])
    return '\n'.join(out+['</g></svg>\n'])


def generate():
    names=sorted(set(n for n in package.FILES if n.startswith('docs/benchmarks/') and n.endswith('.json')))
    loaded={name:json.loads((ROOT/name).read_text()) for name in names}
    cells=[];index=['# All reviewed v2 measurement data','','Generated deterministically by `python3 -B scripts/report_v2.py`. Every reviewed JSON is inventoried; derived comparisons are not counted twice.','',
      '| Artifact | Kind | Raw records | SHA-256 |','|---|---|---:|---|']
    for name,data in loaded.items():
        kind=data.get('kind','derived comparison' if 'rows' in data else 'correctness evidence')
        count=sum(len(run) for run in data['runs']) if kind=='MICRO' else len(data.get('rows',[]))
        index.append(f"| [{name.removeprefix('docs/')} ]({name.removeprefix('docs/')}) | {kind} | {count} | `{hashlib.sha256((ROOT/name).read_bytes()).hexdigest()}` |")
        if kind=='REAL-LINUX-E2E':
            for key,rows in groups(data):cells.append((name,key,rows,summarize(rows)))
    index += ['', '## All uninstrumented E2E cells', '', 'Each cell uses every repeat. RTT entries are medians of repeat quantiles (µs), not pooled percentiles. PPS counts echoes; each echo completes two router traversals. Kernel CPU/RSS are unassigned, not zero.','',
              '| Raw artifact | Backend/mode | Bytes/flows | Workers | Monitor/sample | Count/window/repeats | Echoes/s median (min–max) | CV | RTT p50/p95/p99 µs | Router CPU s (range) | RSS bytes (range) | Lost/send failures |',
              '|---|---|---|---|---|---|---|---:|---|---|---|---|']
    all_bars=[]
    for name,key,rows,s in cells:
        backend,mode,size,flows,workers,monitor,sample,count,window=key
        index.append(f"| [{name.split('/')[-1]}]({name.removeprefix('docs/')}) | {backend}/{mode} | {size}/{flows} | {workers} | {monitor}/{sample} | {count}/{window}/{len(rows)} | {span(s['rate'])} | {s['rate']['cv']:.3f} | {' / '.join(f'{s["rtt"][k]["median"]:.1f}' for k in ('p50_ns','p95_ns','p99_ns'))} | {span(s['cpu'],3)} | {span(s['rss'],0)} | {s['dropped']}/{s['failed']} |")
        all_bars.append((f"{name.split('/')[2]} {size}/{flows} {backend}/{mode} w{workers} m{int(monitor)} s{sample}",s['rate'],'#5eead4'))
    index += ['', '## All MICRO cases', '', 'Whole public process or expiry calls; generated IPv4 layouts, not real sockets. All repeat p50/p95/p99 values are summarized; CPU unmeasured, RSS uncollected.','',
              '| Artifact | Case | Bytes/flows | Repeats × samples | p50 ns (range) | p95 ns (range) | p99 ns (range) |','|---|---|---|---|---|---|---|']
    for name,data in loaded.items():
        if data.get('kind')!='MICRO':continue
        cases={}
        for run in data['runs']:
            for r in run:cases.setdefault((r['case'],r['size'],r['flows']),[]).append(r)
        for (case,size,flows),rows in sorted(cases.items()):
            values=[span(stats([r[k] for r in rows]),0) for k in ('p50_ns','p95_ns','p99_ns')]
            index.append(f"| [{name.split('/')[-1]}]({name.removeprefix('docs/')}) | {case} | {size}/{flows} | {len(rows)} × {rows[0]['n']} | {' | '.join(values)} |")
    index += ['', '## Every diagnostic repeat', '', 'Software profiler runs are separate from headline rates. Instrumented PPS is deliberately not ranked or used as throughput evidence. Per-worker CPU is unmeasured. Full symbols/syscall counts remain in linked raw records.','',
              '| Artifact | Repeat | Workers | CPU s | Software task-clock ms | Context switches | RSS bytes |','|---|---:|---:|---:|---:|---:|---:|']
    for name,data in loaded.items():
        if data.get('kind')!='PROFILE-DIAGNOSTIC':continue
        for row in data['rows']:
            metrics={r['event']:r['value'] for r in (row.get('diagnostic') or {}).get('stats',[])}
            index.append(f"| [{name.removeprefix('docs/')}]({name.removeprefix('docs/')}) | {row['repeat']} | {row.get('workers',1)} | {row['router_cpu_seconds']} | {metrics.get('task-clock','not collected by strace')} | {metrics.get('context-switches','not collected by strace')} | {row['router_sampled_peak_rss_bytes']} |")
    (DOCS/'V2-ALL-DATA.md').write_text('\n'.join(index)+'\n')
    (DOCS/'v2-all-e2e.svg').write_text(svg('All retained uninstrumented E2E cells','Different workloads/families remain separate; no cross-family speedup ranking',all_bars,'completed echoes/s'))
    long={}
    for name,key,rows,s in cells:
        if '/comparison-long/' in name:long[(key[2],Path(name).stem.split('-')[0])]=s
    rate_bars=[];tail_bars=[];comparison=[]
    for size in (64,128,512,1400):
        before=long[(size,'before')];after=long[(size,'after')]
        change=(after['rate']['median']/before['rate']['median']-1)*100
        comparison.append(f"| {size} | {span(before['rate'])} | {span(after['rate'])} | {change:+.2f}% | {2*before['rate']['median']:.0f} → {2*after['rate']['median']:.0f} | {' / '.join(f'{before["rtt"][k]["median"]:.1f} → {after["rtt"][k]["median"]:.1f}' for k in ('p50_ns','p95_ns','p99_ns'))} | {span(before['cpu'],3)} → {span(after['cpu'],3)} | {span(before['rss'],0)} → {span(after['rss'],0)} |")
        for phase,s in [('before',before),('after',after)]:
            rate_bars.append((f'{size} bytes {phase}',s['rate'],'#8aa3b8' if phase=='before' else '#5eead4'))
            tail_bars.append((f'{size} bytes {phase}',s['rtt']['p99_ns'],'#fb923c' if phase=='after' and s['rtt']['p99_ns']['median']>before['rtt']['p99_ns']['median'] else '#8aa3b8'))
    (DOCS/'v2-expiry-rate.svg').write_text(svg('Expiry optimization: completed echo rate','Matched warm 512-flow / 20,000-count runs; 3 repeats; p99 is not universally improved',rate_bars,'echoes/s'))
    (DOCS/'v2-expiry-tail.svg').write_text(svg('Expiry optimization: socket RTT p99','Orange after bars identify worse tails at 64 and 512 bytes; not one-way latency',tail_bars,'microseconds'))
    for family,title in [('multicore','Experimental workers: slower, worse tails'),('monitoring','Monitoring: measured overhead, not free')]:
        selected=[c for c in cells if f'/{family}/' in c[0]]
        for metric,unit,suffix in [('rate','echoes/s','rate'),('tail','microseconds','tail')]:
            bars=[]
            for name,key,rows,s in selected:
                label=f'{key[2]} bytes / {key[4]} workers / monitor {int(key[5])} / sample {key[6]}'
                bars.append((label,s['rate'] if metric=='rate' else s['rtt']['p99_ns'],'#fb923c' if key[4]!=1 else '#8aa3b8'))
            (DOCS/f'v2-{family}-{suffix}.svg').write_text(svg(title,'4 workers oversubscribe the approved 2-vCPU guest; bars/whiskers retain all repeats',bars,unit))
    head='59ff117a408f68500d26f562365c9d2430b16123'  # Frozen review base; reproducible outside Git.
    text=f'''# Router v2 engineering report

Generated from every explicitly reviewed raw benchmark JSON. Source baseline for
this review: `{head}`. Later review/presentation changes are in the feature PR; no main merge is authorized.
[Complete inventory, hashes, cells, MICRO cases and every diagnostic repeat](V2-ALL-DATA.md)
retain all observations. No benchmark was run by this generator.

## Engineering outcome

The expiry change is a measured throughput/CPU improvement with worse 64-byte and
512-byte p99 tails. Multicore is an experimental ownership/observability objective,
**not an optimization win**: measured throughput fell 15.68–24.69% and median p99
worsened. Keep reference workers=1 default. Safe private NAT ownership, bounded
queues, reverse port affinity and actual per-worker observability justify the
demonstrator's complexity; they do not establish scalable performance.

Implemented: validated IPv4/UDP routing and endpoint-dependent SNAT; same-second
expiry skip; pluggable owned TUN I/O; isolated worker shards; bounded queues,
backpressure and shutdown; private schema-1/2 snapshots; optional tuple-free
samples; strict loopback readers/dashboard; reproducible real packet harnesses.
Incomplete: general protocol/router support, production fault qualification,
steady fsync overhead isolation, separate worker CPU and AF_XDP. The corrected live gate passed; see evidence below.

## Matched original/final expiry comparison

All four sizes, 512 flows, 20,000 echoes/window64, three repeats before/after.
Rates count completed echoes. Completed packet traversals/s = 2 × echoes/s;
neither metric is hardware NIC line rate. RTT columns are median repeat quantiles.
No fastest-run selection. Full ranges, CPU/RSS and all smaller cells are linked.

| Total IPv4 bytes | Before echoes/s (range) | After echoes/s (range) | Change | Completed traversals/s | RTT p50 / p95 / p99 µs before → after | CPU seconds (range) | Sampled RSS bytes (range) |
|---:|---|---|---:|---|---|---|---|
'''+ '\n'.join(comparison)+'''

![All-size matched echo rates](v2-expiry-rate.svg)
![Worsened tails remain prominent](v2-expiry-tail.svg)

The frozen baseline core is identified in [optimization provenance](OPTIMIZATION-RESULTS.md).
Feature stages: `5ec52e7` audit/MICRO, `01300cc` E2E/profiles,
`0d4e818` measured expiry change, `f6679fb` worker ownership,
`59ff117` private observability/resilience. Full history remains sanitized.

## Contextual kernel comparison and all cells

[All retained uninstrumented cells](V2-ALL-DATA.md) cover sizes 64/128/512/1400,
flows 1/64/512, cold/warm, three repeats, userspace and kernel baseline. Later
userspace after runs reuse the unchanged original kernel comparison; these are
not independent new kernel measurements. Raw source artifacts remain linked,
including shorter count 1500 cells and longer count 20000 cells: do not conflate them.
[All-cell chart](v2-all-e2e.svg) displays every uninstrumented group separately.
TUN/poll/read/write/custom NAT and veth/kernel conntrack have different devices,
L2/neighbor, scheduling and NAT semantics. This is contextual system comparison,
not isolated algorithm attribution. [Exact methodology](BENCHMARK-METHODOLOGY.md).

## Worker scaling, CPU and profiles

![All 1/2/4 worker rate cells at both sizes](v2-multicore-rate.svg)
![All worker p99 cells](v2-multicore-tail.svg)

[Every worker cell, tails, CPU and RSS](V2-ALL-DATA.md) includes both sizes and all
three repeats; [measured interpretation](MULTICORE-RESULTS.md). Four workers
oversubscribe two guest CPUs plus dispatcher/endpoints. Aggregate profiles show
channels/futex, wakeup/syscall and datagram receive costs replacing part of tuple
scan share. This is sampled attribution, not a proven isolated cost breakdown.
Baseline 999-Hz expiry retain shares were 40.00/46.25/41.98%, about 80 samples/run;
separate expiry diagnostic task-clock median went 82.06 ms to 55.98 ms. Hardware
cycles/instructions are unsupported. Process CPU has 10-ms tick resolution;
RSS is sampled, not lifetime peak. Per-worker CPU is unmeasured. Instrumented PPS
is excluded from headline throughput and remains only in raw diagnostic files.

## Monitoring and privacy

![All off/on/sampled rate cells](v2-monitoring-rate.svg)
![All monitoring p99 cells](v2-monitoring-tail.svg)

All monitoring cells/counts/window/sample settings, min/max, tails, CPU and RSS
are retained in [the appendix](V2-ALL-DATA.md), with [interpretation](MONITORING-RESULTS.md).
Short cells do not isolate steady fsync/export cost. The paced >=3 s correctness
acceptance proves actual periodic writes, not free or steady-state monitoring.
Schema2 omits tuples/payloads; sampling defaults off, capped at 64 per worker. Schema1
retains explicitly sensitive reference tuples. 0700/0600 atomic bounded snapshots,
strict field validation and fixed-command loopback viewer guards remain in force.

## Correctness, resilience and security

Native Linux 30 Rust tests and 58 Python tests were verified at `59ff117`, along with
actual four-worker adversarial/overload/steady snapshot acceptance; new portable
review checks are recorded in [final review](FINAL-REVIEW.md). Exact checksum,
fragment/length, expiry/backward-clock, tuple filtering, disjoint port/capacity,
queue saturation and shutdown tests remain. Generated/fuzz inputs are portable
correctness tools, not live evidence. [Actual gates](RESILIENCE.md) distinguish
passed tests from the unrun broader OS fault campaign. Dashboard screenshots in
[monitoring results](MONITORING-RESULTS.md) show actual retained stopped data;
current/stale/offline live browser transitions passed in the retained successful run.

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

## Cost, efficiency and limits

One native Sol lane; no extra agents, installs, provider/resource changes or new
paid services in this phase. Last supplied subscription usage was 5% weekly;
that is historical, not a current quota reading. Exact dollar/token totals and
aggregate tool/call counts are unavailable and are not estimated.

IPv4/UDP only; no TCP/IPv6/fragments/L2/ICMP generation or production-readiness
claim. Wider OS fault injection, monitored panic/FD failures, SIGKILL recovery,
long randomized steady export timing and separate worker CPU remain gaps.
AF_XDP is unimplemented: AF_XDP-specific attach authority/test topology,
Ethernet/L2 semantics, UMEM/ring lifetime/ownership and real acceptance/measurement
are missing. No batching, migration, multiqueue or zero-copy performance claim.

## Reproduction and handoff

`python3 -B scripts/report_v2.py` regenerates this report, full inventory and SVGs
without packet generation/network/VM operations. Existing guest reproduction:
[benchmarks](BENCHMARK-METHODOLOGY.md), [ownership](MULTICORE-DESIGN.md),
[observability](OBSERVABILITY.md), [resilience](RESILIENCE.md).
[Architecture ownership diagram](v2-architecture.svg) distinguishes dispatcher
TUN ownership from per-worker NAT ownership.

| Category | Handoff status |
|---|---|
| Audit, portable tests and sanitized baseline | VERIFIED at recorded stages |
| Real core optimization and full retained comparisons | VERIFIED gains and tail regressions |
| Worker ownership/correctness | VERIFIED tested cases; performance regressed |
| Actual-state snapshots/privacy and adversarial overload | VERIFIED measured acceptance; wider faults CONDITIONAL/UNRUN |
| Steady monitoring cost / per-worker CPU / hardware | CONDITIONAL/UNRUN, not established |
| Live browser current→stale→offline / genuine new demo | VERIFIED retained successful sampled browser capture |
| AF_XDP / production readiness | CONDITIONAL/UNRUN; unimplemented / not claimed |
| Project code review / portable gates | VERIFIED focused review; 31 Rust / 66 Python tests |
| Costs and accounting | VERIFIED historical 5% disclosure; dollars/tokens/call totals unavailable |
| Final sanitized feature PR | Delivery for owner review; no main merge/release/license change |
'''
    (DOCS/'V2-ENGINEERING-REPORT.md').write_text(text)
    (DOCS/'v2-architecture.svg').write_text(architecture())
    return len(names),len(cells)


def architecture():
    out=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="540" viewBox="0 0 1200 540" role="img" aria-labelledby="title desc">',
         '<title id="title">Opt-in worker ownership and reverse routing</title><desc id="desc">Reference one worker stays default. Dispatcher owns both TUN files. Inside socket hash selects a bounded worker input. Replies select the owner by disjoint external destination port; the owner validates remote tuples before refresh. Workers own private NAT; bounded shared completions return to dispatcher transmit.</desc>',
         '<rect width="1200" height="540" fill="#101f26"/><g font-family="system-ui,sans-serif" fill="#edf8f5">',
         '<text x="25" y="35" font-size="22">Safe ownership demonstrator; measured multicore is slower</text>',
         '<text x="25" y="62" font-size="15">Reference workers=1 default · opt-in 4 workers oversubscribe approved 2-vCPU guest</text>',
         '<rect x="25" y="180" width="170" height="160" fill="#284050"/><text x="40" y="215">Inside / outside TUN</text><text x="40" y="245">Precreated, NO_PI</text><text x="40" y="275">No network setup</text>',
         '<rect x="230" y="125" width="330" height="290" fill="#284050"/><text x="245" y="160">Dispatcher owns both device FDs</text><text x="245" y="195">Validate → internal socket hash</text><text x="245" y="230">Reply dst port → sole shard owner</text><text x="245" y="265">Bounded try_send input queues</text><text x="245" y="300">Bounded completion queue → TX</text><text x="245" y="335">WouldBlock / full queue: counted drop</text><text x="245" y="370">Shutdown flag → join every worker</text>',
         '<path d="M195 260H230M560 180H630M560 260H630M560 340H630M560 400H630" stroke="#5eead4" stroke-width="3" fill="none"/>']
    for i in range(4):
        y=95+i*95
        out += [f'<rect x="635" y="{y}" width="530" height="80" fill="#284050"/>',f'<text x="650" y="{y+25}">Worker {i}: private Router / disjoint range P{i} and capacity C{i}</text>',f'<text x="650" y="{y+55}">Remote tuple filter before refresh · monotonic expiry · no hot NAT lock</text>']
    out += ['<text x="25" y="475">Queue occupancy, shutdown discards, actual TX and optional bounded tuple-free samples → private snapshots</text>', '<text x="25" y="510">No shared NAT allocation · no migration · no AF_XDP / zero-copy / scaling claim</text></g></svg>\n']
    return '\n'.join(out)


if __name__=='__main__':
    artifacts,cells=generate();print(f'Reported {artifacts} reviewed JSON artifacts and {cells} uninstrumented cells; no new measurements')
