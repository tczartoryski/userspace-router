//! Bounded dispatcher/worker ownership; each thread exclusively owns its Router.
use crate::{packet_io::MAX_PACKET_BYTES, Config, Counters, Forward, Packet, Router, Side};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    mpsc::{self, Receiver, SyncSender, TrySendError},
    Arc, Mutex,
};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

#[derive(Clone, Debug)]
pub struct Shards {
    pub configs: Vec<Config>,
}
impl Shards {
    pub fn new(config: &Config, workers: usize) -> Result<Self, &'static str> {
        Router::new(config.clone())?;
        let ports = usize::from(config.ports.1) - usize::from(config.ports.0) + 1;
        let capacity = config.max_flows.min(ports);
        if !(1..=32).contains(&workers) || workers > capacity {
            return Err("workers require positive port/capacity shares (1..32)");
        }
        let mut configs = Vec::with_capacity(workers);
        let mut first = usize::from(config.ports.0);
        for i in 0..workers {
            let length = ports / workers + usize::from(i < ports % workers);
            let mut child = config.clone();
            child.ports = (first as u16, (first + length - 1) as u16);
            child.max_flows = capacity / workers + usize::from(i < capacity % workers);
            Router::new(child.clone())?;
            configs.push(child);
            first += length;
        }
        Ok(Self { configs })
    }
    pub fn owner(&self, side: Side, p: &Packet) -> usize {
        if side == Side::Outside {
            self.configs
                .iter()
                .position(|c| (c.ports.0..=c.ports.1).contains(&p.dport))
                .unwrap_or(0)
        } else {
            // Fixed FNV-1a over the internal socket, independent of payload/remote.
            let mut hash = 0xcbf29ce484222325u64;
            for byte in p.src.octets().into_iter().chain(p.sport.to_be_bytes()) {
                hash = (hash ^ u64::from(byte)).wrapping_mul(0x100000001b3);
            }
            (hash % self.configs.len() as u64) as usize
        }
    }
}
#[derive(Clone, Debug, Default)]
pub struct WorkerReport {
    pub counters: Counters,
    pub active: usize,
    pub output_drops: u64,
    pub shutdown_drops: u64,
}
#[derive(Clone, Debug, Default)]
pub struct Summary {
    pub workers: Vec<WorkerReport>,
    pub counters: Counters,
    pub active: usize,
    pub queue_drops: u64,
}
impl Summary {
    fn add(&mut self, report: WorkerReport) {
        self.counters.received = self
            .counters
            .received
            .saturating_add(report.counters.received);
        self.counters.forwarded = self
            .counters
            .forwarded
            .saturating_add(report.counters.forwarded);
        self.counters.expired = self
            .counters
            .expired
            .saturating_add(report.counters.expired);
        for (dst, src) in self.counters.drops.iter_mut().zip(report.counters.drops) {
            *dst = dst.saturating_add(src);
        }
        self.active += report.active;
        self.queue_drops = self
            .queue_drops
            .saturating_add(report.output_drops)
            .saturating_add(report.shutdown_drops);
        self.workers.push(report);
    }
}
enum Task {
    Packet(Side, Vec<u8>),
    #[cfg(test)]
    Panic,
}
struct Worker {
    sender: Option<SyncSender<Task>>,
    join: Option<JoinHandle<WorkerReport>>,
    report: Arc<Mutex<WorkerReport>>,
}
pub struct Pool {
    shards: Shards,
    workers: Vec<Worker>,
    outputs: Receiver<Forward>,
    stop: Arc<AtomicBool>,
    rejected: Counters,
    input_drops: u64,
}
fn worker_loop(
    router: &mut Router,
    input: Receiver<Task>,
    output: SyncSender<Forward>,
    stop: Arc<AtomicBool>,
    epoch: Instant,
    report: Arc<Mutex<WorkerReport>>,
    wake: Arc<dyn Fn() + Send + Sync>,
) -> WorkerReport {
    let mut result = WorkerReport::default();
    let mut published = Instant::now();
    while !stop.load(Ordering::Relaxed) {
        let _ = router.expire(epoch.elapsed().as_secs());
        match input.recv_timeout(Duration::from_millis(20)) {
            Ok(Task::Packet(side, bytes)) => {
                if let Ok(packet) = router.process(side, &bytes, epoch.elapsed().as_secs()) {
                    if output.try_send(packet).is_err() {
                        result.output_drops = result.output_drops.saturating_add(1);
                    }
                    wake();
                }
            }
            #[cfg(test)]
            Ok(Task::Panic) => panic!("worker fault injection"),
            Err(mpsc::RecvTimeoutError::Disconnected) => break,
            Err(mpsc::RecvTimeoutError::Timeout) => {
                let _ = router.expire(epoch.elapsed().as_secs());
            }
        }
        if published.elapsed() >= Duration::from_millis(250) {
            result.counters = router.counters.clone();
            result.active = router.active_flows();
            *report.lock().expect("worker report poisoned") = result.clone();
            published = Instant::now();
        }
    }
    while input.try_recv().is_ok() {
        result.shutdown_drops = result.shutdown_drops.saturating_add(1);
    }
    result.counters = router.counters.clone();
    result.active = router.active_flows();
    result
}
impl Pool {
    pub fn new(
        config: Config,
        workers: usize,
        queue: usize,
        epoch: Instant,
        wake: Arc<dyn Fn() + Send + Sync>,
    ) -> Result<Self, &'static str> {
        if !(1..=1024).contains(&queue) {
            return Err("queue requires 1..1024 slots");
        }
        let shards = Shards::new(&config, workers)?;
        if (workers + 1) * queue > 4096 {
            return Err("total queue slots exceed 4096");
        }
        let (output, outputs) = mpsc::sync_channel(queue);
        let stop = Arc::new(AtomicBool::new(false));
        let mut pool = Self {
            shards,
            workers: Vec::new(),
            outputs,
            stop,
            rejected: Counters::default(),
            input_drops: 0,
        };
        for config in &pool.shards.configs {
            let mut router = Router::new(config.clone())?;
            let (sender, input) = mpsc::sync_channel(queue);
            let flag = pool.stop.clone();
            let output = output.clone();
            let wake = wake.clone();
            let report = Arc::new(Mutex::new(WorkerReport::default()));
            let shared = report.clone();
            let join = thread::Builder::new()
                .name("router-worker".into())
                .spawn(move || worker_loop(&mut router, input, output, flag, epoch, shared, wake))
                .map_err(|_| "worker spawn failed")?;
            pool.workers.push(Worker {
                sender: Some(sender),
                join: Some(join),
                report,
            });
        }
        Ok(pool)
    }
    pub fn healthy(&self) -> bool {
        self.workers
            .iter()
            .all(|w| w.join.as_ref().is_some_and(|j| !j.is_finished()))
    }
    pub fn submit(&mut self, side: Side, bytes: Vec<u8>) -> Result<(), &'static str> {
        if !self.healthy() {
            return Err("worker exited");
        }
        let parsed = if bytes.capacity() > MAX_PACKET_BYTES {
            Err(crate::DropReason::Malformed)
        } else {
            Packet::parse(&bytes)
        };
        let packet = match parsed {
            Ok(packet) => packet,
            Err(reason) => {
                self.rejected.received = self.rejected.received.saturating_add(1);
                self.rejected.drops[reason as usize] =
                    self.rejected.drops[reason as usize].saturating_add(1);
                return Ok(());
            }
        };
        let owner = self.shards.owner(side, &packet);
        match self.workers[owner]
            .sender
            .as_ref()
            .ok_or("pool stopped")?
            .try_send(Task::Packet(side, bytes))
        {
            Ok(()) => Ok(()),
            Err(TrySendError::Full(_)) => {
                self.input_drops = self.input_drops.saturating_add(1);
                Ok(())
            }
            Err(TrySendError::Disconnected(_)) => Err("worker disconnected"),
        }
    }
    pub fn receive(&self) -> Option<Forward> {
        self.outputs.try_recv().ok()
    }
    pub fn summary(&self) -> Result<Summary, &'static str> {
        let mut result = Summary {
            counters: self.rejected.clone(),
            queue_drops: self.input_drops,
            ..Summary::default()
        };
        for w in &self.workers {
            result.add(
                w.report
                    .lock()
                    .map_err(|_| "worker report poisoned")?
                    .clone(),
            );
        }
        Ok(result)
    }
    pub fn shutdown(&mut self) -> Result<Summary, &'static str> {
        self.stop.store(true, Ordering::Relaxed);
        for worker in &mut self.workers {
            worker.sender.take();
        }
        let mut result = Summary {
            counters: self.rejected.clone(),
            queue_drops: self.input_drops,
            ..Summary::default()
        };
        let mut failed = false;
        for worker in &mut self.workers {
            if let Some(join) = worker.join.take() {
                match join.join() {
                    Ok(report) => result.add(report),
                    Err(_) => failed = true,
                }
            }
        }
        while self.outputs.try_recv().is_ok() {
            result.queue_drops = result.queue_drops.saturating_add(1);
        }
        if failed {
            Err("worker panicked; all workers joined")
        } else {
            Ok(result)
        }
    }
}
impl Drop for Pool {
    fn drop(&mut self) {
        let _ = self.shutdown();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{checksum, udp_checksum, DropReason, Route};
    use std::net::Ipv4Addr;
    use std::sync::{atomic::AtomicUsize, Barrier};
    fn ip(s: &str) -> Ipv4Addr {
        s.parse().unwrap()
    }
    fn config() -> Config {
        Config {
            external: ip("198.51.100.1"),
            ports: (40000, 40015),
            max_flows: 16,
            idle_seconds: 10,
            mtu: 1500,
            routes: vec![
                Route::new(ip("0.0.0.0"), 0, Side::Outside).unwrap(),
                Route::new(ip("10.0.0.0"), 24, Side::Inside).unwrap(),
            ],
        }
    }
    fn packet(source: &str, sport: u16, dest: &str, dport: u16) -> Vec<u8> {
        let mut b = vec![0; 64];
        b[0] = 0x45;
        b[2..4].copy_from_slice(&64u16.to_be_bytes());
        b[8] = 64;
        b[9] = 17;
        let src = ip(source);
        let dst = ip(dest);
        b[12..16].copy_from_slice(&src.octets());
        b[16..20].copy_from_slice(&dst.octets());
        b[20..22].copy_from_slice(&sport.to_be_bytes());
        b[22..24].copy_from_slice(&dport.to_be_bytes());
        b[24..26].copy_from_slice(&44u16.to_be_bytes());
        let sum = checksum(&b[..20]);
        b[10..12].copy_from_slice(&sum.to_be_bytes());
        let sum = udp_checksum(src, dst, &b[20..]);
        b[26..28].copy_from_slice(&if sum == 0 { 65535 } else { sum }.to_be_bytes());
        b
    }
    fn outbound(port: u16) -> Vec<u8> {
        packet("10.0.0.2", port, "198.51.100.2", 9000)
    }
    fn wait_until(mut ready: impl FnMut() -> bool) {
        let deadline = Instant::now() + Duration::from_secs(2);
        while !ready() {
            assert!(Instant::now() < deadline, "bounded worker wait");
            thread::sleep(Duration::from_millis(1));
        }
    }
    fn receive(pool: &Pool) -> Forward {
        let mut result = None;
        wait_until(|| {
            result = pool.receive();
            result.is_some()
        });
        result.unwrap()
    }
    #[test]
    fn remainder_partitions_cover_ports_without_collision_and_socket_affinity_is_stable() {
        let mut c = config();
        c.ports = (65525, 65535);
        c.max_flows = 7;
        let shards = Shards::new(&c, 4).unwrap();
        assert_eq!(
            shards
                .configs
                .iter()
                .map(|c| c.max_flows)
                .collect::<Vec<_>>(),
            vec![2, 2, 2, 1]
        );
        let ports: Vec<_> = shards
            .configs
            .iter()
            .flat_map(|c| c.ports.0..=c.ports.1)
            .collect();
        assert_eq!(ports, (65525..=65535).collect::<Vec<_>>());
        for port in ports {
            let reply = Packet::parse(&packet("198.51.100.2", 9000, "198.51.100.1", port)).unwrap();
            let owner = shards.owner(Side::Outside, &reply);
            assert!(
                (shards.configs[owner].ports.0..=shards.configs[owner].ports.1).contains(&port)
            );
        }
        let first = Packet::parse(&outbound(1234)).unwrap();
        let other = Packet::parse(&packet("10.0.0.2", 1234, "198.51.100.3", 9001)).unwrap();
        assert_eq!(
            shards.owner(Side::Inside, &first),
            shards.owner(Side::Inside, &other)
        );
        assert!(Shards::new(&c, 8).is_err());
        assert!(Shards::new(&c, 0).is_err());
    }
    #[test]
    fn shard_core_wrong_remote_does_not_refresh_and_boundaries_remain_exact() {
        for c in Shards::new(&config(), 4).unwrap().configs {
            let mut r = Router::new(c).unwrap();
            let f = r.process(Side::Inside, &outbound(1234), 0).unwrap();
            let port = Packet::parse(&f.packet).unwrap().sport;
            assert_eq!(
                r.process(
                    Side::Outside,
                    &packet("198.51.100.3", 9000, "198.51.100.1", port),
                    9
                )
                .unwrap_err(),
                DropReason::Filter
            );
            assert_eq!(
                r.process(
                    Side::Outside,
                    &packet("198.51.100.2", 9001, "198.51.100.1", port),
                    9
                )
                .unwrap_err(),
                DropReason::Filter
            );
            r.expire(10).unwrap();
            assert_eq!(r.active_flows(), 0);
            assert_eq!(r.counters.expired, 1);
            assert_eq!(r.expire(9), Err(DropReason::Clock));
            r.process(Side::Inside, &outbound(1234), 10).unwrap();
            r.expire(10).unwrap();
            assert_eq!(r.active_flows(), 1);
        }
    }
    #[test]
    fn real_threads_preserve_both_directions_and_reject_truncated_packets() {
        let shards = Shards::new(&config(), 4).unwrap();
        let mut pool = Pool::new(config(), 4, 16, Instant::now(), Arc::new(|| {})).unwrap();
        let mut external = Vec::new();
        for owner in 0..4 {
            let port = (1..1000)
                .find(|p| {
                    shards.owner(Side::Inside, &Packet::parse(&outbound(*p)).unwrap()) == owner
                })
                .unwrap();
            pool.submit(Side::Inside, outbound(port)).unwrap();
            let f = receive(&pool);
            let translated = Packet::parse(&f.packet).unwrap().sport;
            assert!(!external.contains(&translated));
            external.push(translated);
            pool.submit(
                Side::Outside,
                packet("198.51.100.3", 9000, "198.51.100.1", translated),
            )
            .unwrap();
            pool.submit(
                Side::Outside,
                packet("198.51.100.2", 9000, "198.51.100.1", translated),
            )
            .unwrap();
            let f = receive(&pool);
            assert_eq!(f.side, Side::Inside);
            assert_eq!(Packet::parse(&f.packet).unwrap().dport, port);
        }
        pool.submit(Side::Inside, vec![0; 12]).unwrap();
        let final_state = pool.shutdown().unwrap();
        assert_eq!(final_state.counters.forwarded, 8);
        assert_eq!(final_state.counters.drops[DropReason::Filter as usize], 4);
        assert_eq!(
            final_state.counters.drops[DropReason::Malformed as usize],
            1
        );
        assert_eq!(final_state.active, 4);
    }
    #[test]
    fn saturated_queues_drop_and_shutdown_cannot_wait_for_space() {
        let barrier = Arc::new(Barrier::new(2));
        let entered = Arc::new(AtomicUsize::new(0));
        let block = barrier.clone();
        let count = entered.clone();
        let mut pool = Pool::new(
            config(),
            2,
            1,
            Instant::now(),
            Arc::new(move || {
                if count.fetch_add(1, Ordering::SeqCst) == 0 {
                    block.wait();
                }
            }),
        )
        .unwrap();
        pool.submit(Side::Inside, outbound(1)).unwrap();
        wait_until(|| entered.load(Ordering::SeqCst) > 0);
        pool.submit(Side::Inside, outbound(1)).unwrap();
        pool.submit(Side::Inside, outbound(1)).unwrap();
        assert_eq!(pool.input_drops, 1);
        barrier.wait();
        wait_until(|| entered.load(Ordering::SeqCst) >= 2);
        let (done, complete) = mpsc::channel();
        thread::spawn(move || {
            done.send(pool.shutdown()).unwrap();
        });
        let summary = complete
            .recv_timeout(Duration::from_secs(2))
            .expect("shutdown blocked")
            .unwrap();
        assert!(summary.queue_drops >= 3);
        assert_eq!(summary.counters.forwarded, 2);
    }
    #[test]
    fn panic_is_detected_and_all_workers_are_joined() {
        let mut pool = Pool::new(config(), 4, 1, Instant::now(), Arc::new(|| {})).unwrap();
        pool.workers[0]
            .sender
            .as_ref()
            .unwrap()
            .try_send(Task::Panic)
            .ok()
            .unwrap();
        wait_until(|| !pool.healthy());
        assert!(pool.submit(Side::Inside, outbound(1)).is_err());
        assert!(pool.shutdown().is_err());
        assert!(pool.workers.iter().all(|w| w.join.is_none()));
    }
}
