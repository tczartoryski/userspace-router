//! Portable IPv4/UDP forwarding and endpoint-dependent SNAT. No socket or OS I/O.
use std::collections::BTreeMap;
use std::net::Ipv4Addr;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Side {
    Inside,
    Outside,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Route {
    pub network: Ipv4Addr,
    pub prefix: u8,
    pub side: Side,
}
impl Route {
    pub fn new(network: Ipv4Addr, prefix: u8, side: Side) -> Result<Self, &'static str> {
        if prefix > 32 {
            return Err("prefix exceeds 32");
        }
        let mask = mask(prefix);
        if u32::from(network) & !mask != 0 {
            return Err("route has host bits set");
        }
        Ok(Self {
            network,
            prefix,
            side,
        })
    }
    fn matches(&self, addr: Ipv4Addr) -> bool {
        u32::from(addr) & mask(self.prefix) == u32::from(self.network)
    }
}
fn mask(prefix: u8) -> u32 {
    if prefix == 0 {
        0
    } else {
        u32::MAX << (32 - prefix)
    }
}

#[derive(Clone, Debug)]
pub struct Config {
    pub external: Ipv4Addr,
    pub ports: (u16, u16),
    pub max_flows: usize,
    pub idle_seconds: u64,
    pub mtu: usize,
    pub routes: Vec<Route>,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(usize)]
