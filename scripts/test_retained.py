"""Deterministic retained-demo orchestration tests; no VM or live packets."""
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch

import extended
import traffic


class RetainedTests(unittest.TestCase):
    def test_startup_loss_retries_same_socket_and_tuple(self):
        sock = Mock()
        with patch('extended.time.monotonic', side_effect=[0, 0, .5]), patch(
                'extended.exchange', side_effect=[socket.timeout(), None]) as exchange:
            extended.pulse_exchange(sock)
        self.assertEqual(exchange.call_args_list, [unittest.mock.call(sock, b'live-demo')] * 2)
        self.assertEqual(sock.settimeout.call_count, 2)

    def test_lasting_loss_exhausts_deadline(self):
        sock = Mock()
        with patch('extended.time.monotonic', side_effect=[0, 0, .5, 1]), patch(
                'extended.exchange', side_effect=socket.timeout()) as exchange:
            with self.assertRaisesRegex(TimeoutError, 'deadline exceeded after 2 attempts'):
                extended.pulse_exchange(sock, budget=1)
        self.assertEqual(exchange.call_count, 2)
        self.assertEqual(sock.settimeout.call_args_list, [unittest.mock.call(.5)] * 2)

    def test_final_attempt_cannot_outlive_budget(self):
        sock = Mock()
        with patch('extended.time.monotonic', side_effect=[0, .9]), patch('extended.exchange'):
            extended.pulse_exchange(sock, budget=1)
        self.assertAlmostEqual(sock.settimeout.call_args.args[0], .1)

    def test_bad_reply_and_socket_errors_are_not_retried(self):
        for error in (AssertionError('wrong reply'), OSError('socket failed')):
            with patch('extended.exchange', side_effect=error) as exchange:
                with self.assertRaises(type(error)):
                    extended.pulse_exchange(Mock())
            exchange.assert_called_once()

    def test_restart_uses_fresh_log_before_pulse(self):
        harness = Path(__file__).with_name('linux-integration.sh').read_text()
        retained = harness.split('Retained demo: restart router;', 1)[1]
        self.assertIn('2>"$artifact/retained-router.log"', retained)
        self.assertLess(retained.index('traffic.py" ready'), retained.index('extended.py" pulse'))
        self.assertIn('"$artifact/retained-router.log" "$router_pid" "$server_pid"', retained)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'server.ready').touch()
            (root / 'router.log').write_text('userspace forwarding ready\n')
            fresh = root / 'retained-router.log'
            fresh.touch()
            with patch('traffic.os.kill'), patch('traffic.time.sleep'), patch(
                    'traffic.time.monotonic', side_effect=[0, 0, 5]):
                with self.assertRaisesRegex(AssertionError, 'startup deadline'):
                    traffic.ready(root / 'server.ready', fresh, 1, 2)


if __name__ == '__main__':
    unittest.main()
