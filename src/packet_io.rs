//! Owned, nonblocking packet backend contract. No device setup or network policy.
use crate::{Forward, Side};
use std::io;
pub const MAX_PACKET_BYTES: usize = 65535;
/// None means no packet ready; false means the entire output was dropped by
/// backpressure. A backend must reject truncated input and short packet writes.
pub trait PacketIo {
    fn receive(&mut self, side: Side) -> io::Result<Option<Vec<u8>>>;
    fn transmit(&mut self, packet: Forward) -> io::Result<bool>;
    fn shutdown(&mut self) -> io::Result<()> {
        Ok(())
    }
}

/// One write is one packet. Interrupted retries are bounded and cancellable;
/// WouldBlock drops this output and a short write is fatal, never write_all.
pub fn write_packet(
    writer: &mut impl io::Write,
    bytes: &[u8],
    running: impl Fn() -> bool,
) -> io::Result<bool> {
    if bytes.len() > MAX_PACKET_BYTES {
        return Err(io::Error::other("packet exceeds IPv4 bound"));
    }
    for _ in 0..16 {
        if !running() {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "packet I/O stopped",
            ));
        }
        match writer.write(bytes) {
            Ok(n) if n == bytes.len() => return Ok(true),
            Ok(_) => return Err(io::Error::other("short packet write")),
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(false),
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        }
    }
    Err(io::Error::new(
        io::ErrorKind::Interrupted,
        "packet write retry bound",
    ))
}
/// All cleanup results are evaluated before entry. Never publish a clean final
/// observation after dispatcher, worker-join or backend-shutdown failure.
pub fn finish_dispatch<T>(
    outcome: io::Result<()>,
    joined: io::Result<T>,
    backend: io::Result<()>,
    publish: impl FnOnce(&T) -> io::Result<()>,
) -> io::Result<()> {
    outcome?;
    let state = joined?;
    backend?;
    publish(&state)
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Writer {
        calls: usize,
        result: io::ErrorKind,
    }
    impl io::Write for Writer {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.calls += 1;
            match self.result {
                io::ErrorKind::Other => Ok(bytes.len()),
                io::ErrorKind::WriteZero => Ok(1),
                kind => Err(io::Error::from(kind)),
            }
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }
    #[test]
    fn backpressure_short_writes_interrupts_and_stop_are_bounded() {
        for (kind, expected, calls) in [
            (io::ErrorKind::Other, Some(true), 1),
            (io::ErrorKind::WouldBlock, Some(false), 1),
            (io::ErrorKind::WriteZero, None, 1),
            (io::ErrorKind::Interrupted, None, 16),
        ] {
            let mut writer = Writer {
                calls: 0,
                result: kind,
            };
            assert_eq!(
                write_packet(&mut writer, &[1, 2, 3], || true).ok(),
                expected
            );
            assert_eq!(writer.calls, calls);
        }
        let mut writer = Writer {
            calls: 0,
            result: io::ErrorKind::Other,
        };
        assert!(write_packet(&mut writer, &[1, 2], || false).is_err());
        assert_eq!(writer.calls, 0);
    }
    #[test]
    fn interchangeable_backend_moves_owned_packet_and_reports_backpressure() {
        struct Memory {
            input: Option<Vec<u8>>,
            output: Option<Vec<u8>>,
        }
        impl PacketIo for Memory {
            fn receive(&mut self, _: Side) -> io::Result<Option<Vec<u8>>> {
                Ok(self.input.take())
            }
            fn transmit(&mut self, packet: Forward) -> io::Result<bool> {
                if self.output.is_some() {
                    return Ok(false);
                }
                self.output = Some(packet.packet);
                Ok(true)
            }
        }
        let bytes = vec![0; 64];
        let address = bytes.as_ptr();
        let mut backend = Memory {
            input: Some(bytes),
            output: None,
        };
        let packet = backend.receive(Side::Inside).unwrap().unwrap();
        assert_eq!(packet.as_ptr(), address);
        assert!(backend.receive(Side::Inside).unwrap().is_none());
        assert!(backend
            .transmit(Forward {
                side: Side::Outside,
                packet
            })
            .unwrap());
        assert!(!backend
            .transmit(Forward {
                side: Side::Outside,
                packet: vec![0; 64]
            })
            .unwrap());
        backend.shutdown().unwrap();
    }
}
