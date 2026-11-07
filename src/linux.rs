//! Linux ABI only: attach to persistent TUN devices; never configure networking.
#![cfg_attr(not(target_os = "linux"), allow(dead_code))]
#[cfg(all(
    target_os = "linux",
    not(any(target_arch = "x86_64", target_arch = "aarch64"))
))]
compile_error!("Linux ABI constants are supported only on x86_64 and aarch64");
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;
use userspace_udp_router::{Config, Route, Router, Side, DROP_REASONS};

#[repr(C)]
struct PollFd {
    fd: i32,
    events: i16,
    revents: i16,
}
#[repr(C)]
struct CapHeader {
    version: u32,
    pid: i32,
}
#[repr(C)]
#[derive(Clone, Copy)]
struct CapData {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}
unsafe extern "C" {
    fn ioctl(fd: i32, request: std::os::raw::c_ulong, ...) -> i32;
    fn fcntl(fd: i32, command: i32, ...) -> i32;
    fn poll(fds: *mut PollFd, nfds: std::os::raw::c_ulong, timeout: i32) -> i32;
    fn geteuid() -> u32;
    fn capset(header: *const CapHeader, data: *const CapData) -> i32;
    fn signal(sig: i32, handler: extern "C" fn(i32)) -> usize;
}
static STOP: AtomicBool = AtomicBool::new(false);
extern "C" fn stop(_: i32) {
    STOP.store(true, Ordering::Relaxed);
}
fn drop_capabilities() -> io::Result<()> {
    let header = CapHeader {
        version: 0x2008_0522,
        pid: 0,
    };
    let data = [CapData {
        effective: 0,
        permitted: 0,
        inheritable: 0,
    }; 2];
    // SAFETY: kernel reads exactly the header and two initialized v3 capability records.
    if unsafe { capset(&header, data.as_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}
fn attach(name: &str) -> io::Result<File> {
    if let Some(fd) = name.strip_prefix("fd:") {
        let fd: i32 = fd.parse().map_err(io::Error::other)?;
        if fd < 3 {
            return Err(io::Error::other("inherited fd must be at least 3"));
        }
        // SAFETY: F_GETFL takes no optional argument and does not mutate fd.
        let flags = unsafe { fcntl(fd, 3) };
        if flags < 0 {
            return Err(io::Error::last_os_error());
        }
        if flags & 3 != 2 {
            return Err(io::Error::other("TUN fd must be read/write"));
        }
        let mut request = [0u8; 40];
        // SAFETY: writable ifreq-sized buffer for TUNGETIFF on supplied fd.
        if unsafe { ioctl(fd, 0x8004_54d2, request.as_mut_ptr()) } < 0 {
            return Err(io::Error::last_os_error());
        }
        let tun_flags = i16::from_ne_bytes([request[16], request[17]]) as u16;
        if tun_flags & !0x0800 != 0x1001 {
            return Err(io::Error::other("fd must be single-queue TUN/NO_PI"));
        }
        // SAFETY: F_SETFL accepts an integer flags argument for a valid fd.
        if unsafe { fcntl(fd, 4, flags | 0x800) } < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: CLI explicitly transfers ownership of each distinct inherited fd.
        return Ok(unsafe { File::from_raw_fd(fd) });
    }
    if name.is_empty()
        || name.len() >= 16
        || !name
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"_-".contains(&c))
    {
        return Err(io::Error::other("invalid TUN interface name"));
    }
    // Check existence/type first. Dropped capabilities prevent TUNSETIFF creating a
    // replacement device even if the precreated interface disappears in this window.
    let flags = std::fs::read_to_string(format!("/sys/class/net/{name}/tun_flags"))?;
    let flags =
        u32::from_str_radix(flags.trim().trim_start_matches("0x"), 16).map_err(io::Error::other)?;
    if flags & !0x0800 != 0x1001 {
        return Err(io::Error::other(
            "requires persistent single-queue IFF_TUN|IFF_NO_PI device",
        ));
    }
    if flags & 0x0800 == 0 {
        return Err(io::Error::other("TUN must be persistent and precreated"));
    }
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .custom_flags(0x800)
        .open("/dev/net/tun")?;
    // Linux ifreq: IFNAMSIZ name followed by short flags, union padded to 24
    // bytes on 64-bit / 16 on 32-bit. 40 initialized bytes suffice on either ABI.
    let mut request = [0u8; 40];
    request[..name.len()].copy_from_slice(name.as_bytes());
    request[16..18].copy_from_slice(&0x1001_i16.to_ne_bytes());
    // SAFETY: valid fd and writable ifreq-sized buffer for Linux TUNSETIFF.
    if unsafe { ioctl(file.as_raw_fd(), 0x4004_54ca, request.as_mut_ptr()) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(file)
}
fn check_distinct(files: &[File; 2]) -> io::Result<()> {
    let mut names = [[0u8; 40]; 2];
    for i in 0..2 {
        // SAFETY: TUNGETIFF writes to a full initialized ifreq buffer.
        if unsafe { ioctl(files[i].as_raw_fd(), 0x8004_54d2, names[i].as_mut_ptr()) } < 0 {
            return Err(io::Error::last_os_error());
        }
    }
    if names[0][..16] == names[1][..16] {
        return Err(io::Error::other(
            "TUN device names must differ, including across namespaces",
        ));
    }
    Ok(())
}
const HELP: &str = "Usage: udp-router --inside NAME --outside NAME --external IPv4 --route CIDR=inside --route CIDR=outside [--ports FIRST-LAST] [--max-flows N] [--idle-seconds N] [--mtu N] [--report-seconds N] [--snapshot PRIVATE_DIRECTORY/FILE]\nAttach only to precreated persistent single-queue TUN/NO_PI devices owned by the caller. Alternatively use --inside-fd FD and --outside-fd FD for preattached devices. All process capabilities are dropped before attachment. No routes, addresses, firewall rules or forwarding sysctls are changed.";
fn parse() -> Result<(String, String, Config, u64, Option<String>), String> {
    let mut snapshot = None;
    let mut inside = None;
    let mut outside = None;
    let mut external = None;
    let mut ports = (40000, 49999);
    let mut max_flows = 4096;
    let mut idle_seconds = 60;
    let mut mtu = 1500;
    let mut report = 5;
    let mut routes = Vec::new();
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--help" {
            println!("{HELP}");
            std::process::exit(0);
        }
        let value = args
            .next()
            .ok_or_else(|| format!("missing value for {arg}\n{HELP}"))?;
        match arg.as_str() {
            "--inside-fd" if inside.is_none() => {
                inside = Some(format!(
                    "fd:{}",
                    value.parse::<i32>().map_err(|_| "invalid fd")?
                ))
            }
            "--outside-fd" if outside.is_none() => {
                outside = Some(format!(
                    "fd:{}",
                    value.parse::<i32>().map_err(|_| "invalid fd")?
                ))
            }
            "--inside" if inside.is_none() && !value.contains(':') => inside = Some(value),
            "--outside" if outside.is_none() && !value.contains(':') => outside = Some(value),
            "--external" if external.is_none() => {
                external = Some(value.parse().map_err(|_| "invalid external IPv4")?)
            }
            "--snapshot" if snapshot.is_none() => snapshot = Some(value),
            "--ports" => {
                let (a, b) = value.split_once('-').ok_or("ports must be FIRST-LAST")?;
                ports = (
                    a.parse().map_err(|_| "invalid port")?,
                    b.parse().map_err(|_| "invalid port")?,
                );
            }
            "--max-flows" => max_flows = value.parse().map_err(|_| "invalid max-flows")?,
            "--idle-seconds" => idle_seconds = value.parse().map_err(|_| "invalid idle seconds")?,
            "--mtu" => mtu = value.parse().map_err(|_| "invalid MTU")?,
            "--report-seconds" => report = value.parse().map_err(|_| "invalid report seconds")?,
            "--route" => {
                if routes.len() >= 128 {
                    return Err("too many routes".into());
                }
                let (cidr, side) = value
                    .split_once('=')
                    .ok_or("route must be CIDR=inside|outside")?;
                let side = match side {
                    "inside" => Side::Inside,
                    "outside" => Side::Outside,
                    _ => return Err("invalid route side".into()),
                };
                let (addr, prefix) = cidr.split_once('/').ok_or("missing route prefix")?;
                routes.push(Route::new(
                    addr.parse().map_err(|_| "invalid route IPv4")?,
                    prefix.parse().map_err(|_| "invalid route prefix")?,
                    side,
                )?);
            }
            _ => return Err(format!("unknown or duplicate argument: {arg}\n{HELP}")),
        }
    }
    let inside = inside.ok_or("missing --inside")?;
    let outside = outside.ok_or("missing --outside")?;
    if inside == outside || report == 0 {
        return Err("interfaces must differ; reporting interval must be positive".into());
    }
    Ok((
        inside,
        outside,
        Config {
            external: external.ok_or("missing --external")?,
            ports,
            max_flows,
            idle_seconds,
            mtu,
            routes,
        },
        report,
        snapshot,
    ))
}
fn report(router: &Router, io_drops: u64) {
    eprint!(
        "received={} forwarded={} active={} expired={} io_drops={}",
        router.counters.received,
        router.counters.forwarded,
        router.active_flows(),
        router.counters.expired,
        io_drops
    );
    for reason in DROP_REASONS {
        eprint!(" {reason:?}={}", router.counters.drops[reason as usize]);
    }
    eprintln!();
}
fn send(file: &mut File, packet: &[u8], io_drops: &mut u64) -> io::Result<()> {
    // One write is one packet: never write_all a short TUN write.
    loop {
        match file.write(packet) {
            Ok(n) if n == packet.len() => return Ok(()),
            Ok(_) => return Err(io::Error::other("short TUN packet write")),
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                *io_drops = io_drops.saturating_add(1);
                return Ok(());
            }
            Err(e) => return Err(e),
        }
    }
}
pub fn run() -> Result<(), Box<dyn std::error::Error>> {
    let (inside, outside, config, interval, snapshot) = parse().map_err(io::Error::other)?;
    let mut router = Router::new(config).map_err(io::Error::other)?;
    drop_capabilities()?;
    let mut files = [attach(&inside)?, attach(&outside)?];
    check_distinct(&files)?;
    let interfaces: Vec<String> = files
        .iter()
        .map(|f| {
            let mut req = [0u8; 40];
            // SAFETY: full writable ifreq buffer and live TUN descriptor.
            unsafe {
                ioctl(f.as_raw_fd(), 0x8004_54d2, req.as_mut_ptr());
            }
            String::from_utf8_lossy(&req[..16])
                .trim_end_matches('\0')
                .to_string()
        })
        .collect();
    if let Some(ref path) = snapshot {
        let parent = std::path::Path::new(path)
            .parent()
            .ok_or("snapshot requires private parent directory")?;
        use std::os::unix::fs::MetadataExt;
        let m = std::fs::symlink_metadata(parent)?;
        // SAFETY: geteuid has no arguments or memory effects.
        let owner = unsafe { geteuid() };
        if !m.is_dir() || m.mode() & 0o077 != 0 || m.uid() != owner {
            return Err("snapshot parent must be private (0700)".into());
        }
        eprintln!("NOTICE: telemetry contains sensitive internal and remote tuples");
    }
    // SAFETY: handlers only set a lock-free atomic and never call non-signal-safe I/O.
    unsafe {
        if signal(2, stop) == usize::MAX || signal(15, stop) == usize::MAX {
            return Err(io::Error::last_os_error().into());
        }
    }
    let mut fds: [PollFd; 2] = files.each_ref().map(|file| PollFd {
        fd: file.as_raw_fd(),
        events: 1,
        revents: 0,
    });
    let start = Instant::now();
    let mut last_report = 0;
    let mut io_drops = 0;
    let mut buffer = [0u8; 65536];
    eprintln!("attached inside={inside} outside={outside}; userspace forwarding ready");
    while !STOP.load(Ordering::Relaxed) {
        // SAFETY: fds points to two live initialized pollfd records.
        let rc = unsafe { poll(fds.as_mut_ptr(), 2, 250) };
        if rc < 0 {
            let err = io::Error::last_os_error();
            if err.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(err.into());
        }
        let now = start.elapsed().as_secs();
        router
            .expire(now)
            .map_err(|_| io::Error::other("monotonic clock regressed"))?;
        for i in 0..2 {
            if fds[i].revents & (8 | 16 | 32) != 0 {
                return Err(io::Error::other("TUN poll error/hangup").into());
            }
            if fds[i].revents & 1 == 0 {
                continue;
            }
            let n = match files[i].read(&mut buffer) {
                Ok(0) => return Err(io::Error::other("TUN EOF").into()),
                Ok(n) => n,
                Err(e)
                    if matches!(
                        e.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                    ) =>
                {
                    continue
                }
                Err(e) => return Err(e.into()),
            };
            let side = if i == 0 { Side::Inside } else { Side::Outside };
            if let Ok(forward) = router.process(side, &buffer[..n], now) {
                let out = if forward.side == Side::Inside { 0 } else { 1 };
                send(&mut files[out], &forward.packet, &mut io_drops)?;
            }
        }
        if now - last_report >= interval {
            snapshot_write(
                snapshot.as_deref(),
                &router,
                &interfaces,
                now,
                io_drops,
                true,
            )?;
            report(&router, io_drops);
            last_report = now;
        }
    }
    snapshot_write(
        snapshot.as_deref(),
        &router,
        &interfaces,
        start.elapsed().as_secs(),
        io_drops,
        false,
    )?;
    report(&router, io_drops);
    Ok(())
}

fn snapshot_write(
    path: Option<&str>,
    router: &Router,
    interfaces: &[String],
    now: u64,
    io_drops: u64,
    running: bool,
) -> io::Result<()> {
    let Some(path) = path else {
        return Ok(());
    };
    // Interface names are validated here before JSON interpolation, including inherited FDs.
    if interfaces.iter().any(|n| {
        !n.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
    }) {
        return Err(io::Error::other("unsafe interface name"));
    }
    let unix = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(io::Error::other)?
        .as_secs();
    let data = format!("{{\"schema\":1,\"unix_seconds\":{unix},\"uptime_seconds\":{now},\"running\":{running},\"io_drops\":{io_drops},\"interfaces\":[\"{}\",\"{}\"],\"core\":{}}}\n", interfaces[0], interfaces[1], router.telemetry(now));
    if data.len() > 1_048_576 {
        return Err(io::Error::other("snapshot size bound"));
    }
    let tmp = format!("{path}.{}.tmp", std::process::id());
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&tmp)?;
        file.write_all(data.as_bytes())?;
        file.sync_all()?;
        std::fs::rename(&tmp, path)
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(tmp);
    }
    result
}
