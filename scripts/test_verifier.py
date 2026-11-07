#!/usr/bin/env python3
"""Deterministic synthetic verifier tests; no sockets, namespaces or live traffic."""
import json
from pathlib import Path
import tempfile
import unittest

from traffic import DROP_REASONS, final_counters, verify


def report(**changes):
    counters = dict(received=5, forwarded=2, active=1, expired=0, io_drops=0,
                    **{reason: 0 for reason in DROP_REASONS})
    counters.update(Protocol=2, Filter=1)
    counters.update(changes)
    return ' '.join(f'{key}={value}' for key, value in counters.items()) + '\n'


class VerifierTests(unittest.TestCase):
    def test_good_noisy_and_quiet(self):
        for noise in (0, 2, 17):
            with self.subTest(noise=noise):
                counters = final_counters('forwarding ready\n' + report(
                    received=3 + noise, Protocol=noise))
                self.assertEqual(counters['Protocol'], noise)

    def test_bad_counters_even_after_good_report(self):
        cases = [dict(forwarded=1), dict(forwarded=3), dict(Filter=0),
                 dict(Filter=2), dict(io_drops=1), dict(io_drops=10),
                 dict(active=0), dict(expired=1), dict(received=6)]
        cases += [{reason: 1, 'received': 6} for reason in DROP_REASONS
                  if reason not in ('Filter', 'Protocol')]
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(AssertionError):
                    final_counters(report() + report(**changes))

    def test_bad_schema(self):
        good = report().strip()
        cases = ['', good + ' Filter=1', good.replace('Filter=1', 'Filter=10'),
                 good.replace(' io_drops=0', ''), good + ' Unknown=0',
                 good.replace('Protocol=2', 'Protocol=-2'), good + '\nfatal error',
                 good.replace('forwarded=2', 'forwarded=2junk')]
        for log in cases:
            with self.subTest(log=log):
                with self.assertRaises(AssertionError):
                    final_counters(log)

    def test_verify_artifact_and_reject_without_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'server.jsonl').write_text(json.dumps(dict(
                peer=['198.51.100.1', 40000], ttl=63,
                payload='controlled-real-udp-positive')) + '\n')
            (root / 'client-positive.json').write_text(json.dumps(dict(ttl=63)))
            (root / 'client-negative.json').write_text(json.dumps(dict(timed_out=True)))
            (root / 'router.log').write_text('forwarding ready\n' + report())
            verify(root)
            passed = json.loads((root / 'PASS.json').read_text())
            self.assertEqual(passed['counters']['Protocol'], 2)
            (root / 'PASS.json').unlink()
            (root / 'router.log').write_text(report() + report(io_drops=1))
            with self.assertRaises(AssertionError):
                verify(root)
            self.assertFalse((root / 'PASS.json').exists())


if __name__ == '__main__':
    unittest.main()
