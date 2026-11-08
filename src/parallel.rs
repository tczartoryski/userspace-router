//! Bounded dispatcher/worker ownership; each thread exclusively owns its Router.
use crate::observability::{Decision, Observed, ObservedWorker, QueueState};
use crate::{packet_io::MAX_PACKET_BYTES, Config, Counters, Forward, Packet, Router, Side};
use std::collections::VecDeque;
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
    pub observed_ns: u64,
    pub events: VecDeque<Decision>,
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
    monitor: Option<Monitor>,
}
struct Monitor {
    inputs: Vec<Arc<Mutex<QueueState>>>,
    output: Arc<Mutex<QueueState>>,
    every: u64,
}
struct WorkerContext {
    stop: Arc<AtomicBool>,
    epoch: Instant,
    report: Arc<Mutex<WorkerReport>>,
    wake: Arc<dyn Fn() + Send + Sync>,
    input_metric: Option<Arc<Mutex<QueueState>>>,
    output_metric: Option<Arc<Mutex<QueueState>>>,
    every: u64,
}
fn worker_loop(
    router: &mut Router,
    input: Receiver<Task>,
    output: SyncSender<Forward>,
    context: WorkerContext,
) -> WorkerReport {
    let WorkerContext {
        stop,
        epoch,
        report,
        wake,
        input_metric,
        output_metric,
        every,
    } = context;
    let mut result = WorkerReport::default();
    let mut published = Instant::now();
    while !stop.load(Ordering::Relaxed) {
        let _ = router.expire(epoch.elapsed().as_secs());
        match input.recv_timeout(Duration::from_millis(20)) {
            Ok(Task::Packet(side, bytes)) => {
                let length = bytes.len();
                let decision = router.process(side, &bytes, epoch.elapsed().as_secs());
                if every != 0 {
                    crate::observability::sample(
                        &mut result.events,
                        every,
                        router.counters.received,
                        || Decision {
                            monotonic_ns: epoch.elapsed().as_nanos() as u64,
                            side,
                            reason: match &decision {
                                Ok(_) => "Forward".into(),
                                Err(reason) => format!("{reason:?}"),
                            },
                            bytes: length,
                        },
                    );
                }
                if let Ok(packet) = decision {
                    let mut metric = output_metric
                        .as_ref()
                        .map(|m| m.lock().expect("output metric poisoned"));
                    if output.try_send(packet).is_err() {
                        result.output_drops = result.output_drops.saturating_add(1);
                        if let Some(m) = metric.as_mut() {
                            m.dropped = m.dropped.saturating_add(1);
                        }
                    } else if let Some(m) = metric.as_mut() {
                        m.admit();
                    }
                    drop(metric);
                    wake();
                }
                if let Some(m) = &input_metric {
                    m.lock().expect("input metric poisoned").complete();
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
            result.observed_ns = epoch.elapsed().as_nanos() as u64;
            *report.lock().expect("worker report poisoned") = result.clone();
            published = Instant::now();
        }
    }
    while input.try_recv().is_ok() {
        result.shutdown_drops = result.shutdown_drops.saturating_add(1);
        if let Some(m) = &input_metric {
            m.lock().expect("input metric poisoned").discard();
        }
    }
    result.counters = router.counters.clone();
    result.active = router.active_flows();
    result.observed_ns = epoch.elapsed().as_nanos() as u64;
    *report.lock().expect("worker report poisoned") = result.clone();
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
        Self::observed(config, workers, queue, epoch, wake, false, 0)
    }
    #[allow(clippy::too_many_arguments)]
    pub fn observed(
        config: Config,
        workers: usize,
        queue: usize,
        epoch: Instant,
        wake: Arc<dyn Fn() + Send + Sync>,
        monitoring: bool,
        every: u64,
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
            monitor: monitoring.then(|| Monitor {
                inputs: (0..workers)
                    .map(|_| Arc::new(Mutex::new(QueueState::new(queue, true))))
                    .collect(),
                output: Arc::new(Mutex::new(QueueState::new(queue, false))),
                every,
            }),
        };
        for (id, config) in pool.shards.configs.iter().enumerate() {
            let mut router = Router::new(config.clone())?;
            let (sender, input) = mpsc::sync_channel(queue);
            let flag = pool.stop.clone();
            let output = output.clone();
            let wake = wake.clone();
            let report = Arc::new(Mutex::new(WorkerReport {
                counters: router.counters.clone(),
                active: router.active_flows(),
                observed_ns: epoch.elapsed().as_nanos() as u64,
                ..WorkerReport::default()
            }));
            let shared = report.clone();
            let context = WorkerContext {
                stop: flag,
                epoch,
                report: shared,
                wake,
                input_metric: pool.monitor.as_ref().map(|m| m.inputs[id].clone()),
                output_metric: pool.monitor.as_ref().map(|m| m.output.clone()),
                every: if monitoring { every } else { 0 },
            };
            let join = thread::Builder::new()
                .name("router-worker".into())
                .spawn(move || worker_loop(&mut router, input, output, context))
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
        let mut metric = self
            .monitor
            .as_ref()
            .map(|m| m.inputs[owner].lock().expect("input metric poisoned"));
        match self.workers[owner]
            .sender
            .as_ref()
            .ok_or("pool stopped")?
            .try_send(Task::Packet(side, bytes))
        {
            Ok(()) => {
                if let Some(m) = metric.as_mut() {
                    m.admit();
                }
                Ok(())
            }
            Err(TrySendError::Full(_)) => {
                self.input_drops = self.input_drops.saturating_add(1);
                if let Some(m) = metric.as_mut() {
                    m.dropped = m.dropped.saturating_add(1);
                }
                Ok(())
            }
            Err(TrySendError::Disconnected(_)) => Err("worker disconnected"),
        }
    }
    pub fn receive(&self) -> Option<Forward> {
        let mut metric = self
            .monitor
            .as_ref()
            .map(|m| m.output.lock().expect("output metric poisoned"));
        let packet = self.outputs.try_recv().ok();
        if packet.is_some() {
            if let Some(m) = metric.as_mut() {
                m.complete();
            }
        }
        packet
    }
    pub fn observation(&self) -> Result<Option<Observed>, &'static str> {
        let Some(m) = &self.monitor else {
            return Ok(None);
        };
        let mut workers = Vec::new();
        for (id, w) in self.workers.iter().enumerate() {
            let report = w
                .report
                .lock()
                .map_err(|_| "worker report poisoned")?
                .clone();
            let input = m.inputs[id]
                .lock()
                .map_err(|_| "input metric poisoned")?
                .clone();
            workers.push(ObservedWorker {
                config: self.shards.configs[id].clone(),
                report,
                input,
            });
        }
        Ok(Some(Observed {
            workers,
            output: m
                .output
                .lock()
                .map_err(|_| "output metric poisoned")?
                .clone(),
            dispatcher: self.rejected.clone(),
            sample_every: m.every,
        }))
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
        // Cleanup must survive a poisoned observation mutex, including when
        // invoked by Drop during unwinding. Never publish recovered bad metrics.
        let mut metric = match self.monitor.as_ref().map(|m| m.output.lock()) {
            Some(Ok(guard)) => Some(guard),
            Some(Err(_)) => {
                failed = true;
                None
            }
            None => None,
        };
        while self.outputs.try_recv().is_ok() {
            result.queue_drops = result.queue_drops.saturating_add(1);
            if let Some(m) = metric.as_mut() {
                if m.occupancy > 0 {
                    m.discard();
                } else {
                    failed = true;
                }
            }
        }
        drop(metric);
        if failed {
            Err("worker failure or poisoned telemetry; all workers joined")
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

#[cfg(test)]
mod observation_tests {
    use super::*;
    use crate::{checksum, udp_checksum, Route};
    fn fixture() -> (Config, Vec<u8>) {
        let src = "10.0.0.2".parse::<std::net::Ipv4Addr>().unwrap();
        let dst = "198.51.100.2".parse::<std::net::Ipv4Addr>().unwrap();
        let config = Config {
            external: "198.51.100.1".parse().unwrap(),
            ports: (40000, 40015),
            max_flows: 16,
            idle_seconds: 10,
            mtu: 1500,
            routes: vec![
                Route::new("0.0.0.0".parse().unwrap(), 0, Side::Outside).unwrap(),
                Route::new("10.0.0.0".parse().unwrap(), 24, Side::Inside).unwrap(),
            ],
        };
        let mut b = vec![0; 64];
        b[0] = 0x45;
        b[2..4].copy_from_slice(&64u16.to_be_bytes());
        b[8] = 64;
        b[9] = 17;
        b[12..16].copy_from_slice(&src.octets());
        b[16..20].copy_from_slice(&dst.octets());
        b[20..22].copy_from_slice(&1234u16.to_be_bytes());
        b[22..24].copy_from_slice(&9000u16.to_be_bytes());
        b[24..26].copy_from_slice(&44u16.to_be_bytes());
        let sum = checksum(&b[..20]);
        b[10..12].copy_from_slice(&sum.to_be_bytes());
        let sum = udp_checksum(src, dst, &b[20..]);
        b[26..28].copy_from_slice(&sum.to_be_bytes());
        (config, b)
    }
    #[test]
    fn actual_worker_snapshot_conserves_ledgers_and_bounds_private_samples() {
        let (config, packet) = fixture();
        let epoch = Instant::now();
        let mut pool = Pool::observed(config, 4, 2, epoch, Arc::new(|| {}), true, 1).unwrap();
        for _ in 0..128 {
            pool.submit(Side::Inside, packet.clone()).unwrap();
            let end = Instant::now() + Duration::from_secs(2);
            while pool.receive().is_none() {
                assert!(Instant::now() < end);
                thread::yield_now();
            }
        }
        let final_state = pool.shutdown().unwrap();
        assert_eq!(final_state.counters.forwarded, 128);
        let observed = pool.observation().unwrap().unwrap();
        assert_eq!(observed.output.admitted, 128);
        assert_eq!(observed.output.completed, 128);
        assert_eq!(observed.output.occupancy, 0);
        for w in &observed.workers {
            assert_eq!(w.input.admitted, w.input.completed + w.input.shutdown_drops);
            assert_eq!(w.input.completed, w.report.counters.received);
            assert!(w.input.high_water <= w.input.capacity as u64);
            assert!(w.report.events.len() <= 64);
        }
        assert_eq!(
            observed
                .workers
                .iter()
                .map(|w| w.report.events.len())
                .sum::<usize>(),
            64
        );
        let mut sampler = crate::observability::Sampler::default();
        let now = epoch.elapsed().as_nanos() as u64;
        let json = sampler.json(
            &observed,
            now,
            100,
            false,
            &["tun-in".into(), "tun-out".into()],
            128,
            8192,
            0,
        );
        assert!(json.contains("\"schema\":2"));
        assert!(!json.contains("10.0.0.2"));
        assert!(!json.contains("payload"));
        assert!(json.len() < 1_048_576);
        if let Ok(path) = std::env::var("UDP_ROUTER_TEST_SNAPSHOT") {
            std::fs::write(path, &json).unwrap();
        }
        let next = sampler.json(
            &observed,
            now + 1_000_000_000,
            101,
            false,
            &["tun-in".into(), "tun-out".into()],
            128,
            8192,
            0,
        );
        assert!(next.contains("\"tx_pps\":0.000000"));
    }
    #[test]
    fn generated_affinity_and_malformed_ingress_remain_bounded() {
        let (config, packet) = fixture();
        let mut seed = 17u64;
        for count in [1, 2, 4, 16] {
            let shards = Shards::new(&config, count).unwrap();
            for _ in 0..4096 {
                seed ^= seed << 13;
                seed ^= seed >> 7;
                seed ^= seed << 17;
                let mut p = Packet::parse(&packet).unwrap();
                p.sport = (seed % 65535 + 1) as u16;
                let owner = shards.owner(Side::Inside, &p);
                p.dport = 123;
                p.dst = "198.51.100.3".parse().unwrap();
                assert_eq!(owner, shards.owner(Side::Inside, &p));
                assert!(owner < count);
                p.dport = shards.configs[owner].ports.1;
                assert_eq!(owner, shards.owner(Side::Outside, &p));
            }
        }
        let mut pool =
            Pool::observed(config, 4, 1, Instant::now(), Arc::new(|| {}), true, 0).unwrap();
        for len in 0..64 {
            pool.submit(Side::Inside, vec![0; len]).unwrap();
        }
        pool.shutdown().unwrap();
        let observed = pool.observation().unwrap().unwrap();
        assert_eq!(observed.dispatcher.received, 64);
        assert!(observed.workers.iter().all(|w| w.report.events.is_empty()));
    }
}

#[cfg(test)]
mod dispatcher_failure_tests {
    use super::*;
    #[test]
    fn backend_failure_joins_all_workers_without_clean_snapshot() {
        let config = Config {
            external: "198.51.100.1".parse().unwrap(),
            ports: (40000, 40007),
            max_flows: 4,
            idle_seconds: 2,
            mtu: 1500,
            routes: vec![crate::Route::new("0.0.0.0".parse().unwrap(), 0, Side::Outside).unwrap()],
        };
        let mut pool = Pool::new(config, 4, 1, Instant::now(), Arc::new(|| {})).unwrap();
        let joined = pool.shutdown().map_err(std::io::Error::other);
        assert!(pool.workers.iter().all(|w| w.join.is_none()));
        let mut published = false;
        let result = crate::packet_io::finish_dispatch(
            Err(std::io::Error::other("injected dispatcher backend failure")),
            joined,
            Ok(()),
            |_| {
                published = true;
                Ok(())
            },
        );
        assert!(result.is_err());
        assert!(!published);
        let mut normal = false;
        crate::packet_io::finish_dispatch(Ok(()), Ok(()), Ok(()), |_| {
            normal = true;
            Ok(())
        })
        .unwrap();
        assert!(normal);
    }
}

#[cfg(test)]
mod poison_review_tests {
    use super::*;
    #[test]
    fn poisoned_output_metrics_fail_closed_without_drop_double_panic() {
        let config = Config {
            external: "198.51.100.1".parse().unwrap(),
            ports: (40000, 40007),
            max_flows: 4,
            idle_seconds: 2,
            mtu: 1500,
            routes: vec![crate::Route::new("0.0.0.0".parse().unwrap(), 0, Side::Outside).unwrap()],
        };
        let mut pool =
            Pool::observed(config, 4, 1, Instant::now(), Arc::new(|| {}), true, 0).unwrap();
        let metric = pool.monitor.as_ref().unwrap().output.clone();
        assert!(thread::spawn(move || {
            let _guard = metric.lock().unwrap();
            panic!("injected metric poison");
        })
        .join()
        .is_err());
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| pool.shutdown()));
        assert!(result.unwrap().is_err());
        assert!(pool.workers.iter().all(|w| w.join.is_none()));
        assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| drop(pool))).is_ok());
    }
}
