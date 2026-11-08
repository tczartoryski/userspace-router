//! MICRO benchmark only: no sockets, TUN, kernel comparator or end-to-end rates.
use std::{hint::black_box, net::Ipv4Addr, time::Instant};
use userspace_udp_router::{checksum, udp_checksum, Config, Packet, Route, Router, Side};
fn ip(s: &str) -> Ipv4Addr {
    s.parse().unwrap()
}
fn router(flows: usize) -> Router {
    Router::new(Config {
        external: ip("198.51.100.1"),
        ports: (40000, 49999),
        max_flows: flows,
        idle_seconds: 60,
        mtu: 1500,
        routes: vec![
            Route::new(ip("0.0.0.0"), 0, Side::Outside).unwrap(),
            Route::new(ip("10.0.0.0"), 24, Side::Inside).unwrap(),
        ],
    })
    .unwrap()
}
fn packet(size: usize, flow: usize, reverse: bool) -> Vec<u8> {
    let mut b = vec![0x5a; size];
    b[..28].fill(0);
    b[0] = 0x45;
    b[2..4].copy_from_slice(&(size as u16).to_be_bytes());
    b[6] = 0x40;
    b[8] = 64;
    b[9] = 17;
    let (src, dst, sport, dport) = if reverse {
        (
            ip("198.51.100.2"),
            ip("198.51.100.1"),
            9000,
            40000 + flow as u16,
        )
    } else {
        (ip("10.0.0.2"), ip("198.51.100.2"), 1 + flow as u16, 9000)
    };
    b[12..16].copy_from_slice(&src.octets());
    b[16..20].copy_from_slice(&dst.octets());
    b[20..22].copy_from_slice(&sport.to_be_bytes());
    b[22..24].copy_from_slice(&dport.to_be_bytes());
    b[24..26].copy_from_slice(&((size - 20) as u16).to_be_bytes());
    let sum = checksum(&b[..20]);
    b[10..12].copy_from_slice(&sum.to_be_bytes());
    let sum = udp_checksum(src, dst, &b[20..]);
    b[26..28].copy_from_slice(&if sum == 0 { 65535 } else { sum }.to_be_bytes());
    Packet::parse(&b).unwrap();
    b
}
fn emit(case: &str, size: usize, flows: usize, mut samples: Vec<u64>, wall: u128) {
    samples.sort_unstable();
    let n = samples.len();
    let q = |p: usize| samples[(n * p).div_ceil(100).saturating_sub(1)];
    println!("{{\"schema\":1,\"kind\":\"MICRO\",\"case\":\"{case}\",\"size\":{size},\"flows\":{flows},\"n\":{n},\"p50_ns\":{},\"p95_ns\":{},\"p99_ns\":{},\"sum_ns\":{},\"wall_ns\":{wall},\"cpu_ns\":null,\"rss_bytes\":null}}",q(50),q(95),q(99),samples.iter().map(|x|u128::from(*x)).sum::<u128>());
}
fn main() {
    let budget = Instant::now();
    let args: Vec<_> = std::env::args().skip(1).collect();
    assert!(
        args.len() <= 2,
        "usage: core_bench [samples 1..2000] [flows 1..1000]"
    );
    let n = args
        .first()
        .map(|s| s.parse::<usize>().unwrap())
        .unwrap_or(128);
    assert!((1..=2000).contains(&n));
    let flows = if let Some(s) = args.get(1) {
        let f = s.parse::<usize>().unwrap();
        assert!((1..=1000).contains(&f));
        vec![f]
    } else {
        vec![1, 64, 512]
    };
    let start = Instant::now();
    let mut calibration = Vec::with_capacity(n);
    for _ in 0..n {
        let t = Instant::now();
        black_box(());
        calibration.push(t.elapsed().as_nanos() as u64);
    }
    emit("timestamp", 0, 0, calibration, start.elapsed().as_nanos());
    for size in [64, 128, 512, 1400] {
        for &f in &flows {
            let outbound: Vec<_> = (0..f).map(|i| packet(size, i, false)).collect();
            let reverse: Vec<_> = (0..f).map(|i| packet(size, i, true)).collect();
            for case in [
                "cold_allocation",
                "warm_outbound",
                "reverse_lookup",
                "expiry",
            ] {
                let mut r = router(f);
                if case == "warm_outbound" || case == "reverse_lookup" {
                    for b in &outbound {
                        let out = r.process(Side::Inside, b, 0).unwrap();
                        Packet::parse(&out.packet).unwrap();
                    }
                }
                let wall = Instant::now();
                let mut samples = Vec::with_capacity(n);
                for i in 0..n {
                    assert!(
                        budget.elapsed().as_secs() < 90,
                        "90 second benchmark budget"
                    );
                    // Setup excluded from per-operation latency, included in case wall time.
                    if case == "cold_allocation" || case == "expiry" {
                        r = router(f);
                        let count = if case == "expiry" { f } else { f - 1 };
                        for b in outbound.iter().take(count) {
                            black_box(r.process(Side::Inside, b, 0).unwrap());
                        }
                    }
                    let t = Instant::now();
                    if case == "expiry" {
                        r.expire(black_box(60)).unwrap();
                        black_box(r.active_flows());
                    } else {
                        let (side, b) = if case == "reverse_lookup" {
                            (Side::Outside, &reverse[i % f])
                        } else {
                            (
                                Side::Inside,
                                &outbound[if case == "cold_allocation" {
                                    f - 1
                                } else {
                                    i % f
                                }],
                            )
                        };
                        // Output destruction is inside timing, matching the caller's owned result lifecycle.
                        black_box(r.process(side, black_box(b), 0).unwrap());
                    }
                    samples.push(t.elapsed().as_nanos() as u64);
                    if case == "expiry" {
                        assert_eq!(r.active_flows(), 0);
                        assert_eq!(r.counters.expired, f as u64);
                    }
                }
                emit(case, size, f, samples, wall.elapsed().as_nanos());
            }
        }
    }
}
