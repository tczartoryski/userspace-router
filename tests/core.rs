use std::net::Ipv4Addr;
use userspace_udp_router::*;
fn ip(s: &str) -> Ipv4Addr {
    s.parse().unwrap()
}
fn config() -> Config {
    Config {
        external: ip("198.51.100.1"),
        ports: (40000, 40002),
        max_flows: 3,
        idle_seconds: 10,
        mtu: 1500,
        routes: vec![
            Route::new(ip("0.0.0.0"), 0, Side::Outside).unwrap(),
            Route::new(ip("10.0.0.0"), 24, Side::Inside).unwrap(),
        ],
    }
}
fn router() -> Router {
    Router::new(config()).unwrap()
}
fn packet(src: &str, sport: u16, dst: &str, dport: u16, payload: &[u8]) -> Vec<u8> {
    let mut b = vec![0; 28 + payload.len()];
    b[0] = 0x45;
    let len = b.len() as u16;
    b[2..4].copy_from_slice(&len.to_be_bytes());
    b[6] = 0x40;
    b[8] = 64;
    b[9] = 17;
    b[12..16].copy_from_slice(&ip(src).octets());
    b[16..20].copy_from_slice(&ip(dst).octets());
    b[20..22].copy_from_slice(&sport.to_be_bytes());
    b[22..24].copy_from_slice(&dport.to_be_bytes());
    b[24..26].copy_from_slice(&(len - 20).to_be_bytes());
    b[28..].copy_from_slice(payload);
    repair(&mut b);
    b
}
fn repair(b: &mut [u8]) {
    b[10..12].fill(0);
    let s = checksum(&b[..20]);
    b[10..12].copy_from_slice(&s.to_be_bytes());
    b[26..28].fill(0);
    let src = Ipv4Addr::new(b[12], b[13], b[14], b[15]);
    let dst = Ipv4Addr::new(b[16], b[17], b[18], b[19]);
    let s = udp_checksum(src, dst, &b[20..]);
    b[26..28].copy_from_slice(&if s == 0 { 65535 } else { s }.to_be_bytes());
}
fn outbound(port: u16) -> Vec<u8> {
    packet("10.0.0.2", port, "198.51.100.2", 9000, b"hello")
}
fn inbound(port: u16) -> Vec<u8> {
    packet("198.51.100.2", 9000, "198.51.100.1", port, b"reply")
}
fn dropped(r: &mut Router, side: Side, b: &[u8], now: u64, reason: DropReason) {
    assert_eq!(r.process(side, b, now).unwrap_err(), reason);
}
#[test]
fn bidirectional_translation_ttl_checksums_and_payload() {
    let mut r = router();
    let f = r.process(Side::Inside, &outbound(1234), 0).unwrap();
    assert_eq!(f.side, Side::Outside);
    let p = Packet::parse(&f.packet).unwrap();
    assert_eq!(
        (p.src, p.sport, p.dst, p.dport, p.ttl),
        (ip("198.51.100.1"), 40000, ip("198.51.100.2"), 9000, 63)
    );
    assert_eq!(&f.packet[28..], b"hello");
    assert_eq!(checksum(&f.packet[..20]), 0);
    let f = r.process(Side::Outside, &inbound(40000), 1).unwrap();
    let p = Packet::parse(&f.packet).unwrap();
    assert_eq!(f.side, Side::Inside);
    assert_eq!((p.dst, p.dport, p.ttl), (ip("10.0.0.2"), 1234, 63));
    assert_eq!(&f.packet[28..], b"reply");
    assert_eq!(r.counters.forwarded, 2);
}
#[test]
fn endpoint_dependence_reuse_and_exact_remote_filter() {
    let mut r = router();
    for (dst, dport, want) in [
        ("198.51.100.2", 9000, 40000),
        ("198.51.100.3", 9000, 40001),
        ("198.51.100.2", 9001, 40002),
        ("198.51.100.2", 9000, 40000),
    ] {
        let f = r
            .process(Side::Inside, &packet("10.0.0.2", 1234, dst, dport, b"x"), 0)
            .unwrap();
        assert_eq!(Packet::parse(&f.packet).unwrap().sport, want);
    }
    dropped(
        &mut r,
        Side::Outside,
        &packet("198.51.100.3", 9000, "198.51.100.1", 40000, b"x"),
        1,
        DropReason::Filter,
    );
    dropped(
        &mut r,
        Side::Outside,
        &packet("198.51.100.2", 9001, "198.51.100.1", 40000, b"x"),
        1,
        DropReason::Filter,
    );
    dropped(
        &mut r,
        Side::Outside,
        &inbound(39999),
        1,
        DropReason::Filter,
    );
    assert_eq!(r.active_flows(), 3);
}
#[test]
fn bounded_state_ports_and_expiry_boundary() {
    let mut r = router();
    for p in 1..=3 {
        r.process(Side::Inside, &outbound(p), 0).unwrap();
    }
    dropped(&mut r, Side::Inside, &outbound(4), 9, DropReason::Capacity);
    assert_eq!(r.active_flows(), 3);
    r.expire(10).unwrap();
    assert_eq!(r.active_flows(), 0);
    assert_eq!(r.counters.expired, 3);
    dropped(
        &mut r,
        Side::Outside,
        &inbound(40000),
        10,
        DropReason::Filter,
    );
    assert_eq!(
        Packet::parse(&r.process(Side::Inside, &outbound(4), 10).unwrap().packet)
            .unwrap()
            .sport,
        40000
    );
    let mut c = config();
    c.ports = (65535, 65535);
    c.max_flows = 20;
    let mut r = Router::new(c).unwrap();
    assert_eq!(
        Packet::parse(&r.process(Side::Inside, &outbound(1), 0).unwrap().packet)
            .unwrap()
            .sport,
        65535
    );
    dropped(&mut r, Side::Inside, &outbound(2), 0, DropReason::Capacity);
}
#[test]
fn rejected_packets_do_not_refresh_flows() {
    let mut r = router();
    r.process(Side::Inside, &outbound(1), 0).unwrap();
    dropped(
        &mut r,
        Side::Outside,
        &packet("198.51.100.3", 9000, "198.51.100.1", 40000, b"x"),
        9,
        DropReason::Filter,
    );
    let mut bad = inbound(40000);
    bad[28] ^= 1;
    dropped(&mut r, Side::Outside, &bad, 9, DropReason::Checksum);
    let mut bad = inbound(40000);
    bad[8] = 1;
    repair(&mut bad);
    dropped(&mut r, Side::Outside, &bad, 9, DropReason::Ttl);
    r.expire(10).unwrap();
    assert_eq!(r.active_flows(), 0);
    r.process(Side::Inside, &outbound(1), 10).unwrap();
    r.process(Side::Outside, &inbound(40001), 19).unwrap();
    r.expire(28).unwrap();
    assert_eq!(r.active_flows(), 1);
    r.expire(29).unwrap();
    assert_eq!(r.active_flows(), 0);
}
#[test]
fn longest_prefix_routes_and_policy() {
    let mut c = config();
    c.routes
        .push(Route::new(ip("10.0.0.128"), 25, Side::Outside).unwrap());
    let mut r = Router::new(c).unwrap();
    assert_eq!(r.route(ip("10.0.0.127")), Some(Side::Inside));
    assert_eq!(r.route(ip("10.0.0.129")), Some(Side::Outside));
    dropped(
        &mut r,
        Side::Inside,
        &packet("10.0.0.129", 1, "198.51.100.2", 2, b""),
        0,
        DropReason::Policy,
    );
    dropped(
        &mut r,
        Side::Inside,
        &packet("10.0.0.2", 1, "10.0.0.3", 2, b""),
        0,
        DropReason::Policy,
    );
    dropped(
        &mut r,
        Side::Inside,
        &packet("10.0.0.2", 1, "198.51.100.1", 2, b""),
        0,
        DropReason::Policy,
    );
    dropped(&mut r, Side::Outside, &outbound(1), 0, DropReason::Policy);
    dropped(
        &mut r,
        Side::Inside,
        &packet("192.0.2.2", 1, "198.51.100.2", 2, b""),
        0,
        DropReason::Policy,
    );
    let mut c = config();
    c.routes.remove(0);
    let mut r = Router::new(c).unwrap();
    dropped(&mut r, Side::Inside, &outbound(1), 0, DropReason::Route);
}
#[test]
fn address_policy() {
    let mut r = router();
    for dst in [
        "0.0.0.1",
        "127.0.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "255.255.255.255",
        "240.0.0.1",
        "10.0.0.255",
        "10.0.0.0",
    ] {
        dropped(
            &mut r,
            Side::Inside,
            &packet("10.0.0.2", 1, dst, 2, b""),
            0,
            DropReason::Address,
        );
    }
    for src in ["10.0.0.0", "10.0.0.255", "127.0.0.1"] {
        dropped(
            &mut r,
            Side::Inside,
            &packet(src, 1, "198.51.100.2", 2, b""),
            0,
            DropReason::Address,
        );
    }
    let mut c = config();
    c.routes[1] = Route::new(ip("10.0.0.0"), 31, Side::Inside).unwrap();
    let mut r = Router::new(c).unwrap();
    r.process(
        Side::Inside,
        &packet("10.0.0.0", 1, "198.51.100.2", 2, b""),
        0,
    )
    .unwrap();
}
#[test]
fn explicit_unsupported_and_malformed_drops() {
    let mut r = router();
    for (at, value, reason) in [
        (0, 0x65, DropReason::Protocol),
        (0, 0x44, DropReason::Malformed),
        (0, 0x46, DropReason::Options),
        (9, 6, DropReason::Protocol),
        (6, 0x20, DropReason::Fragment),
        (6, 0x80, DropReason::Fragment),
        (7, 1, DropReason::Fragment),
        (8, 1, DropReason::Ttl),
        (8, 0, DropReason::Ttl),
        (2, 0xff, DropReason::Malformed),
        (24, 1, DropReason::Malformed),
        (25, 7, DropReason::Malformed),
    ] {
        let mut b = outbound(1234);
        b[at] = value;
        if at != 2 && at != 24 && at != 25 {
            repair(&mut b);
        }
        dropped(&mut r, Side::Inside, &b, 0, reason);
    }
    for n in 0..33 {
        let b = outbound(1234);
        dropped(&mut r, Side::Inside, &b[..n], 0, DropReason::Malformed);
    }
    let mut b = outbound(1234);
    b.push(0);
    dropped(&mut r, Side::Inside, &b, 0, DropReason::Malformed);
    let mut b = outbound(1234);
    b[10] ^= 1;
    dropped(&mut r, Side::Inside, &b, 0, DropReason::Checksum);
    let mut b = outbound(1234);
    b[28] ^= 1;
    dropped(&mut r, Side::Inside, &b, 0, DropReason::Checksum);
    for b in [
        packet("10.0.0.2", 0, "198.51.100.2", 1, b""),
        packet("10.0.0.2", 1, "198.51.100.2", 0, b""),
    ] {
        dropped(&mut r, Side::Inside, &b, 0, DropReason::Malformed);
    }
    assert_eq!(r.active_flows(), 0);
    assert_eq!(r.counters.received, r.counters.drops.iter().sum());
}
#[test]
fn mtu_clock_and_zero_udp_checksum() {
    let mut c = config();
    c.mtu = 28;
    let mut r = Router::new(c).unwrap();
    dropped(&mut r, Side::Inside, &outbound(1), 0, DropReason::Mtu);
    let mut r = router();
    let mut b = outbound(1);
    b[26..28].fill(0);
    let f = r.process(Side::Inside, &b, 10).unwrap();
    assert_ne!(&f.packet[26..28], &[0, 0]);
    Packet::parse(&f.packet).unwrap();
    dropped(&mut r, Side::Inside, &b, 9, DropReason::Clock);
    assert_eq!(r.expire(9), Err(DropReason::Clock));
}
#[test]
fn config_rejects_invalid_and_ambiguous_bounds() {
    assert!(Route::new(ip("10.0.0.1"), 24, Side::Inside).is_err());
    assert!(Route::new(ip("0.0.0.0"), 33, Side::Inside).is_err());
    for c in [
        Config {
            max_flows: 0,
            ..config()
        },
        Config {
            max_flows: 65536,
            ..config()
        },
        Config {
            ports: (0, 1),
            ..config()
        },
        Config {
            ports: (2, 1),
            ..config()
        },
        Config {
            idle_seconds: 0,
            ..config()
        },
        Config {
            mtu: 27,
            ..config()
        },
        Config {
            mtu: 65536,
            ..config()
        },
        Config {
            routes: vec![],
            ..config()
        },
        Config {
            external: ip("224.0.0.1"),
            ..config()
        },
    ] {
        assert!(Router::new(c).is_err());
    }
    let mut c = config();
    c.routes.push(c.routes[0]);
    assert!(Router::new(c).is_err());
    let mut c = config();
    c.routes[0].prefix = 255;
    assert!(Router::new(c).is_err());
    let c = Config {
        routes: vec![config().routes[0]; 129],
        ..config()
    };
    assert!(Router::new(c).is_err());
}
// Deterministic PRNG, no external property-test dependency.
fn random(s: &mut u64) -> u64 {
    *s ^= *s << 13;
    *s ^= *s >> 7;
    *s ^= *s << 17;
    *s
}
#[test]
fn arbitrary_bytes_and_mutated_packets_never_panic_or_exceed_bounds() {
    let mut seed = 0x0013_5724_68ab_cdef_u64;
    let mut r = router();
    for i in 0..20000 {
        let len = (random(&mut seed) % 2048) as usize;
        let mut b = vec![0; len];
        for v in &mut b {
            *v = random(&mut seed) as u8;
        }
        if i % 2 == 0 {
            b = outbound((i % 65534 + 1) as u16);
            let at = (random(&mut seed) as usize) % b.len();
            b[at] ^= random(&mut seed) as u8;
        }
        let side = if i % 3 == 0 {
            Side::Outside
        } else {
            Side::Inside
        };
        if let Ok(f) = r.process(side, &b, i / 100) {
            let p = Packet::parse(&f.packet).unwrap();
            assert_eq!(p.ttl, b[8] - 1);
            assert_eq!(f.side, Side::Outside);
            assert_eq!(checksum(&f.packet[..20]), 0);
        }
        assert!(r.active_flows() <= 3);
    }
    assert_eq!(
        r.counters.received,
        r.counters.forwarded + r.counters.drops.iter().sum::<u64>()
    );
}
#[test]
fn payload_length_properties_and_maximum_ipv4_packet() {
    let mut seed = 99;
    for len in (0..1024).chain([65507]) {
        let mut c = config();
        c.mtu = 65535;
        let mut r = Router::new(c).unwrap();
        let mut payload = vec![0; len];
        for v in &mut payload {
            *v = random(&mut seed) as u8;
        }
        let b = packet("10.0.0.2", 1234, "198.51.100.2", 9000, &payload);
        let f = r.process(Side::Inside, &b, 0).unwrap();
        let p = Packet::parse(&f.packet).unwrap();
        assert_eq!(p.sport, 40000);
        assert_eq!(&f.packet[28..], payload);
        let b = packet("198.51.100.2", 9000, "198.51.100.1", 40000, &payload);
        let f = r.process(Side::Outside, &b, 1).unwrap();
        assert_eq!(&f.packet[28..], payload);
        assert_eq!(Packet::parse(&f.packet).unwrap().dport, 1234);
    }
}
#[test]
fn independent_checksum_vectors_and_zero_result_encoding() {
    assert_eq!(
        checksum(&[0x00, 0x01, 0xf2, 0x03, 0xf4, 0xf5, 0xf6, 0xf7]),
        0x220d
    );
    assert_eq!(checksum(&[1]), 0xfeff);
    // Independently sum 16-bit pseudoheader + UDP words, including odd-byte padding.
    let b = packet("10.0.0.2", 1234, "198.51.100.2", 9000, b"abc");
    let mut words = vec![0x0a00u64, 2, 0xc633, 0x6402, 17, 11];
    words.extend(
        b[20..]
            .chunks(2)
            .map(|c| (u64::from(c[0]) << 8) | u64::from(*c.get(1).unwrap_or(&0))),
    );
    let mut sum: u64 = words.iter().sum();
    while sum > 65535 {
        sum = (sum & 65535) + (sum >> 16);
    }
    assert_eq!(sum, 65535);
    // Choose a payload producing a zero translated checksum, which must be encoded as ffff.
    let mut r = router();
    let b = packet("10.0.0.2", 1234, "198.51.100.2", 9000, &[0, 0]);
    let f = r.process(Side::Inside, &b, 0).unwrap();
    let p = Packet::parse(&f.packet).unwrap();
    let mut udp = f.packet[20..].to_vec();
    udp[6..8].fill(0);
    let needed = udp_checksum(p.src, p.dst, &udp);
    let payload = needed.to_be_bytes();
    let f = r
        .process(
            Side::Inside,
            &packet("10.0.0.2", 1234, "198.51.100.2", 9000, &payload),
            0,
        )
        .unwrap();
    assert_eq!(&f.packet[26..28], &[255, 255]);
    Packet::parse(&f.packet).unwrap();
}