pub enum DropReason {
    Malformed,
    Options,
    Fragment,
    Protocol,
    Checksum,
    Address,
    Ttl,
    Mtu,
    Route,
    Policy,
    Filter,
    Capacity,
    Clock,
}
pub const DROP_REASONS: [DropReason; 13] = [
    DropReason::Malformed,
    DropReason::Options,
    DropReason::Fragment,
    DropReason::Protocol,
    DropReason::Checksum,
    DropReason::Address,
    DropReason::Ttl,
    DropReason::Mtu,
    DropReason::Route,
    DropReason::Policy,
    DropReason::Filter,
    DropReason::Capacity,
    DropReason::Clock,
];
#[derive(Clone, Debug, Default)]
pub struct Counters {
    pub received: u64,
    pub forwarded: u64,
    pub expired: u64,
    pub drops: [u64; 13],
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Tuple {
    internal: Ipv4Addr,
    internal_port: u16,
    remote: Ipv4Addr,
    remote_port: u16,
}
#[derive(Clone, Debug)]
struct Flow {
    tuple: Tuple,
    last: u64,
}
#[derive(Debug)]
pub struct Forward {
    pub side: Side,
    pub packet: Vec<u8>,
}
pub struct Router {
    config: Config,
    flows: BTreeMap<u16, Flow>,
    last_time: u64,
    next_port: u16,
    pub counters: Counters,
}
impl Router {
    pub fn new(config: Config) -> Result<Self, &'static str> {
        if !unicast(config.external) || config.ports.0 == 0 || config.ports.0 > config.ports.1 {
            return Err("invalid external address or port range");
        }
        if config.max_flows == 0
            || config.max_flows > 65535
            || config.idle_seconds == 0
            || !(28..=65535).contains(&config.mtu)
        {
            return Err("invalid flow, timeout or MTU bound");
        }
        if config.routes.is_empty() || config.routes.len() > 128 {
            return Err("require 1..128 routes");
        }
        for (i, route) in config.routes.iter().enumerate() {
            Route::new(route.network, route.prefix, route.side)?;
            if config.routes[..i]
                .iter()
                .any(|r| r.network == route.network && r.prefix == route.prefix)
            {
                return Err("duplicate route");
            }
        }
        let router = Self {
            next_port: config.ports.0,
            config,
            flows: BTreeMap::new(),
            last_time: 0,
            counters: Counters::default(),
        };
        if router.forbidden_address(router.config.external) {
            return Err("external address is a configured network or broadcast");
        }
        Ok(router)
    }
    /// Bounded JSON from actual core state. Tuples are sensitive; caller controls storage.
    pub fn telemetry(&self, now: u64) -> String {
        use std::fmt::Write;
        let mut out = format!("{{\"received\":{},\"forwarded\":{},\"expired\":{},\"active\":{},\"max_flows\":{},\"ports\":[{},{}],\"idle_seconds\":{},\"routes\":[", self.counters.received, self.counters.forwarded, self.counters.expired, self.flows.len(), self.config.max_flows, self.config.ports.0, self.config.ports.1, self.config.idle_seconds);
        for (i, r) in self.config.routes.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            write!(
                out,
                "{{\"network\":\"{}/{}\",\"side\":\"{:?}\"}}",
                r.network, r.prefix, r.side
            )
            .unwrap();
        }
        out.push_str("],\"drops\":{");
        for (i, r) in DROP_REASONS.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            write!(out, "\"{r:?}\":{}", self.counters.drops[i]).unwrap();
        }
        out.push_str("},\"mappings\":[");
        for (i, (port, f)) in self.flows.iter().take(2048).enumerate() {
            if i > 0 {
                out.push(',');
            }
            write!(out, "{{\"internal\":\"{}:{}\",\"remote\":\"{}:{}\",\"external\":\"{}:{}\",\"idle_seconds\":{}}}", f.tuple.internal, f.tuple.internal_port, f.tuple.remote, f.tuple.remote_port, self.config.external, port, now.saturating_sub(f.last)).unwrap();
        }
        write!(
            out,
            "],\"mappings_truncated\":{}}}",
            self.flows.len() > 2048
        )
        .unwrap();
        out
    }
    pub fn active_flows(&self) -> usize {
        self.flows.len()
    }
    pub fn route(&self, addr: Ipv4Addr) -> Option<Side> {
        self.config
            .routes
            .iter()
            .filter(|r| r.matches(addr))
            .max_by_key(|r| r.prefix)
            .map(|r| r.side)
    }
    /// Caller supplies elapsed monotonic seconds. Backward time fails closed.
    pub fn expire(&mut self, now: u64) -> Result<(), DropReason> {
        if now < self.last_time {
            return Err(DropReason::Clock);
        }
        self.last_time = now;
        let before = self.flows.len();
        self.flows
            .retain(|_, flow| now - flow.last < self.config.idle_seconds);
        self.counters.expired = self
            .counters
            .expired
            .saturating_add((before - self.flows.len()) as u64);
        Ok(())
    }
    pub fn process(&mut self, side: Side, bytes: &[u8], now: u64) -> Result<Forward, DropReason> {
        self.counters.received = self.counters.received.saturating_add(1);
        let result = self.forward(side, bytes, now);
        match &result {
            Ok(_) => self.counters.forwarded = self.counters.forwarded.saturating_add(1),
            Err(reason) => {
                self.counters.drops[*reason as usize] =
                    self.counters.drops[*reason as usize].saturating_add(1)
            }
        }
        result
    }
    fn forbidden_address(&self, addr: Ipv4Addr) -> bool {
        !unicast(addr)
            || self.config.routes.iter().any(|r| {
                r.prefix <= 30
                    && r.prefix > 0
                    && r.matches(addr)
                    && (u32::from(addr) == u32::from(r.network)
                        || u32::from(addr) == u32::from(r.network) | !mask(r.prefix))
            })
    }
    fn forward(&mut self, side: Side, bytes: &[u8], now: u64) -> Result<Forward, DropReason> {
        let p = Packet::parse(bytes)?;
        if bytes.len() > self.config.mtu {
            return Err(DropReason::Mtu);
        }
        if self.forbidden_address(p.src) || self.forbidden_address(p.dst) {
            return Err(DropReason::Address);
        }
        if p.ttl <= 1 {
            return Err(DropReason::Ttl);
        }
        self.expire(now)?;
        let (out, src, dst, sport, dport, port) = match side {
            Side::Inside => {
                if p.src == self.config.external
                    || self.route(p.src) != Some(Side::Inside)
                    || p.dst == self.config.external
                {
                    return Err(DropReason::Policy);
                }
                let out = self.route(p.dst).ok_or(DropReason::Route)?;
                if out != Side::Outside {
                    return Err(DropReason::Policy);
                }
                let tuple = Tuple {
                    internal: p.src,
                    internal_port: p.sport,
                    remote: p.dst,
                    remote_port: p.dport,
                };
                let existing = self
                    .flows
                    .iter()
                    .find(|(_, f)| f.tuple == tuple)
                    .map(|(port, _)| *port);
                let port = match existing {
                    Some(port) => port,
                    None => {
                        if self.flows.len() >= self.config.max_flows {
                            return Err(DropReason::Capacity);
                        }
                        let count =
                            u32::from(self.config.ports.1) - u32::from(self.config.ports.0) + 1;
                        let mut free = None;
                        for _ in 0..count {
                            let candidate = self.next_port;
                            self.next_port = if candidate == self.config.ports.1 {
                                self.config.ports.0
                            } else {
                                candidate + 1
                            };
                            if !self.flows.contains_key(&candidate) {
                                free = Some(candidate);
                                break;
                            }
                        }
                        let port = free.ok_or(DropReason::Capacity)?;
                        self.flows.insert(port, Flow { tuple, last: now });
                        port
                    }
                };
                (out, self.config.external, p.dst, port, p.dport, port)
            }
            Side::Outside => {
                if p.dst != self.config.external || self.route(p.src) != Some(Side::Outside) {
                    return Err(DropReason::Policy);
                }
                let flow = self.flows.get(&p.dport).ok_or(DropReason::Filter)?;
                if flow.tuple.remote != p.src || flow.tuple.remote_port != p.sport {
                    return Err(DropReason::Filter);
                }
                let out = self.route(flow.tuple.internal).ok_or(DropReason::Route)?;
                if out != Side::Inside {
                    return Err(DropReason::Policy);
                }
                (
                    out,
                    p.src,
                    flow.tuple.internal,
                    p.sport,
                    flow.tuple.internal_port,
                    p.dport,
                )
            }
        };
        self.flows.get_mut(&port).expect("selected flow").last = now;
        let mut packet = bytes.to_vec();
        packet[8] -= 1;
        packet[12..16].copy_from_slice(&src.octets());
        packet[16..20].copy_from_slice(&dst.octets());
        packet[20..22].copy_from_slice(&sport.to_be_bytes());
        packet[22..24].copy_from_slice(&dport.to_be_bytes());
        packet[10..12].fill(0);
        let ip_sum = checksum(&packet[..20]);
        packet[10..12].copy_from_slice(&ip_sum.to_be_bytes());
        packet[26..28].fill(0);
        let udp_sum = udp_checksum(src, dst, &packet[20..]);
        packet[26..28].copy_from_slice(&if udp_sum == 0 { 0xffff } else { udp_sum }.to_be_bytes());
        Ok(Forward { side: out, packet })
    }
}
fn unicast(addr: Ipv4Addr) -> bool {
    let a = addr.octets();
    a[0] != 0 && a[0] != 127 && a[0] < 224 && !addr.is_link_local()
}
#[derive(Debug)]
pub struct Packet {
    pub src: Ipv4Addr,
    pub dst: Ipv4Addr,
    pub sport: u16,
    pub dport: u16,
    pub ttl: u8,
}
impl Packet {
    pub fn parse(b: &[u8]) -> Result<Self, DropReason> {
        if b.len() < 20 {
            return Err(DropReason::Malformed);
        }
        if b[0] >> 4 != 4 {
            return Err(DropReason::Protocol);
        }
        if b[0] & 15 < 5 {
            return Err(DropReason::Malformed);
        }
        if b[0] & 15 != 5 {
            return Err(DropReason::Options);
        }
        if usize::from(read16(b, 2)) != b.len() || b.len() < 28 {
            return Err(DropReason::Malformed);
        }
        if read16(b, 6) & 0xbfff != 0 {
            return Err(DropReason::Fragment);
        }
        if b[9] != 17 {
            return Err(DropReason::Protocol);
        }
        if checksum(&b[..20]) != 0 {
            return Err(DropReason::Checksum);
        }
        if usize::from(read16(b, 24)) != b.len() - 20 {
            return Err(DropReason::Malformed);
        }
        let src = Ipv4Addr::new(b[12], b[13], b[14], b[15]);
        let dst = Ipv4Addr::new(b[16], b[17], b[18], b[19]);
        if read16(b, 26) != 0 && udp_checksum(src, dst, &b[20..]) != 0 {
            return Err(DropReason::Checksum);
        }
        if read16(b, 20) == 0 || read16(b, 22) == 0 {
            return Err(DropReason::Malformed);
        }
        Ok(Self {
            src,
            dst,
            sport: read16(b, 20),
            dport: read16(b, 22),
            ttl: b[8],
        })
    }
}
fn read16(b: &[u8], at: usize) -> u16 {
    u16::from_be_bytes([b[at], b[at + 1]])
}
fn sum(b: &[u8]) -> u32 {
    b.chunks(2)
        .map(|c| u32::from(c[0]) * 256 + u32::from(*c.get(1).unwrap_or(&0)))
        .sum()
}
fn finish(mut sum: u32) -> u16 {
    while sum >> 16 != 0 {
        sum = (sum & 65535) + (sum >> 16);
    }
    !(sum as u16)
}
pub fn checksum(b: &[u8]) -> u16 {
    finish(sum(b))
}
pub fn udp_checksum(src: Ipv4Addr, dst: Ipv4Addr, udp: &[u8]) -> u16 {
    finish(sum(&src.octets()) + sum(&dst.octets()) + 17 + udp.len() as u32 + sum(udp))
}
