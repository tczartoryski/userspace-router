//! Bounded actual-state aggregates; no packet tuples or payload are serialized.
use crate::{parallel::WorkerReport, Config, Counters, Side};
use std::collections::VecDeque;
use std::fmt::Write;
#[derive(Clone, Debug, Default)]
pub struct QueueState {
    pub capacity: usize,
    pub channel_capacity: usize,
    pub admitted: u64,
    pub completed: u64,
    pub occupancy: u64,
    pub high_water: u64,
    pub dropped: u64,
    pub shutdown_drops: u64,
}
impl QueueState {
    pub fn new(channel: usize, processing: bool) -> Self {
        Self {
            capacity: channel + usize::from(processing),
            channel_capacity: channel,
            ..Self::default()
        }
    }
    pub fn admit(&mut self) {
        self.admitted = self.admitted.saturating_add(1);
        self.occupancy += 1;
        self.high_water = self.high_water.max(self.occupancy);
    }
    pub fn complete(&mut self) {
        self.completed = self.completed.saturating_add(1);
        self.occupancy -= 1;
    }
    pub fn discard(&mut self) {
        self.shutdown_drops = self.shutdown_drops.saturating_add(1);
        self.occupancy -= 1;
    }
    fn json(&self) -> String {
        format!("{{\"capacity\":{},\"channel_capacity\":{},\"admitted\":{},\"completed\":{},\"occupancy\":{},\"high_water\":{},\"dropped\":{},\"shutdown_drops\":{}}}",self.capacity,self.channel_capacity,self.admitted,self.completed,self.occupancy,self.high_water,self.dropped,self.shutdown_drops)
    }
}
#[derive(Clone, Debug)]
pub struct Decision {
    pub monotonic_ns: u64,
    pub side: Side,
    pub reason: String,
    pub bytes: usize,
}
pub fn sample(
    events: &mut VecDeque<Decision>,
    every: u64,
    ordinal: u64,
    event: impl FnOnce() -> Decision,
) {
    if every != 0 && ordinal.is_multiple_of(every) {
        if events.len() == 64 {
            events.pop_front();
        }
        events.push_back(event());
    }
}
#[derive(Clone, Debug)]
pub struct ObservedWorker {
    pub config: Config,
    pub report: WorkerReport,
    pub input: QueueState,
}
#[derive(Clone, Debug)]
pub struct Observed {
    pub workers: Vec<ObservedWorker>,
    pub output: QueueState,
    pub dispatcher: Counters,
    pub sample_every: u64,
}
fn core(c: &Counters, active: usize) -> String {
    let mut drops = String::new();
    for (i, reason) in crate::DROP_REASONS.iter().enumerate() {
        if i > 0 {
            drops.push(',');
        }
        write!(drops, "\"{reason:?}\":{}", c.drops[i]).unwrap();
    }
    format!(
        "{{\"received\":{},\"forwarded\":{},\"expired\":{},\"active\":{},\"drops\":{{{drops}}}}}",
        c.received, c.forwarded, c.expired, active
    )
}
#[derive(Default)]
pub struct Sampler {
    previous: Option<(u64, u64, u64, u64)>,
}
impl Sampler {
    #[allow(clippy::too_many_arguments)]
    pub fn json(
        &mut self,
        observed: &Observed,
        now: u64,
        unix: u64,
        running: bool,
        interfaces: &[String],
        tx: u64,
        bytes: u64,
        blocked: u64,
    ) -> String {
        let mut workers = String::new();
        let mut forwarded = 0u64;
        let mut drops = observed
            .output
            .dropped
            .saturating_add(observed.output.shutdown_drops)
            .saturating_add(blocked);
        for (id, w) in observed.workers.iter().enumerate() {
            if id > 0 {
                workers.push(',');
            }
            forwarded = forwarded.saturating_add(w.report.counters.forwarded);
            drops = drops
                .saturating_add(w.input.dropped)
                .saturating_add(w.input.shutdown_drops);
            let mut events = String::new();
            for (i, event) in w.report.events.iter().enumerate() {
                if i > 0 {
                    events.push(',');
                }
                write!(
                    events,
                    "{{\"monotonic_ns\":{},\"direction\":\"{:?}\",\"reason\":\"{}\",\"bytes\":{}}}",
                    event.monotonic_ns, event.side, event.reason, event.bytes
                )
                .unwrap();
            }
            write!(workers,"{{\"id\":{id},\"ports\":[{},{}],\"capacity\":{},\"observed_ns\":{},\"core\":{},\"input\":{},\"events\":[{events}]}}",w.config.ports.0,w.config.ports.1,w.config.max_flows,w.report.observed_ns,core(&w.report.counters,w.report.active),w.input.json()).unwrap();
        }
        let rates = if let Some((before, packets, old_bytes, old_forwarded)) =
            self.previous.filter(|p| now > p.0)
        {
            let span = now - before;
            let seconds = span as f64 / 1e9;
            format!("{{\"interval_ns\":{span},\"tx_pps\":{:.6},\"tx_ip_mbps\":{:.6},\"core_forwarded_pps\":{:.6}}}",tx.saturating_sub(packets) as f64/seconds,bytes.saturating_sub(old_bytes) as f64*8.0/seconds/1e6,forwarded.saturating_sub(old_forwarded) as f64/seconds)
        } else {
            "{\"interval_ns\":null,\"tx_pps\":null,\"tx_ip_mbps\":null,\"core_forwarded_pps\":null}"
                .into()
        };
        self.previous = Some((now, tx, bytes, forwarded));
        format!("{{\"schema\":2,\"unix_seconds\":{unix},\"uptime_seconds\":{},\"monotonic_ns\":{now},\"running\":{running},\"interfaces\":[\"{}\",\"{}\"],\"backend\":\"tun-poll\",\"mode\":\"workers\",\"monitoring\":true,\"event_sample_every\":{},\"io_drops\":{drops},\"tx\":{{\"packets\":{tx},\"ip_bytes\":{bytes},\"would_block\":{blocked}}},\"dispatcher\":{},\"output\":{},\"workers\":[{workers}],\"rates\":{rates}}}\n",now/1_000_000_000,interfaces[0],interfaces[1],observed.sample_every,core(&observed.dispatcher,0),observed.output.json())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ring_and_queue_state_are_bounded_and_rates_begin_unavailable() {
        let mut ring = VecDeque::new();
        for ordinal in 1..=1000 {
            sample(&mut ring, 2, ordinal, || Decision {
                monotonic_ns: ordinal,
                side: Side::Inside,
                reason: "Forward".into(),
                bytes: 64,
            });
        }
        assert_eq!(ring.len(), 64);
        assert_eq!(ring.back().unwrap().monotonic_ns, 1000);
        sample(&mut ring, 0, 1001, || panic!("disabled sampling evaluated"));
        assert_eq!(ring.len(), 64);
        let mut q = QueueState::new(1, true);
        q.admit();
        q.admit();
        q.complete();
        q.discard();
        assert_eq!(q.occupancy, 0);
        assert_eq!(q.high_water, 2);
        assert_eq!(q.admitted, q.completed + q.shutdown_drops);
    }
}