#[test]
fn every_fragment_bit_is_rejected_and_df_is_supported() {
    let mut r = router();
    for bit in 0..16 {
        if bit == 14 {
            continue;
        }
        let mut b = outbound(1234);
        b[6..8].copy_from_slice(&(1u16 << bit).to_be_bytes());
        repair(&mut b);
        dropped(&mut r, Side::Inside, &b, 0, DropReason::Fragment);
    }
    r.process(Side::Inside, &outbound(1234), 0).unwrap();
    let mut b = outbound(1234);
    b[6..8].fill(0);
    repair(&mut b);
    r.process(Side::Inside, &b, 0).unwrap();
}

#[test]
fn single_bit_corruption_is_detected_and_internal_hosts_are_distinct() {
    let mut r = router();
    let original = outbound(1234);
    for at in 0..original.len() {
        for bit in 0..8 {
            let mut b = original.clone();
            b[at] ^= 1 << bit;
            assert!(
                r.process(Side::Inside, &b, 0).is_err(),
                "byte {at} bit {bit}"
            );
        }
    }
    assert_eq!(r.active_flows(), 0);
    for (host, want) in [("10.0.0.2", 40000), ("10.0.0.3", 40001)] {
        let f = r
            .process(
                Side::Inside,
                &packet(host, 1234, "198.51.100.2", 9000, b""),
                0,
            )
            .unwrap();
        assert_eq!(Packet::parse(&f.packet).unwrap().sport, want);
        let f = r.process(Side::Outside, &inbound(want), 0).unwrap();
        assert_eq!(Packet::parse(&f.packet).unwrap().dst, ip(host));
    }
    r.expire(u64::MAX).unwrap();
    assert_eq!(r.active_flows(), 0);
    r.process(Side::Inside, &original, u64::MAX).unwrap();
    r.expire(u64::MAX).unwrap();
    assert_eq!(r.active_flows(), 1);
}

#[test]
fn configured_external_network_or_broadcast_cannot_be_emitted() {
    for external in ["198.51.100.0", "198.51.100.255"] {
        let mut c = config();
        c.external = ip(external);
        c.routes
            .push(Route::new(ip("198.51.100.0"), 24, Side::Outside).unwrap());
        assert!(Router::new(c).is_err());
    }
}

// Synthetic core-state telemetry checks; these do not exercise TUN or live UDP.
#[test]
fn telemetry_reports_real_routes_mappings_counters_and_expiry() {
    let mut r = router();
    r.process(Side::Inside, &outbound(1234), 4).unwrap();
    r.process(Side::Inside, &outbound(4321), 5).unwrap();
    dropped(
        &mut r,
        Side::Outside,
        &inbound(39999),
        6,
        DropReason::Filter,
    );
    let text = r.telemetry(8);
    assert!(text.starts_with("{\"received\":3,\"forwarded\":2,\"expired\":0,\"active\":2,\"max_flows\":3,\"ports\":[40000,40002],\"idle_seconds\":10,"));
    assert!(text.contains("\"routes\":[{\"network\":\"0.0.0.0/0\",\"side\":\"Outside\"},{\"network\":\"10.0.0.0/24\",\"side\":\"Inside\"}]"));
    assert!(text.contains("{\"internal\":\"10.0.0.2:1234\",\"remote\":\"198.51.100.2:9000\",\"external\":\"198.51.100.1:40000\",\"idle_seconds\":4}"));
    assert!(text.contains("\"external\":\"198.51.100.1:40001\",\"idle_seconds\":3"));
    for reason in DROP_REASONS {
        let count = if reason == DropReason::Filter { 1 } else { 0 };
        assert!(text.contains(&format!("\"{reason:?}\":{count}")));
    }
    assert!(text.ends_with("],\"mappings_truncated\":false}"));
    // Reading telemetry must neither expire nor refresh mappings; backward display time saturates.
    assert!(r.telemetry(0).contains("\"idle_seconds\":0}"));
    r.expire(14).unwrap();
    assert!(r.telemetry(14).contains("\"expired\":1,\"active\":1"));
    r.expire(15).unwrap();
    let text = r.telemetry(15);
    assert!(text.contains("\"expired\":2,\"active\":0"));
    assert!(text.ends_with("\"mappings\":[],\"mappings_truncated\":false}"));
}

#[test]
fn telemetry_mapping_limit_is_exact_and_output_is_bounded() {
    let mut c = config();
    c.ports = (1, 65535);
    c.max_flows = 65535;
    let mut r = Router::new(c).unwrap();
    for port in 1..=2049 {
        r.process(Side::Inside, &outbound(port), 0).unwrap();
        if port == 2048 {
            let text = r.telemetry(u64::MAX);
            assert_eq!(text.matches("\"internal\":").count(), 2048);
            assert!(text.ends_with("\"mappings_truncated\":false}"));
        }
    }
    let text = r.telemetry(u64::MAX);
    assert!(text.contains("\"active\":2049"));
    assert_eq!(text.matches("\"internal\":").count(), 2048);
    assert!(text.contains("\"internal\":\"10.0.0.2:2048\""));
    assert!(!text.contains("\"internal\":\"10.0.0.2:2049\""));
    assert!(text.ends_with("\"mappings_truncated\":true}"));
    assert!(text.len() < 1048576);
    assert!(text.is_ascii());
    // Saturated counters remain represented without truncation or signed conversion.
    r.counters.received = u64::MAX;
    assert!(r
        .telemetry(0)
        .starts_with("{\"received\":18446744073709551615,"));
}
